"""Cross-check: every headline number in the Excel workbook (cached values after recalculation) against the independent
Python recalculation in outputs/tables/results.json.   Run:  python tests/verify.py"""
import json, os, sys
from openpyxl import load_workbook
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = json.load(open(f"{ROOT}/outputs/tables/results.json"))
wb = load_workbook(f"{ROOT}/Project1_Antibiotic_Stewardship_12m.xlsx", data_only=True, read_only=True)
cache = {}
def v(sheet, cell):
    if sheet not in cache: cache[sheet] = {c.coordinate: c.value for row in wb[sheet].iter_rows() for c in row if hasattr(c, "coordinate")}
    return cache[sheet].get(cell)
Y = json.load(open(f"{ROOT}/outputs/tables/results_y2_casemix.json"))
T2, PN, SZ = "15 Three years", "16 Patient need", "17 Sizing"
F, S, O, Rl, D, A = "9 Funnel", "10 Sensitivity", "14 Out of sample", "8 Reliability", "11 Deprivation", "5 Age"
checks = [
    (F, "B5", R["england_share"] / 100), (F, "B6", R["n_practices"]), (F, "B10", R["funnel_phi"]), (F, "B14", R["funnel_tau"] * 100),
    (F, "B17", R["funnel_plain_above_998"]), (F, "B18", R["funnel_od_above_998"]), (F, "B19", R["funnel_od_above_95"]),
    (F, "B20", R["funnel_od_below_998"]), (F, "B21", R["funnel_od_flagged_also_persistent"]), (F, "B22", R["funnel_expected_false_positives"]),
    (F, "B66", R["funnel_icb_above_998"]), (F, "B67", R["shortlist_icb_n"]), (F, "B68", R["shortlist_icb_overlap"]),
    (Rl, "B5", R["split_half_r"]), (Rl, "B9", R["spearman_brown_12m"]), (Rl, "B12", R["p_top_next_given_top"]),
    (Rl, "B18", R["noise_share_1month"]), (Rl, "B19", R["noise_share_12month"]),
    (S, "B5", R["england_share"]), (S, "C5", R["persistent_9plus"]), (S, "B6", R["england_share_no_lyme"]), (S, "C6", R["persistent_9plus_no_lyme"]),
    (S, "D6", R["persistent_overlap_with_without_lyme"]), (S, "B7", R["england_share_awr"]), (S, "B8", R["england_adq_share"]),
    (S, "C8", R["persistent_9plus_adq"]), (S, "D8", R["persistent_overlap_items_adq"]), (S, "B12", R["r_share_vs_share_no_lyme"]),
    (S, "B13", R["r_item_share_vs_adq_share"]), (S, "B17", R["shortlist_also_persistent_by_adq"]),
    ("13 Review shortlist", "B4", R["shortlist_n"]),
    (D, "B4", R["r_imd_share"]), (D, "B6", R["r_imd_rate"]), (D, "B18", R["reg_r2"]), (D, "B20", R["r2_icb_only"]),
    (D, "B40", R["reg_rate_r2"]), (D, "B42", R["r_imd_pct65"]), (D, "B48", R["reg_imd_coef_loo"]),
    (A, "B4", R["age_slope"]), (A, "B5", R["age_intercept"]), (A, "B6", R["age_r2"]), (A, "B8", R["r_age_share"]),
    (O, "B13", R["oos_flagged_h1"]), (O, "B14", R["oos_still_998"]), (O, "B15", R["oos_base_998"]), (O, "B16", R["oos_still_95"]),
    (O, "B17", R["oos_top4of6"]), (O, "B18", R["oos_below_england"]), (O, "B19", R["oos_mean_share_h1"]), (O, "B20", R["oos_mean_share_h2"]),
    (O, "B21", R["oos_england_h2"]), (O, "C31", R["shortlist_by_cutoff"]["z>2.58"][1]), (O, "C32", R["shortlist_by_cutoff"]["z>3.09"][1]),
    (O, "C33", R["shortlist_by_cutoff"]["z>3.5"][1]), (O, "B41", R["adq_dropouts"]), (O, "B42", R["adq_dropouts_median_share"], 1e-3),  # workbook stores ADQ values rounded to 2 dp
    (O, "B43", R["england_adq_share"]), (O, "B50", R["sv_med_total_short"]), (O, "C50", R["sv_med_total_other"]),
    (O, "B51", R["sv_med_access_short"]), (O, "C51", R["sv_med_access_other"]), (O, "B52", R["sv_med_wr_short"]),
    (O, "C52", R["sv_med_wr_other"]), (O, "B54", R["sv_wr_per1000_p80"]), (O, "B55", R["sv_short_top_wr"]),
    (O, "B56", R["shortlist_n"] - R["sv_short_top_wr"]), (O, "B57", R["sv_high_wr_normal_share"]),
    # version 3: second year, recorded patient need, sizing (Python side: src/second_year_casemix.py, src/extended_analysis.py)
    (T2, "V5", Y["practices_all_three"]), (T2, "V6", Y["r_share_year_to_year"]), (T2, "V7", Y["r_share_two_years_apart"]),
    (T2, "V9", Y["y1_short_in_both"]), (T2, "V10", Y["y1short_above998_next_year"]), (T2, "V11", Y["y1short_shortlisted_next_year"]),
    (T2, "V12", Y["y1short_above95_next_year"]), (T2, "V13", Y["unflagged_above998_next_year"]), (T2, "V14", Y["y1short_mean_share_y1"]),
    (T2, "V15", Y["y1short_mean_share_y2"]), (T2, "V17", Y["y0_short_in_all3"]), (T2, "V18", Y["y0short_above998_two_years_later"]),
    (T2, "V19", Y["y0unflagged_above998_two_years_later"]), (T2, "V21", Y["shortlisted_all_three_years"]), (T2, "V22", Y["shortlisted_two_plus_years"]),
    (T2, "V23", Y["y2_short_both_years"]), (T2, "V25", Y["y2_low_in_both"]), (T2, "V26", Y["low_both_years"]),
    (PN, "P5", Y["shortlist_in_casemix"]), (PN, "P6", Y["shortlist_still_above998_casemix"]), (PN, "P7", Y["shortlist_still_above95_casemix"]),
    (PN, "P8", Y["casemix_above998_all"]), (PN, "P9", Y["low_in_casemix"]), (PN, "P10", Y["low_still_below998_casemix"]), (PN, "P11", Y["r_z_before_after_casemix"]),
    (SZ, "G5", R["sizing_by_benchmark"]["England"]["shortlist_part"]), (SZ, "G8", R["sizing_by_benchmark"]["p10"]["shortlist_part"]),
    (SZ, "I7", R["sizing_by_benchmark"]["p25"]["access_pts"]), (SZ, "I8", R["sizing_by_benchmark"]["p10"]["access_pts"]), (SZ, "F6", R["sizing_by_benchmark"]["median"]["benchmark_pct"]),
    (SZ, "B5", R["excess_wr_shortlist"]), (SZ, "B6", R["excess_wr_all_above"]), (SZ, "B7", R["n_above_england"]),
    (SZ, "B10", R["access_pts_if_shortlist_switched"]), (SZ, "B11", R["access_pts_if_all_switched"]), (SZ, "B15", R["low_n"]),
    (SZ, "B16", R["low_med_access_1000"]), (SZ, "B17", R["low_med_wr_1000"]), (SZ, "C16", R["all_med_access_1000"]), (SZ, "C17", R["all_med_wr_1000"]),
]
bad = 0
for chk in checks:
    sh, cell, exp = chk[:3]; tol = chk[3] if len(chk) > 3 else 1e-6
    got = v(sh, cell)
    ok = isinstance(got, (int, float)) and abs(got - exp) <= tol * max(1, abs(exp))
    if not ok:
        bad += 1; print(f"MISMATCH {sh}!{cell}: workbook={got!r} python={exp!r}")
print(f"{len(checks) - bad} of {len(checks)} workbook values match the Python recalculation")
sys.exit(1 if bad else 0)
