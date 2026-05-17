from pyspark.sql import SparkSession
from pyspark.sql.functions import col, regexp_replace
from pyspark.sql.types import StructType, StructField, StringType, LongType
from functools import reduce
import re

# NEW: Explicit schema to prevent memory blowouts during XML parsing
wiki_schema = StructType([
    StructField("title", StringType(), True),
    StructField("id", LongType(), True),         # Added the critical ID field
    StructField("ns", LongType(), True),
    StructField("revision", StructType([
        StructField("text", StructType([
            StructField("_VALUE", StringType(), True)
        ]), True)
    ]), True)
])

# ============================================================================
# HIGH-SPEED NATIVE SPARK SQL REGEX (Optimized for JVM Performance)
# ============================================================================
# We use the '|' (OR) operator to group multiple replacements into single passes,
# reducing the number of times Spark has to scan and allocate new memory for the string.

FAST_REGEX_RULES = [
    # PASS 1: Nuke massive blocks (Citations, HTML comments, Bare URLs, Files, Categories)
    # Replaced (?s) with [\s\S] for faster cross-line matching without flag overhead
    (r"|<ref[^>]*>[\s\S]*?</ref>|<ref[^>]*/>|\[\[(?:File|Image|Category):[^\]]*\]\]|\[http[^\]]+\]", ""),
    
    # PASS 2 & 3: Templates (Run twice to catch basic nesting without catastrophic backtracking)
    (r"\{\{[^{}]*\}\}", ""), 
    (r"\{\{[^{}]*\}\}", ""), 
    
    # PASS 4: Extract readable text from links
    (r"\[\[[^\]]*?\|([^\]]*?)\]\]", "$1"),  # [[Target|Text]] -> Text
    (r"\[\[([^\]|]*?)\]\]", "$1"),          # [[Target]] -> Target
    (r"\[http[^\s]+\s+([^\]]+)\]", "$1"),   # [http://site.com Text] -> Text
    
    # PASS 5: Global Formatting Sweep (HTML tags, bold/italic, headers, template parameters, pipes)
    (r"<[^>]+>|'{2,5}|={2,6}\s*|\s*={2,6}|\|\s*[a-zA-Z_][\w\s]*\s*=\s*|\|", ""),
    
    # PASS 6: Clean up the leftover whitespace
    (r"\n{3,}", "\n\n")
]

if __name__ == "__main__":
    # Initialize Spark with extended Network Timeouts to prevent Heartbeat crashes
    spark = SparkSession.builder \
        .appName("Wikipedia Indexer - Native JVM") \
        .config("spark.es.nodes", "elasticsearch") \
        .config("spark.es.port", "9200") \
        .config("spark.es.nodes.wan.only", "true") \
        .config("spark.es.index.auto.create", "true") \
        .config("spark.es.batch.write.refresh", "false") \
        .config("spark.es.batch.size.entries", "5000") \
        .config("spark.es.batch.size.bytes", "5mb") \
        .config("spark.network.timeout", "600s") \
        .config("spark.executor.heartbeatInterval", "60s") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    
    # 1. Load Data
    print("\n[1/4] Loading and filtering Wikipedia XML...")
    df = spark.read.format("xml") \
        .option("rowTag", "page") \
        .schema(wiki_schema) \
        .load("/opt/spark/work-dir/data/simplewiki_small.bz2") # Make sure the filename is correct

    # 2. Filter BEFORE repartitioning
    df = df.select(
        col("id").alias("article_id"),
        col("title").alias("article_title"), 
        col("revision.text._VALUE").alias("article_text"), 
        col("ns").alias("namespace")
    )
    df = df.filter(col("article_text").isNotNull())
    df = df.filter(~col("article_text").startswith("#REDIRECT"))
    df = df.filter(col("namespace") == 0)
    
    # 3. Shuffle clean data
    clean_df = df.repartition(24)
    
    # 4. Apply Native Regex Chain (Extremely fast, compiles into one SQL step)
    print("\n[2/4] Applying JVM-Native Regex cleaning...")
    
    # This dynamically chains the regexp_replace functions together without leaving the JVM
    cleaned_column = reduce(
        lambda column, rule: regexp_replace(column, rule[0], rule[1]),
        FAST_REGEX_RULES,
        col("article_text")
    )
    
    clean_df = clean_df.withColumn("article_text", cleaned_column)
    clean_df = clean_df.filter(col("article_text") != "")
    
    # 5. Index
    print("\n[3/4] Indexing to Elasticsearch...")
    clean_df.write.format("org.elasticsearch.spark.sql").option("es.mapping_id", "artice_id").mode("overwrite").save("wikipedia_index")
    
    print("\n[4/4] SUCCESS!")
    spark.stop()