"""make_charts.py - report figures and Tableau files from the revised analysis.
Run after src/extended_analysis.py:   python src/make_charts.py
"""
import json, os, sys
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_clean, ROOT

os.chdir(ROOT)
OUT = "outputs/charts"; TB = "outputs/tableau"
os.makedirs(OUT, exist_ok=True); os.makedirs(TB, exist_ok=True)
R = json.load(open("outputs/tables/results.json"))
P = pd.read_csv("outputs/tables/practices_12m_v2.csv", dtype={"pc": str}).set_index("pc")
rx, _, _ = load_clean(True)
rx["wr"] = rx.watch_items + rx.reserve_items

plt.rcParams.update({"font.family": ["Inter", "Helvetica", "Arial", "DejaVu Sans"], "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#9aa5a6",
                     "axes.titleweight": "bold", "axes.titlesize": 12.5, "axes.titlelocation": "left", "figure.dpi": 200})
INK, TEAL, RED, AMBER, BLUE, GREY, PURP = "#0f3d3e", "#0f7c7e", "#c0392b", "#e08e0b", "#2f6fb5", "#b7c2c3", "#6a3d9a"
SRC = "Source: NHSBSA English Prescribing Dataset (Sep 2025-Aug 2026); NHS England GP list sizes; UKHSA UK-AWaRe (2025)."
NP = len(P); N = f"{NP:,} GP practices present in all 12 months"


def save(fig, name, note="", src=SRC):
    fig.text(0.01, -0.01, (note + "\n" if note else "") + src, fontsize=7, color="#6b7778", va="top")
    fig.savefig(f"{OUT}/{name}", bbox_inches="tight", facecolor="white"); plt.close(fig)


for f in os.listdir(OUT):
    os.remove(f"{OUT}/{f}")

# 1. monthly trend
m = rx.groupby("ym").agg(cls=("cls", "sum"), wr=("wr", "sum"), pat=("patients", "sum"), lyme=("lyme_items", "sum"))
m["rate"] = m.cls / m.pat * 1000; m["share"] = m.wr / m.cls * 100; m["share_nl"] = (m.wr - m.lyme) / (m.cls - m.lyme) * 100
m.to_csv("outputs/tables/monthly_trend_v2.csv")
labels = [pd.Period(x, "M").strftime("%b\n%y") for x in m.index]
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.4))
a1.bar(labels, m.rate, color=[BLUE if v >= m.rate.quantile(.75) else "#9ec5e8" for v in m.rate])
for i, v in enumerate(m.rate): a1.text(i, v + 0.6, f"{v:.1f}", ha="center", fontsize=8)
a1.set_title("Antibiotic items per 1,000 patients: winter peak"); a1.set_yticks([]); a1.spines["left"].set_visible(False)
a2.plot(labels, m.share, color=RED, marker="o", lw=2, label="Watch+Reserve %")
a2.plot(labels, m.share_nl, color=PURP, marker="o", lw=1.5, ls="--", label="without lymecycline")
for i, v in enumerate(m.share): a2.text(i, v + 0.25, f"{v:.1f}", ha="center", fontsize=8, color=RED)
a2.set_ylim(12, 21); a2.set_title("Watch+Reserve share: lowest in winter"); a2.legend(frameon=False, fontsize=8, loc="lower left")
fig.tight_layout(); save(fig, "01_monthly_trend.png", f"{N}.")

# 2. ICB
ic = pd.read_csv("outputs/tables/icb_12m_v2.csv").sort_values("share")
ic["short"] = ic.icb.str.replace("NHS ", "").str.replace(" INTEGRATED CARE BOARD", "").str.title().str.replace(" And ", " & ")
nat = R["england_share"]
fig, ax = plt.subplots(figsize=(9, 10)); y = np.arange(len(ic))
col = [TEAL if v < nat - 1 else (RED if v > nat + 1 else GREY) for v in ic.share]
ax.hlines(y, nat, ic.share, color=col, lw=2); ax.scatter(ic.share, y, color=col, s=55, zorder=3)
for yi, v in zip(y, ic.share):
    ax.text(v + (0.15 if v >= nat else -0.15), yi, f"{v:.1f}", va="center", ha="left" if v >= nat else "right", fontsize=7.5)
ax.axvline(nat, color=AMBER, lw=1.6); ax.text(nat, len(ic) - 0.3, f" England {nat:.1f}%", color=AMBER, fontsize=8.5, fontweight="bold", va="bottom")
ax.set_yticks(y); ax.set_yticklabels(ic.short, fontsize=8); ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_xlabel("Watch+Reserve share of antibacterial items, Sep 2025-Aug 2026 (%)"); ax.set_title("Watch+Reserve share by ICB over 12 months")
save(fig, "02_icb_12m.png", "Teal = more than 1 point below England; red = more than 1 point above.")

# 3. reliability: first half vs second half
fig, ax = plt.subplots(figsize=(7.2, 6))
hb = ax.hexbin(P.share_h1, P.share_h2, gridsize=55, mincnt=1, linewidths=0, extent=(0, 45, 0, 45),
               cmap=LinearSegmentedColormap.from_list("t", ["#eef6f6", TEAL, INK]))
ax.plot([0, 45], [0, 45], color="#9aa5a6", lw=1, ls=":"); ax.set_xlim(0, 45); ax.set_ylim(0, 45)
ax.text(0.03, 0.96, f"r = {R['split_half_r']:.2f}\n(95% CI {R['split_half_r_ci'][0]:.2f} to {R['split_half_r_ci'][1]:.2f})",
        transform=ax.transAxes, va="top", color=INK, fontsize=11.5, fontweight="bold", bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=TEAL))
ax.set_xlabel("Watch+Reserve % in Sep 2025-Feb 2026"); ax.set_ylabel("Watch+Reserve % in Mar-Aug 2026")
cb = fig.colorbar(hb, ax=ax, fraction=0.04); cb.set_label("Practices per hexagon", fontsize=8); cb.outline.set_visible(False)
ax.set_title("A practice's share in one half-year predicts the next")
save(fig, "03_reliability_split_half.png",
     f"{N}. Dotted line = same value in both halves. Noise share: {R['noise_share_1month']*100:.0f}% of one month's spread, {R['noise_share_12month']*100:.0f}% over 12 months.")

# 4. adjusted funnel plot
p0 = R["england_share"] / 100; tau2 = R["funnel_tau"] ** 2
nn = np.geomspace(700, P.cls.max() * 1.05, 200)
fig, ax = plt.subplots(figsize=(10, 5.8))
short = P.flag_funnel & P.flag_persistent & P.flag_persistent_nl
ax.scatter(P.loc[~P.flag_funnel, "cls"], P.loc[~P.flag_funnel, "share"], s=4, color="#b7c2c3", alpha=.55, lw=0, label="Within limits")
ax.scatter(P.loc[P.flag_funnel & ~short, "cls"], P.loc[P.flag_funnel & ~short, "share"], s=12, color=AMBER, lw=0, label="Above 99.8% limit only")
ax.scatter(P.loc[short, "cls"], P.loc[short, "share"], s=14, color=RED, lw=0, label=f"Review shortlist ({int(short.sum())})")
for z, ls, c in [(3.09, "--", RED), (1.96, ":", AMBER), (-1.96, ":", AMBER), (-3.09, "--", RED)]:
    ax.plot(nn, (p0 + z * np.sqrt(p0 * (1 - p0) / nn + tau2)) * 100, ls=ls, color=c, lw=1.3)
ax.axhline(p0 * 100, color=INK, lw=1.2)
ax.text(nn[-1], (p0 + 3.09 * np.sqrt(p0 * (1 - p0) / nn[-1] + tau2)) * 100 + .4, "99.8%", color=RED, fontsize=8, ha="right")
ax.text(nn[-1], (p0 + 1.96 * np.sqrt(p0 * (1 - p0) / nn[-1] + tau2)) * 100 + .4, "95%", color=AMBER, fontsize=8, ha="right")
ax.set_xscale("log"); ax.set_xlim(700, nn[-1]); ax.set_ylim(0, 45)
ax.set_xticks([1000, 2000, 5000, 10000, 20000, 50000]); ax.set_xticklabels(["1,000", "2,000", "5,000", "10,000", "20,000", "50,000"])
ax.set_xlabel("Antibacterial items prescribed in 12 months (log scale)"); ax.set_ylabel("Watch+Reserve %")
ax.legend(frameon=False, fontsize=8, loc="upper right")
ax.set_title(f"Adjusted funnel plot: {R['funnel_od_above_998']} practices sit above the 99.8% limit")
save(fig, "04_funnel_adjusted.png",
     f"Limits allow for sampling noise AND the normal spread between practices (Spiegelhalter, 2005; tau = {R['funnel_tau']*100:.1f} points). "
     "Shortlist = above 99.8%, top fifth 9+ months, and still 9+ months without lymecycline.")

# 5. age scatter
a = P.dropna(subset=["pct65"])
fig, ax = plt.subplots(figsize=(8, 5.4))
hb = ax.hexbin(a.pct65, a.rate, gridsize=45, mincnt=1, linewidths=0, cmap=LinearSegmentedColormap.from_list("t", ["#eef6f6", TEAL, INK]))
xx = np.linspace(0, a.pct65.max(), 50); ax.plot(xx, R["age_intercept"] + R["age_slope"] * xx, color=RED, lw=2)
ax.text(0.03, 0.95, f"y = {R['age_slope']:.2f}x + {R['age_intercept']:.1f}\nR² = {R['age_r2']:.2f}", transform=ax.transAxes, va="top",
        color=RED, fontsize=12, fontweight="bold", bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=RED))
ax.set_xlabel("% of registered patients aged 65+  (x)"); ax.set_ylabel("Antibacterial items per 1,000 patients per year  (y)")
cb = fig.colorbar(hb, ax=ax, fraction=0.04); cb.set_label("Practices per hexagon", fontsize=8); cb.outline.set_visible(False)
ax.set_title("Older practice populations go with higher yearly antibiotic rates")
save(fig, "05_age_scatter.png", f"{len(a):,} practices. Slope 95% CI {R['age_slope_ci'][0]:.2f} to {R['age_slope_ci'][1]:.2f}. Age bands from July 2026. A link, not proof of cause.")

# 6. box plots: age (share) and IMD (share)
P["age_fifth"] = pd.qcut(P.pct65, 5, labels=[1, 2, 3, 4, 5])
fig, (b1, b2) = plt.subplots(1, 2, figsize=(12, 5))
for ax, grp, title, cols, ticks in [
        (b1, "age_fifth", "By age: boxes stay level", ["cdb6e3", "b493d4", "9a70c4", "8250b2", "6a3d9a"], ["Youngest", "2", "3", "4", "Oldest"]),
        (b2, "imd_fifth", "By deprivation: a slight fall", ["c9e6e4", "9fd0cd", "6fb7b4", "3f9c99", "0f7c7e"], ["Least\ndeprived", "2", "3", "4", "Most\ndeprived"])]:
    data = [P.loc[P[grp] == g, "share"].dropna().values for g in [1, 2, 3, 4, 5]]
    bp = ax.boxplot(data, patch_artist=True, widths=0.55, medianprops=dict(color="white", lw=2.2),
                    flierprops=dict(marker="o", markersize=2.5, markerfacecolor="#9aa5a6", markeredgecolor="none", alpha=.6))
    for patch, c in zip(bp["boxes"], cols): patch.set_facecolor("#" + c); patch.set_edgecolor("#" + c)
    for i, v in enumerate(data):
        ax.text(i + 1, np.median(v), f"{np.median(v):.1f}", ha="center", va="bottom", fontsize=8.5, fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=.85))
    ax.set_xticks(range(1, 6)); ax.set_xticklabels(ticks); ax.set_title(title, fontsize=12); ax.set_ylim(0, 45); ax.set_ylabel("Practice Watch+Reserve %")
fig.suptitle("Watch+Reserve share by age group and by deprivation group (fifths of practices)", x=0.01, ha="left", fontweight="bold", fontsize=12.5)
fig.tight_layout()
save(fig, "06_box_age_deprivation.png",
     f"Box = middle 50%; line = median; dots = unusual practices. r(age, share) = {R['r_age_share']:.2f}; r(IMD, share) = {R['r_imd_share']:.2f}. "
     "IMD 2025 score weighted by where each practice's patients live.",
     SRC + " MHCLG English Indices of Deprivation 2025; NHS England patients by LSOA (Jul 2026).")

# 7. correlation matrix
cols = {"rate": "Items per 1,000/yr", "share": "Watch+Reserve %", "pct65": "% aged 65+", "pct1524": "% aged 15-24",
        "pct09": "% aged 0-9", "pat": "Practice size", "imd": "IMD 2025 score", "months_top": "Months in top fifth"}
corr = P[list(cols)].rename(columns=cols).corr()
corr.to_csv("outputs/tables/correlation_matrix_v2.csv")
cm = LinearSegmentedColormap.from_list("div", [BLUE, "#f7f7f7", RED]); mask = np.triu(np.ones_like(corr, dtype=bool))
fig, ax = plt.subplots(figsize=(8.6, 6.8))
im = ax.imshow(np.where(mask, np.nan, corr.values), cmap=cm, vmin=-1, vmax=1)
for i in range(len(corr)):
    for j in range(len(corr)):
        if not mask[i, j]:
            v = corr.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=9.5, fontweight="bold" if abs(v) >= .3 else "normal",
                    color="white" if abs(v) > .55 else INK)
labs = list(corr.columns)
ax.set_xticks(range(len(labs) - 1)); ax.set_xticklabels(labs[:-1], rotation=35, ha="right", fontsize=8.5)
ax.set_yticks(range(1, len(labs))); ax.set_yticklabels(labs[1:], fontsize=8.5)
ax.set_xlim(-.5, len(labs) - 1.5); ax.set_ylim(len(labs) - .5, .5)
for s in ax.spines.values(): s.set_visible(False)
ax.tick_params(length=0)
cb = fig.colorbar(im, ax=ax, fraction=.04); cb.set_label("Pearson r", fontsize=8); cb.outline.set_visible(False)
ax.set_title("Correlation matrix (12-month practice totals)", fontsize=12)
fig.text(0.01, -0.1, f"{NP:,} practices. Age bands are shares of one total, and months in the top fifth is built from W+R %, so some links are built in.\n" + SRC,
         fontsize=7, color="#6b7778", va="top")
fig.savefig(f"{OUT}/07_correlation_matrix.png", bbox_inches="tight", facecolor="white"); plt.close(fig)

# 8. review shortlist top 15
t = P[short].sort_values("z_od", ascending=False).head(15)[::-1]
fig, ax = plt.subplots(figsize=(10.5, 6.2))
ax.barh([f"Practice {len(t) - k}" for k in range(len(t))], t.z_od, color=RED, alpha=.85)   # anonymised: no names in public figures
ax.axvline(3.09, color=INK, lw=1, ls="--"); ax.text(3.09, 14.6, " 99.8% limit (z = 3.09)", fontsize=8, color=INK)
for i, (g, s, ib, mt, z) in enumerate(zip(t.gap, t.share, t.icb_share, t.months_top, t.z_od)):
    ax.text(z + 0.08, i, f"z = {z:.1f}  ·  {s:.1f}% vs ICB {ib:.1f}%  ·  +{g:,.0f} items  ·  top fifth {mt}/12", va="center", fontsize=8)
ax.set_xlim(0, t.z_od.max() * 2.1); ax.set_xticks([]); ax.spines["bottom"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_title(f"Review shortlist: the 15 most unusual of the {int(short.sum())} practices that pass all three tests")
save(fig, "08_review_shortlist.png", "Tests: above the adjusted 99.8% funnel limit; top fifth 9+ of 12 months; still 9+ months without lymecycline. "
     "Ranked by adjusted z, so big practices are not favoured. About 6 of the 117 above the limit could be chance. No diagnosis data: a list to look into, not a judgement. Practices not named.")

# 9. Watch drugs
d = pd.read_csv("outputs/tables/watch_drugs_12m.csv").head(8)[::-1]
fig, ax = plt.subplots(figsize=(8.5, 4.4))
ax.barh(d.substance.str.replace(" (Amoxicillin/clavulanic acid)", "", regex=False), d.pct_of_watch,
        color=[RED if i >= 5 else "#e6a49c" for i in range(len(d))])
for i, (v, n_) in enumerate(zip(d.pct_of_watch, d["items"])): ax.text(v + .4, i, f"{v:.1f}%  ({n_/1e6:.2f}m items)", va="center", fontsize=8)
ax.set_xlim(0, 40); ax.set_xticks([]); ax.spines["bottom"].set_visible(False); ax.tick_params(axis="y", length=0)
ax.set_title(f"Three drugs make up {R['top3_watch_pct']:.1f}% of Watch items")
save(fig, "09_watch_drugs.png", f"{R['watch_total_from_drug_pull']:,} Watch items, 12 months, same practices. Matches the main data exactly.")

# ---------------- Tableau files ----------------
pr = P.reset_index().rename(columns={"pc": "practice_code", "pn": "practice_name"})
pr["icb_short"] = pr.icb.str.replace("NHS ", "").str.replace(" INTEGRATED CARE BOARD", "").str.title()
pr["age_group"] = pr.age_fifth.map({1: "1 Youngest", 2: "2", 3: "3", 4: "4", 5: "5 Oldest"})
pr["imd_group"] = pr.imd_fifth.map({1: "1 Least deprived", 2: "2", 3: "3", 4: "4", 5: "5 Most deprived"})
pr["pattern"] = np.select([short.values, pr.flag_funnel.values, pr.flag_persistent.values],
                          ["Review shortlist", "Above funnel limit", "Top fifth 9+ months"], "Other")
pr.to_csv(f"{TB}/tableau_practices_12m.csv", index=False)
corr.stack().rename("r").reset_index().rename(columns={"level_0": "Variable A", "level_1": "Variable B"}).to_csv(f"{TB}/tableau_correlation_long.csv", index=False)
print("charts:", sorted(os.listdir(OUT)))

# ---------------- version 3: second year, recorded patient need, sizing (src/second_year_casemix.py) ----------------
Y2 = json.load(open("outputs/tables/results_y2_casemix.json"))
TY = pd.read_csv("outputs/tables/practices_two_years.csv", dtype={"pc": str}).set_index("pc").dropna(subset=["share_2425", "share_2526"])
CM = pd.read_csv("outputs/tables/practices_y2_casemix.csv", dtype={"pc": str}).set_index("pc")
SRC2 = "Source: NHSBSA English Prescribing Dataset (Sep 2024-Aug 2026); NHS England GP list sizes; UKHSA UK-AWaRe (2025)."

# 10. same practices next year
both_ = TY.short_2425.astype(bool) & TY.short_2526.astype(bool)
one_ = (TY.short_2425.astype(bool) | TY.short_2526.astype(bool)) & ~both_
fig, ax = plt.subplots(figsize=(7.6, 6.4))
ax.scatter(TY.share_2425[~(both_ | one_)] * 100, TY.share_2526[~(both_ | one_)] * 100, s=5, color=GREY, alpha=.35, lw=0, label="Other practices")
ax.scatter(TY.share_2425[one_] * 100, TY.share_2526[one_] * 100, s=14, color=AMBER, alpha=.8, lw=0, label="Shortlisted in one year")
ax.scatter(TY.share_2425[both_] * 100, TY.share_2526[both_] * 100, s=18, color=RED, lw=0, label=f"Shortlisted in both years ({int(both_.sum())})")
lim_ = [5, 42]; ax.plot(lim_, lim_, color=INK, lw=.8, ls="--"); ax.set_xlim(lim_); ax.set_ylim(lim_)
ax.text(0.97, 0.05, f"r = {Y2['r_share_year_to_year']:.2f}", transform=ax.transAxes, ha="right", fontsize=11, fontweight="bold", color=RED,
        bbox=dict(boxstyle="square,pad=0.35", fc="white", ec=RED))
ax.set_xlabel("Watch+Reserve % of items, Sep 2024 - Aug 2025"); ax.set_ylabel("Watch+Reserve % of items, Sep 2025 - Aug 2026")
ax.set_title("The same practices stand out a year later"); ax.legend(frameon=False, fontsize=8, loc="upper left")
save(fig, "10_two_years.png", f"{Y2['practices_both_years']:,} practices present in both years. Of {Y2['y1_short_in_both']} shortlisted on 2024-25 data alone, "
     f"{Y2['y1short_above998_next_year']*100:.0f}% were above the 99.8% limit in 2025-26 (others: {Y2['unflagged_above998_next_year']*100:.1f}%). Dashed line: same share both years.", SRC2)

# 11. recorded patient need
sh_ = CM.short.astype(bool)
fig, ax = plt.subplots(figsize=(7.6, 6.2))
ax.scatter(CM.z_od[~sh_], CM.z_cm[~sh_], s=5, color=GREY, alpha=.35, lw=0, label="Other practices")
ax.scatter(CM.z_od[sh_], CM.z_cm[sh_], s=18, color=RED, lw=0, label=f"Review shortlist ({int(sh_.sum())})")
for v_ in (3.09, -3.09):
    ax.axhline(v_, color=INK, lw=.8, ls=":"); ax.axvline(v_, color=INK, lw=.8, ls=":")
ax.plot([-8, 9], [-8, 9], color=INK, lw=.6, ls="--")
ax.set_xlim(-8, 9); ax.set_ylim(-8, 9)
ax.set_xlabel("Adjusted z against the England share"); ax.set_ylabel("Adjusted z against each practice's case-mix-expected share")
ax.set_title("Allowing for recorded patient need barely moves the outliers")
ax.text(0.97, 0.05, f"{Y2['shortlist_still_above998_casemix']} of {Y2['shortlist_in_casemix']} still above\nthe 99.8% limit (z = 3.09)", transform=ax.transAxes,
        ha="right", fontsize=10, fontweight="bold", color=RED, bbox=dict(boxstyle="square,pad=0.35", fc="white", ec=RED))
ax.legend(frameon=False, fontsize=8, loc="upper left")
save(fig, "11_patient_need.png", "Case-mix model: % 65+, % 15-24, IMD, practice size and QOF 2025-26 registers for COPD, asthma, diabetes, CKD, cancer, dementia and heart failure. "
     "QOF has no register for penicillin allergy, bronchiectasis or acne.", SRC2.replace("UKHSA", "NHS England QOF 2025-26; UKHSA"))

# 12. where the excess sits
n_top = int((P.share >= P.share.quantile(0.8)).sum()); ex_short = R["excess_wr_shortlist"]; ex_top = R["excess_wr_top_fifth"] - ex_short; ex_rest = R["excess_wr_all_above"] - R["excess_wr_top_fifth"]
fig, ax = plt.subplots(figsize=(8.6, 3.4))
parts = [(ex_short, f"Review shortlist\n({R['shortlist_n']} practices)", RED), (ex_top, f"Rest of the top fifth\n({n_top - R['shortlist_n']:,} practices)", AMBER),
         (ex_rest, f"Other practices above England\n({R['n_above_england'] - n_top:,} practices)", GREY)]
left_ = 0
for v_, lab_, c_ in parts:
    ax.barh([0], [v_], left=left_, color=c_, height=.5)
    ax.text(left_ + v_ / 2, 0.36, f"{v_/1000:.0f}k items\n{v_/R['excess_wr_all_above']*100:.0f}%", ha="center", va="bottom", fontsize=9, fontweight="bold", color=INK)
    ax.text(left_ + v_ / 2, -0.36, lab_, ha="center", va="top", fontsize=8, color=INK)
    left_ += v_
ax.set_xlim(0, left_); ax.set_ylim(-1, 1); ax.axis("off")
ax.set_title(f"The shortlist holds only {ex_short/R['excess_wr_all_above']*100:.0f}% of the Watch+Reserve items above the England share")
save(fig, "12_where_excess_sits.png", f"Excess = Watch+Reserve items minus items x England share ({R['england_share']:.1f}%), per practice, summed over practices above England. "
     f"All of it switched to Access = +{R['access_pts_if_all_switched']:.1f} points of Access (items, not doses). Against the best tenth of practices instead, "
     f"the shortlist holds {R['sizing_by_benchmark']['p10']['shortlist_part']*100:.0f}% and the total is {R['sizing_by_benchmark']['p10']['access_pts']:.1f} points (workbook sheet 17).")
print("v3 charts done")
# add the earlier year and the case-mix z to the Tableau practice file
pr["share_2425"] = pr.practice_code.map(TY.share_2425 * 100)
pr["short_2425"] = pr.practice_code.map(TY.short_2425.astype(float))
pr["z_casemix"] = pr.practice_code.map(CM.z_cm)
pr.to_csv(f"{TB}/tableau_practices_12m.csv", index=False)
