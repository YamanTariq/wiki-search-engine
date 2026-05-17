# Start with the official Spark image
FROM apache/spark:3.5.1

# Switch to the root user so we have permission to install packages
USER root

# Install the required Python libraries for Pandas UDFs
RUN pip install --no-cache-dir pandas pyarrow

# Switch back to the default spark user for security
USER spark