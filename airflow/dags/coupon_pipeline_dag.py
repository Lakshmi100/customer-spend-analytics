"""
Customer Spend Analytics — Daily Coupon Recommendation Pipeline.

Runs the entire project end-to-end:

    generate_data → spark_ingestion → snowflake_load → dbt_build
                                                            │
                                                            ▼
                              ml_features → ml_segmentation
                                              │
                                              ▼
                                       ml_rank_coupons
                                              │
                                              ▼
                                     publish_summary

Schedule:    daily at 02:00 UTC
Owner:       lakshmi
Catchup:     False (only run on the latest schedule, never backfill)

Notes for future production hardening:
    - generate_data should be removed once real ingestion exists
    - spark_ingestion should become SparkSubmitOperator → EMR/Databricks
    - snowflake_load could become SnowflakeOperator with COPY INTO templates
    - publish_summary should write to S3 / Slack / dashboard
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

# Project root inside the container (mounted in docker-compose.yml)
PROJECT_ROOT = "/opt/project"
INGEST_DATE_TEMPLATE = "{{ dag_run.conf.get('ingest_date') or ds }}"

# Default args inherited by every task in the DAG
DEFAULT_ARGS = {
    "owner": "lakshmi",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _print_pipeline_summary(**context):
    """
    Final task — log a summary of what just happened. In production
    this would post to Slack, write a status file, etc.
    """
    print("=" * 60)
    ingest_date = (
        (context.get("dag_run") and context["dag_run"].conf.get("ingest_date"))
        or context.get("ds")
        or datetime.utcnow().date().isoformat()
    )
    print(f"✓ Pipeline completed at {datetime.utcnow().isoformat()}Z")
    print(f"  Run ID:        {context['run_id']}")
    print(f"  Logical date:  {context['logical_date']}")
    print(f"  Ingest date:   {ingest_date}")
    print("=" * 60)
    print("Stages executed:")
    print("  1. Synthetic data refreshed for ingest_date")
    print("  2. PySpark ingestion + PII tokenization")
    print("  3. Snowflake RAW tables loaded")
    print("  4. dbt build (49 tests passing)")
    print("  5. ML features + segmentation")
    print("  6. Coupon recommendations refreshed")
    return "ok"


with DAG(
    dag_id="coupon_pipeline",
    description="ABC Bank customer spend analytics → coupon recommendations",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",       # daily at 02:00 UTC
    catchup=False,
    max_active_runs=1,
    tags=["abc-bank", "ml", "snowflake", "dbt"],
    doc_md=__doc__,
) as dag:

    start = EmptyOperator(task_id="start")

    # ========================================================================
    # 1. Synthetic data generation
    #    In production this whole stage would be replaced by a real upstream
    #    feed from the bank's transaction system.
    # ========================================================================
    generate_data = BashOperator(
        task_id="generate_data",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Running daily delta for ingest_date=$INGEST_DATE\" && "
            f"python data_generation/generate_customers.py && "
            f"python data_generation/generate_transactions.py"
        ),
        doc_md=(
            "Regenerates the synthetic data set for the target ingest_date. "
            "The date is passed via Airflow conf as ingest_date or ds."
        ),
    )

    # ========================================================================
    # 2. PySpark ingestion
    #    Tokenizes PII, validates schema, writes partitioned parquet
    # ========================================================================
    spark_ingestion = BashOperator(
        task_id="spark_ingestion",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Processing daily delta for ingest_date=$INGEST_DATE\" && "
            f"python ingestion/spark_ingestion.py"
        ),
        doc_md="Tokenizes PII, k-anonymizes demographics, partitions by year_month for the target ingest_date.",
    )

    # ========================================================================
    # 3. Snowflake load
    #    PUT files to internal stage, COPY INTO RAW tables
    # ========================================================================
    snowflake_load = BashOperator(
        task_id="snowflake_load",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Loading Snowflake RAW for ingest_date=$INGEST_DATE\" && "
            f"python ingestion/snowflake_loader.py"
        ),
        doc_md="Uploads parquet to Snowflake stage and loads only the target ingest_date set into RAW tables.",
    )

    # ========================================================================
    # 4. dbt build (transformations + tests in one command)
    # ========================================================================
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {PROJECT_ROOT}/coupon_analytics && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Running dbt build for ingest_date=$INGEST_DATE\" && "
            f"dbt build --profiles-dir /opt/project/coupon_analytics/profiles"
        ),
        doc_md=(
            "Runs all 8 dbt models (staging → intermediate → marts) "
            "AND all 49 data tests for the active ingest_date."
        ),
    )

    # ========================================================================
    # 5. ML feature engineering
    # ========================================================================
    ml_features = BashOperator(
        task_id="ml_features",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Running feature engineering for ingest_date=$INGEST_DATE\" && "
            f"python -m ml.features"
        ),
        doc_md="Pulls the active customer_360 snapshot, scales features, and saves artifacts for the target ingest_date.",
    )

    # ========================================================================
    # 6. KMeans segmentation
    # ========================================================================
    ml_segmentation = BashOperator(
        task_id="ml_segmentation",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Running segmentation for ingest_date=$INGEST_DATE\" && "
            f"python -m ml.segmentation"
        ),
        doc_md="Fits KMeans and profiles clusters for the active data slice.",
    )

    # ========================================================================
    # 7. Coupon ranking
    # ========================================================================
    ml_rank_coupons = BashOperator(
        task_id="ml_rank_coupons",
        bash_command=(
            f"cd {PROJECT_ROOT} && "
            f"export INGEST_DATE='{INGEST_DATE_TEMPLATE}' && "
            f"echo \"Running coupon ranking for ingest_date=$INGEST_DATE\" && "
            f"python -m ml.coupon_ranker"
        ),
        doc_md="Scores active customer×coupon pairs and persists the top recommendations for the target ingest_date.",
    )

    # ========================================================================
    # 8. Pipeline summary
    # ========================================================================
    publish_summary = PythonOperator(
        task_id="publish_summary",
        python_callable=_print_pipeline_summary,
    )

    end = EmptyOperator(task_id="end")

    # ========================================================================
    # Task dependencies
    # ========================================================================
    (
        start
        >> generate_data
        >> spark_ingestion
        >> snowflake_load
        >> dbt_build
        >> ml_features
        >> ml_segmentation
        >> ml_rank_coupons
        >> publish_summary
        >> end
    )
