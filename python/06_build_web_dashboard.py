"""
06_build_web_dashboard.py  -  PUBLISH (web version of the dashboard)
---------------------------------------------------------------------
Aggregates the clean model into small, fully additive cubes and injects them
into dashboard/index.html, a single self-contained page (no libraries, no
server) that can be hosted free on GitHub Pages.

Run:  python python/06_build_web_dashboard.py
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
TEMPLATE = ROOT / "python" / "dashboard_template.html"
OUT = ROOT / "dashboard" / "index.html"

fb = pd.read_csv(PROC / "fact_batch.csv", parse_dates=["production_date"])
dt = pd.read_csv(PROC / "fact_downtime.csv", parse_dates=["event_date"])
px = pd.read_csv(PROC / "fact_market_price.csv")
sup = pd.read_csv(PROC / "dim_supplier.csv")

fb["ym"] = fb.production_date.dt.strftime("%Y-%m")
fb = fb.merge(px, left_on="ym", right_on="year_month", how="left")
fb["value"] = fb.rbdpo_output_mt * fb.rbdpo_price_myr_mt + fb.pfad_output_mt * fb.pfad_price_myr_mt
fb["cost"] = fb.cpo_input_mt * fb.cpo_price_myr_mt
fb["ffa_x_cpo"] = fb.cpo_ffa_pct * fb.cpo_input_mt
fb["offspec"] = fb.is_off_spec.fillna(0)
fb["tband"] = ((fb.deo_temp_c // 2) * 2).astype(int)
fb["hiffa"] = (fb.rbdpo_ffa_pct > 0.10).astype(int)

# Cube 1: month x line x supplier (everything additive)
c1 = (fb.groupby(["ym", "line_code", "supplier_id"])
        .agg(n=("batch_id", "size"), cpo=("cpo_input_mt", "sum"), rbdpo=("rbdpo_output_mt", "sum"),
             ffa=("ffa_x_cpo", "sum"), lab=("has_lab_result", "sum"), off=("offspec", "sum"),
             steam=("steam_mt", "sum"), value=("value", "sum"), cost=("cost", "sum"))
        .reset_index())
# Cube 2: month x line x supplier x deodorizer temperature band (quality)
c2 = (fb[fb.has_lab_result == 1].groupby(["ym", "line_code", "supplier_id", "tband"])
        .agg(lab=("batch_id", "size"), hi=("hiffa", "sum")).reset_index())
# Cube 3: downtime month x line x category
dt["ym"] = dt.event_date.dt.strftime("%Y-%m")
c3 = (dt.groupby(["ym", "line_code", "category", "is_planned"])
        .agg(ev=("event_id", "size"), mins=("duration_min", "sum")).reset_index())


def pack(df, rnd=2):
    return {"cols": list(df.columns), "rows": df.round(rnd).values.tolist()}


data = {
    "months": sorted(fb.ym.unique().tolist()),
    "suppliers": sup[["supplier_id", "supplier_name", "region"]].values.tolist(),
    "batch": pack(c1),
    "quality": pack(c2),
    "downtime": pack(c3),
    "targets": {"yield": 0.95, "offspec": 0.05},
}
html = TEMPLATE.read_text().replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")))
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(html)
print(f"Saved {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.0f} KB; cubes {len(c1)}/{len(c2)}/{len(c3)} rows)")
