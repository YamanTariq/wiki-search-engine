import os
from functools import reduce

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, length, regexp_replace, trim
from pyspark.sql.types import LongType, StringType, StructField, StructType


DUMP_PATH = os.getenv("WIKI_DUMP_PATH", "/opt/spark/work-dir/data/simplewiki_small.bz2")
INDEX_NAME = os.getenv("ES_INDEX", "wikipedia_index")
PARTITIONS = int(os.getenv("WIKI_PARTITIONS", "24"))
ES_NODES = os.getenv("ES_NODES", "elasticsearch")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_WAN_ONLY = os.getenv("ES_WAN_ONLY", "true")

WIKI_SCHEMA = StructType(
    [
        StructField("title", StringType(), True),
        StructField("id", LongType(), True),
        StructField("ns", LongType(), True),
        StructField(
            "revision",
            StructType(
                [
                    StructField(
                        "text",
                        StructType([StructField("_VALUE", StringType(), True)]),
                        True,
                    )
                ]
            ),
            True,
        ),
    ]
)

# These replacements run inside Spark/JVM, not as slow Python UDFs.
CLEANING_RULES = [
    (
        r"<!--[\s\S]*?-->|"
        r"<ref[^>]*>[\s\S]*?</ref>|<ref[^>]*/>|"
        r"<math[^>]*>[\s\S]*?</math>|"
        r"<code[^>]*>[\s\S]*?</code>|"
        r"<syntaxhighlight[^>]*>[\s\S]*?</syntaxhighlight>|"
        r"<gallery[^>]*>[\s\S]*?</gallery>|"
        r"<nowiki[^>]*>[\s\S]*?</nowiki>|"
        r"<timeline[^>]*>[\s\S]*?</timeline>|"
        r"\{\|[\s\S]*?\|\}",
        "",
    ),
    (r"\{\{[^{}]*\}\}", ""),
    (r"\{\{[^{}]*\}\}", ""),
    (r"\{\{[^{}]*\}\}", ""),
    (r"\{\{[\s\S]*?\}\}", ""),
    (r"(?i)\[\[(?:File|Image|Category):[^\]]*\]\]", ""),
    (r"\[\[[a-z]{2,3}:[^\]]*\]\]", ""),
    (r"\[\[[^\]]*?\|([^\]]*?)\]\]", "$1"),
    (r"\[\[([^\]|]*?)\]\]", "$1"),
    (r"\[https?://[^\s\]]+\s+([^\]]+)\]", "$1"),
    (r"\[https?://[^\]]+\]", ""),
    (r"https?://[^\s]+", ""),
    (r"__[A-Z]+__", ""),
    (r"'{2,5}", ""),
    (r"={2,6}\s*([^=]+?)\s*={2,6}", "$1"),
    (r"<[^>]+>", ""),
    (r"\|\s*[a-zA-Z_][\w\s]*\s*=\s*", ""),
    (r"\|", " "),
    (r"(?m)^[\*#:;]+\s*", ""),
    (r"(?i)ISBN\s*[0-9\-]+", ""),
    (r"(?i)ISSN\s*[0-9\-]+", ""),
    (r"[\[\]\{\}]", ""),
    (r"[ \t]{2,}", " "),
    (r"\n{3,}", "\n\n"),
]


def clean_text(column):
    return trim(
        reduce(
            lambda current, rule: regexp_replace(current, rule[0], rule[1]),
            CLEANING_RULES,
            column,
        )
    )


spark = (
    SparkSession.builder.appName("Wikipedia Indexer")
    .config("spark.es.nodes", ES_NODES)
    .config("spark.es.port", ES_PORT)
    .config("spark.es.nodes.wan.only", ES_WAN_ONLY)
    .config("spark.es.index.auto.create", "false")
    .config("spark.es.batch.write.refresh", "false")
    .config("spark.es.batch.size.entries", "5000")
    .config("spark.es.batch.size.bytes", "5mb")
    .config("spark.sql.shuffle.partitions", str(PARTITIONS))
    .config("spark.network.timeout", "600s")
    .config("spark.executor.heartbeatInterval", "60s")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

print("=" * 70)
print("Wikipedia -> Elasticsearch")
print("=" * 70)
print(f"Dataset: {DUMP_PATH}")
print(f"Index: {INDEX_NAME}")
print(f"Elasticsearch: {ES_NODES}:{ES_PORT}")
print(f"Partitions: {PARTITIONS}")

print("\n[1/3] Reading XML and filtering real articles...")
df = (
    spark.read.format("xml")
    .option("rowTag", "page")
    .schema(WIKI_SCHEMA)
    .load(DUMP_PATH)
    .select(
        col("id").cast(StringType()).alias("article_id"),
        col("title").alias("article_title"),
        col("revision.text._VALUE").alias("article_text"),
        col("ns").cast("int").alias("namespace"),
    )
)

df = df.filter(col("article_id").isNotNull())
df = df.filter(col("article_text").isNotNull())
df = df.filter(col("namespace") == 0)
df = df.filter(~col("article_text").rlike(r"(?i)^#redirect"))

print("\n[2/3] Cleaning wiki markup...")
clean_df = (
    df.repartition(PARTITIONS)
    .withColumn("article_text", clean_text(col("article_text")))
    .withColumn("article_text", trim(col("article_text")))
    .filter(length(col("article_text")) >= 20)
    .withColumn("text_length", length(col("article_text")))
)

print("\n[3/3] Writing to Elasticsearch...")
(
    clean_df.write.format("org.elasticsearch.spark.sql")
    .option("es.mapping.id", "article_id")
    .mode("append")
    .save(INDEX_NAME)
)

spark.stop()
print("\nDone.")
