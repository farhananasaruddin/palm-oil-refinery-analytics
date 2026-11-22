"""
03_run_sql_pipeline.py  -  TRANSFORM (runs the SQL layer) + EXPORT
-------------------------------------------------------------------
1. Builds the star schema           sql/01_schema.sql
2. Cleans staging -> facts/dims     sql/02_clean_transform.sql
3. Creates reporting views          sql/04_reporting_views.sql
4. Runs every analysis query        sql/03_analysis_queries.sql
   (each query is tagged "-- @name: qNN_xxx") and saves results to
   outputs/sql_results/<name>.csv
5. Exports the clean model to data/processed/*.csv  (Power BI + Excel source)

Run:  python python/03_run_sql_pipeline.py
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "refinery.db"
SQL = ROOT / "sql"
OUT_Q = ROOT / "outputs" / "sql_results"
OUT_P = ROOT / "data" / "processed"
OUT_Q.mkdir(parents=True, exist_ok=True)
OUT_P.mkdir(parents=True, exist_ok=True)

EXPORT_TABLES = ["fact_batch", "fact_downtime", "fact_market_price",
                 "dim_date", "dim_line", "dim_supplier", "dq_log"]


def run_script(con, name):
    con.executescript((SQL / name).read_text())
    print(f"  executed {name}")


def run_named_queries(con, name):
    text = (SQL / name).read_text()
    blocks = re.split(r"^--\s*@name:\s*(\w+)\s*$", text, flags=re.M)
    # blocks = [preamble, name1, body1, name2, body2, ...]
    for qname, body in zip(blocks[1::2], blocks[2::2]):
        df = pd.read_sql_query(body, con)
        df.to_csv(OUT_Q / f"{qname}.csv", index=False)
        print(f"  {qname:<40} {len(df):>5} rows")


def main():
    con = sqlite3.connect(DB)
    print("Building model:")
    run_script(con, "01_schema.sql")
    run_script(con, "02_clean_transform.sql")
    run_script(con, "04_reporting_views.sql")
    con.commit()

    print("\nData-quality log:")
    print(pd.read_sql_query("SELECT step_no, rule, action, rows_affected FROM dq_log", con).to_string(index=False))

    print("\nAnalysis queries:")
    run_named_queries(con, "03_analysis_queries.sql")

    print("\nExporting clean model to data/processed/:")
    for t in EXPORT_TABLES:
        df = pd.read_sql_query(f"SELECT * FROM {t}", con)
        df.to_csv(OUT_P / f"{t}.csv", index=False)
        print(f"  {t:<20} {len(df):>6,} rows")
    con.close()


if __name__ == "__main__":
    main()
