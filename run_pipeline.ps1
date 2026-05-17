param(
    [string]$DumpFile = "simplewiki_small.bz2",
    [string]$IndexName = "wikipedia_index",
    [int]$Partitions = 24,
    [string]$ExecutorMemory = "4g"
)

$ErrorActionPreference = "Stop"

$EsUrl = "http://localhost:9200"
$dataPath = Join-Path $PSScriptRoot "data\$DumpFile"
if (-not (Test-Path -LiteralPath $dataPath)) {
    throw "Dataset not found: $dataPath"
}

Write-Host "--- Starting Elasticsearch, Kibana, and Spark ---" -ForegroundColor Green
docker compose up -d --build

Write-Host "--- Waiting for Elasticsearch ---" -ForegroundColor Cyan
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "$EsUrl/_cluster/health" -ErrorAction Stop
        if ($health.status -eq "green" -or $health.status -eq "yellow") {
            $ready = $true
            Write-Host "Elasticsearch is ready: $($health.status)" -ForegroundColor Green
            break
        }
    } catch {
        Start-Sleep -Seconds 5
    }
}

if (-not $ready) {
    throw "Elasticsearch did not become ready. Check: docker logs elasticsearch"
}

Write-Host "--- Creating Elasticsearch index ---" -ForegroundColor Cyan
try {
    Invoke-RestMethod -Uri "$EsUrl/$IndexName" -Method Delete -ErrorAction Stop | Out-Null
    Write-Host "Deleted old index." -ForegroundColor Yellow
} catch {
    Write-Host "No old index found." -ForegroundColor Gray
}

$indexConfig = @'
{
  "settings": {
    "index": {
      "refresh_interval": "-1",
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
      "article_id": {
        "type": "keyword"
      },
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
      "namespace": {
        "type": "integer"
      },
      "text_length": {
        "type": "integer"
      }
    }
  }
}
'@

Invoke-RestMethod `
    -Uri "$EsUrl/$IndexName" `
    -Method Put `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($indexConfig)) `
    -ContentType "application/json; charset=utf-8" | Out-Null

Write-Host "--- Running Spark ingestion ---" -ForegroundColor Green
$containerDumpPath = "/opt/spark/work-dir/data/$DumpFile"
docker exec -i `
    --env "WIKI_DUMP_PATH=$containerDumpPath" `
    --env "ES_INDEX=$IndexName" `
    --env "WIKI_PARTITIONS=$Partitions" `
    spark-master `
    /opt/spark/bin/spark-submit `
    --master spark://spark-master:7077 `
    --conf "spark.executor.memory=$ExecutorMemory" `
    --conf "spark.executor.cores=4" `
    --conf "spark.jars.ivy=/tmp/.ivy" `
    --packages org.elasticsearch:elasticsearch-spark-30_2.12:8.19.0,com.databricks:spark-xml_2.12:0.17.0 `
    /opt/spark/work-dir/scripts/process_wiki.py

if ($LASTEXITCODE -ne 0) {
    throw "Spark job failed."
}

Write-Host "--- Enabling search and counting indexed articles ---" -ForegroundColor Cyan
Invoke-RestMethod -Uri "$EsUrl/$IndexName/_settings" -Method Put -Body '{"index":{"refresh_interval":"1s"}}' -ContentType "application/json" | Out-Null
Invoke-RestMethod -Uri "$EsUrl/$IndexName/_refresh" -Method Post | Out-Null
$count = Invoke-RestMethod -Uri "$EsUrl/$IndexName/_count"

Write-Host "Indexed articles: $($count.count)" -ForegroundColor Green
Write-Host "Done. Spark UI: http://localhost:8080  Kibana: http://localhost:5601" -ForegroundColor Magenta
