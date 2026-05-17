Write-Host "--- 🚀 Ensuring Distributed Cluster is Running ---" -ForegroundColor Green
# We removed the 'down' command. 'up -d' will just start it if it's off, or do nothing if it's already running.
docker compose up -d

Write-Host "--- ⏳ Waiting 30 seconds for connections... ---" -ForegroundColor Cyan
Start-Sleep -Seconds 30 

Write-Host "--- 🧹 Wiping ONLY the old Wikipedia Index data ---" -ForegroundColor Yellow
# This API call deletes the specific database table, NOT your Kibana settings.
try {
    Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index" -Method Delete -ErrorAction SilentlyContinue
    Write-Host "Old index deleted successfully." -ForegroundColor Green
} catch {
    Write-Host "No existing index found to delete (or Elasticsearch is still booting)." -ForegroundColor Gray
}

Write-Host "--- ⚙️ Optimizing Elasticsearch for Bulk Ingestion ---" -ForegroundColor Cyan
$es_settings = @{
    settings = @{
        "index.refresh_interval" = "-1"
        "index.number_of_replicas" = 0
    }
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index" -Method Put -Body $es_settings -ContentType "application/json" -ErrorAction SilentlyContinue

Write-Host "--- 🧠 Submitting PySpark Job to the Master Node ---" -ForegroundColor Green
docker exec -it spark-master /opt/spark/bin/spark-submit `
  --master spark://spark-master:7077 `
  --conf "spark.executor.memory=8g" `
  --conf "spark.jars.ivy=/tmp/.ivy" `
  --packages org.elasticsearch:elasticsearch-spark-30_2.12:8.12.0,com.databricks:spark-xml_2.12:0.17.0 `
  /opt/spark/work-dir/scripts/process_wiki.py

Write-Host "--- 🎉 Ingestion Complete! Check Kibana to verify. ---" -ForegroundColor Magenta