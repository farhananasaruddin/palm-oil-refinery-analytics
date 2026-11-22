"""
04_data_mining.py  -  DATA MINING / MODELLING
----------------------------------------------
Works on the clean model (data/processed/) and answers four questions:

 1. Regression      - How much refining yield do we lose per +1 % crude FFA?
                      (multiple linear regression with standard errors)
 2. Classification  - Can we predict an off-spec batch BEFORE it is made?
                      (Random Forest + permutation importance)
 3. Clustering      - What natural crude-oil quality segments exist?
                      (K-Means, k chosen by silhouette score)
 4. Anomaly detect. - Which batches used abnormal energy?
                      (Isolation Forest per line)

Outputs: images/*.png, outputs/data_mining/*.csv, outputs/data_mining/model_summary.json

Run:  python python/04_data_mining.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (classification_report, confusion_matrix,
                             roc_auc_score, silhouette_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
IMG = ROOT / "images"
OUT = ROOT / "outputs" / "data_mining"
IMG.mkdir(exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

# ---- chart style (one consistent, colour-blind-checked palette) -----------
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]          # Line A, Line B, Line C (fixed order)
LINE_COLOR = dict(zip("ABC", SERIES))
CRITICAL = "#d03b3b"
plt.rcParams.update({
    "font.family": ["Inter", "DejaVu Sans"], "font.size": 10,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED, "legend.frameon": False,
    "lines.linewidth": 2,
})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(IMG / name, dpi=160)
    plt.close(fig)
    print(f"  saved images/{name}")


def subtitle(ax, text):
    ax.text(0, 1.02, text, transform=ax.transAxes, color=INK2, fontsize=9.5, va="bottom")


# ---- load -------------------------------------------------------------------
fb = pd.read_csv(PROC / "fact_batch.csv", parse_dates=["production_date"])
sup = pd.read_csv(PROC / "dim_supplier.csv")
fb = fb.merge(sup[["supplier_id", "supplier_name"]], on="supplier_id", how="left")
fb["night"] = (fb["shift"] == "Night").astype(int)
for ln in "BC":
    fb[f"line_{ln}"] = (fb["line_code"] == ln).astype(int)
summary = {}

# =============================================================================
# 1) REGRESSION - drivers of refining yield
# =============================================================================
print("\n[1] Multiple linear regression: refining yield")
X_cols = ["cpo_ffa_pct", "cpo_dobi", "cpo_moisture_pct", "bleaching_earth_pct", "line_B", "line_C", "night"]
d = fb.dropna(subset=X_cols + ["refining_yield_pct"])
X = np.column_stack([np.ones(len(d)), d[X_cols].values])
y = d["refining_yield_pct"].values
beta, *_ = np.linalg.lstsq(X, y, rcond=None)
resid = y - X @ beta
n, k = X.shape
sigma2 = resid @ resid / (n - k)
se = np.sqrt(np.diag(sigma2 * np.linalg.inv(X.T @ X)))
t = beta / se
p = 2 * (1 - stats.t.cdf(np.abs(t), n - k))
r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
reg = pd.DataFrame({"term": ["intercept"] + X_cols, "coef": beta, "std_err": se, "t": t, "p_value": p})
reg.to_csv(OUT / "regression_yield_coefficients.csv", index=False)
print(reg.round(4).to_string(index=False))
print(f"  R^2 = {r2:.3f}  (n = {n:,})")
summary["regression"] = {"r2": round(r2, 3), "n": int(n),
                         "yield_pts_per_1pct_ffa": round(float(beta[1]), 3),
                         "yield_pts_per_1pct_bleaching_earth": round(float(beta[4]), 3),
                         "line_C_penalty_pts": round(float(beta[6]), 3)}

# Chart: FFA vs yield scatter by line + fitted slope
fig, ax = plt.subplots(figsize=(8, 4.8))
sample = fb.sample(1500, random_state=1)
for ln in "ABC":
    s = sample[sample.line_code == ln]
    ax.scatter(s.cpo_ffa_pct, s.refining_yield_pct, s=12, color=LINE_COLOR[ln], alpha=0.55,
               edgecolors=SURFACE, linewidths=0.4, label=f"Line {ln}")
slope, intercept, r, *_ = stats.linregress(fb.cpo_ffa_pct, fb.refining_yield_pct)
xs = np.linspace(fb.cpo_ffa_pct.min(), fb.cpo_ffa_pct.max(), 50)
ax.plot(xs, intercept + slope * xs, color=INK, linewidth=1.6)
ax.text(0.03, 0.06, f"Fitted slope: {slope:.2f} pts of yield per +1 % FFA  (R² = {r**2:.2f})",
        transform=ax.transAxes, color=INK, fontsize=9.5)
ax.set_xlabel("Crude palm oil FFA (%)")
ax.set_ylabel("Refining yield (%)")
ax.set_title("Every extra 1 % of FFA in the crude costs about 1 point of yield", pad=22)
subtitle(ax, "Refining yield vs crude FFA, 1,500 sampled batches")
ax.legend(loc="upper right", ncol=3)
save(fig, "01_ffa_vs_yield.png")

# Chart: correlation heatmap (diverging blue - grey - red)
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("div", ["#184f95", "#6da7ec", "#f0efec", "#ec835a", "#b8302f"])
corr_cols = {"cpo_ffa_pct": "CPO FFA", "cpo_dobi": "CPO DOBI", "bleaching_earth_pct": "Bleaching earth",
             "deo_temp_c": "Deo temp", "deo_vacuum_mbar": "Deo vacuum", "refining_yield_pct": "Yield",
             "rbdpo_ffa_pct": "RBDPO FFA", "color_red": "Colour (R)", "steam_per_mt_cpo": "Steam / t"}
C = fb[list(corr_cols)].corr().rename(index=corr_cols, columns=corr_cols)
C.to_csv(OUT / "correlation_matrix.csv")
fig, ax = plt.subplots(figsize=(7.6, 6.4))
im = ax.imshow(C.values, cmap=cmap, vmin=-1, vmax=1)
ax.set_xticks(range(len(C)), C.columns, rotation=40, ha="right", color=INK2)
ax.set_yticks(range(len(C)), C.index, color=INK2)
ax.grid(False)
for i in range(len(C)):
    for j in range(len(C)):
        v = C.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=8,
                color="#ffffff" if abs(v) > 0.6 else INK)
ax.set_title("Crude quality drives yield; deodorizer settings drive product FFA", pad=12)
cb = fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
cb.outline.set_visible(False)
cb.ax.tick_params(colors=MUTED)
save(fig, "02_correlation_heatmap.png")

# =============================================================================
# 2) CLASSIFICATION - predict off-spec before production
# =============================================================================
print("\n[2] Random Forest: off-spec prediction")
F = ["cpo_ffa_pct", "cpo_dobi", "cpo_moisture_pct", "bleaching_earth_pct", "phosphoric_acid_pct",
     "deo_temp_c", "deo_vacuum_mbar", "line_B", "line_C", "night"]
nice = {"cpo_ffa_pct": "CPO FFA", "cpo_dobi": "CPO DOBI", "cpo_moisture_pct": "CPO moisture",
        "bleaching_earth_pct": "Bleaching earth dose", "phosphoric_acid_pct": "Phosphoric acid dose",
        "deo_temp_c": "Deodorizer temperature", "deo_vacuum_mbar": "Deodorizer vacuum",
        "line_B": "Line B", "line_C": "Line C", "night": "Night shift"}
dc = fb.dropna(subset=F + ["is_off_spec"])
Xtr, Xte, ytr, yte = train_test_split(dc[F], dc["is_off_spec"].astype(int), test_size=0.25,
                                      stratify=dc["is_off_spec"], random_state=7)
rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=5, class_weight="balanced",
                            random_state=7, n_jobs=-1).fit(Xtr, ytr)
proba = rf.predict_proba(Xte)[:, 1]
pred = (proba >= 0.5).astype(int)
auc = roc_auc_score(yte, proba)
cm = confusion_matrix(yte, pred)
print(classification_report(yte, pred, digits=3))
print(f"  ROC AUC = {auc:.3f}\n  confusion matrix [[TN FP][FN TP]] = {cm.tolist()}")
pi = permutation_importance(rf, Xte, yte, scoring="roc_auc", n_repeats=15, random_state=7)
imp = pd.DataFrame({"feature": [nice[f] for f in F], "importance": pi.importances_mean,
                    "std": pi.importances_std}).sort_values("importance")
imp.to_csv(OUT / "offspec_feature_importance.csv", index=False)
tn, fp, fn, tp = cm.ravel()
summary["classification"] = {"roc_auc": round(auc, 3), "recall_offspec": round(tp / (tp + fn), 3),
                             "precision_offspec": round(tp / (tp + fp), 3), "test_batches": int(len(yte)),
                             "top_drivers": imp.sort_values("importance", ascending=False).feature.head(3).tolist()}

fig, ax = plt.subplots(figsize=(8, 4.6))
ax.barh(imp.feature, imp.importance, color=SERIES[0], height=0.62)
ax.grid(axis="y", visible=False)
for yv, (v, f) in enumerate(zip(imp.importance, imp.feature)):
    ax.text(v + 0.002, yv, f"{v:.3f}", va="center", fontsize=8.5, color=INK2)
ax.set_xlabel("Drop in ROC AUC when the feature is shuffled")
ax.set_title(f"Deodorizer temperature is the #1 lever for in-spec product", pad=22)
subtitle(ax, f"Random Forest off-spec classifier: permutation importance (test AUC {auc:.2f})")
save(fig, "03_offspec_feature_importance.png")

# Chart: off-spec (high FFA) rate by deodorizer temperature band
band = (fb.dropna(subset=["rbdpo_ffa_pct"]).assign(t=lambda x: (x.deo_temp_c // 2) * 2)
        .groupby("t").agg(n=("batch_id", "size"), hi=("rbdpo_ffa_pct", lambda s: (s > 0.10).mean() * 100))
        .query("n >= 20").reset_index())
fig, ax = plt.subplots(figsize=(8, 4.4))
cols = [CRITICAL if v >= 5 else SERIES[0] for v in band.hi]
ax.bar([f"{int(t)}-{int(t)+2}" for t in band.t], band.hi, color=cols, width=0.62)
ax.grid(axis="x", visible=False)
for i, v in enumerate(band.hi):
    ax.text(i, v + 1.2, f"{v:.1f}%", ha="center", fontsize=9, color=INK2)
ax.set_xlabel("Deodorizer temperature band (°C)")
ax.set_ylabel("Batches with RBDPO FFA > 0.10 % (%)")
ax.set_title("Running the deodorizer below 258 °C is where FFA goes off-spec", pad=22)
subtitle(ax, "Share of batches failing the FFA spec, by deodorizer temperature (red = ≥ 5 % failing)")
save(fig, "04_deo_temp_vs_offspec.png")

# =============================================================================
# 3) CLUSTERING - crude oil quality segments
# =============================================================================
print("\n[3] K-Means: crude oil quality segments")
cl_cols = ["cpo_ffa_pct", "cpo_dobi"]
dk = fb.dropna(subset=cl_cols).copy()
Z = StandardScaler().fit_transform(dk[cl_cols])
scores = {}
for kk in range(2, 7):
    lab = KMeans(n_clusters=kk, n_init=10, random_state=3).fit_predict(Z)
    scores[kk] = silhouette_score(Z, lab, sample_size=2000, random_state=3)
print("  silhouette by k:", {k_: round(v, 3) for k_, v in scores.items()})
K = 3  # best-scoring k is 2-3; 3 gives an actionable good / standard / poor split
km = KMeans(n_clusters=K, n_init=10, random_state=3).fit(Z)
dk["cluster"] = km.labels_
prof = dk.groupby("cluster").agg(batches=("batch_id", "size"), cpo_ffa=("cpo_ffa_pct", "mean"),
                                 dobi=("cpo_dobi", "mean"), bleaching_earth=("bleaching_earth_pct", "mean"),
                                 yield_pct=("refining_yield_pct", "mean"), off_spec=("is_off_spec", "mean"))
order = prof.sort_values("yield_pct", ascending=False).index.tolist()
names = dict(zip(order, ["Premium crude", "Standard crude", "Challenging crude"]))
dk["segment"] = dk.cluster.map(names)
prof["segment"] = prof.index.map(names)
prof["off_spec"] *= 100
prof = prof.set_index("segment").loc[["Premium crude", "Standard crude", "Challenging crude"]].round(3)
mix = (dk.groupby(["supplier_name", "segment"]).size().unstack(fill_value=0)
       .pipe(lambda x: x.div(x.sum(axis=1), axis=0) * 100).round(1))
prof.to_csv(OUT / "crude_segments_profile.csv")
mix.to_csv(OUT / "crude_segments_by_supplier.csv")
print(prof.to_string())
summary["clustering"] = {"k": K, "silhouette": round(scores[K], 3),
                         "segments": prof.reset_index().to_dict(orient="records")}

fig, ax = plt.subplots(figsize=(8, 4.8))
seg_color = {"Premium crude": SERIES[0], "Standard crude": SERIES[2], "Challenging crude": SERIES[1]}
for seg in ["Premium crude", "Standard crude", "Challenging crude"]:
    s = dk[dk.segment == seg].sample(min(600, (dk.segment == seg).sum()), random_state=2)
    ax.scatter(s.cpo_ffa_pct, s.cpo_dobi, s=12, alpha=0.6, color=seg_color[seg],
               edgecolors=SURFACE, linewidths=0.4,
               label=f"{seg}  (yield {prof.loc[seg, 'yield_pct']:.1f} %, off-spec {prof.loc[seg, 'off_spec']:.1f} %)")
ax.set_xlabel("Crude palm oil FFA (%)")
ax.set_ylabel("DOBI (bleachability index)")
ax.set_title("Three natural crude-oil quality segments", pad=22)
subtitle(ax, "K-Means clusters on FFA and DOBI (standardised), sampled batches")
ax.legend(loc="upper right", fontsize=8.5)
save(fig, "05_crude_quality_segments.png")

# =============================================================================
# 4) ANOMALY DETECTION - abnormal energy use
# =============================================================================
print("\n[4] Isolation Forest: energy anomalies")
de = fb.dropna(subset=["steam_per_mt_cpo", "kwh_per_mt_cpo"]).copy()
de["anomaly"] = 0
for ln in "ABC":
    m = de.line_code == ln
    iso = IsolationForest(contamination=0.01, random_state=11).fit(de.loc[m, ["steam_per_mt_cpo", "kwh_per_mt_cpo"]])
    de.loc[m, "anomaly"] = (iso.predict(de.loc[m, ["steam_per_mt_cpo", "kwh_per_mt_cpo"]]) == -1).astype(int)
anom = de[de.anomaly == 1][["batch_id", "production_date", "line_code", "shift", "cpo_input_mt",
                             "deo_temp_c", "steam_per_mt_cpo", "kwh_per_mt_cpo", "dq_flags"]]
anom.sort_values("production_date").to_csv(OUT / "energy_anomalies.csv", index=False)
excess = (anom.steam_per_mt_cpo / anom.line_code.map(de.groupby("line_code").steam_per_mt_cpo.median()) - 1) * 100
print(f"  {len(anom)} anomalous batches; median deviation from line steam norm {excess.abs().median():.0f} %")
summary["anomalies"] = {"count": int(len(anom)), "median_abs_steam_deviation_pct": round(float(excess.abs().median()), 1)}

fig, ax = plt.subplots(figsize=(9, 4.4))
for ln in "ABC":
    s = de[(de.line_code == ln) & (de.anomaly == 0)]
    ax.scatter(s.production_date, s.steam_per_mt_cpo, s=6, color=LINE_COLOR[ln], alpha=0.35, label=f"Line {ln}")
a = de[de.anomaly == 1]
ax.scatter(a.production_date, a.steam_per_mt_cpo, s=46, facecolors="none", edgecolors=CRITICAL,
           linewidths=1.6, label="Flagged anomaly")
ax.set_ylabel("Steam (t per t CPO)")
ax.set_title("Isolation Forest flags 1 % of batches with abnormal energy use", pad=22)
subtitle(ax, "Steam intensity per batch; Line C sits on a higher band because it is the oldest line")
ax.legend(loc="upper left", ncol=4, fontsize=8.5, markerscale=1.5)
save(fig, "06_energy_anomalies.png")

# =============================================================================
# 5) Descriptive charts used in the README
# =============================================================================
mk = pd.read_csv(ROOT / "outputs" / "sql_results" / "q02_monthly_trend_mom.csv")
ml = (fb.assign(ym=fb.production_date.dt.to_period("M").astype(str))
        .groupby(["ym", "line_code"]).apply(lambda g: g.rbdpo_output_mt.sum() / g.cpo_input_mt.sum() * 100,
                                            include_groups=False)
        .unstack())
fig, ax = plt.subplots(figsize=(9, 4.4))
for ln in "ABC":
    ax.plot(ml.index, ml[ln], color=LINE_COLOR[ln], label=f"Line {ln}")
    ax.text(len(ml) - 1 + 0.25, ml[ln].iloc[-1], f"Line {ln}", va="center", fontsize=9, color=INK2)
ax.axvspan("2024-09", "2024-11", color=GRID, alpha=0.6, linewidth=0)
ax.text("2024-10", ax.get_ylim()[1], "Peak crop", ha="center", va="top", fontsize=8.5, color=MUTED)
ax.set_xticks(range(0, len(ml), 3), ml.index[::3])
ax.set_ylabel("Refining yield (%)")
ax.set_title("Yield dips in the peak crop season; Line C trails A and B", pad=22)
subtitle(ax, "Monthly refining yield by line (RBDPO out / CPO in)")
ax.legend(loc="lower left", ncol=3)
ax.set_xlim(-0.5, len(ml) + 1.2)
save(fig, "07_monthly_yield_by_line.png")

pareto = pd.read_csv(ROOT / "outputs" / "sql_results" / "q08_downtime_pareto.csv").sort_values("hours")
fig, ax = plt.subplots(figsize=(8, 4.4))
ax.barh(pareto.category, pareto.hours, color=SERIES[0], height=0.62)
ax.grid(axis="y", visible=False)
for yv, (h, c) in enumerate(zip(pareto.hours, pareto.cumulative_pct)):
    ax.text(h + 2, yv, f"{h:.0f} h  ·  cum. {c:.0f}%", va="center", fontsize=8.5, color=INK2)
ax.set_xlabel("Downtime (hours)")
ax.set_xlim(0, pareto.hours.max() * 1.35)
ax.set_title("Vacuum system and mechanical faults cause 45 % of lost time", pad=22)
subtitle(ax, "Downtime Pareto by cause, Jan 2024 - Jun 2025")
save(fig, "08_downtime_pareto.png")

with open(OUT / "model_summary.json", "w") as fh:
    json.dump(summary, fh, indent=2, default=float)
print("\nSaved outputs/data_mining/model_summary.json")
