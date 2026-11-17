"""
second_year_casemix.py - the two tests that go beyond the single-year screen.

1. Two earlier years (Sep 2023 - Aug 2024 and Sep 2024 - Aug 2025). The same screen is run on that year on its own, then the
   practices it flags are followed into Sep 2025 - Aug 2026, a whole year later.
2. Recorded patient need. QOF 2025-26 disease registers (COPD, asthma, diabetes and others) are added to
   a binomial model of each practice's Watch+Reserve share. The funnel plot is then redrawn around each
   practice's case-mix-expected share instead of the England share, and the shortlist is re-tested.

Writes outputs/tables/results_y2_casemix.json and outputs/tables/practices_y2_casemix.csv.
Run after src/extended_analysis.py and before src/make_charts.py:   python src/second_year_casemix.py
"""
import json, os, sys
import numpy as np, pandas as pd
from scipy import stats
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_clean, ROOT

OUT = f"{ROOT}/outputs/tables"
R = {}
Z = 3.09   # 99.8% limit


def flags(d, col):
    cut = d.groupby("ym")[col].quantile(0.8)
    return (d[col] >= d.ym.map(cut)).astype(int)


def od_z(p_obs, p_exp, n):
    """Spiegelhalter (2005) over-dispersed z around an expected share (England, or a case-mix model).
    Winsorised at the 10th/90th percentiles, additive random effect tau^2 (DerSimonian-Laird)."""
    se = np.sqrt(p_exp * (1 - p_exp) / n)
    z = (p_obs - p_exp) / se
    zw = z.clip(z.quantile(0.1), z.quantile(0.9)); phi = float((zw ** 2).mean()); w = 1 / se ** 2; k = len(z)
    t2 = max(0.0, (k * phi - (k - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
    return (p_obs - p_exp) / np.sqrt(se ** 2 + t2), float(np.sqrt(t2))


def screen(rx):
    """The project's three screening criteria for one year of practice-month data."""
    rx = rx.copy()
    rx["wr"] = rx.watch_items + rx.reserve_items
    rx["share"] = rx.wr / rx.cls
    rx["top"] = flags(rx, "share")
    rx["wr_nl"] = rx.wr - rx.lyme_items; rx["cls_nl"] = rx.cls - rx.lyme_items
    rx["top_nl"] = flags(rx.assign(s=rx.wr_nl / rx.cls_nl), "s")
    P = rx.groupby("pc").agg(icb=("icb", "last"), cls=("cls", "sum"), wr=("wr", "sum"), acc=("access_items", "sum"),
                             pat=("patients", "mean"), months_top=("top", "sum"), months_top_nl=("top_nl", "sum"))
    P["share"] = P.wr / P.cls
    p0 = P.wr.sum() / P.cls.sum()
    P["z_od"], tau = od_z(P.share, p0, P.cls)
    P["short"] = (P.z_od > Z) & (P.months_top >= 9) & (P.months_top_nl >= 9)
    return P, p0, tau


# ---------------- 1. second year ----------------
rxA, stepsA, _ = load_clean(True, f"{ROOT}/data/raw/y2425")    # Sep 2024 - Aug 2025
rxB, _, _ = load_clean(True)                                   # Sep 2025 - Aug 2026 (main year)
A, p0A, tauA = screen(rxA); B, p0B, tauB = screen(rxB)
both = A.index.intersection(B.index)
R.update(y1_practices=len(A), y1_share=p0A * 100, y1_tau=tauA, y2_practices=len(B), practices_both_years=len(both),
         y1_above_998=int((A.z_od > Z).sum()), y1_shortlist=int(A.short.sum()), y1_below_998=int((A.z_od < -Z).sum()),
         y1_rows_final=stepsA[-1][1])
a, b = A.loc[both], B.loc[both]
R["r_share_year_to_year"] = float(np.corrcoef(a.share, b.share)[0, 1])
R["spearman_share_year_to_year"] = float(stats.spearmanr(a.share, b.share)[0])

# out of sample, a full year later: flag on 2024-25 only, look at 2025-26
fA = a.short
R.update(y1_short_in_both=int(fA.sum()),
         y1short_above998_next_year=float((b.z_od[fA] > Z).mean()),
         y1short_shortlisted_next_year=float(b.short[fA].mean()),
         y1short_above95_next_year=float((b.z_od[fA] > 1.96).mean()),
         y1short_above_england_next_year=float((b.share[fA] > p0B).mean()),
         unflagged_above998_next_year=float((b.z_od[~fA] > Z).mean()),
         y1short_mean_share_y1=float(a.share[fA].mean() * 100), y1short_mean_share_y2=float(b.share[fA].mean() * 100))
# the other direction: how many of this year's shortlist were already flagged last year?
fB = b.short
R.update(y2_short_in_both=int(fB.sum()), y2short_above998_last_year=float((a.z_od[fB] > Z).mean()),
         y2short_shortlisted_last_year=float(a.short[fB].mean()), y2_short_both_years=int((fA & fB).sum()))
# positive deviants: low in both years?
lowA, lowB = a.z_od < -Z, b.z_od < -Z
R.update(y2_low_in_both=int(lowB.sum()), y2low_below998_last_year=float(lowA[lowB].mean()),
         y2low_below_england_last_year=float((a.share[lowB] < p0A).mean()), low_both_years=int((lowA & lowB).sum()))
# relative risk: chance of being shortlisted in 2025-26 if shortlisted in 2024-25 vs if not
R["rr_shortlist_next_year"] = float(b.short[fA].mean() / b.short[~fA].mean())

# ---------------- 1b. a third year (Sep 2023 - Aug 2024): flagged three years running? ----------------
# 2022-23 is skipped on purpose: the December 2022 Group A strep outbreak sharply raised Watch prescribing
# (clarithromycin, azithromycin), so that year is not a fair baseline (Cunningham et al., 2024).
rx0, steps0, _ = load_clean(True, f"{ROOT}/data/raw/y2324")
Y0, p00, tau0 = screen(rx0)
all3 = Y0.index.intersection(A.index).intersection(B.index)
c0, c1, c2 = Y0.loc[all3], A.loc[all3], B.loc[all3]
f0 = c0.short
n_years = c0.short.astype(int) + c1.short.astype(int) + c2.short.astype(int)
R.update(y0_practices=len(Y0), y0_share=p00 * 100, y0_shortlist=int(Y0.short.sum()), y0_above_998=int((Y0.z_od > Z).sum()),
         practices_all_three=len(all3), y0_short_in_all3=int(f0.sum()),
         r_share_two_years_apart=float(np.corrcoef(Y0.loc[Y0.index.intersection(B.index)].share, B.loc[Y0.index.intersection(B.index)].share)[0, 1]),
         r_share_y0_y1=float(np.corrcoef(c0.share, c1.share)[0, 1]),
         y0short_above998_two_years_later=float((c2.z_od[f0] > Z).mean()),
         y0unflagged_above998_two_years_later=float((c2.z_od[~f0] > Z).mean()),
         y0short_shortlisted_two_years_later=float(c2.short[f0].mean()),
         y0unflagged_shortlisted_two_years_later=float(c2.short[~f0].mean()),
         shortlisted_all_three_years=int((n_years == 3).sum()), shortlisted_two_plus_years=int((n_years >= 2).sum()),
         y2short_shortlisted_in_y0=int((c2.short & c0.short).sum()))

# ---------------- 2. recorded patient need (QOF 2025-26) ----------------
q = pd.read_csv(f"{ROOT}/data/raw/qof/2526/PREVALENCE_2526.csv", dtype={"PRACTICE_CODE": str})
q = q[q.GROUP_CODE.isin(["COPD", "AST", "DM", "CKD", "CAN", "DEM", "HF"])]
q = q[~q.REGISTER_NAME.str.contains("LVSD", na=False)]   # HF has two registers; the LVSD one is a subset, so keep only the full register
q = q.groupby(["PRACTICE_CODE", "GROUP_CODE"]).agg(reg=("REGISTER_SIZE", "sum"), den=("PRACTICE_LIST_SIZE", "max"))
q["prev"] = q.reg / q.den * 100           # each register over its own age-specific list (QOF method)
Q = q.prev.unstack().rename(columns=str.lower)
Pm = pd.read_csv(f"{OUT}/practices_12m_v2.csv", dtype={"pc": str}).set_index("pc")   # written by extended_analysis.py
M = B.join(Pm[["imd", "pct65", "pct1524", "shortlisted"]]).join(Q, how="left")
M["ls"] = np.log10(M.pat)
R["qof_matched"] = int(M[Q.columns].notna().all(axis=1).sum())
M = M.dropna(subset=list(Q.columns) + ["imd", "pct65", "pct1524"])
R["casemix_n"] = len(M)
M["y"] = M.share; M["fail"] = M.cls - M.wr
prev_cols = list(Q.columns)
base = "pct65 + pct1524 + imd + ls"
clin = base + " + " + " + ".join(prev_cols)


def glm(f):
    return smf.glm(f"wr + fail ~ {f}", M, family=sm.families.Binomial()).fit(scale="X2")   # quasi-binomial


def pseudo_r2(fit):
    """share of the between-practice variance in share explained by the fitted values (weighted)."""
    w = M.cls; yb = np.average(M.y, weights=w)
    return float(1 - np.average((M.y - fit.fittedvalues) ** 2, weights=w) / np.average((M.y - yb) ** 2, weights=w))


g0, g1 = glm(base), glm(clin)
g2 = glm(clin + " + C(icb)")
R.update(casemix_r2_age_imd_size=pseudo_r2(g0), casemix_r2_plus_registers=pseudo_r2(g1),
         casemix_r2_plus_registers_icb=pseudo_r2(g2))
# the same comparison as ordinary least squares on the share in %, matching Table 2 of the report
M["s"] = M.share * 100; M["icb_share"] = Pm["icb_share"].reindex(M.index) if "icb_share" in Pm else np.nan
ols_r2 = lambda f: float(smf.ols(f"s ~ {f}", M).fit().rsquared)
R.update(ols_r2_age_imd_size=ols_r2("imd + pct65 + ls"), ols_r2_patient_all=ols_r2(clin),
         ols_r2_patient_all_icb=ols_r2(clin + " + icb_share"))
R["casemix_coef"] = {c: [float(g1.params[c]), float(g1.pvalues[c])] for c in prev_cols + ["pct65", "pct1524", "imd"]}
# correlation of each register with share, for the report table
R["r_prev_share"] = {c: float(np.corrcoef(M[c], M.share)[0, 1]) for c in prev_cols}
# case-mix-adjusted funnel: expected share from the clinical model, no ICB term (area is not patient need)
M["exp_cm"] = g1.fittedvalues
M["z_cm"], tau_cm = od_z(M.share, M.exp_cm, M.cls)
S = M.short
R["r_z_before_after_casemix"] = float(np.corrcoef(M.z_od, M.z_cm)[0, 1])
R.update(casemix_tau=tau_cm, shortlist_in_casemix=int(S.sum()),
         shortlist_still_above998_casemix=int((M.z_cm[S] > Z).sum()),
         shortlist_still_above95_casemix=int((M.z_cm[S] > 1.96).sum()),
         casemix_above998_all=int((M.z_cm > Z).sum()), casemix_below998_all=int((M.z_cm < -Z).sum()))
# how the shortlist and the low practices differ on recorded need
grp = np.where(M.short, "shortlist", np.where(M.z_od < -Z, "low", "other"))
R["prev_median_by_group"] = M.groupby(grp)[prev_cols + ["pct65", "pct1524", "imd"]].median().round(2).to_dict()
L = M[M.z_od < -Z]
R.update(low_in_casemix=len(L), low_still_below998_casemix=int((L.z_cm < -Z).sum()))

M[["icb", "share", "z_od", "short", "exp_cm", "z_cm"] + prev_cols].to_csv(f"{OUT}/practices_y2_casemix.csv")
Y0[["wr", "cls", "share", "z_od", "short", "months_top", "months_top_nl"]].rename(columns=lambda c: c + "_2324").join(
    A[["wr", "cls", "share", "z_od", "short", "months_top", "months_top_nl"]].rename(columns=lambda c: c + "_2425"), how="outer").join(
    B[["share", "z_od", "short", "months_top"]].rename(columns=lambda c: c + "_2526"), how="outer").to_csv(f"{OUT}/practices_two_years.csv")
json.dump(R, open(f"{OUT}/results_y2_casemix.json", "w"), indent=1, default=float)
for k, v in R.items():
    print(k, v)
