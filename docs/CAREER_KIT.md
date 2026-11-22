# Career Kit: Using This Project in Job Applications

## 1. Personalise before you publish (checklist)

- [ ] Replace `farhananasaruddin` in `README.md` and `python/dashboard_template.html`, then re-run `python run_pipeline.py --keep-raw`.
- [ ] Replace `Norfarhana Mohd Nasaruddin` in `README.md` and `LICENSE`, and add your LinkedIn URL and email.
- [ ] Build the Power BI report with `powerbi/BUILD_GUIDE.md`. Commit the `.pbix`, the PDF export and the page screenshots.
- [ ] Run every script once yourself and read every SQL query. In an interview you must be able to explain any line.
- [ ] Change at least one thing so the work is yours. Ideas: add a query, add a DAX measure, change the dashboard design, or
      try another model (for example gradient boosting or logistic regression) and compare it with the Random Forest.
- [ ] Keep the "synthetic data" note visible. Being upfront about it builds trust. Hiding it destroys trust.

## 2. Publish on GitHub (about 10 minutes)

```bash
# 1. Create an empty public repo on github.com named palm-oil-refinery-analytics (no README)
# 2. In the project folder:
git init
git add .
git commit -m "Palm oil refinery analytics: ELT pipeline, SQL, data mining, Excel, Power BI"
git branch -M main
git remote add origin https://github.com/farhananasaruddin/palm-oil-refinery-analytics.git
git push -u origin main
```

**Turn on the live dashboard (GitHub Pages):**
Repo > **Settings > Pages >** Source: *Deploy from a branch* > Branch `main`, folder `/ (root)` > Save.
After about a minute it is live at
`https://farhananasaruddin.github.io/palm-oil-refinery-analytics/dashboard/`.

**Make it visible:**
- Pin the repo on your GitHub profile.
- Add the topics `data-analytics`, `power-bi`, `sql`, `excel`, `python`, `chemical-engineering` and `palm-oil` (gear icon next to *About*).
- Create a profile README (a repo named after your username) with a short intro and a link to this project.

## 3. CV bullet points (choose 2 or 3)

**Project: Palm Oil Refinery Operations Analytics** | Python · SQL · Excel · Power BI | github.com/farhananasaruddin/...

- Built an end-to-end ELT pipeline. It extracts 6 CSV, JSON and Excel sources (4,800 batch records, 320 maintenance events)
  into a SQL star schema and applies 23 documented data-quality rules, including mass-balance imputation of missing tonnages.
- Wrote 15 analytical SQL queries using CTEs, window functions and conditional aggregation. They identified a RM 20 m
  supplier yield gap and traced 77 % of off-spec product to one refining line.
- Applied regression (R² 0.93), Random Forest classification (ROC AUC 0.97), K-Means clustering and Isolation Forest to
  quantify yield drivers, predict off-spec batches and flag energy anomalies.
- Delivered a 5-page Power BI dashboard (40+ DAX measures, star-schema model) and a formula-driven Excel workbook
  (SUMIFS, INDEX/MATCH, scenario inputs). Published an interactive web version on GitHub Pages.

## 4. LinkedIn post (draft)

> As a Chemical Engineering graduate moving into data analytics, I wanted a portfolio project that uses both skill sets. 🛢️📊
>
> I built an end-to-end analytics project for a (simulated) palm oil refinery:
> 🔹 Extracted messy plant data (shift logs, lab results, CMMS events) with Python
> 🔹 Cleaned and modelled it in SQL, with 23 data-quality rules and a mass-balance check to fill missing tonnages
> 🔹 Mined it with regression, Random Forest and clustering
> 🔹 Built the dashboard in Power BI and Excel
>
> Key insight: every +1 % FFA in crude palm oil costs about 1.06 points of refining yield, and a 2 °C colder deodorizer on one line caused 77 % of off-spec batches.
>
> Live dashboard: [link] · Code: [link]
> Feedback welcome!
> #DataAnalytics #PowerBI #SQL #ChemicalEngineering #PalmOil

## 5. Interview questions to prepare

| Question | Answer outline |
|---|---|
| *Why synthetic data?* | Real refinery data is confidential. I designed the generator from process knowledge (FFA → PFAD, DOBI → bleaching earth, deodorizer temperature → product FFA), added realistic data problems, and then checked whether my analysis could recover the relationships. It did, for example the −1.06 yield coefficient. |
| *Walk me through your cleaning.* | I followed the `dq_log` steps: de-duplication, three date formats, alias mapping for supplier typos, unit fixes (fraction vs %, MWh), sensor glitches (decimal point lost), and mass-balance imputation. I kept everything auditable with `dq_flags`. |
| *Why ELT, cleaning in SQL rather than Python?* | Staging keeps the raw data untouched. SQL rules are transparent and easy to review, and they are what most companies run in their warehouse. |
| *Why weighted averages?* | Yield is a ratio. Averaging batch yields gives small batches too much weight, so I use SUM(RBDPO) / SUM(CPO). The same applies in the DAX `DIVIDE` measures. |
| *How did you pick k for K-Means?* | Silhouette score was highest at k = 2. I chose k = 3 because it gives an actionable premium / standard / challenging split, and I said so in the write-up. |
| *Is the Random Forest useful with 50 % precision?* | As an early warning, yes. It catches 87 % of off-spec batches. A false alarm costs one extra lab check, while a missed batch costs reprocessing. |
| *What would you do with real data?* | Validate with a plant trial on the Line C set-point, add cost data for a true margin, and automate the refresh (scheduled Python job and Power BI Service refresh). |
| *Explain one DAX measure.* | `Downtime Cumulative %` uses ALLSELECTED plus a FILTER that keeps the categories with hours ≥ the current one. That gives the running total for the Pareto chart. |
| *How does your ChemE background help?* | Mass balances for imputation, knowing that FFA becomes PFAD, and reading deodorizer temperature and vacuum as a pair. Domain knowledge tells you which correlations to trust. |
