"""
01_generate_raw_data.py
-----------------------
Generates a SYNTHETIC but process-realistic dataset for a palm oil physical
refinery (Degumming -> Bleaching -> Deodorization) with three refining lines.

The data is deliberately "messy" (mixed date formats, inconsistent labels,
unit errors, duplicates, sensor glitches, missing values) so that the
cleaning stage of the pipeline has real work to do - just like plant data
pulled from a DCS historian, LIMS and hand-filled shift logs.

Process relationships built in (to be rediscovered in the analysis):
  * Refining yield falls ~1.06 % for every +1 % FFA in the crude palm oil
  * Low DOBI (poor bleachability) CPO needs more bleaching earth and gives
    darker product
  * Lower deodorizer temperature / poorer vacuum -> higher FFA in RBDPO
  * Line C is the oldest line: more downtime, more energy, slightly lower yield
  * Peak crop season (Sep-Nov) brings higher-FFA crude oil

Outputs (data/raw/):
  batch_production.csv   - shift log / DCS export, one row per batch
  lab_results.csv        - LIMS export of RBDPO quality tests
  energy_readings.csv    - utility meter export per batch
  downtime_log.json      - CMMS export of stoppage events (nested JSON)
  suppliers.xlsx         - supplier (palm oil mill) master data
  market_prices.csv      - monthly commodity prices (MYR / tonne)

Run:  python python/01_generate_raw_data.py
"""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
rng = np.random.default_rng(SEED)
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)

START, END = date(2024, 1, 1), date(2025, 6, 30)
DAYS = [START + timedelta(d) for d in range((END - START).days + 1)]

LINES = {
    #        capacity t/day, commissioned, extra loss %, downtime events/day
    "A": dict(cap=600, year=2012, loss=0.00, dt_rate=0.14, temp=262.5, vac=2.5),
    "B": dict(cap=600, year=2016, loss=-0.05, dt_rate=0.12, temp=263.0, vac=2.4),
    "C": dict(cap=420, year=2005, loss=0.30, dt_rate=0.32, temp=260.5, vac=3.0),
}
SHIFTS = ["Morning", "Evening", "Night"]

SUPPLIERS = [
    # id, official name, state, certification, distance km, base FFA %, base DOBI, share
    ("SUP01", "Ladang Sungai Mas Mill", "Johor", "MSPO + RSPO", 45, 3.20, 2.85, 0.22),
    ("SUP02", "Bukit Hijau Palm Oil Mill", "Pahang", "MSPO + RSPO", 160, 3.55, 2.65, 0.20),
    ("SUP03", "Kuala Teras Mill", "Perak", "MSPO", 310, 3.90, 2.45, 0.16),
    ("SUP04", "Seri Mutiara Mill", "Sabah", "MSPO", 1650, 4.55, 2.10, 0.12),
    ("SUP05", "Tanjung Emas Mill", "Sarawak", "MSPO + RSPO", 1100, 4.15, 2.30, 0.12),
    ("SUP06", "Permatang Jaya Mill", "Selangor", "MSPO", 120, 3.40, 2.75, 0.18),
]
# Messy spellings seen in the shift logs (operators type supplier names by hand)
SUPPLIER_VARIANTS = {
    "SUP01": ["Ladang Sungai Mas Mill", "LADANG SUNGAI MAS MILL", "Ladang Sg. Mas Mill", " Ladang Sungai Mas Mill "],
    "SUP02": ["Bukit Hijau Palm Oil Mill", "Bukit Hijau POM", "bukit hijau palm oil mill"],
    "SUP03": ["Kuala Teras Mill", "Kuala Terass Mill", "KUALA TERAS MILL "],
    "SUP04": ["Seri Mutiara Mill", "Sri Mutiara Mill", "seri mutiara mill"],
    "SUP05": ["Tanjung Emas Mill", "Tg. Emas Mill", "TANJUNG EMAS MILL"],
    "SUP06": ["Permatang Jaya Mill", "Permatang Jaya Mill.", "permatang jaya mill"],
}
LINE_VARIANTS = {
    "A": ["Line A", "Line A", "Line A", "LINE-A", "line a", "A"],
    "B": ["Line B", "Line B", "Line B", "LINE-B", "line b", "B"],
    "C": ["Line C", "Line C", "Line C", "LINE-C", "line c", "C"],
}
SHIFT_VARIANTS = {
    "Morning": ["Morning", "Morning", "MORNING", "AM"],
    "Evening": ["Evening", "Evening", "EVENING", "PM"],
    "Night": ["Night", "Night", "NIGHT", "Night Shift"],
}
DOWNTIME_CAUSES = {
    # category: (relative frequency, median minutes, description variants)
    "Mechanical": (0.26, 95, ["Pump seal leak", "Agitator gearbox fault", "pump trip - mechanical"]),
    "Vacuum System": (0.20, 120, ["Vacuum ejector fouling", "vacuum loss", "Steam ejector trip"]),
    "Filtration": (0.18, 70, ["Bleacher filter clogged", "Niagara filter changeover overrun", "filter cloth torn"]),
    "Utilities": (0.12, 80, ["Boiler trip - low steam", "Cooling tower fault", "Instrument air low"]),
    "Electrical": (0.10, 60, ["Power dip", "MCC breaker trip", "VFD fault"]),
    "Feedstock Shortage": (0.08, 180, ["CPO tank low - lorry delay", "Waiting for CPO", "Feed tank empty"]),
    "Planned Maintenance": (0.06, 360, ["Scheduled PM", "Planned heat exchanger cleaning", "Planned shutdown"]),
}


def month_factor(d: date) -> float:
    """Peak crop season Sep-Nov -> more FFA (longer queues at mills)."""
    return {9: 0.35, 10: 0.45, 11: 0.35, 12: 0.15, 8: 0.15}.get(d.month, 0.0)


def fmt_date(d: date) -> str:
    """Shift logs come from different plant PCs -> mixed date formats."""
    r = rng.random()
    if r < 0.72:
        return d.strftime("%Y-%m-%d")
    if r < 0.90:
        return d.strftime("%d/%m/%Y")
    return d.strftime("%d-%b-%Y")


def pick(lst):
    return lst[rng.integers(len(lst))]


# --------------------------------------------------------------------------
# 1) Downtime events first (they reduce the throughput of the affected batch)
# --------------------------------------------------------------------------
cats = list(DOWNTIME_CAUSES)
cat_p = np.array([DOWNTIME_CAUSES[c][0] for c in cats])
cat_p = cat_p / cat_p.sum()
downtime_events, downtime_minutes = [], {}
ev_no = 1
for d in DAYS:
    for ln, cfg in LINES.items():
        rate = cfg["dt_rate"] * (1.3 if d.month in (9, 10, 11) else 1.0)
        for _ in range(rng.poisson(rate)):
            cat = rng.choice(cats, p=cat_p)
            med = DOWNTIME_CAUSES[cat][1]
            mins = int(np.clip(rng.lognormal(np.log(med), 0.5), 15, 900))
            shift_idx = int(rng.integers(3))
            start = datetime(d.year, d.month, d.day, 7 + 8 * shift_idx) + timedelta(minutes=int(rng.integers(0, 300)))
            end = start + timedelta(minutes=mins)
            key = (d, ln, SHIFTS[shift_idx])
            downtime_minutes[key] = downtime_minutes.get(key, 0) + mins
            rec = {
                "event_id": f"DT{ev_no:05d}",
                "asset": {"line": pick(LINE_VARIANTS[ln]), "area": pick(["Degumming", "Bleaching", "Deodorizer", "Filtration", "Utilities"])},
                "timing": {"start_time": start.isoformat(timespec="minutes"),
                           "end_time": end.isoformat(timespec="minutes") if rng.random() > 0.02 else None},
                "cause": {"category": pick([cat, cat, cat.upper(), cat.lower()]),
                          "description": pick(DOWNTIME_CAUSES[cat][2])},
                "reported_by": f"TECH{int(rng.integers(1, 15)):02d}",
            }
            downtime_events.append(rec)
            ev_no += 1

# --------------------------------------------------------------------------
# 2) Batches (one batch per line per shift)
# --------------------------------------------------------------------------
sup_ids = [s[0] for s in SUPPLIERS]
sup_share = np.array([s[7] for s in SUPPLIERS])
sup_share = sup_share / sup_share.sum()
sup_cfg = {s[0]: s for s in SUPPLIERS}

batches, labs, energy = [], [], []
b_no = 1
for d in DAYS:
    for ln, cfg in LINES.items():
        for sh in SHIFTS:
            if rng.random() < 0.035:  # shift not run (no batch)
                continue
            bid = f"B{d:%y%m%d}-{ln}{SHIFTS.index(sh) + 1}"
            sup = rng.choice(sup_ids, p=sup_share)
            _, _, _, _, _, base_ffa, base_dobi, _ = sup_cfg[sup]

            lost = downtime_minutes.get((d, ln, sh), 0)
            avail = max(0.05, 1 - lost / 480)
            cpo = cfg["cap"] / 3 * avail * rng.normal(1.0, 0.04)

            ffa = float(np.clip(base_ffa + month_factor(d) + rng.normal(0, 0.33), 2.4, 6.5))
            dobi = float(np.clip(base_dobi - 0.10 * (ffa - 3.6) + rng.normal(0, 0.18), 1.5, 3.4))
            moist = float(np.clip(rng.normal(0.16, 0.035), 0.08, 0.30))
            be = float(np.clip(0.85 + 0.42 * (2.8 - dobi) + rng.normal(0, 0.09), 0.6, 2.2))
            pa = float(np.clip(rng.normal(0.065, 0.01), 0.04, 0.10))
            temp = float(rng.normal(cfg["temp"], 2.6))
            vac = float(np.clip(rng.normal(cfg["vac"], 0.35), 1.6, 5.0))
            night = sh == "Night"

            loss = 1.06 * ffa + 0.9 * moist + 0.80 + 0.42 * be + cfg["loss"] + (0.08 if night else 0) + rng.normal(0, 0.18)
            yld = 100 - loss
            rbdpo = cpo * yld / 100
            pfad = cpo * (1.02 * ffa + 0.25 + rng.normal(0, 0.06)) / 100

            # RBDPO quality (spec: FFA <= 0.10 %, colour <= 3.0 R, moisture <= 0.10 %)
            q_ffa = 0.017 + 0.0055 * ffa + 0.0095 * max(0, 263 - temp) + 0.012 * (vac - 2.5) + (0.004 if night else 0) + rng.normal(0, 0.011)
            q_ffa = max(0.02, q_ffa)
            color = 2.30 + 0.85 * (2.6 - dobi) - 0.45 * (be - 1.0) - 0.035 * (temp - 262) + rng.normal(0, 0.17)
            color = max(1.0, color)
            q_moist = float(np.clip(rng.normal(0.045, 0.012), 0.01, 0.15))
            pv = float(np.clip(rng.normal(0.45, 0.18), 0.05, 1.5))

            steam = cpo * (0.048 + 0.0016 * (temp - 260) + (0.009 if ln == "C" else 0) + rng.normal(0, 0.003))
            kwh = cpo * (24 + (5.5 if ln == "C" else 0) + rng.normal(0, 1.4))

            row = {
                "batch_id": bid,
                "production_date": fmt_date(d),
                "shift": pick(SHIFT_VARIANTS[sh]),
                "line": pick(LINE_VARIANTS[ln]),
                "supplier": pick(SUPPLIER_VARIANTS[sup]),
                "cpo_input_mt": round(cpo, 2),
                "cpo_ffa_pct": round(ffa, 2),
                "cpo_dobi": round(dobi, 2),
                "cpo_moisture_pct": round(moist, 3),
                "bleaching_earth_pct": round(be, 2),
                "phosphoric_acid_pct": round(pa, 3),
                "deo_temp_c": round(temp, 1),
                "deo_vacuum_mbar": round(vac, 2),
                "rbdpo_output_mt": round(rbdpo, 2),
                "pfad_output_mt": round(pfad, 2),
                "operator_id": f"OP{int(rng.integers(1, 31)):02d}",
            }
            batches.append(row)

            # --- lab results (LIMS) ---
            if rng.random() > 0.015:  # a few batches never got tested
                base_t = datetime(d.year, d.month, d.day, 7 + 8 * SHIFTS.index(sh)) + timedelta(hours=6, minutes=int(rng.integers(0, 90)))
                n_tests = 2 if rng.random() < 0.04 else 1  # re-tests
                for k in range(n_tests):
                    t = base_t + timedelta(hours=2 * k)
                    f = q_ffa if k == n_tests - 1 else q_ffa + 0.02
                    labs.append({
                        "sample_id": f"S{len(labs) + 1:06d}",
                        "batch_ref": bid,
                        "test_datetime": t.strftime("%Y-%m-%d %H:%M"),
                        "rbdpo_ffa_pct": "<0.03" if f < 0.03 else f"{f:.3f}",
                        "color_lovibond_red": f"{color:.1f}" if rng.random() > 0.08 else f"{color:.1f}R",
                        "moisture_pct": f"{q_moist:.3f}" if rng.random() > 0.01 else "",
                        "peroxide_value": f"{pv:.2f}",
                        "analyst": f"LAB{int(rng.integers(1, 7)):02d}",
                    })

            # --- energy meters ---
            in_mwh = rng.random() < 0.06
            energy.append({
                "batch_id": bid,
                "steam_mt": round(steam, 2),
                "electricity": round(kwh / 1000, 3) if in_mwh else round(kwh, 1),
                "electricity_unit": "MWh" if in_mwh else "kWh",
            })
            b_no += 1

bp = pd.DataFrame(batches)

# --------------------------------------------------------------------------
# 3) Inject realistic data-quality problems
# --------------------------------------------------------------------------
n = len(bp)
def idx(frac):
    return rng.choice(n, size=max(1, int(n * frac)), replace=False)

bp["cpo_input_mt"] = bp["cpo_input_mt"].astype(object)
bp["deo_temp_c"] = bp["deo_temp_c"].astype(object)
bp["cpo_ffa_pct"] = bp["cpo_ffa_pct"].astype(object)
bp["rbdpo_output_mt"] = bp["rbdpo_output_mt"].astype(object)
bp["cpo_dobi"] = bp["cpo_dobi"].astype(object)

for i in idx(0.02):   # FFA keyed as a fraction instead of percent (0.038 vs 3.8)
    bp.at[i, "cpo_ffa_pct"] = round(float(bp.at[i, "cpo_ffa_pct"]) / 100, 4)
for i in idx(0.005):  # decimal point lost on temperature (2625 instead of 262.5)
    bp.at[i, "deo_temp_c"] = round(float(bp.at[i, "deo_temp_c"]) * 10, 0)
for i in idx(0.01):   # sensor offline
    bp.at[i, "deo_temp_c"] = pick(["", "N/A", "-"])
for i in idx(0.003):  # sign error
    bp.at[i, "cpo_input_mt"] = -float(bp.at[i, "cpo_input_mt"])
for i in idx(0.004):  # missing weighbridge reading
    bp.at[i, "cpo_input_mt"] = pick(["", "N/A"])
for i in idx(0.005):
    bp.at[i, "rbdpo_output_mt"] = ""
for i in idx(0.008):
    bp.at[i, "cpo_dobi"] = ""

dups = bp.iloc[idx(0.015)]                  # double-entered batches
bp = pd.concat([bp, dups]).sample(frac=1, random_state=SEED).reset_index(drop=True)
bp.to_csv(RAW / "batch_production.csv", index=False)

pd.DataFrame(labs).to_csv(RAW / "lab_results.csv", index=False)
pd.DataFrame(energy).sample(frac=1, random_state=7).to_csv(RAW / "energy_readings.csv", index=False)

with open(RAW / "downtime_log.json", "w") as fh:
    json.dump({"source": "CMMS export", "plant": "Refinery 1 (synthetic)",
               "exported_at": "2025-07-01T08:00", "events": downtime_events}, fh, indent=1)

sup_df = pd.DataFrame(SUPPLIERS, columns=["supplier_id", "supplier_name", "state", "certification",
                                          "distance_km", "_ffa", "_dobi", "_share"])
sup_df = sup_df.drop(columns=["_ffa", "_dobi", "_share"])
sup_df["contract_start"] = ["2019-03-01", "2020-07-15", "2021-01-10", "2022-05-01", "2021-09-20", "2018-11-05"]
with pd.ExcelWriter(RAW / "suppliers.xlsx") as xw:
    sup_df.to_excel(xw, sheet_name="Supplier_Master", index=False)

# Monthly prices (synthetic, but in a realistic MYR/tonne range)
months = pd.period_range("2024-01", "2025-06", freq="M")
cpo_price = 3900 + np.cumsum(rng.normal(25, 120, len(months)))
cpo_price = np.clip(cpo_price, 3700, 4900)
prices = pd.DataFrame({
    "month": months.astype(str),
    "cpo_price_myr_mt": cpo_price.round(0),
    "rbdpo_price_myr_mt": (cpo_price + rng.normal(230, 35, len(months))).round(0),
    "pfad_price_myr_mt": (cpo_price * rng.normal(0.88, 0.02, len(months))).round(0),
})
prices.to_csv(RAW / "market_prices.csv", index=False)

print(f"batch_production.csv : {len(bp):,} rows (incl. duplicates)")
print(f"lab_results.csv      : {len(labs):,} rows")
print(f"energy_readings.csv  : {len(energy):,} rows")
print(f"downtime_log.json    : {len(downtime_events):,} events")
print(f"suppliers.xlsx       : {len(sup_df)} suppliers")
print(f"market_prices.csv    : {len(prices)} months")
