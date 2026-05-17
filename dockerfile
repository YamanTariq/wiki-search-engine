# Start with the official Spark image.
FROM apache/spark:3.5.1

USER root

# Spark package jars are cached here by the launcher/Compose volume.
RUN mkdir -p /tmp/.ivy && chown -R spark:spark /tmp/.ivy

USER spark
