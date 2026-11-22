"""
02_extract_load.py  -  EXTRACT + LOAD (the "E" and "L" of ELT)
---------------------------------------------------------------
Pulls the six raw sources (CSV, JSON, Excel) and lands them *as-is* into
staging tables (stg_*) in a SQLite database. Every column is stored as TEXT
so nothing is silently coerced or lost - all cleaning happens later in SQL,
where every rule is visible and auditable.

Run:  python python/02_extract_load.py
"""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "refinery.db"


def extract_csv(name: str) -> pd.DataFrame:
    return pd.read_csv(RAW / name, dtype=str, keep_default_na=False)


def extract_downtime_json(name: str) -> pd.DataFrame:
    """CMMS export is nested JSON -> flatten to one row per event."""
    with open(RAW / name) as fh:
        payload = json.load(fh)
    df = pd.json_normalize(payload["events"], sep="_")
    return df.fillna("").astype(str).replace({"None": "", "nan": ""})


def extract_excel(name: str, sheet: str) -> pd.DataFrame:
    return pd.read_excel(RAW / name, sheet_name=sheet, dtype=str).fillna("")


def load(df: pd.DataFrame, table: str, con: sqlite3.Connection) -> None:
    df = df.copy()
    df["_source_row"] = range(1, len(df) + 1)        # lineage back to the raw file
    df["_loaded_at"] = datetime.now().isoformat(timespec="seconds")
    df.to_sql(table, con, if_exists="replace", index=False,
              dtype={c: "TEXT" for c in df.columns if c != "_source_row"})
    print(f"  loaded {table:<22} {len(df):>6,} rows  {df.shape[1] - 2} cols")


def main() -> None:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    print(f"Extracting from {RAW.relative_to(ROOT)} -> {DB.relative_to(ROOT)}")
    load(extract_csv("batch_production.csv"), "stg_batch_production", con)
    load(extract_csv("lab_results.csv"), "stg_lab_results", con)
    load(extract_csv("energy_readings.csv"), "stg_energy_readings", con)
    load(extract_downtime_json("downtime_log.json"), "stg_downtime_log", con)
    load(extract_excel("suppliers.xlsx", "Supplier_Master"), "stg_suppliers", con)
    load(extract_csv("market_prices.csv"), "stg_market_prices", con)
    con.commit()
    con.close()


if __name__ == "__main__":
    main()
