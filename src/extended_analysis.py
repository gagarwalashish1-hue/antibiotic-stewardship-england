"""
extended_analysis.py - every result in the revised project, computed independently of Excel.
The Excel workbook recomputes the same numbers with formulas; this script is the cross-check.

Run from the repo root:  python src/extended_analysis.py
Needs: pandas, numpy, scipy, openpyxl
"""
import json, os, sys, zipfile
import numpy as np, pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_clean, ROOT

OUT = f"{ROOT}/outputs/tables"; os.makedirs(OUT, exist_ok=True)
R = {}   # every headline number lands here -> outputs/tables/results.json

rx, steps, atyp = load_clean(True)
rx_all, _, _ = load_clean(False)
R["n_practices"] = rx.pc.nunique(); R["n_practices_before_atypical"] = rx_all.pc.nunique(); R["n_atypical"] = len(atyp)
months = sorted(rx.ym.unique()); H1 = months[:6]
rx["wr"] = rx.watch_items + rx.reserve_items
rx["share"] = rx.wr / rx.cls * 100


def practice_table(d):
    g = d.groupby("pc").agg(pn=("pn", "last"), icb=("icb", "last"), cls=("cls", "sum"), wr=("wr", "sum"),
                            acc=("access_items", "sum"), oth=("other_items", "sum"), lyme=("lyme_items", "sum"),
                            pat=("patients", "mean"))
    g["rate"] = g.cls / g.pat * 1000
    g["share"] = g.wr / g.cls * 100
    return g


# ---------------- monthly top fifth and persistence ----------------
def flags(d, col):
    cut = d.groupby("ym")[col].quantile(0.8)            # same as Excel PERCENTILE.INC
    return (d[col] >= d.ym.map(cut)).astype(int), cut


rx["top"], cut = flags(rx, "share")
P = practice_table(rx)
P["months_top"] = rx.groupby("pc").top.sum()
R["england_share"] = rx.wr.sum() / rx.cls.sum() * 100
R["england_share_awr"] = rx.wr.sum() / (rx.cls.sum() - rx.other_items.sum()) * 100   # OpenPrescribing-style denominator
R["england_rate"] = rx.cls.sum() / P.pat.sum() * 1000
R["persistent_9plus"] = int((P.months_top >= 9).sum()); R["persistent_12"] = int((P.months_top == 12).sum())
R["binom_expected_9plus"] = float((1 - stats.binom.cdf(8, 12, 0.2)) * len(P))

# month-to-month: does the flag repeat?
rx["top_next"] = rx.groupby("pc").top.shift(-1)
x = rx.dropna(subset=["top_next"])
R["p_top_next_given_top"] = float(x[x.top == 1].top_next.mean())
R["p_same_status_next"] = float((x.top == x.top_next).mean())
R["p_same_status_if_independent"] = 0.2 ** 2 + 0.8 ** 2

# ---------------- reliability: split-half and noise share ----------------
h = rx.assign(half=np.where(rx.ym.isin(H1), "h1", "h2")).groupby(["pc", "half"])[["wr", "cls"]].sum().unstack()
s1 = h["wr"]["h1"] / h["cls"]["h1"] * 100; s2 = h["wr"]["h2"] / h["cls"]["h2"] * 100
P["share_h1"], P["share_h2"] = s1, s2
r_sh, p_sh = stats.pearsonr(s1, s2)
R["split_half_r"] = float(r_sh)
R["split_half_r_ci"] = [float(np.tanh(np.arctanh(r_sh) + k * 1.96 / np.sqrt(len(s1) - 3))) for k in (-1, 1)]
R["spearman_brown_12m"] = float(2 * r_sh / (1 + r_sh))
# noise share = average binomial sampling variance / total variance between practices
pm = rx.share / 100
noise_m = (pm * (1 - pm) / rx.cls).groupby(rx.ym).mean()
tot_m = pm.groupby(rx.ym).var()
R["noise_share_1month"] = float((noise_m / tot_m).mean())
p12 = P.share / 100
R["noise_share_12month"] = float((p12 * (1 - p12) / P.cls).mean() / p12.var())

# ---------------- July-only vs 12-month top 15 by gap ----------------
icb_tab = P.groupby("icb").agg(cls=("cls", "sum"), wr=("wr", "sum"), acc=("acc", "sum"), oth=("oth", "sum"),
                               n=("pn", "size"), pat=("pat", "sum"))
icb_tab["share"] = icb_tab.wr / icb_tab.cls * 100
icb_tab["share_awr"] = icb_tab.wr / (icb_tab.cls - icb_tab.oth) * 100
P["icb_share"] = P.icb.map(icb_tab.share)
P["gap"] = P.wr - P.cls * P.icb_share / 100
jul = rx[rx.ym == "2026-07"].set_index("pc")
P["gap_jul"] = jul.wr - jul.cls * P.icb_share / 100
top15 = P.gap.nlargest(15).index; top15_jul = P.gap_jul.nlargest(15).index
R["july_top15_in_12m_top15"] = len(set(top15) & set(top15_jul))
R["icb_min"] = [icb_tab.share.idxmin(), float(icb_tab.share.min())]
R["icb_max"] = [icb_tab.share.idxmax(), float(icb_tab.share.max())]

# ---------------- overdispersed funnel (Spiegelhalter 2005) ----------------
p0 = R["england_share"] / 100
P["se0"] = np.sqrt(p0 * (1 - p0) / P.cls)
P["z"] = (P.share / 100 - p0) / P.se0
lo, hi = P.z.quantile([0.1, 0.9])
zw = P.z.clip(lo, hi)
n = len(P); phi = float((zw ** 2).mean())
w = 1 / P.se0 ** 2
tau2 = max(0.0, (n * phi - (n - 1)) / (w.sum() - (w ** 2).sum() / w.sum()))
P["z_od"] = (P.share / 100 - p0) / np.sqrt(P.se0 ** 2 + tau2)
R.update(funnel_phi=phi, funnel_tau=float(np.sqrt(tau2)),
         funnel_plain_above_998=int((P.z > 3.09).sum()),
         funnel_od_above_998=int((P.z_od > 3.09).sum()), funnel_od_above_95=int((P.z_od > 1.96).sum()),
         funnel_od_below_998=int((P.z_od < -3.09).sum()))
flag_od = P.index[P.z_od > 3.09]
R["funnel_od_flagged_also_persistent"] = int((P.loc[flag_od, "months_top"] >= 9).sum())
P["rank_gap"] = P.gap.rank(ascending=False, method="min")
P["rank_z"] = P.z_od.rank(ascending=False, method="min")
R["top15_gap_vs_top15_z_overlap"] = len(set(top15) & set(P.z_od.nlargest(15).index))
R["ICB_share_of_variance"] = None  # filled below by regression

# ---------------- lymecycline sensitivity ----------------
rx["wr_nl"] = rx.wr - rx.lyme_items; rx["cls_nl"] = rx.cls - rx.lyme_items
rx["share_nl"] = rx.wr_nl / rx.cls_nl * 100
rx["top_nl"], _ = flags(rx, "share_nl")
P["share_nl"] = rx.groupby("pc").wr_nl.sum() / rx.groupby("pc").cls_nl.sum() * 100
P["months_top_nl"] = rx.groupby("pc").top_nl.sum()
pers = set(P.index[P.months_top >= 9]); pers_nl = set(P.index[P.months_top_nl >= 9])
R.update(persistent_9plus_no_lyme=len(pers_nl), persistent_overlap_with_without_lyme=len(pers & pers_nl),
         persistent_changed_pct=float(1 - len(pers & pers_nl) / len(pers)) * 100,
         england_share_no_lyme=float(rx.wr_nl.sum() / rx.cls_nl.sum() * 100),
         r_share_vs_share_no_lyme=float(np.corrcoef(P.share, P.share_nl)[0, 1]))
P["lyme_pct"] = P.lyme / P.cls * 100

# ---------------- dose-based (ADQ) sensitivity and Watch drug table ----------------
adq = pd.read_csv(f"{ROOT}/data/raw/abx_12m_adq_watchdrug.csv", dtype={"pc": str})
adq["ym"] = adq.ym.astype(str).str[:4] + "-" + adq.ym.astype(str).str[4:]
adq = adq.merge(rx[["ym", "pc"]], on=["ym", "pc"])                      # same practice-months as the analysis
assert len(adq) == len(rx)
A = adq.groupby("pc")[["adq_A", "adq_W", "adq_R", "adq_O", "adq_lyme"]].sum()
P["adq_share"] = (A.adq_W + A.adq_R) / A[["adq_A", "adq_W", "adq_R", "adq_O"]].sum(axis=1) * 100
R["england_adq_share"] = float((A.adq_W.sum() + A.adq_R.sum()) / A[["adq_A", "adq_W", "adq_R", "adq_O"]].sum().sum() * 100)
R["england_adq_access"] = float(A.adq_A.sum() / A[["adq_A", "adq_W", "adq_R", "adq_O"]].sum().sum() * 100)
R["england_items_access"] = float(rx.access_items.sum() / rx.cls.sum() * 100)
R["r_item_share_vs_adq_share"] = float(np.corrcoef(P.share, P.adq_share)[0, 1])
mapping = pd.read_csv(f"{ROOT}/data/aware_mapping.csv")
wcols = [c for c in adq.columns if c.startswith("w_")]
drug = adq[wcols].sum().rename(lambda c: c[2:]).rename("items").to_frame()
drug["substance"] = drug.index.map(mapping.set_index("BNF_CHEMICAL_SUBSTANCE_CODE").BNF_CHEMICAL_SUBSTANCE)
drug = drug.sort_values("items", ascending=False)
R["watch_total_from_drug_pull"] = int(drug["items"].sum()); R["watch_total_from_main_pull"] = int(rx.watch_items.sum())
drug["pct_of_watch"] = drug["items"] / drug["items"].sum() * 100
drug["cum_pct"] = drug.pct_of_watch.cumsum()
drug.to_csv(f"{OUT}/watch_drugs_12m.csv")
R["top3_watch_drugs"] = drug.substance.head(3).tolist(); R["top3_watch_pct"] = float(drug.pct_of_watch.head(3).sum())

# ---------------- age (July 2026 bands) ----------------
age = pd.read_csv(f"{ROOT}/data/raw/gp-reg-pat-prac-quin-age.csv", dtype=str)
age = age[(age.ORG_TYPE == "GP") & (age.SEX != "ALL") & (age.AGE_GROUP_5 != "ALL")]
age["n"] = age.NUMBER_OF_PATIENTS.astype(int)
ag = age.pivot_table(index="ORG_CODE", columns="AGE_GROUP_5", values="n", aggfunc="sum").fillna(0)
old = ["65_69", "70_74", "75_79", "80_84", "85_89", "90_94", "95+"]
P["pct65"] = ag[old].sum(axis=1) / ag.sum(axis=1) * 100
P["pct1524"] = ag[["15_19", "20_24"]].sum(axis=1) / ag.sum(axis=1) * 100
P["pct09"] = ag[["0_4", "5_9"]].sum(axis=1) / ag.sum(axis=1) * 100
lr = stats.linregress(P.pct65, P.rate)
R.update(age_slope=lr.slope, age_slope_ci=[lr.slope - 1.96 * lr.stderr, lr.slope + 1.96 * lr.stderr],
         age_intercept=lr.intercept, age_r2=lr.rvalue ** 2, age_p=lr.pvalue)
r_as, p_as = stats.pearsonr(P.pct65, P.share)
R.update(r_age_share=r_as, p_age_share=p_as)

# ---------------- deprivation: practice IMD 2025 score ----------------
dep_dir = f"{ROOT}/data/deprivation"
imd = pd.read_excel(f"{dep_dir}/File_5_IoD2025_Scores_for_the_Indices_of_Deprivation.xlsx", sheet_name="IoD2025 Scores",
                    usecols=["LSOA code (2021)", "Index of Multiple Deprivation (IMD) Score"])
imd.columns = ["lsoa", "imd"]
with zipfile.ZipFile(f"{dep_dir}/gp-reg-pat-prac-lsoa-male-female-July-26.zip") as z:
    ls = pd.read_csv(z.open("gp-reg-pat-prac-lsoa-all.csv"), usecols=["PRACTICE_CODE", "LSOA_CODE", "NUMBER_OF_PATIENTS"])
ls = ls[ls.PRACTICE_CODE.isin(P.index)].merge(imd, left_on="LSOA_CODE", right_on="lsoa", how="left")
cov = ls.groupby("PRACTICE_CODE").apply(lambda d: d.loc[d.imd.notna(), "NUMBER_OF_PATIENTS"].sum() / d.NUMBER_OF_PATIENTS.sum())
ok = ls[ls.imd.notna()]
P["imd"] = ok.groupby("PRACTICE_CODE").apply(lambda d: np.average(d.imd, weights=d.NUMBER_OF_PATIENTS))
P["imd_coverage"] = cov
R["imd_practices_matched"] = int(P.imd.notna().sum()); R["imd_median_coverage"] = float(cov.median())
pi = P.dropna(subset=["imd"])
for v in ("share", "rate"):
    r_, p_ = stats.pearsonr(pi.imd, pi[v]); R[f"r_imd_{v}"] = r_; R[f"p_imd_{v}"] = p_
P["imd_fifth"] = pd.qcut(P.imd, 5, labels=[1, 2, 3, 4, 5])
R["share_by_imd_fifth"] = (P.groupby("imd_fifth", observed=True).wr.sum() / P.groupby("imd_fifth", observed=True).cls.sum() * 100).round(2).tolist()

# ---------------- multiple regression: W+R share ----------------
import numpy.linalg as la
m = P.dropna(subset=["imd", "pct65"]).copy()
m["log_size"] = np.log10(m.pat)


def ols(y, X, names):
    X = np.column_stack([np.ones(len(X)), X]); b, *_ = la.lstsq(X, y, rcond=None)
    res = y - X @ b; dfree = len(y) - X.shape[1]; s2 = res @ res / dfree
    se = np.sqrt(np.diag(s2 * la.inv(X.T @ X))); t = b / se; p = 2 * stats.t.sf(abs(t), dfree)
    r2 = 1 - (res @ res) / ((y - y.mean()) @ (y - y.mean()))
    out = pd.DataFrame({"coef": b, "se": se, "t": t, "p": p, "ci_low": b - 1.96 * se, "ci_high": b + 1.96 * se},
                       index=["intercept"] + names)
    return out, r2


reg, r2 = ols(m.share.values, m[["imd", "pct65", "log_size", "icb_share"]].values, ["imd", "pct65", "log_size", "icb_share"])
reg.to_csv(f"{OUT}/regression_share.csv"); R["reg_r2"] = r2; R["reg_n"] = len(m)
R["reg"] = reg.round(4).to_dict(orient="index")
_, r2_icb = ols(m.share.values, m[["icb_share"]].values, ["icb_share"]); R["r2_icb_only"] = r2_icb
reg_rate, r2_rate = ols(m.rate.values, m[["imd", "pct65", "log_size"]].values, ["imd", "pct65", "log_size"])
reg_rate.to_csv(f"{OUT}/regression_rate.csv"); R["reg_rate_r2"] = r2_rate; R["reg_rate"] = reg_rate.round(4).to_dict(orient="index")
_, R["reg_share_no_icb_r2"] = ols(m.share.values, m[["imd", "pct65", "log_size"]].values, ["imd", "pct65", "log_size"])  # same 3 factors as the volume model
# standardised (per 1 SD) effects so the predictors can be compared
for v in ["imd", "pct65", "log_size", "icb_share"]:
    R.setdefault("reg_per_sd", {})[v] = float(reg.loc[v, "coef"] * m[v].std())

# ---------------- sensitivity table ----------------
P_all = practice_table(rx_all.assign(wr=rx_all.watch_items + rx_all.reserve_items))
rx_all["wr"] = rx_all.watch_items + rx_all.reserve_items; rx_all["share"] = rx_all.wr / rx_all.cls * 100
rx_all["top"], _ = flags(rx_all, "share")
R["persistent_9plus_incl_atypical"] = int((rx_all.groupby("pc").top.sum() >= 9).sum())
R["england_share_incl_atypical"] = float(rx_all.wr.sum() / rx_all.cls.sum() * 100)
lr_all = stats.linregress(P_all.join(P[["pct65"]], how="inner").pct65 if False else
                          ag.reindex(P_all.index)[old].sum(axis=1) / ag.reindex(P_all.index).sum(axis=1) * 100, P_all.rate)
R["age_r2_incl_atypical"] = lr_all.rvalue ** 2

# ---------------- review shortlist: unusual (funnel) AND persistent AND not just lymecycline ----------------
P["flag_funnel"] = P.z_od > 3.09
P["flag_persistent"] = P.months_top >= 9
P["flag_persistent_nl"] = P.months_top_nl >= 9
short = P[P.flag_funnel & P.flag_persistent & P.flag_persistent_nl].sort_values("z_od", ascending=False)
R["shortlist_n"] = len(short)
R["shortlist_top15_overlap_with_old_top15"] = len(set(short.index[:15]) & set(top15))
short.head(30).assign(rank_by_z=range(1, 31))[["rank_by_z", "pn", "icb", "cls", "share", "icb_share", "gap", "z_od", "months_top", "months_top_nl", "lyme_pct"]].to_csv(f"{OUT}/review_shortlist.csv")

R["funnel_expected_false_positives"] = float(len(P) * stats.norm.sf(3.09))
short_gap = P[P.flag_funnel & P.flag_persistent & P.flag_persistent_nl].sort_values("gap", ascending=False)
R["shortlist_top15_by_z_vs_by_gap_overlap"] = len(set(short.index[:15]) & set(short_gap.index[:15]))

# ---------------- ICB concentration of the shortlist ----------------
P["shortlisted"] = P.index.isin(short.index)
ic2 = P.groupby("icb").agg(n=("pn", "size"), s=("shortlisted", "sum"), share=("icb_share", "first"))
ic2["frac"] = ic2.s / ic2.n
R["icbs_with_no_shortlisted"] = int((ic2.s == 0).sum()); R["max_shortlisted_icb"] = [ic2.s.idxmax(), int(ic2.s.max())]
R["r_icb_share_vs_frac_shortlisted"] = float(np.corrcoef(ic2.share, ic2.frac)[0, 1])

# ---------------- sensitivity: funnel against each practice's own ICB ----------------
pi_ = P.icb_share / 100
P["se_icb"] = np.sqrt(pi_ * (1 - pi_) / P.cls)
P["z_icb"] = (P.share / 100 - pi_) / P.se_icb
lo2, hi2 = P.z_icb.quantile([0.1, 0.9]); zw2 = P.z_icb.clip(lo2, hi2)
phi2 = float((zw2 ** 2).mean()); w2 = 1 / P.se_icb ** 2
tau2_icb = max(0.0, (n * phi2 - (n - 1)) / (w2.sum() - (w2 ** 2).sum() / w2.sum()))
P["z_icb_od"] = (P.share / 100 - pi_) / np.sqrt(P.se_icb ** 2 + tau2_icb)
P["flag_funnel_icb"] = P.z_icb_od > 3.09
short_icb = P[P.flag_funnel_icb & P.flag_persistent & P.flag_persistent_nl]
R.update(funnel_icb_tau=float(np.sqrt(tau2_icb)), funnel_icb_above_998=int(P.flag_funnel_icb.sum()),
         shortlist_icb_n=len(short_icb), shortlist_icb_overlap=len(set(short_icb.index) & set(short.index)),
         icbs_with_no_shortlisted_icbversion=int((~ic2.index.isin(short_icb.icb.unique())).sum()))

# ---------------- sensitivity: persistence and shortlist by dose (ADQ) ----------------
adq_m = adq.copy()
adq_m["adq_share"] = (adq_m.adq_W + adq_m.adq_R) / adq_m[["adq_A", "adq_W", "adq_R", "adq_O"]].sum(axis=1) * 100
adq_m["top_adq"], _ = flags(adq_m, "adq_share")
P["months_top_adq"] = adq_m.groupby("pc").top_adq.sum()
pers_adq = set(P.index[P.months_top_adq >= 9])
R.update(persistent_9plus_adq=len(pers_adq), persistent_overlap_items_adq=len(pers & pers_adq),
         shortlist_also_persistent_by_adq=int(P.loc[short.index, "months_top_adq"].ge(9).sum()))

# ---------------- regression robustness: leave-one-out ICB share, ICB fixed effects ----------------
g_ = P.groupby("icb")
P["icb_share_loo"] = (g_.wr.transform("sum") - P.wr) / (g_.cls.transform("sum") - P.cls) * 100
m2 = P.dropna(subset=["imd", "pct65"]).copy(); m2["log_size"] = np.log10(m2.pat)
reg_loo, _ = ols(m2.share.values, m2[["imd", "pct65", "log_size", "icb_share_loo"]].values, ["imd", "pct65", "log_size", "icb_share_loo"])
d_ = pd.get_dummies(m2.icb, drop_first=True).astype(float)
reg_fe, r2_fe = ols(m2.share.values, np.column_stack([m2[["imd", "pct65", "log_size"]].values, d_.values]),
                    ["imd", "pct65", "log_size"] + list(d_.columns))
R.update(reg_imd_coef_loo=float(reg_loo.loc["imd", "coef"]), reg_imd_p_loo=float(reg_loo.loc["imd", "p"]),
         reg_imd_coef_fe=float(reg_fe.loc["imd", "coef"]), reg_imd_p_fe=float(reg_fe.loc["imd", "p"]), reg_fe_r2=r2_fe,
         r_imd_pct65=float(P[["imd", "pct65"]].corr().iloc[0, 1]))
reg_rate_fe, _ = ols(m2.rate.values, np.column_stack([m2[["imd", "pct65", "log_size"]].values, d_.values]),
                     ["imd", "pct65", "log_size"] + list(d_.columns))
R["reg_rate_imd_coef_fe"] = float(reg_rate_fe.loc["imd", "coef"])

# ---------------- out of sample: flag on Sep-Feb only, check Mar-Aug (sheet 14) ----------------
def adj_z(wr, n):
    p0_ = wr.sum() / n.sum(); se_ = np.sqrt(p0_ * (1 - p0_) / n); z_ = (wr / n - p0_) / se_
    zw_ = z_.clip(z_.quantile(0.1), z_.quantile(0.9)); phi_ = (zw_ ** 2).mean(); w_ = 1 / se_ ** 2; n_ = len(z_)
    t2_ = max(0.0, (n_ * phi_ - (n_ - 1)) / (w_.sum() - (w_ ** 2).sum() / w_.sum()))
    return (wr / n - p0_) / np.sqrt(se_ ** 2 + t2_), p0_


hh = rx.assign(half=np.where(rx.ym.isin(H1), 1, 2)).groupby(["pc", "half"]).agg(wr=("wr", "sum"), cls=("cls", "sum"),
                                                                                 top=("top", "sum"), top_nl=("top_nl", "sum")).unstack()
z1, _ = adj_z(hh.wr[1], hh.cls[1]); z2, p02 = adj_z(hh.wr[2], hh.cls[2])
f1 = (z1 > 3.09) & (hh.top[1] >= 5) & (hh.top_nl[1] >= 5)
s2 = hh.wr[2] / hh.cls[2] * 100
R.update(oos_flagged_h1=int(f1.sum()), oos_still_998=float((z2[f1] > 3.09).mean()), oos_base_998=float((z2 > 3.09).mean()),
         oos_still_95=float((z2[f1] > 1.96).mean()), oos_top4of6=float((hh.top[2][f1] >= 4).mean()),
         oos_below_england=float((s2[f1] < p02 * 100).mean()), oos_mean_share_h1=float((hh.wr[1] / hh.cls[1] * 100)[f1].mean()),
         oos_mean_share_h2=float(s2[f1].mean()), oos_england_h2=float(p02 * 100))
R["shortlist_by_cutoff"] = {f"z>{zc}": [int(((P.z_od > zc) & (P.months_top >= m) & (P.months_top_nl >= m)).sum()) for m in (8, 9, 10, 11)]
                            for zc in (2.58, 3.09, 3.5)}
drop = short.index[P.loc[short.index, "months_top_adq"] < 9]
R.update(adq_dropouts=len(drop), adq_dropouts_median_share=float(P.loc[drop, "adq_share"].median()))
R.update(shortlist_median_patients=float(P.loc[short.index, "pat"].median()),
         others_median_patients=float(P.loc[~P.index.isin(short.index), "pat"].median()))
# deprivation and share: ordinary vs ICB-clustered errors, and a binomial (count) model weighted by practice size
try:
    import statsmodels.formula.api as smf, statsmodels.api as sm
    d_ = P.dropna(subset=["imd"]).assign(ls=lambda x: np.log10(x.pat), y=lambda x: x.share / 100)
    f_ = "share ~ imd + pct65 + ls + C(icb)"
    R["imd_share_fe_p_ols"] = float(smf.ols(f_, d_).fit().pvalues["imd"])
    R["imd_share_fe_p_clustered"] = float(smf.ols(f_, d_).fit(cov_type="cluster", cov_kwds={"groups": d_.icb}).pvalues["imd"])
    gb = smf.glm("y ~ imd + pct65 + ls + C(icb)", d_, family=sm.families.Binomial(), var_weights=d_.cls).fit(
        scale="X2", cov_type="cluster", cov_kwds={"groups": d_.icb})
    R["imd_share_quasibinomial_p_clustered"] = float(gb.pvalues["imd"])
    fr = "rate ~ imd + pct65 + ls + C(icb)"
    R["imd_rate_fe_coef"] = float(smf.ols(fr, d_).fit().params["imd"])
    R["imd_rate_fe_p_clustered"] = float(smf.ols(fr, d_).fit(cov_type="cluster", cov_kwds={"groups": d_.icb}).pvalues["imd"])
except ImportError:
    print("statsmodels not installed: skipping clustered-error checks (pip install statsmodels)")

# persistence under two alternative choices (Table 3 / sheet 10)
def _pers(d, denom_other=True):
    d = d.copy(); d["wr_"] = d.watch_items + d.reserve_items
    d["s_"] = d.wr_ / (d.cls if denom_other else d.cls - d.other_items)
    c_ = d.groupby("ym").s_.quantile(0.8); d["t_"] = (d.s_ >= d.ym.map(c_)).astype(int)
    g_ = d.groupby("pc").t_.sum(); return set(g_[g_ >= 9].index)
_main = set(P.index[P.months_top >= 9])
_op = _pers(rx, denom_other=False); _all = _pers(rx_all)
R.update(persistent_9plus_op_denominator=len(_op), persistent_9plus_op_same=len(_op & _main),
         persistent_9plus_incl_atypical_same=len(_all & _main))

# share versus volume: is a high share driven by more Watch+Reserve, or by less Access? (sheet 14)
_f = 1000 / P.pat
_tot, _acc, _wrr = P.cls * _f, P.acc * _f, P.wr * _f
_s = P.index.isin(short.index)
_wr80 = _wrr.quantile(0.8); _sh80 = P.share.quantile(0.8)        # pandas default = Excel PERCENTILE.INC
R.update(sv_med_total_short=float(_tot[_s].median()), sv_med_total_other=float(_tot[~_s].median()),
         sv_med_access_short=float(_acc[_s].median()), sv_med_access_other=float(_acc[~_s].median()),
         sv_med_wr_short=float(_wrr[_s].median()), sv_med_wr_other=float(_wrr[~_s].median()),
         sv_wr_per1000_p80=float(_wr80), sv_short_top_wr=int((_s & (_wrr >= _wr80)).sum()),
         sv_high_wr_normal_share=int(((_wrr >= _wr80) & (P.share < _sh80)).sum()))

# ---------------- save ----------------
P.to_csv(f"{OUT}/practices_12m_v2.csv")
icb_tab.to_csv(f"{OUT}/icb_12m_v2.csv")
pd.DataFrame(steps, columns=["step", "rows_kept"]).to_csv(f"{OUT}/cleaning_log_v2.csv", index=False)
pd.DataFrame({"atypical_excluded": sorted(atyp)}).to_csv(f"{OUT}/atypical_practices.csv", index=False)


# ---------------- sizing: how much of the problem sits with the shortlist? ----------------
E_ = P.wr.sum() / P.cls.sum()
ex_ = (P.wr - E_ * P.cls)                    # Watch+Reserve items above what the England share would give
R.update(excess_wr_shortlist=float(ex_[P.shortlisted].sum()),
         excess_wr_all_above=float(ex_[ex_ > 0].sum()), n_above_england=int((ex_ > 0).sum()),
         excess_wr_top_fifth=float(ex_[P.share >= P.share.quantile(0.8)].sum()),
         access_pts_if_shortlist_switched=float(ex_[P.shortlisted].sum() / P.cls.sum() * 100),
         access_pts_if_all_switched=float(ex_[ex_ > 0].sum() / P.cls.sum() * 100))
# how sensitive is the sizing to the comparison point? (England share, median practice, best quarter, best tenth)
R["sizing_by_benchmark"] = {}
for nm_, b_ in [("England", E_), ("median", P.share.median() / 100), ("p25", P.share.quantile(0.25) / 100), ("p10", P.share.quantile(0.10) / 100)]:
    e_ = P.wr - b_ * P.cls
    R["sizing_by_benchmark"][nm_] = {"benchmark_pct": float(b_ * 100), "shortlist_part": float(e_[P.shortlisted].sum() / e_[e_ > 0].sum()),
                                     "excess_items": float(e_[e_ > 0].sum()), "access_pts": float(e_[e_ > 0].sum() / P.cls.sum() * 100)}
R["oos_unflagged_998"] = float((z2[~f1] > 3.09).mean())   # comparator that excludes the flagged practices

# ---------------- positive deviants: practices significantly below the lower 99.8% limit ----------------
lo = P[P.z_od < -3.09]
R.update(low_n=len(lo), low_icbs=int(lo.icb.nunique()), low_median_share=float(lo.share.median()),
         low_both_halves_below_england=float(((lo.share_h1 < E_ * 100) & (lo.share_h2 < E_ * 100)).mean()),
         low_med_access_1000=float((lo.acc / lo.pat * 1000).median()), low_med_wr_1000=float((lo.wr / lo.pat * 1000).median()),
         all_med_access_1000=float((P.acc / P.pat * 1000).median()), all_med_wr_1000=float((P.wr / P.pat * 1000).median()),
         low_med_imd=float(lo.imd.median()), all_med_imd=float(P.imd.median()),
         low_med_pct65=float(lo.pct65.median()), all_med_pct65=float(P.pct65.median()),
         low_med_patients=float(lo.pat.median()))


def conv(o):
    if isinstance(o, (np.floating,)): return float(o)
    if isinstance(o, (np.integer,)): return int(o)
    return str(o)


json.dump(R, open(f"{OUT}/results.json", "w"), indent=1, default=conv)
for k, v in R.items():
    if k not in ("reg", "reg_rate"): print(f"{k}: {v}")
print(reg.round(4)); print("R2", round(r2, 3)); print(reg_rate.round(3)); print(drug.head(8).round(1))
