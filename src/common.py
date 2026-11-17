"""Shared loading and cleaning, used by every script (same steps as the Excel 'Cleaning log')."""
import glob, os
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_PATIENTS = 1000
MIN_RATE = 150   # items per 1,000 patients per year; below this the list is atypical (digital-first, student, specialist)


def load_clean(exclude_atypical=True, raw=None):
    """raw: folder with abx_12m_practice_month.csv and lists/ (default data/raw = Sep 2025-Aug 2026;
    data/raw/y2425 holds the earlier year Sep 2024-Aug 2025)."""
    raw = raw or f"{ROOT}/data/raw"
    rx = pd.read_csv(f"{raw}/abx_12m_practice_month.csv", dtype={"pc": str})
    lists = {os.path.basename(f)[5:12]: pd.read_csv(f, dtype=str).set_index("CODE")["NUMBER_OF_PATIENTS"].astype(int)
             for f in sorted(glob.glob(f"{raw}/lists/list_*.csv"))}
    lm = sorted(lists)
    near = lambda m: min(lm, key=lambda x: abs((pd.Period(x, "M") - pd.Period(m, "M")).n))
    rx["list_month"] = rx["ym"].map(near)
    rx["patients"] = [lists[l].get(pc, np.nan) for l, pc in zip(rx["list_month"], rx["pc"])]
    steps = [("Practice-month rows from NHSBSA API (BNF 5.1 antibacterials, UNIDENTIFIED removed)", len(rx))]
    rx = rx[rx["patients"].notna()]; steps.append(("Matched to a GP practice patient list", len(rx)))
    rx = rx[~rx["pc"].str.startswith("Y")]; steps.append(("Excluding Y-code services (care homes, walk-ins etc.)", len(rx)))
    rx = rx[rx["patients"] >= MIN_PATIENTS]; steps.append(("Practices with at least 1,000 patients", len(rx)))
    rx["cls"] = rx[["access_items", "watch_items", "reserve_items", "other_items"]].sum(axis=1)
    rx = rx[rx["cls"] > 0]   # drops practice-months with no classified items (0 rows in all three years, so not in the cleaning log)
    nm = rx.groupby("pc")["ym"].nunique(); rx = rx[rx["pc"].isin(nm[nm == 12].index)]
    steps.append(("Practices present in all 12 months", len(rx)))
    g = rx.groupby("pc").agg(cls=("cls", "sum"), pat=("patients", "mean"))
    rate = g.cls / g.pat * 1000
    atyp = rate[rate < MIN_RATE].index
    if exclude_atypical:
        rx = rx[~rx["pc"].isin(atyp)]
        steps.append((f"Excluding atypical lists: under {MIN_RATE} antibiotic items per 1,000 patients a year (final set)", len(rx)))
    rx = rx.sort_values(["pc", "ym"]).reset_index(drop=True)
    return rx, steps, set(atyp)
