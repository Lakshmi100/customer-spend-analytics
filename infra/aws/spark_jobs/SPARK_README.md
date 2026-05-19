# Spark Jobs — EMR Serverless

This directory contains PySpark jobs designed to run on **AWS EMR Serverless**.

## Architecture

```
Local development             AWS production
──────────────────             ─────────────────
spark-submit job.py            EMR Serverless
   │                              │
   ▼                              ▼
Local Spark                    Auto-scaled Spark workers
   │                              │
   ▼                              ▼
local files / S3               s3://...processed/
```

The same script works in both environments — Spark abstracts the
parallelism. At 1.6M rows, it spins up 1-2 workers. At 100M rows, it
auto-scales to 50+ workers.

## Files

- **`tokenize_and_partition.py`** — Reads raw incoming data, applies PII
  tokenization + k-anonymity, writes partitioned parquet
- **`upload_to_s3.sh`** — Helper to push the job script to S3 for EMR
  Serverless to pick up

## Job: tokenize_and_partition

### What it does

1. Reads PII salt from AWS Secrets Manager
2. Reads raw customers + transactions from S3
3. Hashes customer IDs with salted SHA-256 (16-char tokens)
4. Buckets exact age/income/ZIP into k-anonymous bands
5. Drops all PII fields (name, email, phone, DOB, address)
6. Writes tokenized parquet partitioned by year_month/day

### Inputs

```
s3://<raw-bucket>/customers/ingest_date=YYYY-MM-DD/*.parquet
s3://<raw-bucket>/transactions/ingest_date=YYYY-MM-DD/*.parquet
```

### Outputs

```
s3://<processed-bucket>/customers/ingest_date=YYYY-MM-DD/*.parquet
s3://<processed-bucket>/transactions/year_month=YYYY-MM/day=YYYY-MM-DD/*.parquet
```

### Local testing

You can run this against your S3 buckets from your laptop before
deploying to EMR Serverless. This is the recommended way to iterate.

**Prerequisites:**
- PySpark installed locally (`pip install pyspark`)
- Java 11 or 17 (PySpark requirement)
- AWS credentials configured (`aws sts get-caller-identity` must work)
- Raw data already uploaded to s3://csa-dev-raw-XXX/ for a given date

**Run:**
```bash
spark-submit \
    --packages org.apache.hadoop:hadoop-aws:3.3.4 \
    tokenize_and_partition.py \
    --raw-bucket csa-dev-raw-039323921608 \
    --processed-bucket csa-dev-processed-039323921608 \
    --pii-salt-secret-arn arn:aws:secretsmanager:us-east-1:039323921608:secret:csa-dev-pii-salt-XXXXXX \
    --ingest-date 2026-05-12 \
    --region us-east-1
```

The `--packages org.apache.hadoop:hadoop-aws:3.3.4` is critical — it
downloads the S3A connector that lets local Spark read/write `s3a://`
paths.

### EMR Serverless deployment

1. Upload the job to S3:
   ```bash
   ./upload_to_s3.sh
   ```

2. EMR Serverless module (Chunk B2 — coming soon) will reference:
   ```
   s3://csa-dev-artifacts-039323921608/spark_jobs/tokenize_and_partition.py
   ```

## Architectural notes

### Why we partition by year_month/day

Snowflake's COPY INTO with partition filters becomes O(today's data) instead
of O(all data). At 100M rows/day across years, this is the difference
between a daily load taking 30 seconds vs 30 minutes.

### Why we use append, not overwrite, for transactions

Multiple ingest_date partitions can map to the same year_month. Using
`mode("append")` lets us add day=2026-05-12 without disturbing day=2026-05-11
in the same year_month folder. Snowflake's COPY INTO is idempotent — it
won't double-load files it's seen before (with default behavior).

### Why we fetch the salt before creating the UDF

The salt is captured by closure into the UDF. PySpark pickles UDFs and
ships them to workers — so the salt travels with the code. This means
workers don't need IAM permission to read the salt themselves; only
the driver does. Smaller attack surface.
