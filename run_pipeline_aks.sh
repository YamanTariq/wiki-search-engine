#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-wiki-search}"
INDEX_NAME="${ES_INDEX:-wikipedia_index}"
DEMO_REFRESH="${DEMO_REFRESH:-false}"
ES_LOCAL_PORT="${ES_LOCAL_PORT:-9200}"
ES_SERVICE_PORT="${ES_SERVICE_PORT:-9200}"

if [[ "${1:-}" == "--demo-refresh" ]]; then
  DEMO_REFRESH="true"
fi

if [[ "${DEMO_REFRESH}" == "true" ]]; then
  REFRESH_INTERVAL="5s"
else
  REFRESH_INTERVAL="-1"
fi

cleanup() {
  if [[ -n "${PORT_FORWARD_PID:-}" ]]; then
    kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "--- Applying Kubernetes manifests ---"
kubectl apply -f k8s/00-namespace.yaml

if ! kubectl -n "${NAMESPACE}" get secret azure-files-secret >/dev/null 2>&1; then
  echo "Missing Azure Files secret: azure-files-secret"
  echo "Create it first with:"
  echo "kubectl -n ${NAMESPACE} create secret generic azure-files-secret \\"
  echo "  --from-literal=azurestorageaccountname=<storage-account-name> \\"
  echo "  --from-literal=azurestorageaccountkey=<storage-account-key>"
  exit 1
fi

kubectl apply -f k8s/01-azure-files-pv-pvc.yaml
kubectl apply -f k8s/02-elasticsearch.yaml
kubectl apply -f k8s/03-kibana.yaml
kubectl apply -f k8s/04-spark-master.yaml
kubectl apply -f k8s/05-spark-workers.yaml
kubectl apply -f k8s/06-streamlit.yaml

echo "--- Waiting for Elasticsearch ---"
kubectl -n "${NAMESPACE}" rollout status statefulset/elasticsearch --timeout=10m

echo "--- Opening local port-forward to Elasticsearch ---"
kubectl -n "${NAMESPACE}" port-forward svc/elasticsearch "${ES_LOCAL_PORT}:${ES_SERVICE_PORT}" >/tmp/wiki-es-port-forward.log 2>&1 &
PORT_FORWARD_PID="$!"
sleep 5

ES_URL="http://127.0.0.1:${ES_LOCAL_PORT}"

echo "--- Recreating Elasticsearch index: ${INDEX_NAME} ---"
curl -fsS -X DELETE "${ES_URL}/${INDEX_NAME}" >/dev/null || true

curl -fsS -X PUT "${ES_URL}/${INDEX_NAME}" \
  -H "Content-Type: application/json" \
  --data-binary @- <<JSON
{
  "settings": {
    "index": {
      "refresh_interval": "${REFRESH_INTERVAL}",
      "number_of_replicas": 0,
      "number_of_shards": 3,
      "query": {
        "default_field": ["article_title^3", "article_text"]
      }
    },
    "analysis": {
      "normalizer": {
        "lowercase_normalizer": {
          "type": "custom",
          "filter": ["lowercase"]
        }
      },
      "analyzer": {
        "wiki_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": ["lowercase", "english_stop", "english_stemmer"]
        }
      },
      "filter": {
        "english_stop": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "english_stemmer": {
          "type": "stemmer",
          "language": "english"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "article_id": { "type": "keyword" },
      "article_title": {
        "type": "text",
        "analyzer": "wiki_analyzer",
        "fields": {
          "keyword": {
            "type": "keyword",
            "normalizer": "lowercase_normalizer",
            "ignore_above": 256
          }
        }
      },
      "article_text": {
        "type": "text",
        "analyzer": "wiki_analyzer"
      },
      "namespace": { "type": "integer" },
      "text_length": { "type": "integer" }
    }
  }
}
JSON

echo "--- Starting Spark ingestion job ---"
kubectl -n "${NAMESPACE}" delete job spark-submit-wiki-ingestion --ignore-not-found=true
kubectl apply -f k8s/07-spark-submit-job.yaml

echo "--- Watching ingestion. Open another terminal for Spark UI port-forward if needed. ---"
while true; do
  STATUS="$(kubectl -n "${NAMESPACE}" get job spark-submit-wiki-ingestion -o jsonpath='{.status.conditions[0].type}' 2>/dev/null || true)"
  COUNT="$(curl -fsS "${ES_URL}/${INDEX_NAME}/_count" 2>/dev/null | sed -E 's/.*"count":([0-9]+).*/\1/' || echo 0)"
  echo "Indexed documents so far: ${COUNT}"

  if [[ "${STATUS}" == "Complete" ]]; then
    break
  fi

  if [[ "${STATUS}" == "Failed" ]]; then
    kubectl -n "${NAMESPACE}" logs job/spark-submit-wiki-ingestion --tail=200
    echo "Spark ingestion failed."
    exit 1
  fi

  sleep 10
done

echo "--- Spark job completed. Re-enabling normal refresh and refreshing index ---"
curl -fsS -X PUT "${ES_URL}/${INDEX_NAME}/_settings" \
  -H "Content-Type: application/json" \
  --data-binary '{"index":{"refresh_interval":"1s"}}' >/dev/null
curl -fsS -X POST "${ES_URL}/${INDEX_NAME}/_refresh" >/dev/null

FINAL_COUNT="$(curl -fsS "${ES_URL}/${INDEX_NAME}/_count" | sed -E 's/.*"count":([0-9]+).*/\1/')"
echo "Final indexed documents: ${FINAL_COUNT}"
echo "Done."
