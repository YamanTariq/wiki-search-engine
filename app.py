import streamlit as st
from elasticsearch import Elasticsearch
import os

# Connect to your local Docker Elasticsearch
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
INDEX_NAME = os.getenv("ES_INDEX", "wikipedia_index")
es = Elasticsearch(ES_URL)


def build_search_query(user_query):
    query_text = user_query.strip()
    normalized_query = query_text.lower()

    should_queries = [
        {
            "term": {
                "article_title.keyword": {
                    "value": normalized_query,
                    "boost": 20
                }
            }
        },
        {
            "match_phrase": {
                "article_title": {
                    "query": query_text,
                    "boost": 10
                }
            }
        },
        {
            "match_phrase": {
                "article_text": {
                    "query": query_text,
                    "boost": 3
                }
            }
        },
        {
            "multi_match": {
                "query": query_text,
                "fields": ["article_title^5", "article_text"],
                "type": "best_fields",
                "operator": "and",
                "boost": 2
            }
        }
    ]

    # Fuzzy matching catches typos like "Einsten" -> "Einstein".
    # It is weighted lower so exact/phrase/BM25 matches still rank first.
    if len(query_text) >= 4:
        should_queries.append(
            {
                "multi_match": {
                    "query": query_text,
                    "fields": ["article_title^3", "article_text^0.2"],
                    "fuzziness": "AUTO",
                    "prefix_length": 2,
                    "max_expansions": 20,
                    "boost": 0.8
                }
            }
        )

    return {
        "_source": ["article_id", "article_title", "text_length"],
        "query": {
            "bool": {
                "should": should_queries,
                "minimum_should_match": 1
            }
        },
        "highlight": {
            "fields": {
                "article_title": {
                    "number_of_fragments": 0
                },
                "article_text": {
                    "fragment_size": 220,
                    "number_of_fragments": 1
                }
            },
            "pre_tags": ["**"],
            "post_tags": ["**"]
        },
        "size": 10
    }

st.title("🔍 Distributed Wikipedia Search")
st.markdown("Powered by Apache Spark & Elasticsearch")

# The Search Bar
query = st.text_input("Enter search term (e.g., Quantum Physics, Einstein):")

if query:
    # 1. Define the Elasticsearch Query
    search_query = build_search_query(query)

    # 2. Execute Search
    response = es.search(index=INDEX_NAME, body=search_query)

    # 3. Extract Metrics
    took_ms = response["took"]  # How fast the cluster executed the search
    total_hits = response["hits"]["total"]["value"] # Total matching documents
    results = response["hits"]["hits"]

    # 4. Display the Performance Metrics
    st.success(f"⚡ **Speed:** Searched 434,237 documents in **{took_ms} milliseconds**")
    st.info(f"🎯 **Total Matches:** {total_hits} articles found")
    st.divider()

    # 5. Render the Articles
    for hit in results:
        # Extract the fields
        title = hit["_source"].get("article_title", "Unknown Title")
        article_id = hit["_source"].get("article_id", "Unknown ID")
        score = hit["_score"] # This is the BM25 Ranking Score
        
        # Get the highlighted snippet.
        if "highlight" in hit and "article_text" in hit["highlight"]:
            snippet = hit["highlight"]["article_text"][0] + "..."
        elif "highlight" in hit and "article_title" in hit["highlight"]:
            snippet = hit["highlight"]["article_title"][0]
        else:
            snippet = "No snippet available."

        # Clean up some of the ugly Wikitext just for display purposes
        clean_snippet = snippet.replace("{{", "").replace("}}", "")

        # Render to UI
        st.subheader(f"📄 {title}")
        st.caption(f"**Article ID:** {article_id} | **Relevance Score:** {score} (BM25 + boosts + fuzzy fallback)")
        st.write(clean_snippet)
        st.markdown("---")
