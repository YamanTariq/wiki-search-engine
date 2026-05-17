from pyspark.sql import SparkSession
from pyspark.sql.functions import col, pandas_udf
from pyspark.sql.types import StringType
import pandas as pd
import re

# ============================================================================
# PRODUCTION-GRADE WIKIPEDIA CLEANING PATTERNS
# ============================================================================
CLEANING_PATTERNS = [
    (re.compile(r"", re.DOTALL), ""),  
    (re.compile(r"<ref[^>]*>.*?</ref>", re.DOTALL), ""),  
    (re.compile(r"<ref[^>]*/>"), ""),  
    (re.compile(r"<math[^>]*>.*?</math>", re.DOTALL), ""),  
    (re.compile(r"<code[^>]*>.*?</code>", re.DOTALL), ""),  
    (re.compile(r"<syntaxhighlight[^>]*>.*?</syntaxhighlight>", re.DOTALL), ""),
    (re.compile(r"<gallery[^>]*>.*?</gallery>", re.DOTALL), ""),  
    (re.compile(r"<nowiki[^>]*>.*?</nowiki>", re.DOTALL), ""),  
    (re.compile(r"<timeline[^>]*>.*?</timeline>", re.DOTALL), ""),  
    (re.compile(r"\{\|.*?\|\}", re.DOTALL), ""),  
    (re.compile(r"\[\[Category:.*?\]\]", re.IGNORECASE), ""),  
    (re.compile(r"\[\[(?:File|Image):.*?\]\]", re.DOTALL | re.IGNORECASE), ""),  
    (re.compile(r"\[\[[a-z]{2,3}:.*?\]\]"), ""),  
    (re.compile(r"\[\[[^\]]*?\|([^\]]*?)\]\]"), r"\1"),  
    (re.compile(r"\[\[([^\]|]*?)\]\]"), r"\1"),  
    (re.compile(r"\[https?://[^\s\]]+\s+([^\]]+)\]"), r"\1"),  
    (re.compile(r"\[https?://[^\]]+\]"), ""),  
    (re.compile(r"https?://[^\s]+"), ""),  
    (re.compile(r"__[A-Z]+__"), ""),  
    (re.compile(r"'{2,5}"), ""),  
    (re.compile(r"={2,6}\s*(.*?)\s*={2,6}"), r"\1"),  
    (re.compile(r"<[^>]+>"), ""),  
    (re.compile(r"\|\s*[a-zA-Z_][\w\s]*\s*=\s*"), ""),  
    (re.compile(r"\|"), ""),  
    (re.compile(r"^[\*#:;]+\s*", re.MULTILINE), ""),  
    (re.compile(r"ISBN\s*[0-9\-]+", re.IGNORECASE), ""),  
    (re.compile(r"ISSN\s*[0-9\-]+", re.IGNORECASE), ""),  
    (re.compile(r"\n{3,}"), "\n\n"),  
    (re.compile(r" {2,}"), " "),  
    (re.compile(r"^\s+|\s+$", re.MULTILINE), ""),  
    (re.compile(r"[\[\]\{\}]"), ""),  
]

# ============================================================================
# PANDAS UDF: Vectorized Cleaning with Robust Patterns
# ============================================================================
@pandas_udf(StringType())
def clean_wikipedia_text(texts: pd.Series) -> pd.Series:
    cleaned = texts.fillna("")
    
    max_iterations = 10
    iteration = 0
    
    # FIX 1: The loop now immediately breaks if no more '{{' templates exist
    while iteration < max_iterations and cleaned.str.contains(r"\{\{", regex=True).any():
        cleaned = cleaned.str.replace(r"\{\{[^{}]*\}\}", "", regex=True)
        iteration += 1
    
    cleaned = cleaned.str.replace(r"\{\{.*?\}\}", "", regex=True)
    
    for pattern, replacement in CLEANING_PATTERNS:
        cleaned = cleaned.str.replace(pattern, replacement, regex=True)
        
    cleaned = cleaned.str.strip()
    return cleaned.where(cleaned.str.len() > 10, None)

# ============================================================================
# MAIN PIPELINE
# ============================================================================
if __name__ == "__main__":
    
    spark = SparkSession.builder \
        .appName("Wikipedia Indexer - Production") \
        .config("spark.es.nodes", "elasticsearch") \
        .config("spark.es.port", "9200") \
        .config("spark.es.nodes.wan.only", "true") \
        .config("spark.es.index.auto.create", "true") \
        .config("spark.es.batch.size.entries", "5000") \
        .config("spark.es.batch.size.bytes", "5mb") \
        .config("spark.es.net.http.auth.user", "") \
        .config("spark.es.batch.write.refresh", "false") \
        .getOrCreate()
    
    spark.sparkContext.setLogLevel("WARN")
    
    print("=" * 70)
    print("Wikipedia → Elasticsearch Pipeline (Production)")
    print("=" * 70)
    
    print("\n[1/4] Loading Wikipedia XML dump...")
    df = spark.read \
        .format("xml") \
        .option("rowTag", "page") \
        .load("/opt/spark/work-dir/data/simplewiki_small.bz2")
    
    # FIX 3: Filter out garbage BEFORE pushing data across the network
    print("\n[2/4] Dropping non-articles and repartitioning...")
    df = df.select(
        col("title").alias("article_title"),
        col("revision.text._VALUE").alias("article_text"),
        col("ns").alias("namespace")
    )
    
    df = df.filter(col("article_text").isNotNull())
    df = df.filter(~col("article_text").startswith("#REDIRECT"))
    df = df.filter(col("namespace") == 0)
    
    # Now shuffle the pure data across the workers
    clean_df = df.repartition(24)
    
    print("\n[3/4] Applying production-grade text cleaning (Vectorized)...")
    clean_df = clean_df.withColumn(
        "article_text",
        clean_wikipedia_text(col("article_text"))
    )
    
    clean_df = clean_df.filter(col("article_text").isNotNull())
    
    # FIX 2: All .count() commands removed. Data streams directly to ES.
    print("\n[4/4] Indexing directly to Elasticsearch...")
    clean_df.write \
        .format("org.elasticsearch.spark.sql") \
        .mode("overwrite") \
        .save("wikipedia_index")
    
    spark.stop()
    
    print("\n" + "=" * 70)
    print("SUCCESS! Pipeline execution complete.")
    print("=" * 70)