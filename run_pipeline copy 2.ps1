Write-Host "--- 🚀 Ensuring Distributed Cluster is Running ---" -ForegroundColor Green
docker compose up -d

Write-Host "--- ⏳ Waiting for Elasticsearch to become healthy... ---" -ForegroundColor Cyan
$es_ready = $false
$max_retries = 20
$retry_count = 0

# SMART POLLING LOOP: Keeps checking until Elasticsearch says it is "green" or "yellow"
while (-not $es_ready -and $retry_count -lt $max_retries) {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:9200/_cluster/health" -ErrorAction Stop
        if ($response.status -eq "green" -or $response.status -eq "yellow") {
            $es_ready = $true
            Write-Host "✅ Elasticsearch is UP and ready!" -ForegroundColor Green
        } else {
            Write-Host "Elasticsearch is booting... (Status: $($response.status))" -ForegroundColor Yellow
            Start-Sleep -Seconds 5
        }
    } catch {
        Write-Host "Elasticsearch is not reachable yet. Retrying in 5 seconds..." -ForegroundColor Gray
        Start-Sleep -Seconds 5
    }
    $retry_count++
}

# If it fails 20 times, stop the script completely so it doesn't crash Spark
if (-not $es_ready) {
    Write-Host "❌ ERROR: Elasticsearch failed to start. Run 'docker logs elasticsearch' in your terminal to see why." -ForegroundColor Red
    exit
}

Write-Host "--- 🧹 Wiping ONLY the old Wikipedia Index data ---" -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index" -Method Delete -ErrorAction SilentlyContinue
    Write-Host "Old index deleted successfully." -ForegroundColor Green
} catch {
    Write-Host "No existing index found to delete." -ForegroundColor Gray
}

Write-Host "--- ⚙️ Creating Index with Custom Analyzers & Default Boosting ---" -ForegroundColor Cyan

# This combined payload optimizes performance, configures languages, and assigns default boosting
$index_config = @'
{
  "settings": {
    "index": {
      "refresh_interval": "-1",
      "number_of_replicas": 0,
      "number_of_shards": 3,
      "query": {
        "default_field": ["title^3", "text"]
      }
    },
    "analysis": {
      "analyzer": {
        "wiki_analyzer": {
          "type": "custom",
          "tokenizer": "standard",
          "filter": [
            "lowercase",
            "wiki_stop_filter",
            "wiki_stem_filter"
          ]
        }
      },
      "filter": {
        "wiki_stop_filter": {
          "type": "stop",
          "stopwords": "_english_"
        },
        "wiki_stem_filter": {
          "type": "stemmer",
          "language": "english"
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "article_id": {
        "type": "keyword"
      },
      "title": {
        "type": "text",
        "analyzer": "wiki_analyzer",
        "fields": {
          "keyword": {
            "type": "keyword",
            "ignore_above": 256
          }
        }
      },
      "text": {
        "type": "text",
        "analyzer": "wiki_analyzer"
      }
    }
  }
}
'@

# We force UTF8 string conversion to ensure Elasticsearch receives proper JSON characters over HTTP REST
Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index" -Method Put -Body ([System.Text.Encoding]::UTF8.GetBytes($index_config)) -ContentType "application/json; charset=utf-8" -ErrorAction Stop
Write-Host "✅ Index initialized with stemming, stop-words, and 3x Title boosting!" -ForegroundColor Green

Write-Host "--- 🧠 Submitting PySpark Job to the Master Node ---" -ForegroundColor Green
docker exec -it spark-master /opt/spark/bin/spark-submit `
  --master spark://spark-master:7077 `
  --conf "spark.executor.memory=8g" `
  --conf "spark.jars.ivy=/tmp/.ivy" `
  --packages org.elasticsearch:elasticsearch-spark-30_2.12:8.12.0,com.databricks:spark-xml_2.12:0.17.0 `
  /opt/spark/work-dir/scripts/process_wiki.py

Write-Host "--- 🔓 Re-enabling Elasticsearch Search Capabilities ---" -ForegroundColor Cyan
Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index/_settings" -Method Put -Body '{"index":{"refresh_interval":"1s"}}' -ContentType "application/json" -ErrorAction SilentlyContinue

Write-Host "--- 🎉 Ingestion Complete! Custom mapping is live and text is fully optimized for ranking. ---" -ForegroundColor Magenta