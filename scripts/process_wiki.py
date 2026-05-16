from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_replace, lower

# 1. Initialize the Spark Session
# This tells Spark how to connect to our Elasticsearch container
spark = SparkSession.builder \
    .appName("Wikipedia Distributed Indexer") \
    .config("spark.es.nodes", "elasticsearch") \
    .config("spark.es.port", "9200") \
    .config("spark.es.nodes.wan.only", "true") \
    .config("spark.es.index.auto.create", "true") \
    .getOrCreate()

# Suppress overly chatty logs
spark.sparkContext.setLogLevel("WARN")

print("--- Starting Distributed Wikipedia Processing ---")

# 2. Read the Compressed XML File
# Spark automatically decompresses the .bz2 file in parallel across workers!
# We use the databricks-xml library to easily parse the XML 'page' tags.
df = spark.read \
    .format("xml") \
    .option("rowTag", "page") \
    .load("/opt/spark/work-dir/data/simplewiki_small.bz2")

print("Raw data loaded. Cleaning and transforming...")

# 3. Clean and Transform the Data
# The Wiki XML has a nested structure. We extract the Title and the Text Body.
clean_df = df.select(
    col("title").alias("article_title"),
    col("revision.text._VALUE").alias("article_text")
)

# Filter out empty articles or redirect pages
clean_df = clean_df.filter(col("article_text").isNotNull())
clean_df = clean_df.filter(~col("article_text").startswith("#REDIRECT"))

# Basic Text Cleaning: Remove basic wiki markup like [[ ]] and HTML tags
# (For your final project, you can make this regex much more advanced!)
clean_df = clean_df.withColumn("article_text", regexp_replace("article_text", r"\[\[|\]\]|<[^>]*>", ""))

print("Data cleaned. Blasting data to Elasticsearch...")

# 4. Write to Elasticsearch in Parallel
# Spark will open multiple network connections and push chunks of data simultaneously.
clean_df.write \
    .format("org.elasticsearch.spark.sql") \
    .mode("overwrite") \
    .save("wikipedia_index")

print("--- SUCCESS! Data is now in Elasticsearch ---")

spark.stop()