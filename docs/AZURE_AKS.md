# Azure AKS Deployment Guide

This branch is for the cloud/distributed demo. Keep the local Docker Compose workflow on the local branch, and use this branch when you want AKS to show multiple nodes/pods.

## What You Will Deploy

- AKS cluster with 3 Linux nodes.
- Azure Container Registry image for this project.
- Azure Files share mounted at `/data` for `simplewiki_meh.bz2`.
- Elasticsearch with a persistent Azure managed disk.
- Kibana connected to Elasticsearch.
- Spark master and 3 Spark workers.
- Optional Streamlit search UI.

Kibana dashboards persist because Kibana saves objects into Elasticsearch's `.kibana` index. Therefore, preserving Elasticsearch storage preserves dashboards. Still export Kibana saved objects after creating them as a backup.

References:

- AKS Azure Files persistent volumes: https://learn.microsoft.com/azure/aks/azure-files-dynamic-pv
- AKS and Azure Container Registry integration: https://learn.microsoft.com/azure/aks/cluster-container-registry-integration
- AKS stop/start cluster: https://learn.microsoft.com/azure/aks/start-stop-cluster
- Kibana saved objects: https://www.elastic.co/guide/en/kibana/current/saved-objects-service.html

## 1. Create Azure Resources

Use Azure Cloud Shell or your local terminal with Azure CLI installed.

```bash
az login
az account set --subscription "<your-subscription-id>"

az group create \
  --name wiki-search-rg \
  --location eastus
```

Create Azure Container Registry:

```bash
az acr create \
  --resource-group wiki-search-rg \
  --name <unique-acr-name> \
  --sku Basic
```

Create AKS:

```bash
az aks create \
  --resource-group wiki-search-rg \
  --name wiki-search-aks \
  --node-count 3 \
  --node-vm-size Standard_D4s_v5 \
  --attach-acr <unique-acr-name> \
  --generate-ssh-keys
```

Get cluster credentials:

```bash
az aks get-credentials \
  --resource-group wiki-search-rg \
  --name wiki-search-aks
```

Verify distributed nodes:

```bash
kubectl get nodes -o wide
```

## 2. Build And Push The Docker Image

From the repo root:

```bash
az acr login --name <unique-acr-name>

docker build -t <unique-acr-name>.azurecr.io/wiki-search-engine:latest .
docker push <unique-acr-name>.azurecr.io/wiki-search-engine:latest
```

Replace the placeholder image in Kubernetes YAML:

```bash
grep -R "REPLACE_WITH_ACR" -n k8s
```

Change:

```text
REPLACE_WITH_ACR.azurecr.io/wiki-search-engine:latest
```

to:

```text
<unique-acr-name>.azurecr.io/wiki-search-engine:latest
```

## 3. Create Azure Files Share For The Wikipedia Dump

Create storage account:

```bash
az storage account create \
  --resource-group wiki-search-rg \
  --name <unique-storage-account-name> \
  --location eastus \
  --sku Standard_LRS
```

Get the storage key:

```bash
STORAGE_KEY=$(az storage account keys list \
  --resource-group wiki-search-rg \
  --account-name <unique-storage-account-name> \
  --query "[0].value" \
  --output tsv)
```

Create the Azure Files share:

```bash
az storage share-rm create \
  --resource-group wiki-search-rg \
  --storage-account <unique-storage-account-name> \
  --name wikidata \
  --quota 100
```

Upload the dataset:

```bash
az storage file upload \
  --account-name <unique-storage-account-name> \
  --account-key "$STORAGE_KEY" \
  --share-name wikidata \
  --source ./data/simplewiki_meh.bz2 \
  --path simplewiki_meh.bz2
```

Create the Kubernetes secret used by `k8s/01-azure-files-pv-pvc.yaml`:

```bash
kubectl apply -f k8s/00-namespace.yaml

kubectl -n wiki-search create secret generic azure-files-secret \
  --from-literal=azurestorageaccountname=<unique-storage-account-name> \
  --from-literal=azurestorageaccountkey="$STORAGE_KEY"
```

## 4. Deploy The Cluster Services

Run:

```bash
chmod +x run_pipeline_aks.sh
./run_pipeline_aks.sh --demo-refresh
```

What this does:

- Applies the Kubernetes manifests except the Spark submit job.
- Waits for Elasticsearch.
- Port-forwards Elasticsearch locally.
- Creates the `wikipedia_index` mapping.
- Starts the Spark ingestion Job.
- Prints document counts while ingestion is running.
- Re-enables normal refresh at the end.

For fastest non-demo ingestion:

```bash
./run_pipeline_aks.sh
```

## 5. Watch The Distributed Demo

Show nodes:

```bash
kubectl get nodes -o wide
```

Show pods spread across nodes:

```bash
kubectl -n wiki-search get pods -o wide
```

Open Spark UI:

```bash
kubectl -n wiki-search port-forward svc/spark-master 8080:8080
```

Then open:

```text
http://localhost:8080
```

Open Kibana:

```bash
kubectl -n wiki-search port-forward svc/kibana 5601:5601
```

Then open:

```text
http://localhost:5601
```

Open Streamlit:

```bash
kubectl -n wiki-search port-forward svc/streamlit 8501:8501
```

Then open:

```text
http://localhost:8501
```

Show live Elasticsearch document count:

```bash
kubectl -n wiki-search port-forward svc/elasticsearch 9200:9200
```

In another terminal:

```bash
watch -n 5 'curl -s http://localhost:9200/wikipedia_index/_count'
```

Good demo searches:

- `machine learning`
- `Einsten`
- `quantam physics`

Explain ranking:

- Exact title boost.
- Phrase boost.
- BM25 text ranking.
- Fuzzy fallback for typos.

## 6. Create Kibana Visualizations

In Kibana:

1. Open Stack Management.
2. Create a data view:
   - Name: `Wikipedia Articles`
   - Index pattern: `wikipedia_index`
3. Use Discover to inspect indexed documents.
4. Create visualizations such as:
   - total documents
   - top article titles by text length
   - namespace count
   - search/query screenshots
5. Create a dashboard.
6. Export saved objects:
   - Stack Management
   - Saved Objects
   - Export

Keep the exported `.ndjson` file outside the cluster as backup.

## 7. Persistence Rules

Safe:

```bash
kubectl -n wiki-search scale deployment spark-worker --replicas=0
az aks stop --resource-group wiki-search-rg --name wiki-search-aks
az aks start --resource-group wiki-search-rg --name wiki-search-aks
```

Dangerous:

```bash
kubectl -n wiki-search delete pvc elasticsearch-data-elasticsearch-0
az group delete --name wiki-search-rg
```

Deleting the Elasticsearch PVC can delete the index and Kibana dashboards.

## 8. Cost Controls

- Use 3 nodes normally.
- Scale workers/nodes up only for the final demo if needed.
- Stop AKS when not using it:

```bash
az aks stop --resource-group wiki-search-rg --name wiki-search-aks
```

- Set an Azure budget alert around $70-$80.
- Delete the resource group only after the final presentation:

```bash
az group delete --name wiki-search-rg
```

## 9. Troubleshooting

Pods pending:

```bash
kubectl -n wiki-search describe pod <pod-name>
```

Most likely causes:

- ACR image placeholder was not replaced.
- Azure Files secret missing or wrong.
- Nodes are too small for requested CPU/RAM.

Spark job logs:

```bash
kubectl -n wiki-search logs job/spark-submit-wiki-ingestion -f
```

Elasticsearch logs:

```bash
kubectl -n wiki-search logs statefulset/elasticsearch -f
```

Scale Spark workers:

```bash
kubectl -n wiki-search scale deployment spark-worker --replicas=4
```

Scale AKS nodes:

```bash
az aks scale \
  --resource-group wiki-search-rg \
  --name wiki-search-aks \
  --node-count 5
```
