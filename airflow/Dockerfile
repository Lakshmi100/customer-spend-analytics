FROM apache/airflow:2.10.3-python3.11

# ─────────────────────────────────────────────────────────────────
# Install OpenJDK 17 for PySpark (needs a JVM to launch executors)
# Must be done as root; switch back to airflow user for pip install
# ─────────────────────────────────────────────────────────────────
USER root
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless procps && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set JAVA_HOME so PySpark can find the JVM
# (path is correct for Debian-based Airflow image on x86_64)
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PATH="${JAVA_HOME}/bin:${PATH}"

# ─────────────────────────────────────────────────────────────────
# Install Python dependencies as the airflow user
# ─────────────────────────────────────────────────────────────────
COPY --chown=airflow:0 requirements.txt /tmp/requirements.txt

USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements.txt