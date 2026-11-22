"""
run_pipeline.py  -  runs the whole project end to end (about 1 minute)

    python run_pipeline.py            # full rebuild, including raw data
    python run_pipeline.py --keep-raw # reuse the raw files in data/raw/
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("01_generate_raw_data.py", "Generate raw (messy) source files"),
    ("02_extract_load.py", "Extract sources -> SQLite staging"),
    ("03_run_sql_pipeline.py", "SQL clean / model / analyse / export"),
    ("04_data_mining.py", "Data mining + charts"),
    ("05_build_excel_workbook.py", "Excel analysis workbook"),
    ("06_build_web_dashboard.py", "Web dashboard (GitHub Pages)"),
]

if __name__ == "__main__":
    steps = STEPS[1:] if "--keep-raw" in sys.argv else STEPS
    t0 = time.time()
    for script, label in steps:
        print(f"\n{'=' * 70}\n> {label}  ({script})\n{'=' * 70}")
        subprocess.run([sys.executable, str(ROOT / "python" / script)], check=True, cwd=ROOT)
    print(f"\nPipeline finished in {time.time() - t0:.0f} s")
    print("Optional: recalculate the Excel formulas (LibreOffice) or simply open the file in Excel.")
