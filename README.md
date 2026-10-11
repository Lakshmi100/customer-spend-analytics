# Customer Spend Analytics → Digital Coupon Engine

> An end-to-end data engineering portfolio project simulating a bank-merchant
> partnership. Customer transaction data flows through PySpark for PII
> tokenization, lands in Snowflake, gets transformed by dbt into a
> customer 360 mart, and feeds a KMeans segmentation model + a coupon
> recommendation ranker — all orchestrated by Airflow running in Docker.

![Python](https://img.shields.io/badge/python-3.11-blue)
![Snowflake](https://img.shields.io/badge/snowflake-cloud_DW-29B5E8)
![dbt](https://img.shields.io/badge/dbt-1.11-FF694B)
![Airflow](https://img.shields.io/badge/airflow-2.10-017CEE)
![Docker](https://img.shields.io/badge/docker-compose-2496ED)
![AWS](https://img.shields.io/badge/AWS-Lambda%20%2B%20EMR%20%2B%20Step%20Functions-FF9900)
![Terraform](https://img.shields.io/badge/terraform-1.14-844FBA)
![License](https://img.shields.io/badge/license-MIT-green)


---

## TL;DR

Acme Bank shares anonymized customer transaction data with an analytics
platform. The platform builds spend profiles, segments customer behavior,
predicts category preferences, and returns personalized digital coupons
back to the bank — all without ever touching PII. Customers redeem coupons
through their banking app.

This repo contains the entire pipeline: synthetic data generation,
ingestion with PII tokenization, dbt transformations, ML segmentation,
a recommender API, a demo dashboard, and Airflow orchestration.

**Phase 2** extends the same pipeline to AWS as a serverless, Terraform-managed,
daily-scheduled production architecture: AWS Lambda for delta generation and
Snowflake loading, EMR Serverless for PySpark tokenization, Step Functions for
orchestration, EventBridge for daily cron scheduling. Service authentication
uses RSA key-pair (no passwords). Total monthly AWS spend: ~$12, with nightly
compute teardown via Smart Mode.

---

## Architecture

For a comprehensive walkthrough of the system design — including trust
boundary details, the AWS Step Functions state machine, cross-cutting
concerns, and the architectural decisions journal — see
**[ARCHITECTURE.md](./ARCHITECTURE.md)**.

## Demo

| | |
|---|---|
| 🎟 **Coupon recommender** | Streamlit dashboard at `localhost:8501` |
| 🔌 **REST API** | FastAPI + Swagger at `localhost:8000/docs` |
| 🌬 **Airflow UI** | DAG orchestration at `localhost:8080` |
| 📊 **dbt docs** | Lineage graph at `localhost:8080` (after `dbt docs serve`) |

Sample API call:
```bash
curl http://localhost:8000/coupons/c34b443cb92d6f10
```

Sample response:
```json
{
  "customer_persona": "Luxury Seeker Vanessa",
  "customer_cluster": 6,
  "recommendations": [
    {
      "merchant_name": "Tiffany & Co",
      "discount_display": "$150 off",
      "score": 0.862,
      "reasoning": "VERY strong preference for luxury_goods (6.4x avg); transacted 3 days ago; cluster peers also prefer this"
    },
    ...
  ]
}
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  SYNTHETIC DATA LAYER                                               │
│  20 personas → 1,000 customers → 1.6M transactions over 24 months   │
│  (with realistic PII for tokenization demonstration)                │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  INGESTION (PySpark)                                                │
│  • PII tokenization (SHA-256 + salt)                                │
│  • K-anonymity (age bands, income bands, ZIP prefix)                │
│  • Schema validation, partitioning by year_month                    │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SNOWFLAKE (Storage + Compute)                                      │
│  • RAW.CUSTOMERS (1,000 rows, no PII — fully tokenized)             │
│  • RAW.TRANSACTIONS (1.6M rows, partitioned)                        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TRANSFORMATION (dbt — 8 models, 49 tests passing)                  │
│  • staging        → 2 views (universal cleanup)                     │
│  • intermediate   → 3 views (joins, RFM features, monthly aggs)     │
│  • marts          → 3 tables (customer_360, category_affinity,      │
│                     customer_spend_trends)                          │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ML LAYER                                                           │
│  • KMeans segmentation (k=8, recovered persona structure 95-100%)   │
│  • Coupon ranker (log-scaled affinity 50% + recency 30% + cluster   │
│    20%, with discount-value tiebreaker)                             │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SERVING                                                            │
│  • FastAPI service (Swagger UI auto-generated)                      │
│  • Streamlit dashboard (bank-side coupon view)                      │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATION (Airflow on Docker Compose)                          │
│  Daily DAG: generate → ingest → load → dbt → ml → recommend         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Tools |
|---|---|
| **Data generation** | Python, Faker |
| **Ingestion** | PySpark 3.5, parquet, snappy compression |
| **Storage** | Snowflake (RAW / STAGING / MARTS schemas) |
| **Transformation** | dbt-core 1.11, dbt-snowflake |
| **ML** | scikit-learn (KMeans, StandardScaler), pandas, numpy |
| **API** | FastAPI, Pydantic, uvicorn |
| **Dashboard** | Streamlit, requests |
| **Orchestration** | Apache Airflow 2.10 |
| **Containerization** | Docker, Docker Compose |
| **Visualization** | matplotlib, seaborn |

---

## Project Layout

```
customer-spend-analytics/
├── data_generation/           # Synthetic data scripts
│   ├── personas.py            # 20 customer archetypes
│   ├── generate_customers.py  # 1,000 customers with PII
│   └── generate_transactions.py  # 1.6M transactions (24 months)
│
├── ingestion/                 # PySpark + PII tokenization + Snowflake load
│   ├── pii_tokenizer.py
│   ├── spark_ingestion.py
│   ├── snowflake_setup.py
│   └── snowflake_loader.py
│
├── coupon_analytics/          # dbt project
│   ├── dbt_project.yml
│   ├── models/
│   │   ├── staging/           # 2 views
│   │   ├── intermediate/      # 3 views
│   │   └── marts/             # 3 tables
│   └── macros/
│
├── ml/                        # ML pipeline + recommender
│   ├── snowflake_io.py
│   ├── features.py            # Feature engineering for KMeans
│   ├── segmentation.py        # KMeans + cluster profiling
│   ├── visualize_segments.py  # Portfolio charts
│   ├── coupon_catalog.py      # 33 synthetic coupons
│   ├── coupon_ranker.py       # Composite scoring engine
│   ├── predict.py             # Inference API
│   └── artifacts/             # Trained models + parquet outputs
│
├── api/                       # FastAPI service
│   └── main.py
│
├── dashboard/                 # Streamlit demo
│   └── app.py
│
├── airflow/                   # Docker Compose orchestration
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── requirements.txt
│   └── dags/
│       └── coupon_pipeline_dag.py
│
└── data/                      # Generated parquet (gitignored)
    ├── raw/
    └── processed/
```

---

## Layer-by-Layer Walkthrough

### 1. Synthetic Data: 20 personas, behaviorally distinct

Twenty customer archetypes spanning the full lifecycle and income range:
**Luxury Seeker Vanessa** ($290K, urban penthouse), **Soccer Mom Linda**
($95K, suburb, Costco regular), **College Student Sasha** ($18K, fast
food and rideshare), **Active Retiree Carol** ($58K + SS, pharmacy and
gardening), and 16 more.

Each persona has:
- Age range, income range, family situation
- Category-weighted spending mix (sums to 1.0)
- Online vs in-store split
- Transaction frequency profile

The generators produce **1,000 customers** (with real PII for tokenization
demonstration) and **1,614,567 transactions** over 24 months, with
seasonality and salary-cycle effects.

### 2. PII Tokenization & K-Anonymity

The `ingestion/pii_tokenizer.py` module enforces a **trust boundary**
between the bank's internal data and the analytics platform:

| Field | Treatment |
|---|---|
| `first_name`, `last_name`, `email`, `phone`, `street_address`, `date_of_birth` | **Dropped entirely** |
| `customer_id`, `account_number` | **Tokenized** with salted SHA-256 (deterministic, non-reversible) |
| `age` | **Bucketed** to bands (`18-24`, `25-34`, ...) |
| `annual_income` | **Bucketed** to bands (`under_40k`, `over_200k`, ...) |
| `zip_code` | **Truncated** to 3-digit prefix (`30309` → `303XX`) |

By the time data lands in Snowflake's `RAW` schema, there is no way to
identify an individual.

### 3. Snowflake Layout

```
ABC_BANK_ANALYTICS
├── RAW           # Tokenized landing zone (loaded by PySpark via COPY INTO)
│   ├── CUSTOMERS
│   └── TRANSACTIONS
├── STAGING       # dbt staging + intermediate models (views)
└── MARTS         # dbt marts (tables, materialized for ML query speed)
```

A dedicated `DBT_ROLE` has SELECT-only on RAW and full access on
STAGING/MARTS — least-privilege execution.

### 4. dbt Transformations (8 models, 49 tests)

```
RAW.CUSTOMERS, RAW.TRANSACTIONS
        │
        ▼
   stg_customers, stg_transactions    ← Staging (universal cleanup)
        │
        ▼
   int_customer_transactions           ← Intermediate (reusable joins)
        │
        ├──► int_monthly_spend_by_category
        ├──► int_rfm_features          ← Recency / Frequency / Monetary
        │
        ▼
   customer_360                        ← Mart (50+ ML features per customer)
   category_affinity                   ← Mart (powers the coupon ranker)
   customer_spend_trends               ← Mart (MoM patterns, seasonality)
```

**Build it:**
```bash
cd coupon_analytics
dbt build         # runs all 8 models AND all 49 tests in dependency order
dbt docs generate
dbt docs serve    # browse the lineage graph at localhost:8080
```

### 5. ML: Customer Segmentation

KMeans with k=8 (selected via silhouette analysis across k=2..12).
Trained on a curated subset of 24 numeric features from `customer_360`.

**Result: clusters recovered persona structure with 95-100% purity** for
18 of 20 personas, despite being a fully unsupervised model.

| Persona | Lands in cluster | % captured |
|---|---|---|
| Luxury Seeker Vanessa | 6 | 100% |
| College Student Sasha | 1 | 100% |
| Soccer Mom Linda | 4 | 97% |
| Tech Bro Tyler | 2 | 100% |
| Empty Nesters Bob & Susan | 0 | 98% |
| ... (full table in `ml/artifacts/`) | | |

### 6. Coupon Recommendation Engine

For each (customer, coupon), a composite score:

```
score = 0.50 × affinity_score      # log-scaled customer category affinity
      + 0.30 × recency_score       # exponential decay on days_since_last_txn
      + 0.20 × cluster_score       # cluster-level peer signal
```

Plus a discount-value tiebreaker for near-ties.

**Sample output for Luxury Seeker:**
- Tiffany & Co — `$150 off` (score 0.862)
- Louis Vuitton — `10% off` (score 0.862)
- Marriott Bonvoy — `$100 off` (score 0.509)

**Sample output for College Student:**
- Chipotle — `$5 off` (score 0.956)
- Starbucks — `20% off` (score 0.956)
- Lyft — `$5 off` (score 0.922)

Each recommendation comes with human-readable reasoning explaining which
signals drove it.

### 7. Serving: FastAPI + Streamlit

**FastAPI** exposes the recommender as a REST service with auto-generated
OpenAPI docs. Endpoints:
- `GET /health` — Snowflake connectivity check
- `GET /coupons/{customer_token}` — top N coupons with reasoning
- `GET /customers/{customer_token}/profile` — customer 360 view
- `GET /customers/random?persona=...` — random customer (for demo)
- `GET /stats/clusters` — cluster distribution summary

**Streamlit** provides a polished bank-side UI: pick a customer (by
persona or randomly), see their 360 profile, view recommended coupons
with score breakdowns and reasoning.

### 8. Airflow Orchestration

A single DAG (`coupon_pipeline`) orchestrates the full pipeline daily:

```
start → generate_data → spark_ingestion → snowflake_load → dbt_build
                                                                │
                                                                ▼
                                                          ml_features
                                                                │
                                                                ▼
                                                          ml_segmentation
                                                                │
                                                                ▼
                                                          ml_rank_coupons
                                                                │
                                                                ▼
                                                          publish_summary
                                                                │
                                                                ▼
                                                              end
```

Runs in a 4-container Docker Compose stack (Postgres + Airflow init +
webserver + scheduler).

---

## Setup & Reproduce

### Prerequisites

- Python 3.11+
- Java 11 or 17 (for PySpark)
- Docker Desktop (for Airflow)
- A Snowflake account (free trial works)

### 1. Clone and set up environment

```bash
git clone <your-repo-url> customer-spend-analytics
cd customer-spend-analytics

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Snowflake credentials

### 2. Configure Snowflake credentials (RSA key-pair auth)

The project uses RSA key-pair authentication against a Snowflake
`TYPE=SERVICE` user. Password auth won't work — Snowflake's Enterprise
tier enforces MFA on human users, and services can't complete MFA
prompts.

**Generate a key pair on your machine:**

```bash
mkdir -p ~/.snowflake-keys
cd ~/.snowflake-keys

# Generate 2048-bit RSA private key (no passphrase for local dev;
# production would encrypt with passphrase stored separately)
openssl genrsa -out csa_service_key.p8 2048

# Derive the matching public key
openssl rsa -in csa_service_key.p8 -pubout -out csa_service_key.pub

# Lock down permissions (Snowflake connector rejects world-readable keys)
chmod 600 csa_service_key.p8
```

**Register the public key on your Snowflake user.**
In a Snowflake worksheet, create the service user (one-time) and
attach the public key:

```sql
-- Create a service user (skip if you already have one)
CREATE USER IF NOT EXISTS CSA_SERVICE_USER
  TYPE = SERVICE
  DEFAULT_ROLE = ACCOUNTADMIN
  DEFAULT_WAREHOUSE = COMPUTE_WH
  DEFAULT_NAMESPACE = ABC_BANK_ANALYTICS.RAW;

-- Register the public key (paste the contents of csa_service_key.pub
-- between the header/footer BEGIN/END lines — one continuous string
-- with no line breaks)
ALTER USER CSA_SERVICE_USER
  SET RSA_PUBLIC_KEY = 'MIIBIj...paste_public_key_body...QIDAQAB';

-- Grant roles the service user needs
GRANT ROLE ACCOUNTADMIN TO USER CSA_SERVICE_USER;
GRANT ROLE DBT_ROLE TO USER CSA_SERVICE_USER;
```

**Configure `.env`** at the repo root:

```bash
cp .env.example .env
```

Edit `.env` to set:

```bash
SNOWFLAKE_ACCOUNT=<your-org-name>-<your-account>   # e.g., ABCDEF-123456
SNOWFLAKE_USER=CSA_SERVICE_USER
SNOWFLAKE_PRIVATE_KEY_PATH=/Users/<you>/.snowflake-keys/csa_service_key.p8
SNOWFLAKE_WAREHOUSE=COMPUTE_WH
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_DATABASE=ABC_BANK_ANALYTICS
SNOWFLAKE_SCHEMA=RAW

# Generate the PII tokenization salt (32 hex bytes)
python -c "import secrets; print(f'PII_SALT={secrets.token_hex(32)}')" >> .env
```

**Also configure `airflow/.env`** — the Docker Compose stack reads this
one separately. Same values, but the private key path is the *container*
path where we'll mount the key (not your Mac path):

```bash
cp airflow/.env.example airflow/.env
```

Edit `airflow/.env`:

```bash
SNOWFLAKE_PRIVATE_KEY_PATH=/opt/keys/csa_service_key.p8
```

The `.env` at the repo root is for standalone Python (running scripts
directly from your venv). The `airflow/.env` is for the containerized
Airflow stack.

**Update the dbt profile** at `~/.dbt/profiles.yml`:

```yaml
coupon_analytics:
  outputs:
    dev:
      type: snowflake
      account: <your-org-name>-<your-account>
      user: CSA_SERVICE_USER
      private_key_path: /opt/keys/csa_service_key.p8
      role: DBT_ROLE
      warehouse: DBT_WH
      database: ABC_BANK_ANALYTICS
      schema: MARTS
      threads: 4
      client_session_keep_alive: False
  target: dev
```

Also mirror this file to `coupon_analytics/profiles/profiles.yml`
because the Airflow DAG's `dbt build --profiles-dir` command points
there (add `coupon_analytics/profiles/` to `.gitignore` so it stays
out of the repo).

### 3. Set up Snowflake schema (one-time)

```bash
python ingestion/snowflake_setup.py
```

### 4. Run the pipeline

```bash
# Generate synthetic data
python data_generation/generate_customers.py
python data_generation/generate_transactions.py

# Ingest with PySpark + PII tokenization
python ingestion/spark_ingestion.py

# Load to Snowflake
python ingestion/snowflake_loader.py

# Run dbt transformations + tests
cd coupon_analytics
dbt build
cd ..

# ML: features → segmentation → ranker
python -m ml.features
python -m ml.segmentation
python -m ml.visualize_segments
python -m ml.coupon_ranker
```

### 5. Serve the recommender

In two separate terminals:
```bash
# Terminal 1: API
uvicorn api.main:app --reload --port 8000

# Terminal 2: Dashboard
streamlit run dashboard/app.py
```

Visit `http://localhost:8501` for the dashboard or
`http://localhost:8000/docs` for the API.

### 6. Run the daily pipeline via Airflow (optional)

### 6. Run the daily pipeline via Airflow

Prerequisites:
- `airflow/.env` configured (per Step 2)
- Private key at `~/.snowflake-keys/csa_service_key.p8` with chmod 600
- Docker Desktop running

**Build and start the containers:**

```bash
cd airflow
docker compose up -d --build
# First build takes ~10-15 min — installs OpenJDK 17 + PySpark 3.5.0
# on top of the Airflow base image. Subsequent starts use cached layers.
```

Three containers come up: `airflow_postgres` (metadata DB),
`airflow_webserver`, and `airflow_scheduler`. The private key mounts
read-only into webserver + scheduler at `/opt/keys/csa_service_key.p8`
via the volume declaration in `docker-compose.yml`.

**Verify the environment is healthy:**

```bash
# All three containers should show "healthy" or "Up"
docker compose ps

# Verify Java is installed in the scheduler
docker exec airflow_scheduler java -version
# Expected: openjdk version "17.x.x"

# Verify PySpark can start a session
docker exec airflow_scheduler python -c "from pyspark.sql import SparkSession; \
    print('PySpark:', SparkSession.builder.appName('t').master('local[*]').getOrCreate().version)"
# Expected: PySpark: 3.5.0

# Verify Snowflake auth works before triggering the DAG
docker exec airflow_scheduler python -c "
from ingestion.snowflake_auth import get_connection
conn = get_connection()
cur = conn.cursor()
cur.execute('SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE()')
print('AUTH SUCCESS:', cur.fetchone())
conn.close()
"
# Expected: AUTH SUCCESS: ('CSA_SERVICE_USER', 'ACCOUNTADMIN', 'COMPUTE_WH')
```

If the auth check fails with "Multi-factor authentication is required",
your shell probably has stale `SNOWFLAKE_USER` or
`SNOWFLAKE_PRIVATE_KEY_PATH` exports overriding the `.env` file
(docker-compose gives shell env vars priority over `.env`). Fix with
`unset SNOWFLAKE_USER SNOWFLAKE_PRIVATE_KEY_PATH` then
`docker compose down && docker compose up -d`.

**Trigger the DAG:**

Open `http://localhost:8080` (login `admin`/`admin`), find
`coupon_pipeline`, toggle it on, and click the ▶️ trigger button.
Or from CLI:

```bash
docker exec airflow_webserver airflow dags trigger coupon_pipeline
```

Full run takes ~5-8 min end-to-end (all 8 work tasks + start/end
wrappers). Watch progress in the UI's Graph View.

---

## What This Project Demonstrates

**Data engineering competencies:**
- Distributed processing with PySpark
- Modern cloud data warehousing (Snowflake)
- ELT transformation patterns with dbt (staging → intermediate → marts)
- Data quality testing (49 dbt tests across uniqueness, referential
  integrity, accepted values, and not-null assertions)
- PII handling: tokenization, k-anonymity, trust boundaries
- Workflow orchestration (Airflow with proper task dependencies)
- Containerization (Docker Compose for the full Airflow stack)

**ML competencies:**
- Customer segmentation (KMeans with elbow + silhouette validation)
- Feature engineering (RFM scores, category affinity, behavioral mix)
- Composite scoring with explainability (per-recommendation reasoning)
- Model serving (FastAPI with auto-generated OpenAPI docs)

**Production thinking:**
- Least-privilege Snowflake roles (separate ingestion vs transformation)
- Reproducible builds (versioned requirements, Docker Compose)
- Automated data quality checks fail the pipeline on regressions
- Auditable transformations (every model in Git, full lineage docs)

---

## Production Hardening Roadmap

The repo demonstrates the architecture; here's what would change to
take it to production at a real bank:

| Component | Local demo | Production |
|---|---|---|
| **Data source** | Synthetic Faker data | Real bank transaction feed (Kafka / S3 dump) |
| **Spark** | Local PySpark | EMR / Databricks / Glue (`SparkSubmitOperator`) |
| **Snowflake stage** | Internal stage | External stage on S3 with Snowpipe auto-ingest |
| **dbt** | `dbt build` from CLI | dbt Cloud or `dbt-core` in CI/CD |
| **Secrets** | `.env` files | AWS Secrets Manager / Snowflake external functions |
| **Airflow** | Docker Compose | Managed Airflow (MWAA / Astronomer) |
| **Inference** | Score on every API call | Pre-computed daily, cached in Redis / DynamoDB |
| **Recommender** | Affinity-based heuristic | XGBoost on click-through history |
| **Monitoring** | dbt test failures + Airflow UI | Datadog metrics + PagerDuty + drift detection |
| **PII salt** | Static in `.env` | Rotated quarterly via Secrets Manager |

---

## Notes & Caveats

- **Naming:** The README refers to "Acme Bank" as a friendly placeholder.
  The code uses `ABC_BANK_ANALYTICS` as the Snowflake database name,
  matching the original project context.
- **Spark in Docker:** The Airflow Docker image deliberately does NOT
  include PySpark or Java to keep the image small (~600MB vs ~2GB).
  In production, the `spark_ingestion` task would use `SparkSubmitOperator`
  pointing at a real Spark cluster. For local demos this means
  `spark_ingestion` will fail in the Docker DAG run — that's expected.
- **Synthetic data limitations:** The seasonal patterns are intentionally
  mild — month-over-month spend variance is realistic but doesn't show
  pronounced holiday spikes. Production data would have stronger seasonal
  signals.
- **Score saturation:** The v1 ranker had ~50% perfect-score ties due to
  linear normalization. The v2 ranker (current) uses log-scaled
  normalization and exponential recency decay, dropping ties to <1%.

---

## Author

**Lakshmi**

Built end-to-end as a portfolio project to demonstrate production-pattern
data engineering and ML skills. Open to feedback, questions, and
collaboration.

---

## License

MIT — see `LICENSE` file.

---

## Acknowledgments

- The 20-persona archetype framework draws on standard segmentation
  practice in retail banking
- PII tokenization patterns follow GLBA / GDPR-aligned k-anonymity guidance
- dbt model naming follows the Kimball-inspired staging/intermediate/marts
  convention recommended by dbt Labs


## AWS Phase 2 — Multi-cloud Daily Delta Pipeline

Architecture: orchestrated daily pipeline running on AWS, with the same
PySpark + dbt + Snowflake stack as the local version but now production-grade:

[delta generator Lambda] → [EMR Serverless Spark] → [Snowflake loader Lambda]
                ↑                ↑                          ↑
                └──────── orchestrated by Step Functions ──┘

### Components

- **`generate_daily_delta` Lambda** (Python 3.12 + Lambda Layer with pandas/pyarrow/numpy/Faker)
  - Looks up existing customers from Snowflake (RAW.CUSTOMERS) — persona-driven
  - Generates daily synthetic delta: 0-5 new customers, ~50 transactions
  - Writes raw PII parquet to s3://csa-dev-raw/.../ingest_date={today}/

- **`tokenize_and_partition.py` on EMR Serverless** (PySpark)
  - Re-tokenizes customer_id → customer_token with salted SHA-256
  - K-anonymity: bands age, income, household_income, zip prefix
  - Fail-loud PII guard prevents silent PII leaks into processed layer
  - Writes partitioned parquet to s3://csa-dev-processed/transactions/year_month=.../day=.../

- **`snowflake_loader` Lambda**
  - Reads tokenized parquet via Snowflake STORAGE INTEGRATION (cross-account IAM trust + external ID)
  - TRUNCATE + COPY INTO with METADATA$FILENAME path extraction for partition columns
  - Idempotent design (verified empirically)

- **Step Functions** (Standard, manual trigger)
  - `.sync` integration on EMR Serverless waits for Spark to finish before next step
  - Retry-once with exponential backoff on transient errors
  - Catch handler routes any failure to PipelineFailed terminal state

### Cross-cloud architecture

The whole pipeline ports cleanly to GCP — equivalent services map as:
  - S3 → Cloud Storage
  - Lambda → Cloud Functions or Cloud Run
  - EMR Serverless → Dataproc Serverless
  - Step Functions → Cloud Workflows
  - Secrets Manager → Secret Manager
  - Snowflake → unchanged (same Snowflake cloud-region)

GCP port handoff guide will be generated in the wrap-up session.

### Known limitations (deferred work)

The core pipeline works end-to-end in both local and AWS environments.
These are hardening items for future iterations:

1. **Single service user across workloads.** `CSA_SERVICE_USER` is used
   for all Snowflake connections (with role switching for privilege
   scoping — ACCOUNTADMIN for pipeline work, DBT_ROLE for dbt). Production
   would split into separate service users per workload, each with its
   own key pair, for full defense-in-depth on the credential dimension.

2. **Private key has no passphrase.** Current key is stored unencrypted
   on disk (permissions 600 only). Production would encrypt with
   passphrase stored as a separate Secrets Manager entry, decrypted
   in memory at connection time.

3. **No automated key rotation.** Snowflake supports `RSA_PUBLIC_KEY_2`
   for zero-downtime rotation (register new key alongside old, roll
   forward, then drop old). Currently manual.

4. **dbt runs locally only.** dbt transformations execute in the local
   Airflow stack (`dbt_build` task). Production would run dbt on a
   scheduled compute (ECS Fargate task or dbt Cloud), authenticated
   via Secrets Manager with the same key-pair pattern as the Lambdas.

5. **No proactive failure alerting.** Failed Step Functions executions
   surface in the AWS console but no alarm fires. Production would
   wire a CloudWatch alarm on the state machine's `ExecutionsFailed`
   metric to SNS → email/Slack.

### War stories (debugging lessons worth keeping)

- **The dbt year_month NULL bug:** local pipeline caught Spark's Hive-style
  partition columns missing from parquet content (path-only)
- **AWS variant of same bug:** Snowflake's COPY INTO doesn't auto-reconstruct
  partition columns; fixed with METADATA$FILENAME regex extraction
- **Lambda packaging size cliff:** 70MB direct → 250MB via S3 → 250MB unzipped
  cap → layers separate big deps with their own 250MB cap → pyarrow pruning
- **Terraform provisioner side-effect blindness:** local-exec aws s3 cp
  completes before S3 is globally consistent; wrap in aws_s3_object resource
  to guarantee dependency ordering
- **PII guard caught its own config flaw:** customer_token in PII blocklist
  was a false positive — the column was re-overwritten with our safe token
  before the guard checked. Same name, different identity, different trust
  level
- **Multi-producer schema drift:** local generator produces raw customer_id;
  Lambda delta generator produces customer_token. Spark transformation
  needed to handle both — added schema detection with explicit ValueError
  if neither column present