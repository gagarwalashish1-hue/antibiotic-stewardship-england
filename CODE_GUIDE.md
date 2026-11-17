# How the code works

A plain-English guide to every script in this project: what it does, what goes in, and what comes out. The scripts run in this order:

```
get_data.py → extended_analysis.py → second_year_casemix.py → build_workbook.py → chart_polish.py
→ (open and save the workbook once in Excel) → make_charts.py → make_tableau.py → tests/verify.py
```

---

## 1. Getting the data

### `src/get_data.py`
**Job:** download everything the project needs from NHS sources.

- One month of the full NHS prescribing file is about 7.8 GB (18.6 million rows). Rather than download all of it, the script sends a **SQL query to the NHSBSA Open Data Portal API**. The NHS server does the filtering and adding up, and returns only about 8,000 rows a month: one row per practice.
- It repeats the query for each of the 12 months, and for the two earlier years.
- It also downloads practice list sizes (patients registered at each practice) and the QOF disease registers.
- **Out:** `data/raw/abx_12m_practice_month.csv`, `data/raw/lists/`, `data/raw/qof/`, and the two SQL files in `sql/`.

### `sql/nhsbsa_api_query.sql`: the main query
What each part does:

| Part | Meaning |
|---|---|
| `SELECT YEAR_MONTH, PRACTICE_CODE …` | One row per practice per month |
| `sum(ITEMS) all_items` | Total antibiotic prescriptions |
| `sum(CASE WHEN … IN ('0501012G0', …) THEN ITEMS ELSE 0 END) access_items` | Adds up items only for drugs on the **Access** list. The same pattern gives Watch, Reserve and Other |
| `lyme_items` | Lymecycline (mostly for acne) counted separately, so it can be left out in a sensitivity check |
| `WHERE BNF_PRESENTATION_CODE LIKE '0501%'` | Keeps only antibacterials (BNF chapter 5.1) |
| `AND UNIDENTIFIED <> 'Y'` | Drops prescriptions not linked to a practice |
| `GROUP BY YEAR_MONTH, PRACTICE_CODE` | Totals everything per practice per month |

The drug codes are not typed by hand. `get_data.py` writes them from `data/aware_mapping.csv` (the UKHSA AWaRe list), so the query and the mapping can never disagree.

### `sql/nhsbsa_adq_and_watch_drugs.sql`: the second query
Same idea, but it adds up **ADQ** (a dose-based measure) instead of items, and counts items for each Watch drug separately. It is used for the "by dose" check and the Watch-drugs chart.

---

## 2. Cleaning

### `src/common.py`
**Job:** one shared cleaning function (`load_clean`) that every other script uses, so every number starts from the same clean data. It follows the same steps as the Excel `Cleaning log` sheet:

1. Match each practice-month to a patient list size (using the nearest month's list).
2. Remove **Y-code** services (care homes, walk-in centres and similar).
3. Remove practices with **fewer than 1,000 patients**.
4. Remove practices missing any month.
5. Remove **atypical lists**: fewer than 150 items per 1,000 patients a year (student health centres and digital-first services).

---

## 3. The analysis

### `src/extended_analysis.py`
**Job:** calculate every headline number in Python, independently of Excel. The main steps:

- **Watch+Reserve share** for each practice = (Watch + Reserve) ÷ all classified items × 100.
- **Reliability:** compares each practice's share in Sep–Feb with Mar–Aug. A high correlation (r = 0.86) means the share is a stable feature of the practice, not noise.
- **Funnel plot (Spiegelhalter 2005):** for each practice, z = (practice share − England share) ÷ expected spread. The spread allows for practice size, plus an extra term (τ²) for normal differences between practices. Practices above z = 3.09 (the 99.8% limit) are unusual.
- **Shortlist:** above the 99.8% limit, **and** in the top fifth for 9 or more of the 12 months, **and** still so without lymecycline.
- **Regressions:** do age, deprivation (IMD 2025) or practice size explain the share?
- **Out-of-sample test:** flag practices using Sep–Feb only, then check whether they are still high in Mar–Aug.
- **Out:** `outputs/tables/results.json` (every headline number) and the practice tables.

### `src/second_year_casemix.py`
**Job:** the two tests that make the finding believable.

1. **Earlier years.** Runs the same screen on 2023-24 and 2024-25 on their own, then follows the flagged practices into 2025-26. This produces the 61% "still above the limit a year later" result and the **36 practices flagged in all three years**.
2. **Patient need.** A binomial model predicts each practice's expected share from its QOF disease registers (COPD, asthma, diabetes, CKD, cancer, dementia, heart failure), age mix, deprivation and size. The funnel is then redrawn around each practice's **own expected share**. 101 of the 106 shortlisted practices are still above the limit.
- **Out:** `outputs/tables/results_y2_casemix.json`.

---

## 4. Building the outputs

| Script | What it builds |
|---|---|
| `src/build_workbook.py` | The Excel workbook. Every result in it is a **live Excel formula**, not a pasted number, so anyone can trace any figure back to the data |
| `src/chart_polish.py` | Makes the grey dots on the Excel funnel chart see-through (the Excel library cannot do this directly) |
| `src/make_charts.py` | The 12 figures in the report (`outputs/charts/`) and the CSV files for Tableau |
| `src/make_tableau.py` | The Tableau Public workbook (`tableau/*.twbx`). Practices are shown by an ID number, not by name |

---

## 5. Checking

### `tests/verify.py`
**Job:** proves Excel and Python agree. It opens the workbook, reads 107 headline numbers, and compares each with the Python result in `results.json`. All 107 match.

The two methods were built separately, so if either one had a mistake, they would disagree.
