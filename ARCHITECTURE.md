# Architecture

Detailed system design for the Customer Spend Analytics — Personalized
Coupon Engine. This document describes the pipeline as it exists today
(August 2026), covering both the local development stack (Phase 1) and
the AWS serverless production stack (Phase 2), plus the shared Snowflake
target that both pipelines write to.

For a quick overview of the project, see the main [README.md](./README.md).
For setup and reproduce instructions, see the *Setup & Reproduce* section
of the README.

---

## 1. Executive Summary

The Customer Spend Analytics pipeline ingests synthetic banking data
(1,000 customers, ~1.6M transactions across ~760 days), tokenizes PII at
a well-defined trust boundary, loads into Snowflake, transforms via dbt
into analytics-ready models, and produces personalized coupon
recommendations via a KMeans-based recommender served over FastAPI +
Streamlit.

The project runs in two independent stacks that share the same Snowflake
target:

- **Phase 1 (local):** Airflow on Docker Compose. Full end-to-end pipeline
  from synthetic data generation through recommender serving. Used for
  active development and interview walkthroughs.

- **Phase 2 (AWS):** EventBridge → Step Functions → Lambda + EMR Serverless.
  A daily delta-based incremental architecture that demonstrates the same
  logical pipeline in production shape. Cost ~$12/month with nightly
  compute teardown.

Both stacks authenticate to Snowflake via RSA key-pair on a `TYPE=SERVICE`
user, use the same PII tokenization primitives (salted SHA-256 + k-anonymity
banding), and share the same trust boundary architecture.














---

## 2. High-Level System Diagram

```
    ┌─────────────────────────────────────────────────────────────────────┐
    │                        LOCAL DEVELOPMENT (Phase 1)                  │
    │                                                                     │
    │   ┌──────────────┐                                                  │
    │   │ Docker       │                                                  │
    │   │ Compose      │  ← runs 3 containers: postgres, webserver,      │
    │   └──────────────┘    scheduler (+ init job)                       │
    │           │                                                         │
    │           ▼                                                         │
    │   ┌──────────────┐                                                  │
    │   │ Airflow DAG  │  coupon_pipeline (9 tasks including start/end)   │
    │   │              │                                                  │
    │   │ generate     │  synthetic data → 1000 customers                 │
    │   │ spark_ingest │  PySpark local[*] → PII stripped + tokenized     │
    │   │ snowflake_ld │  parquet → RAW.CUSTOMERS + RAW.TRANSACTIONS      │
    │   │ dbt_build    │  8 dbt models, 49 tests                          │
    │   │ ml_features  │  feature engineering                             │
    │   │ ml_segment   │  KMeans segmentation (20 personas)               │
    │   │ ml_rank      │  composite-scored coupon recommendations         │
    │   │ publish_sum  │  summary                                         │
    │   └──────┬───────┘                                                  │
    │          │                                                          │
    │          ▼                                                          │
    │   ┌──────────────┐    ┌──────────────┐                              │
    │   │ FastAPI      │    │ Streamlit    │  demo UIs                    │
    │   │ localhost    │    │ localhost    │                              │
    │   │   :8000      │    │   :8501      │                              │
    │   └──────────────┘    └──────────────┘                              │
    │                                                                     │
    │   All communication uses RSA key-pair to Snowflake                  │
    │                                                                     │
    └────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │       ┌─── shared warehouse ───┐
                                 │       │                        │
                                 └──────►│    Snowflake           │◄──────┐
                                         │    ABC_BANK_ANALYTICS  │       │
                                         │    (Enterprise)        │       │
                                         │                        │       │
                                         │    RAW schema          │       │
                                         │    MARTS schema        │       │
                                         └────────────────────────┘       │
                                                                          |
                                                                          |  
                                                                          |
                                                                          |
                                                                          |
                                                                          |
                                                                          │
    ┌─────────────────────────────────────────────────────────────────────┤
    │                        AWS PRODUCTION (Phase 2)                     │
    │                                                                     │
    │   ┌──────────────┐                                                  │
    │   │ EventBridge  │  cron(0 6 * * ? *)  →  daily at 06:00 UTC        │
    │   └──────┬───────┘                                                  │
    │          │                                                          │
    │          ▼                                                          │
    │   ┌──────────────────────────────────────────────────────────────┐  │
    │   │  Step Functions state machine: csa-dev-pipeline              │  │
    │   │                                                              │  │
    │   │  GenerateDelta         → Lambda: csa-dev-generate-daily-delta│  │
    │   │       │                                                      │  │
    │   │       ▼                                                      │  │
    │   │  TokenizeWithSpark     → EMR Serverless Spark job            │  │
    │   │       │                                                      │  │
    │   │       ▼                                                      │  │
    │   │  LoadToSnowflake       → Lambda: csa-dev-snowflake-loader    │──┘
    │   │                                                              │
    │   │  Each task: retry once on transient errors,                  │
    │   │  route non-transient errors to PipelineFailed state          │
    │   └──────────────────────────────────────────────────────────────┘
    │                                                                     │
    │   ┌──────────────────────────────────────────────────────────────┐  │
    │   │  S3: csa-raw-*, csa-processed-*, csa-artifacts-*             │  │
    │   │  Secrets Manager: {snowflake creds + private_key, PII_SALT}  │  │
    │   │  IAM roles: separate per workload, external-ID protected     │  │
    │   │  Terraform: persistent stack (always-on) +                   │  │
    │   │             ephemeral stack (nightly teardown)               │  │
    │   └──────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │   Same key-pair auth to Snowflake as Local stack                    │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Trust Boundary — Where PII Lives and Dies

The single most important architectural feature of this pipeline is the
**trust boundary**: a well-defined line where raw PII gets stripped
before any downstream code sees it. Everything upstream is trusted with
PII; everything downstream operates on tokens and bands only.

```
┌──────────────────────────────────────────────────────────────────────┐
│  UPSTREAM (trusted, PII present)                                     │
│                                                                      │
│  generate_customers.py  →  writes:                                   │
│                              customer_id           (raw)             │
│                              account_number        (raw)             │
│                              first_name, last_name (raw)             │
│                              email, phone_number   (raw)             │
│                              date_of_birth         (raw)             │
│                              street_address        (raw)             │
│                              zip_code, age, income (raw)             │
│                              customer_token        (safe token)      │
│                              account_token         (safe token)      │
│                                                                      │
│  generate_transactions.py → writes:                                  │
│                              transaction_id                          │
│                              customer_id           (raw, for join)   │
│                              customer_token        (safe token)      │
│                              amount, date, etc.                      │
│                                                                      │
│    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼    ▼        │
├──────────────────────────────────────────────────────────────────────┤
│                    ★ TRUST BOUNDARY ★                                │
│                                                                      │
│   spark_ingestion.py (PySpark or EMR Serverless)                     │
│                                                                      │
│      DROP:       customer_id, account_number, first_name,            │
│                  last_name, email, phone_number, date_of_birth,      │
│                  street_address                                      │
│      BAND:       age → age_band ("25-34")                            │
│                  annual_income → income_band ("under_40k")           │
│                  zip_code → zip_prefix ("303XX")                     │
│      KEEP:       customer_token, account_token (tokens),             │
│                  persona_id, family_status, geography, state,        │
│                  ingested_at, batch_id, source_file (metadata)       │
│                                                                      │
│      GUARD:      fail-loud PII assertion catches any missed drops    │
│                  by checking both PII_DROP_COLUMNS and                │
│                  PII_TOKENIZE_COLUMNS sets                           │
├──────────────────────────────────────────────────────────────────────┤
│  DOWNSTREAM (analytics-only, no PII)                                 │
│                                                                      │
│  data/processed/customers/*.parquet    ← tokens + bands + metadata   │
│  data/processed/transactions/*.parquet ← tokens + amounts + dates    │
│                          ↓                                           │
│  Snowflake RAW schema  ← COPY INTO with explicit column whitelist    │
│                          ↓                                           │
│  Snowflake MARTS schema ← 8 dbt models, 49 tests                     │
│                          ↓                                           │
│  ML feature engineering ← operates only on tokens                    │
│                          ↓                                           │
│  KMeans + recommender  ← never sees raw identity                     │
│                          ↓                                           │
│  FastAPI + Streamlit   ← displays tokens (no PII leaks to UI)        │
└──────────────────────────────────────────────────────────────────────┘
```

### Trust Boundary — Design Principles

The trust boundary uses **defense in depth**, not a single mechanism:

- **Drop set (PII_DROP_COLUMNS)** — direct identifiers dropped outright:
  names, email, phone, DOB, address. These have no downstream use.

- **Tokenize set (PII_TOKENIZE_COLUMNS)** — raw identifiers replaced by
  deterministic salted-SHA-256 tokens: `customer_id` → `customer_token`,
  `account_number` → `account_token`. Downstream code can still join on
  the token but cannot recover the original identity.

- **Banding** — quasi-identifiers converted to k-anonymity ranges: exact
  age → age_band ("25-34"); exact income → income_band ("under_40k");
  exact zip → zip_prefix ("303XX"). Individual records become
  indistinguishable from others in the same band.

- **Fail-loud guard** — after the drops, an explicit assertion checks
  that no column names from either PII set remain. If a drop is missed,
  the assertion aborts the job before any parquet gets written.

- **Downstream schema strictness** — Snowflake's `RAW.CUSTOMERS` and
  `RAW.TRANSACTIONS` are defined WITHOUT the raw PII columns. Even if
  Spark's drop failed, the Snowflake `COPY INTO` with explicit column
  whitelisting would fail loudly rather than silently propagate PII.

- **Salt scoping** — the SHA-256 tokenization uses a project-scoped salt
  (`PII_SALT`) stored in Secrets Manager. Without the salt, an attacker
  with stolen tokens cannot mount a rainbow-table attack against known
  customer IDs.

---

## 4. Local Stack (Phase 1) — Development Environment

### 4.1 Docker Compose Layout

The local stack runs via a single `airflow/docker-compose.yml`, which
defines three services (plus a one-shot init job):

```
airflow_postgres     — Airflow metadata database
airflow_init         — one-shot: runs airflow db migrate, creates admin user
airflow_webserver    — Airflow UI at localhost:8080
airflow_scheduler    — DAG scheduler, task executor
```

The Airflow image is built from `airflow/Dockerfile`, which extends
`apache/airflow:2.10.3-python3.11` with:

- **OpenJDK 17** (installed as root, then USER airflow) — required for
  PySpark to launch executors locally
- **JAVA_HOME + PATH** environment variables pointing to the Java install
- **Python dependencies** installed via `airflow/requirements.txt`:
  - snowflake-connector-python, dbt-core, dbt-snowflake
  - pandas, numpy, pyarrow, scikit-learn, joblib
  - pyspark 3.5.0 (matches OpenJDK version)
  - cryptography (for key-pair PEM/DER conversion)
  - python-dotenv, faker

### 4.2 The DAG — coupon_pipeline

Nine tasks in a linear chain, each a BashOperator invoking a Python script:

```
start (EmptyOperator)
  ↓
generate_data
  ↓ runs: python data_generation/generate_customers.py
  ↓ then: python data_generation/generate_transactions.py
  ↓ produces: data/raw/customers.parquet, data/raw/transactions.parquet
  ↓
spark_ingestion
  ↓ runs: python ingestion/spark_ingestion.py
  ↓ tokenizes PII, drops PII cols, applies k-anon banding
  ↓ produces: data/processed/{customers,transactions}/*.parquet
  ↓
snowflake_load
  ↓ runs: python ingestion/snowflake_loader.py
  ↓ PUT to internal stage, COPY INTO RAW.CUSTOMERS, TRUNCATE+COPY RAW.TRANSACTIONS
  ↓
dbt_build
  ↓ runs: dbt build --profiles-dir coupon_analytics/profiles
  ↓ builds 8 models in MARTS schema, runs 49 data-quality tests
  ↓
ml_features
  ↓ runs: python ml/build_features.py
  ↓ produces feature dataset from customer_360 mart
  ↓
ml_segmentation
  ↓ runs: python ml/kmeans_segmentation.py
  ↓ fits KMeans, assigns cluster labels, profiles personas
  ↓ produces: ml/artifacts/kmeans_model.joblib
  ↓
ml_rank_coupons
  ↓ runs: python ml/rank_coupons.py
  ↓ composite-scores coupons per customer via cluster affinity + behavior
  ↓ produces: coupon recommendations table in MARTS
  ↓
publish_summary
  ↓ prints summary stats (rowcounts, model metrics)
  ↓
end (EmptyOperator)
```

Each task runs in the Airflow scheduler container. `spark_ingestion` uses
a local Spark session (`.master("local[*]")`), so PySpark and Java must
be installed in the container.

### 4.3 Snowflake Authentication (Local Stack)

All local Python code connects to Snowflake via a **shared authentication
helper**: `ingestion/snowflake_auth.py`. The helper:

1. Reads `SNOWFLAKE_PRIVATE_KEY_PATH` from environment
2. Opens the PEM-encoded private key file (mounted read-only into the
   container from `~/.snowflake-keys/csa_service_key.p8`)
3. Uses the `cryptography` library to convert PEM to DER bytes
4. Passes DER bytes to `snowflake.connector.connect(private_key=...)`

The authenticating user is `CSA_SERVICE_USER` (Snowflake `TYPE=SERVICE`),
exempt from Snowflake's MFA policy by design. Roles are switched
per-workload:

- `ingestion/snowflake_loader.py` — uses `ACCOUNTADMIN` role (COPY, MERGE,
  TRUNCATE across schemas)
- `ml/snowflake_io.py` — uses `ACCOUNTADMIN` role (read from MARTS)
- dbt (via profiles.yml) — uses `DBT_ROLE` (least-privilege for transform
  layer)

All three call the same `get_connection()` helper, with per-call overrides
for warehouse/role. Single source of truth for auth logic; adding a new
Snowflake caller means one import, not a copy-paste of PEM-loading code.

### 4.4 The Serving Layer (FastAPI + Streamlit)

Not orchestrated by the DAG; runs standalone from the Python venv:

- **FastAPI** at `localhost:8000` — exposes `/recommend/{customer_token}`
  endpoint returning ranked coupons with reasoning
- **Streamlit** at `localhost:8501` — interactive dashboard for exploring
  segments, browsing customers, viewing recommendations

Both read from the Snowflake MARTS schema via the same `snowflake_auth.py`
helper. Neither has direct filesystem access to the data — all queries
go through the analytics warehouse.

---

## 5. AWS Stack (Phase 2) — Production Architecture

### 5.1 Design Intent

Phase 2 demonstrates the same logical pipeline in production shape:
serverless, scheduled, cost-controlled, and independently deployable.
The unit of work is a **daily delta** — a small number of new customers
(~2-5) and their transactions (~50) generated each day, rather than the
1000-customer bulk load that the local stack does.

### 5.2 Terraform Stack Split

Infrastructure is split into two Terraform stacks with independent state
backends:

**Persistent stack** (`infra/aws/terraform/envs/dev/persistent/`) —
resources that stay up between sessions:

- 3 S3 buckets: `csa-raw-*`, `csa-processed-*`, `csa-artifacts-*`
- 2 Secrets Manager secrets: Snowflake creds (with private key),
  PII salt
- 3 IAM roles: ingestion, ML, API (each with least-privilege policy)
- 2 ECR repositories (currently unused; retained from earlier design)
- Snowflake STORAGE INTEGRATION IAM role (bootstrap-pattern trust
  policy with `sts:ExternalId` for confused-deputy defense)
- Spark job source (`tokenize_and_partition.py`) as an `aws_s3_object`
  Terraform resource — no manual upload step required
- Approximate cost: **~$1-2/month** (Secrets Manager dominates)

**Ephemeral stack** (`infra/aws/terraform/envs/dev/ephemeral/`) —
compute resources that can be torn down nightly:

- EMR Serverless application (cold-start, auto-stops 5 min after job)
- 2 Lambda functions: `csa-dev-generate-daily-delta`,
  `csa-dev-snowflake-loader`
- 1 Lambda Layer: `csa-dev-data-libs` (pandas, pyarrow, numpy)
- Step Functions state machine: `csa-dev-pipeline`
- EventBridge daily schedule rule
- CloudWatch log groups
- Approximate cost when running: **~$0.30-0.50/day**, torn down
  overnight

### 5.3 Terraform Modules — Building Blocks

11 reusable modules under `infra/aws/terraform/modules/`:

| Module | Purpose |
|---|---|
| `storage` | 3 S3 buckets with encryption + lifecycle |
| `secrets` | Secrets Manager entries (Snowflake creds, PII salt) |
| `iam` | IAM roles + policies for each workload |
| `ecr` | Container repositories |
| `snowflake_storage` | Cross-account IAM role with external-ID trust |
| `lambda_layer_data` | pandas/pyarrow layer (pruned pyarrow to fit 250MB cap) |
| `lambda_generate_daily_delta` | Delta-generator Lambda |
| `lambda_snowflake_loader` | Snowflake-loader Lambda |
| `emr_serverless` | Spark application (cold-start config) |
| `step_functions` | State machine with retry/catch policies |
| `eventbridge_schedule` | Daily cron rule + IAM target |

Each module has its own inputs, outputs, and a single-responsibility
scope. Composition happens in `main.tf` of each environment stack.

### 5.4 The State Machine — csa-dev-pipeline

A Standard-workflow Step Functions state machine defined in Amazon
States Language (ASL). Three linear task states, plus retry/catch
handlers, plus a terminal `PipelineFailed` state:

```
Input: { "ingest_date"?: "YYYY-MM-DD" }   (defaults to today)

  ↓

GenerateDelta                            [Type: Task]
  ├── Resource: lambda:invoke
  ├── FunctionName: csa-dev-generate-daily-delta
  ├── Retry: 1 attempt on Lambda.TooManyRequestsException,
  │            Lambda.ServiceException, Lambda.AWSLambdaException,
  │            Lambda.SdkClientException (5s interval, 2.0 backoff)
  ├── Catch: States.ALL → PipelineFailed
  ├── ResultPath: $.delta
  └── Next: TokenizeWithSpark

  ↓

TokenizeWithSpark                        [Type: Task]
  ├── Resource: emr-serverless:startJobRun.sync
  │              (.sync = wait for terminal state, no polling loop)
  ├── ApplicationId: from persistent stack outputs
  ├── ExecutionRoleArn: from persistent stack outputs
  ├── JobDriver.SparkSubmit:
  │     EntryPoint: s3://csa-artifacts-*/spark/tokenize_and_partition.py
  │     Arguments: --ingest-date $.delta.ingest_date
  ├── Retry: 1 attempt on transient EMR errors
  ├── Catch: States.ALL → PipelineFailed
  ├── ResultPath: $.spark
  └── Next: LoadToSnowflake

  ↓

LoadToSnowflake                          [Type: Task]
  ├── Resource: lambda:invoke
  ├── FunctionName: csa-dev-snowflake-loader
  ├── Payload: { ingest_date: $.delta.ingest_date }
  ├── Retry: 1 attempt (same transient errors as GenerateDelta)
  ├── Catch: States.ALL → PipelineFailed
  ├── ResultPath: $.snowflake
  └── End: true

  ↓  (success)

Output: {
  delta: { ingest_date, new_customers, new_transactions },
  spark: { JobRunId, State, ApplicationId, ... },
  snowflake: {
    customers_total, customers_inserted, customers_updated,
    customers_staged, transactions_loaded, transactions_distinct_days
  }
}


  ↓  (failure at any step)

PipelineFailed                           [Type: Fail]
  ├── Error: csaPipelineFailure
  └── Cause: "csa pipeline failed - inspect execution history for details"
```

State machine timeout: 1800 seconds (30 min) total. Individual tasks
inherit this budget.

### 5.5 The Two Lambdas

**`csa-dev-generate-daily-delta`** (Python 3.12 + Layer):
- Reads existing customer tokens from `RAW.CUSTOMERS` (SAMPLE for
  efficiency)
- Generates 2-5 new customers with fresh tokens
- Generates ~50 transactions using existing + new customer tokens
- Writes to S3: `s3://csa-raw-*/customers/ingest_date=YYYY-MM-DD/*.parquet`
  and `s3://csa-raw-*/transactions/ingest_date=YYYY-MM-DD/*.parquet`
- Returns: `{ ingest_date, new_customers, new_transactions }`

**`csa-dev-snowflake-loader`** (Python 3.12):
- Reads Snowflake credentials + private key from Secrets Manager
- Uses shared cryptography-library key-pair auth (matches local stack)
- COPY INTO staging → MERGE INTO `RAW.CUSTOMERS` on `customer_token`
  (Type 1 SCD: insert new, update existing)
- TRUNCATE + COPY INTO `RAW.TRANSACTIONS` (idempotent full reload
  because S3 files are immutable)
- Returns: `{ customers_total, customers_inserted, customers_updated,
  transactions_loaded, ... }`

Both Lambdas use the same authentication pattern as the local Python
code — read private key from Secrets Manager, parse via `cryptography`,
pass DER bytes to `snowflake.connector.connect()`. Consistent with the
local stack.

### 5.6 EMR Serverless — The Tokenization Job

Runs `spark/tokenize_and_partition.py` (Terraform-managed as an
`aws_s3_object`). Same Spark logic as the local `ingestion/
spark_ingestion.py`, adapted for S3 paths:

- Reads today's raw partition: `s3://csa-raw-*/customers/ingest_date=X/`
- Applies the same PII drops and k-anonymity banding
- Writes tokenized output: `s3://csa-processed-*/customers/ingest_date=X/`
  and `s3://csa-processed-*/transactions/ingest_date=X/year_month=Y/`
- Uses the S3-optimized parquet committer (reduced 21-min local runtime
  to ~3 min on EMR)

Cold-start config: application scales from 0 workers when idle,
auto-stops 5 min after job finishes. No idle compute cost.

### 5.7 Cross-Account Security (Snowflake ↔ AWS)

The Snowflake STORAGE INTEGRATION creates a secure S3 access channel:

```
Snowflake service account (multi-tenant, shared across all customers)
    │
    │ Wants to COPY from S3
    ▼
Snowflake generates STS AssumeRole request:
    - RoleARN: your AWS role
    - ExternalId: your unique token (per-integration secret)
    ▼
AWS IAM checks trust policy:
    ├── Principal.AWS == Snowflake's account principal ✓
    └── Condition.StringEquals: sts:ExternalId == your token ✓
    ▼
Assume succeeds; Snowflake gets temp credentials
    ▼
COPY INTO reads from S3
```

The `sts:ExternalId` prevents the **confused-deputy attack**: without it,
any Snowflake customer could theoretically use their own Snowflake account
to COPY from your S3. With it, only requests carrying your specific token
succeed.

---

## 6. The Shared Snowflake Target

Both stacks write to the same Snowflake tables:

```
ABC_BANK_ANALYTICS  (database)
├── RAW schema                    ← Both pipelines write here
│   ├── CUSTOMERS                  (columns: customer_token, account_token,
│   │                                bands, persona, metadata — NO customer_id)
│   ├── TRANSACTIONS               (columns: customer_token, amounts,
│   │                                dates, metadata — NO customer_id)
│   └── CUSTOMERS_STAGE            (temp staging for MERGE)
│
└── MARTS schema                   ← dbt writes here (local only)
    ├── customer_360               (denormalized customer view)
    ├── customer_spend_summary     (aggregated spend)
    ├── coupon_recommendations     (ML output)
    └── ...5 more models
```

**Load patterns differ by table:**

| Table | Pattern | Rationale |
|---|---|---|
| `RAW.CUSTOMERS` | **MERGE** (Type 1 SCD) on `customer_token` | Customers are slowly-changing dimensions. Most days bring zero new. MERGE preserves existing rows and updates changed profile fields. |
| `RAW.TRANSACTIONS` | **TRUNCATE + COPY** (full reload from S3) | Transactions are immutable events. Full reload is idempotent because source S3 files never change. |

**MERGE for customers means both pipelines coexist safely** — running
the local pipeline and then the AWS pipeline produces additive results:
existing customer_tokens get their `ingested_at` refreshed, new
customer_tokens get inserted. Neither destroys the other's data.

---

## 7. Cross-Cutting Concerns

### 7.1 Authentication (Both Stacks)

RSA 2048-bit key-pair. Same key file (`csa_service_key.p8`) used by:

- Local Python code (via `~/.snowflake-keys/` mount into containers)
- Local dbt (via `private_key_path` in `profiles.yml`)
- AWS Lambdas (via Secrets Manager, decoded at invocation)

Snowflake side registers only the public key on `CSA_SERVICE_USER`
(`TYPE=SERVICE`), exempt from MFA policy. Roles selected per-workload:
`ACCOUNTADMIN` for pipeline work, `DBT_ROLE` for dbt transformations.

Private key never travels over the network. Snowflake authenticates by
signature verification, not by receiving the key. Even full capture of
an authentication handshake gives an attacker nothing usable.

### 7.2 Cost Discipline

- **Local:** Docker Compose runs on your laptop. Zero cloud cost when
  idle. Snowflake warehouses auto-suspend after 60s idle.

- **AWS:** Persistent stack ~$1-2/month (Secrets Manager dominates).
  Ephemeral stack ~$0.30-0.50 per active day, torn down nightly via
  `make session-end`. Full month with daily practice: ~$12-15.

- **Snowflake:** Enterprise account, ~$3/credit. `WEEKLY_SAFETY_CAP`
  resource monitor at 5 credits/week (~$15) auto-suspends `COMPUTE_WH`
  if exceeded. Typical week: 0.2-0.5 credits used.

- **Total monthly:** ~$15-20 across AWS + Snowflake for active
  development and daily practice runs.

### 7.3 Infrastructure as Code

Every AWS resource is declared in Terraform. Nothing was clicked in the
AWS console. Two backends (S3 for state, DynamoDB for locking) ensure
concurrent-safe changes. Common Make targets:

- `make session-start` — brings up ephemeral stack (~3 min)
- `make session-end` — tears down ephemeral stack (~1 min)
- `make cost-mtd` — month-to-date AWS spend by service
- `make verify-clean` — confirms no ephemeral resources are running
- `make persistent-apply` — updates the always-on stack
- `make ephemeral-apply` — updates the compute stack

### 7.4 Observability

- **Airflow UI** at `localhost:8080` — task states, logs, DAG history
- **AWS Step Functions console** — execution history, state transitions,
  failure details with cause
- **CloudWatch log groups** — per-Lambda logs, per-EMR-application logs,
  state-machine execution logs
- **Snowflake ACCOUNT_USAGE** — query history, warehouse metering,
  cost attribution

---

## 8. Architectural Decisions Journal

| Decision | Choice | Rationale |
|---|---|---|
| **Orchestrator (production)** | Step Functions | MWAA has ~$350/mo floor; a 3-step linear pipeline doesn't need Airflow's rich DAG semantics |
| **Compute (production)** | EMR Serverless | Pay per second of actual work; no idle cost; ~3 min end-to-end vs ~21 min local |
| **Auth (both stacks)** | RSA key-pair | MFA is right for humans, impossible for services; TYPE=SERVICE users are Snowflake's canonical answer |
| **Storage integration** | Snowflake STORAGE INTEGRATION + external ID | Confused-deputy defense; per-integration secret prevents cross-tenant assume |
| **Trust boundary location** | PySpark / EMR ingestion layer | Central chokepoint; both DROP and TOKENIZE sets enforced with fail-loud guard |
| **Customer load pattern** | Type 1 SCD MERGE | Customers are slowly-changing; MERGE preserves history where full-replace wouldn't |
| **Transaction load pattern** | TRUNCATE + COPY | Transactions are immutable events; full reload from S3 is idempotent |
| **Terraform stack split** | Persistent + ephemeral | Cost control — always-on resources stay up, compute torn down nightly |
| **Lambda dependencies** | Layer pattern with pyarrow pruning | Pandas + pyarrow unzipped is ~290MB; pruning pyarrow subsystems drops to ~220MB, fits Lambda's 250MB cap |
| **Spark script deployment** | `aws_s3_object` in Terraform | Explicit dependency tracking; no manual upload; version-controlled |
| **Snowflake user identity** | Single `CSA_SERVICE_USER` for all workloads | Simplicity; production would split by role (see Future Work) |

---

## 9. Future Work

Items not implemented but understood:

- **Separate service users per workload** — one for pipeline, one for dbt,
  each with its own key pair. Currently all workloads share
  `CSA_SERVICE_USER` (with role switching for privilege scoping)
- **Passphrase-encrypted private key** — current key has no passphrase.
  Production would encrypt with passphrase stored as separate Secrets
  Manager entry.
- **Key rotation via Snowflake's `RSA_PUBLIC_KEY_2`** — supports
  zero-downtime rotation by registering new key alongside old.
- **CloudWatch alarms on failed scheduled runs** — currently rely on
  manual `list-executions` check next morning.
- **dbt on cloud** — dbt currently runs locally only. Production would
  run on ECS Fargate or dbt Cloud with same key-pair auth pattern.
- **Multi-cloud port** — pipeline design is portable to GCP:
  S3→Cloud Storage, Lambda→Cloud Functions, EMR Serverless→Dataproc
  Serverless, Step Functions→Cloud Workflows. Snowflake unchanged.

---

## 10. References

- Main [README.md](./README.md) — project overview, setup, reproduce
- [INTERVIEW_PREP.md](./INTERVIEW_PREP.md) — interview stories + Q&A
  (not in public repo)
- Terraform code: `infra/aws/terraform/`
- DAG definition: `airflow/dags/coupon_pipeline_dag.py`
- Trust boundary implementation: `ingestion/spark_ingestion.py`,
  `ingestion/pii_tokenizer.py`
- Snowflake auth helper: `ingestion/snowflake_auth.py`
- Step Functions ASL: `infra/aws/terraform/modules/step_functions/
  state_machine.json`
