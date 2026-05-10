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
    print(f"✓ Pipeline completed at {datetime.utcnow().isoformat()}Z")
    print(f"  Run ID:        {context['run_id']}")
    print(f"  Logical date:  {context['logical_date']}")
    print("=" * 60)
    print("Stages executed:")
    print("  1. Synthetic data refreshed")
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
            f"python data_generation/generate_customers.py && "
            f"python data_generation/generate_transactions.py"
        ),
        doc_md="Regenerates synthetic customers (1k) and transactions (~1.6M).",
    )

    # ========================================================================
    # 2. PySpark ingestion
    #    Tokenizes PII, validates schema, writes partitioned parquet
    # ========================================================================
    spark_ingestion = BashOperator(
        task_id="spark_ingestion",
        bash_command=f"cd {PROJECT_ROOT} && python ingestion/spark_ingestion.py",
        doc_md="Tokenizes PII, k-anonymizes demographics, partitions by year_month.",
    )

    # ========================================================================
    # 3. Snowflake load
    #    PUT files to internal stage, COPY INTO RAW tables
    # ========================================================================
    snowflake_load = BashOperator(
        task_id="snowflake_load",
        bash_command=f"cd {PROJECT_ROOT} && python ingestion/snowflake_loader.py",
        doc_md="Uploads parquet to Snowflake stage, runs COPY INTO RAW tables.",
    )

    # ========================================================================
    # 4. dbt build (transformations + tests in one command)
    # ========================================================================
    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command=(
            f"cd {PROJECT_ROOT}/coupon_analytics && "
            f"dbt build --profiles-dir /opt/project/coupon_analytics/profiles"
        ),
        doc_md=(
            "Runs all 8 dbt models (staging → intermediate → marts) "
            "AND all 49 data tests. Fails the DAG on any test failure."
        ),
    )

    # ========================================================================
    # 5. ML feature engineering
    # ========================================================================
    ml_features = BashOperator(
        task_id="ml_features",
        bash_command=f"cd {PROJECT_ROOT} && python -m ml.features",
        doc_md="Pulls customer_360, scales features, saves artifacts.",
    )

    # ========================================================================
    # 6. KMeans segmentation
    # ========================================================================
    ml_segmentation = BashOperator(
        task_id="ml_segmentation",
        bash_command=f"cd {PROJECT_ROOT} && python -m ml.segmentation",
        doc_md="Fits KMeans, profiles clusters, saves model + assignments.",
    )

    # ========================================================================
    # 7. Coupon ranking
    # ========================================================================
    ml_rank_coupons = BashOperator(
        task_id="ml_rank_coupons",
        bash_command=f"cd {PROJECT_ROOT} && python -m ml.coupon_ranker",
        doc_md="Scores all customer×coupon pairs, persists top-3 per customer.",
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
