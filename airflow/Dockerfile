FROM apache/airflow:2.10.3-python3.11

# Install our project's Python dependencies
# We use the Airflow base image and layer our deps on top.
# COPY requirements.txt /tmp/requirements.txt
# Copy requirements with airflow user ownership so the next pip install
# can read the file. Without --chown=airflow, /tmp/requirements.txt is
# owned by root and the airflow user gets Permission denied on read.
COPY --chown=airflow:0 requirements.txt /tmp/requirements.txt

# Switch to airflow user for pip install (best practice)
USER airflow
RUN pip install --no-cache-dir -r /tmp/requirements.txt
