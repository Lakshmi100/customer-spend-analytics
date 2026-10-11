import os
from pathlib import Path

import pandas as pd

from data_generation import generate_customers, generate_transactions


def test_generate_customers_accepts_ingest_date_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INGEST_DATE", "2026-01-15")

    generate_customers.main()

    delta_dir = tmp_path / "data" / "raw" / "customers" / "ingest_date=2026-01-15"
    assert delta_dir.exists(), "customers delta should be written under ingest_date partition"
    files = list(delta_dir.glob("*.parquet"))
    assert files, "customers delta should include at least one parquet file"
    customer_rows = pd.read_parquet(files[0])
    assert len(customer_rows) == 5, "daily delta should include exactly 5 customer rows"


def test_generate_transactions_accepts_ingest_date_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("INGEST_DATE", "2026-01-15")

    raw_customers = tmp_path / "data" / "raw" / "customers" / "ingest_date=2026-01-15"
    raw_customers.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([
        {
            "customer_id": f"ABC-{i:08d}",
            "customer_token": f"token-{i}",
            "persona_id": ["P01", "P04", "P10", "P15", "P20"][i % 5],
            "state": "CA",
            "is_active": True,
            "account_open_date": "2024-01-01",
        }
        for i in range(5)
    ]).to_parquet(raw_customers / "customers.parquet", index=False)

    generate_transactions.main()

    delta_dir = tmp_path / "data" / "raw" / "transactions" / "ingest_date=2026-01-15"
    assert delta_dir.exists(), "transactions delta should be written under ingest_date partition"
    files = list(delta_dir.glob("*.parquet"))
    assert files, "transactions delta should include at least one parquet file"
    transaction_rows = pd.read_parquet(files[0])
    assert len(transaction_rows) == 50, "daily delta should include exactly 50 transaction rows"
