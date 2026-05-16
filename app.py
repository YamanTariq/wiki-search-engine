import streamlit as st
from elasticsearch import Elasticsearch

# Connect to your local Docker Elasticsearch
es = Elasticsearch("http://localhost:9200")

st.title("🔍 Distributed Wikipedia Search")
st.markdown("Powered by Apache Spark & Elasticsearch")

# The Search Bar
query = st.text_input("Enter search term (e.g., Quantum Physics, Einstein):")

if query:
    # 1. Define the Elasticsearch Query
    search_query = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["article_title^2", "article_text"] # Title matches count double!
            }
        },
        # Tell ES to return a highlighted snippet of where the word was found
        "highlight": {
            "fields": {"article_text": {}},
            "pre_tags": ["**"], # Markdown for bold
            "post_tags": ["**"]
        },
        "size": 10 # Only fetch top 10 to keep it fast
    }

    # 2. Execute Search
    response = es.search(index="wikipedia_index", body=search_query)

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
        score = hit["_score"] # This is the BM25 Ranking Score
        
        # Get the highlighted snippet, or fallback to the first 300 characters
        if "highlight" in hit and "article_text" in hit["highlight"]:
            snippet = hit["highlight"]["article_text"][0] + "..."
        else:
            snippet = hit["_source"].get("article_text", "")[:300] + "..."

        # Clean up some of the ugly Wikitext just for display purposes
        clean_snippet = snippet.replace("{{", "").replace("}}", "")

        # Render to UI
        st.subheader(f"📄 {title}")
        st.caption(f"**Relevance Score:** {score} (BM25 Algorithm)")
        st.write(clean_snippet)
        st.markdown("---")