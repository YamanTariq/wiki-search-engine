Write-Host "--- 🛑 Tearing down old cluster ---" -ForegroundColor Yellow
docker compose down -v

Write-Host "--- 🚀 Spinning up Distributed Cluster (1 Master, 3 Workers, ES, Kibana) ---" -ForegroundColor Green
docker compose up -d

Write-Host "--- ⏳ Waiting 30 seconds for Elasticsearch and Spark to fully boot... ---" -ForegroundColor Cyan
Start-Sleep -Seconds 30

Write-Host "--- 🧹 Wiping old Elasticsearch Index ---" -ForegroundColor Yellow
try {
    Invoke-RestMethod -Uri "http://localhost:9200/wikipedia_index" -Method Delete -ErrorAction SilentlyContinue
} catch {

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
  --conf "spark.jars.ivy=/tmp/.ivy" `
  --packages org.elasticsearch:elasticsearch-spark-30_2.12:8.12.0,com.databricks:spark-xml_2.12:0.17.0 `
  /opt/spark/work-dir/scripts/process_wiki.py

Write-Host "--- 🎉 Pipeline Complete! Check http://localhost:8501 for your Streamlit UI ---" -ForegroundColor Magenta