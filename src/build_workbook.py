# Internal helper: writes the Excel workbook. All analysis inside the workbook is live Excel formulas.
import glob, os
import numpy as np, pandas as pd
from openpyxl import Workbook
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.chart import BarChart, LineChart, ScatterChart, Reference, Series
from openpyxl.chart.trendline import Trendline
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter as CL
from openpyxl.chart.error_bar import ErrorBars
from openpyxl.chart.data_source import NumDataSource, NumRef
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.line import LineProperties
from openpyxl.chart.label import DataLabel
from openpyxl.chart.trendline import TrendlineLabel
from openpyxl.chart.data_source import NumFmt
from openpyxl.chart.text import RichText as _RT
from openpyxl.drawing.text import Paragraph as _P, ParagraphProperties as _PP, CharacterProperties as _CP


def TLBL():
    """Trend line label as a white box with a red border and bold red text (like the report figures)."""
    return TrendlineLabel(numFmt=NumFmt(formatCode="#,##0.00", sourceLinked=False), spPr=GraphicalProperties(solidFill="FFFFFF", ln=LineProperties(solidFill="C0392B", w=12700)),
                          txPr=_RT(p=[_P(pPr=_PP(defRPr=_CP(sz=1100, b=True, solidFill="C0392B")), endParaRPr=_CP())]))

OUT = "Project1_Antibiotic_Stewardship_12m.xlsx"
INK, TEAL, RED, AMBER, BLUE, GREY, PURP = "0F3D3E", "0F7C7E", "C0392B", "E08E0B", "2F6FB5", "B7C2C3", "6A3D9A"
HEAD = PatternFill("solid", fgColor=INK)
CALC = PatternFill("solid", fgColor="EAF4F4")     # light teal = formula column
note_font = Font(italic=True, size=9, color="555555")

# ---------- data prep (values only; nothing calculated here ends up as a number in the workbook) ----------
import sys, json, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_clean, ROOT, MIN_RATE
os.chdir(ROOT)
rx, steps, ATYP = load_clean(True)
RES = json.load(open("outputs/tables/results.json"))
adq = pd.read_csv("data/raw/abx_12m_adq_watchdrug.csv", dtype={"pc": str})
adq["ym"] = adq.ym.astype(str).str[:4] + "-" + adq.ym.astype(str).str[4:]
rx = rx.merge(adq[["ym", "pc", "adq_A", "adq_W", "adq_R", "adq_O"]], on=["ym", "pc"], how="left")
assert rx.adq_A.notna().all()
rx = rx.sort_values(["pc", "ym"]).reset_index(drop=True)
imd_tab = pd.read_csv("outputs/tables/practices_12m_v2.csv", dtype={"pc": str}).set_index("pc")[["imd", "imd_coverage"]]
drug_tab = pd.read_csv("outputs/tables/watch_drugs_12m.csv")
pcs = rx.groupby("pc", sort=True).agg(pn=("pn", "last"), icb=("icb", "last")).reset_index()   # latest name and ICB (some ICBs merged during the year)
NP, ND = len(pcs), len(rx)
months = sorted(rx["ym"].unique())
assert ND == 12 * NP and all(rx["ym"].values[10::12] == "2026-07")

age = pd.read_csv("data/raw/gp-reg-pat-prac-quin-age.csv", dtype=str)
age = age[(age.ORG_TYPE == "GP") & (age.SEX != "ALL") & (age.AGE_GROUP_5 != "ALL")]
age["n"] = age.NUMBER_OF_PATIENTS.astype(int)
bands = ["0_4", "5_9", "10_14", "15_19", "20_24", "25_29", "30_34", "35_39", "40_44", "45_49", "50_54", "55_59",
         "60_64", "65_69", "70_74", "75_79", "80_84", "85_89", "90_94", "95+"]
ag = age.pivot_table(index="ORG_CODE", columns="AGE_GROUP_5", values="n", aggfunc="sum").fillna(0)[bands].astype(int)
ag = ag.loc[ag.index.isin(pcs.pc)].reset_index()
NA = len(ag)
icbs = pd.read_csv("outputs/tables/icb_12m_v2.csv").sort_values("share")   # only used for row ORDER (low -> high)
icbs["icb_short"] = icbs.icb.str.replace("NHS ", "", regex=False).str.replace(" INTEGRATED CARE BOARD", "", regex=False).str.title()
mapping = pd.read_csv("data/aware_mapping.csv")


def dl():
    d = DataLabelList(); d.showVal = True
    d.showSerName = False; d.showCatName = False; d.showLegendKey = False; d.showPercent = False; d.showLeaderLines = False
    return d


def box_stats(ws, r, key, grp, val, c0):
    """Write box-plot numbers for one group into row r, starting at column c0.
    grp/val are full ranges; key is the cell holding this group's label."""
    L = [CL(c0 + i) for i in range(12)]   # Q1 Med Q3 IQR LowW UpW Outliers | base lowbox highbox errminus errplus
    for q, col in zip([1, 2, 3], L[:3]):
        ws[f"{col}{r}"] = ArrayFormula(f"{col}{r}", f"=_xlfn.QUARTILE.INC(IF({grp}={key},{val}),{q})")
    ws[f"{L[3]}{r}"] = f"={L[2]}{r}-{L[0]}{r}"
    ws[f"{L[4]}{r}"] = ArrayFormula(f"{L[4]}{r}", f"=MIN(IF(({grp}={key})*({val}>={L[0]}{r}-1.5*{L[3]}{r}),{val}))")
    ws[f"{L[5]}{r}"] = ArrayFormula(f"{L[5]}{r}", f"=MAX(IF(({grp}={key})*({val}<={L[2]}{r}+1.5*{L[3]}{r}),{val}))")
    ws[f"{L[6]}{r}"] = f'=COUNTIFS({grp},{key},{val},">"&{L[5]}{r})+COUNTIFS({grp},{key},{val},"<"&{L[4]}{r})'
    ws[f"{L[7]}{r}"] = f"={L[0]}{r}"
    ws[f"{L[8]}{r}"] = f"={L[1]}{r}-{L[0]}{r}"
    ws[f"{L[9]}{r}"] = f"={L[2]}{r}-{L[1]}{r}"
    ws[f"{L[10]}{r}"] = f"={L[0]}{r}-{L[4]}{r}"
    ws[f"{L[11]}{r}"] = f"={L[5]}{r}-{L[2]}{r}"
    for i, col in enumerate(L):
        ws[f"{col}{r}"].fill = CALC; ws[f"{col}{r}"].number_format = "0" if i == 6 else "0.0"


BOX_HEAD = ["Q1 (25%)", "Median", "Q3 (75%)", "IQR = Q3-Q1", "Lower whisker", "Upper whisker", "Unusual practices (dots)",
            "chart: base = Q1", "chart: Median-Q1", "chart: Q3-Median", "chart: Q1-Lower", "chart: Upper-Q3"]


def box_chart(ws, title_, cat_ref, r1, r2, c0, light, dark, ytitle, ymin=None, ymax=None, w=17, h=9):
    """Classic Excel box plot: stacked columns (invisible base + two box halves) with error bars as whiskers."""
    sh = f"'{ws.title}'"
    ch = BarChart(); ch.type = "col"; ch.grouping = "stacked"; ch.overlap = 100; ch.gapWidth = 60
    ch.title = title_; ch.width = w; ch.height = h; ch.legend = None; ch.y_axis.title = ytitle
    for i, fill in enumerate([None, light, dark]):
        ser = Series(Reference(ws, min_col=c0 + 7 + i, min_row=r1, max_row=r2), title=f"part{i}")
        if fill is None:
            ser.graphicalProperties.noFill = True; ser.graphicalProperties.line.noFill = True
            ser.errBars = ErrorBars(errDir="y", errBarType="minus", errValType="cust", noEndCap=False,
                                    minus=NumDataSource(numRef=NumRef(f=f"{sh}!${CL(c0+10)}${r1}:${CL(c0+10)}${r2}")))
        else:
            ser.graphicalProperties.solidFill = fill; ser.graphicalProperties.line.solidFill = "FFFFFF"; ser.graphicalProperties.line.width = 19050
        if i == 2:
            ser.errBars = ErrorBars(errDir="y", errBarType="plus", errValType="cust", noEndCap=False,
                                    plus=NumDataSource(numRef=NumRef(f=f"{sh}!${CL(c0+11)}${r1}:${CL(c0+11)}${r2}")))
        ch.series.append(ser)
    ch.set_categories(cat_ref)
    if ymin is not None: ch.y_axis.scaling.min = ymin
    if ymax is not None: ch.y_axis.scaling.max = ymax
    ch.y_axis.numFmt = "0"
    return ch


wb = Workbook()


def header(ws, row, names, widths=None):
    for j, n in enumerate(names, 1):
        c = ws.cell(row, j, n); c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD
        c.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 32
    if widths:
        for j, w in enumerate(widths, 1): ws.column_dimensions[CL(j)].width = w


def title(ws, text, sub=""):
    ws["A1"] = text; ws["A1"].font = Font(bold=True, size=15, color=INK)
    if sub: ws["A2"] = sub; ws["A2"].font = note_font


# ================= Data =================
D = wb.active; D.title = "Data"
cols = ["Month", "Practice code", "Practice name", "ICB", "List month used", "Patients", "Access items", "Watch items",
        "Reserve items", "Other items", "Lymecycline items (already inside Watch)", "Classified items", "Watch+Reserve items", "W+R %", "Top fifth this month? (1=yes)",
        "W+R % without lymecycline", "Top fifth without lymecycline? (1=yes)", "Same practice's flag next month", "Sampling variance of W+R share = p(1-p)/n",
        "Half of year (1 = Sep-Feb, 2 = Mar-Aug)", "ADQ Access", "ADQ Watch", "ADQ Reserve", "ADQ Other", "W+R % by dose (ADQ)", "Top fifth by dose? (1=yes)"]
header(D, 1, cols, [9, 10, 30, 34, 10, 10, 9, 9, 9, 9, 10, 10, 10, 8, 11, 11, 11, 11, 12, 10, 10, 10, 10, 10, 10, 10])
DE = ND + 1
for i, r in enumerate(rx.itertuples(index=False), start=2):
    D.cell(i, 1, r.ym); D.cell(i, 2, r.pc); D.cell(i, 3, r.pn); D.cell(i, 4, r.icb); D.cell(i, 5, r.list_month)
    D.cell(i, 6, int(r.patients)); D.cell(i, 7, int(r.access_items)); D.cell(i, 8, int(r.watch_items))
    D.cell(i, 9, int(r.reserve_items)); D.cell(i, 10, int(r.other_items)); D.cell(i, 11, int(r.lyme_items))
    D.cell(i, 12, f"=G{i}+H{i}+I{i}+J{i}"); D.cell(i, 13, f"=H{i}+I{i}"); D.cell(i, 14, f"=M{i}/L{i}*100")
    D.cell(i, 15, f"=IF(N{i}>=INDEX('1 Monthly'!$L$5:$L$16,MATCH(A{i},'1 Monthly'!$A$5:$A$16,0)),1,0)")
    D.cell(i, 16, f"=(M{i}-K{i})/(L{i}-K{i})*100")
    D.cell(i, 17, f"=IF(P{i}>=INDEX('1 Monthly'!$AA$5:$AA$16,MATCH(A{i},'1 Monthly'!$A$5:$A$16,0)),1,0)")
    D.cell(i, 18, f'=IF(B{i+1}=B{i},O{i+1},"")')
    D.cell(i, 19, f"=(N{i}/100)*(1-N{i}/100)/L{i}")
    D.cell(i, 20, 1 if r.ym <= "2026-02" else 2)
    D.cell(i, 21, round(float(r.adq_A), 2)); D.cell(i, 22, round(float(r.adq_W), 2))
    D.cell(i, 23, round(float(r.adq_R), 2)); D.cell(i, 24, round(float(r.adq_O), 2))
    D.cell(i, 25, f"=(V{i}+W{i})/SUM(U{i}:X{i})*100")
    D.cell(i, 26, f"=IF(Y{i}>=INDEX('1 Monthly'!$AE$5:$AE$16,MATCH(A{i},'1 Monthly'!$A$5:$A$16,0)),1,0)")
D.freeze_panes = "A2"
for c in "LMNOPQRS": D.column_dimensions[c].width = 11

# ================= 1 Monthly =================
M = wb.create_sheet("1 Monthly")
title(M, "1 · Monthly trend for England", "Each row adds up all practices for one month with SUMIFS. Light-teal cells are formulas.")
header_row = 4
header(M, header_row, ["Month", "Practices", "Classified items", "Patients", "Access items", "W+R items", "Lymecycline items",
                       "Items per 1,000 patients", "Access %", "W+R %", "W+R % excl. lymecycline", "Top-fifth cut-off (80th percentile of practice W+R %)"],
       [9, 10, 13, 13, 12, 11, 12, 12, 9, 9, 12, 20])
rng = lambda c: f"Data!${c}$2:${c}${DE}"
for k, mo in enumerate(months):
    r = header_row + 1 + k
    M.cell(r, 1, mo)
    M.cell(r, 2, f"=COUNTIF({rng('A')},A{r})")
    M.cell(r, 3, f"=SUMIFS({rng('L')},{rng('A')},A{r})")
    M.cell(r, 4, f"=SUMIFS({rng('F')},{rng('A')},A{r})")
    M.cell(r, 5, f"=SUMIFS({rng('G')},{rng('A')},A{r})")
    M.cell(r, 6, f"=SUMIFS({rng('M')},{rng('A')},A{r})")
    M.cell(r, 7, f"=SUMIFS({rng('K')},{rng('A')},A{r})")
    M.cell(r, 8, f"=C{r}/D{r}*1000"); M.cell(r, 9, f"=E{r}/C{r}*100"); M.cell(r, 10, f"=F{r}/C{r}*100")
    M.cell(r, 11, f"=(F{r}-G{r})/(C{r}-G{r})*100")
    M.cell(r, 26, f'=TEXT(DATE(LEFT(A{r},4),RIGHT(A{r},2),1),"mmm yy")')
    M[f"L{r}"] = ArrayFormula(f"L{r}", f"=_xlfn.PERCENTILE.INC(IF({rng('A')}=A{r},{rng('N')}),0.8)")
    M[f"AA{r}"] = ArrayFormula(f"AA{r}", f"=_xlfn.PERCENTILE.INC(IF({rng('A')}=A{r},{rng('P')}),0.8)")
    M[f"AA{r}"].fill = CALC; M[f"AA{r}"].number_format = "0.00"
    # noise share for this month: average sampling variance / variance of practice shares
    M[f"AB{r}"] = f"=AVERAGEIFS({rng('S')},{rng('A')},A{r})"
    M[f"AC{r}"] = ArrayFormula(f"AC{r}", f"=_xlfn.VAR.S(IF({rng('A')}=A{r},{rng('N')}/100))")
    M[f"AD{r}"] = f"=AB{r}/AC{r}"
    M[f"AE{r}"] = ArrayFormula(f"AE{r}", f"=_xlfn.PERCENTILE.INC(IF({rng('A')}=A{r},{rng('Y')}),0.8)")
    M[f"AE{r}"].fill = CALC; M[f"AE{r}"].number_format = "0.00"
    for c_ in ("AB", "AC", "AD"): M[f"{c_}{r}"].fill = CALC; M[f"{c_}{r}"].number_format = "0.000000" if c_ != "AD" else "0.0%"
    for c in range(2, 13):
        M.cell(r, c).fill = CALC; M.cell(r, c).number_format = "#,##0" if c <= 7 else "0.00"
M["A18"] = "Formulas:  Items per 1,000 = C/D×1000   ·   W+R % = F/C×100   ·   Top-fifth cut-off = PERCENTILE.INC(this month's practice W+R %, 0.8) — an array formula."
M["A18"].font = note_font
ch = BarChart(); ch.title = "Antibiotic items per 1,000 patients"; ch.height = 7.5; ch.width = 16; ch.legend = None
ch.add_data(Reference(M, min_col=8, min_row=4, max_row=16), titles_from_data=True); ch.set_categories(Reference(M, min_col=26, min_row=5, max_row=16))
ch.series[0].graphicalProperties.solidFill = BLUE; ch.dataLabels = dl(); ch.y_axis.numFmt = "0"
M.add_chart(ch, "A20")
ln = LineChart(); ln.title = "Watch+Reserve share % (lowest in winter)"; ln.height = 7.5; ln.width = 16
ln.add_data(Reference(M, min_col=10, min_row=4, max_row=16), titles_from_data=True)
ln.add_data(Reference(M, min_col=11, min_row=4, max_row=16), titles_from_data=True)
ln.set_categories(Reference(M, min_col=26, min_row=5, max_row=16)); ln.y_axis.scaling.min = 14; ln.y_axis.scaling.max = 20
ln.series[0].graphicalProperties.line.solidFill = RED; ln.series[1].graphicalProperties.line.solidFill = PURP
ln.series[1].graphicalProperties.line.dashStyle = "dash"; ln.legend.position = "b"
for s_ in ln.series: s_.smooth = False
M.add_chart(ln, "J20")
M.cell(4, 14).value = None
for j, h in enumerate(BOX_HEAD):
    c = M.cell(4, 14 + j, "Practice W+R %: " + h); c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, vertical="center")
    M.column_dimensions[CL(14 + j)].width = 12
M.row_dimensions[4].height = 48
for j, h_ in enumerate(["Top-fifth cut-off without lymecycline", "Average sampling variance (noise)", "Variance of practice shares (total)", "Noise share = noise ÷ total", "Top-fifth cut-off by dose (ADQ)"]):
    c = M.cell(4, 27 + j, h_); c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, vertical="center")
    M.column_dimensions[CL(27 + j)].width = 14
M.cell(4, 26, "Month label")
for k in range(12):
    box_stats(M, 5 + k, f"A{5+k}", rng("A"), rng("N"), 14)
box_month = box_chart(M, "Box plot: practice W+R % each month — the whole spread, not just the average",
                      Reference(M, min_col=26, min_row=5, max_row=16), 5, 16, 14, "F2B8B0", RED, "Practice W+R %", 0, 40, w=30, h=9)
M.add_chart(box_month, "A37")
monthly_chart_bar, monthly_chart_line = ch, ln

# ================= 2 Practices =================
P = wb.create_sheet("2 Practices")
pcols = ["Practice code", "Practice name", "ICB", "Classified items (12m)", "Access items", "W+R items", "Lymecycline items",
         "Average patients", "Items per 1,000 per year", "W+R %", "ICB W+R %", "Gap vs ICB (items)", "Months in top fifth",
         "% aged 65+", "% aged 15-24", "% aged 0-9", "Age fifth (1=youngest)", "July W+R items", "July classified items",
         "July gap vs ICB", "Rank: 12-month gap", "Rank: July-only gap",
         "W+R % first half (Sep-Feb)", "W+R % second half (Mar-Aug)", "W+R % without lymecycline", "Months in top fifth without lymecycline",
         "W+R % by dose (ADQ)", "Other items", "Lymecycline % of items",
         "IMD 2025 score (patient-weighted)", "% aged 65+ (copy for regression)", "log10(practice size)", "ICB W+R % (copy for regression)",
         "Standard error if at England rate", "z (plain funnel)", "z adjusted for over-dispersion", "Winsorised z", "Weight 1/SE²",
         "Above 99.8% funnel limit? (1=yes)", "Review shortlist? (funnel + 9+ months + 9+ without lymecycline)", "Shortlist rank (by adjusted z)", "IMD fifth (1=least deprived)",
         "Months in top fifth by dose (ADQ)", "SE if at own ICB rate", "z vs own ICB (plain)", "Winsorised z vs ICB", "Weight vs ICB 1/SE²",
         "z vs own ICB, adjusted", "Above 99.8% limit vs own ICB? (1=yes)", "Shortlist using own-ICB funnel? (1=yes)", "ICB W+R % excluding this practice",
         "IMD (copy)", "% aged 65+ (copy)", "log10 size (copy)", "ICB W+R % excl. this practice (copy)",
         "Chart: W+R % if above 99.8% only (#N/A = not plotted)", "Chart: W+R % if on review shortlist (#N/A = not plotted)",
         "Sep-Feb W+R items", "Sep-Feb classified items", "Mar-Aug W+R items", "Mar-Aug classified items",
         "Sep-Feb months in top fifth (of 6)", "Sep-Feb months in top fifth without lymecycline", "Mar-Aug months in top fifth (of 6)",
         "Sep-Feb SE", "Sep-Feb z (plain)", "Sep-Feb winsorised z", "Sep-Feb weight", "Sep-Feb z adjusted",
         "Flagged on Sep-Feb only? (z>3.09, 5+ of 6 months, 5+ without lymecycline)",
         "Mar-Aug SE", "Mar-Aug z (plain)", "Mar-Aug winsorised z", "Mar-Aug weight", "Mar-Aug z adjusted", "Mar-Aug W+R %"]
header(P, 1, pcols, [10, 30, 34, 11, 10, 10, 10, 10, 10, 8, 8, 10, 9, 8, 8, 8, 9, 9, 10, 9, 9, 9] + [11] * 57)
P.row_dimensions[1].height = 60
PE = NP + 1
for i, r in enumerate(pcs.itertuples(index=False), start=2):
    s = 2 + 12 * (i - 2); e = s + 11; j = s + 10
    P.cell(i, 1, r.pc); P.cell(i, 2, r.pn); P.cell(i, 3, r.icb)
    P.cell(i, 4, f"=SUM(Data!L{s}:L{e})"); P.cell(i, 5, f"=SUM(Data!G{s}:G{e})"); P.cell(i, 6, f"=SUM(Data!M{s}:M{e})")
    P.cell(i, 7, f"=SUM(Data!K{s}:K{e})"); P.cell(i, 8, f"=AVERAGE(Data!F{s}:F{e})")
    P.cell(i, 9, f"=D{i}/H{i}*1000"); P.cell(i, 10, f"=F{i}/D{i}*100")
    P.cell(i, 11, f"=INDEX('3 ICB'!$F$5:$F$40,MATCH(C{i},'3 ICB'!$A$5:$A$40,0))")
    P.cell(i, 12, f"=F{i}-D{i}*K{i}/100"); P.cell(i, 13, f"=SUM(Data!O{s}:O{e})")
    P.cell(i, 14, f"=INDEX('Age data'!$X$2:$X${NA+1},MATCH(A{i},'Age data'!$A$2:$A${NA+1},0))")
    P.cell(i, 15, f"=INDEX('Age data'!$Y$2:$Y${NA+1},MATCH(A{i},'Age data'!$A$2:$A${NA+1},0))")
    P.cell(i, 16, f"=INDEX('Age data'!$Z$2:$Z${NA+1},MATCH(A{i},'Age data'!$A$2:$A${NA+1},0))")
    P.cell(i, 17, f"=MATCH(N{i},'5 Age'!$B$14:$B$18,1)")
    P.cell(i, 18, f"=Data!M{j}"); P.cell(i, 19, f"=Data!L{j}"); P.cell(i, 20, f"=R{i}-S{i}*K{i}/100")
    P.cell(i, 21, f"=RANK(L{i},$L$2:$L${PE})"); P.cell(i, 22, f"=RANK(T{i},$T$2:$T${PE})")
    h1e = s + 5; h2s = s + 6
    P.cell(i, 23, f"=SUM(Data!M{s}:M{h1e})/SUM(Data!L{s}:L{h1e})*100")
    P.cell(i, 24, f"=SUM(Data!M{h2s}:M{e})/SUM(Data!L{h2s}:L{e})*100")
    P.cell(i, 25, f"=(F{i}-G{i})/(D{i}-G{i})*100")
    P.cell(i, 26, f"=SUM(Data!Q{s}:Q{e})")
    P.cell(i, 27, f"=(SUM(Data!V{s}:V{e})+SUM(Data!W{s}:W{e}))/SUM(Data!U{s}:X{e})*100")
    P.cell(i, 28, f"=SUM(Data!J{s}:J{e})")
    P.cell(i, 29, f"=G{i}/D{i}*100")
    P.cell(i, 30, f"=INDEX('IMD data'!$B$2:$B${NP+1},MATCH(A{i},'IMD data'!$A$2:$A${NP+1},0))")
    P.cell(i, 31, f"=N{i}"); P.cell(i, 32, f"=LOG10(H{i})"); P.cell(i, 33, f"=K{i}")
    P.cell(i, 34, f"=SQRT('9 Funnel'!$B$5*(1-'9 Funnel'!$B$5)/D{i})")
    P.cell(i, 35, f"=(J{i}/100-'9 Funnel'!$B$5)/AH{i}")
    P.cell(i, 36, f"=(J{i}/100-'9 Funnel'!$B$5)/SQRT(AH{i}^2+'9 Funnel'!$B$13)")
    P.cell(i, 37, f"=MIN(MAX(AI{i},'9 Funnel'!$B$8),'9 Funnel'!$B$9)")
    P.cell(i, 38, f"=1/AH{i}^2")
    P.cell(i, 39, f"=IF(AJ{i}>3.09,1,0)")
    P.cell(i, 40, f"=IF(AND(AM{i}=1,M{i}>=9,Z{i}>=9),1,0)")
    P.cell(i, 41, f'=IF(AN{i}=1,COUNTIFS($AN$2:$AN${PE},1,$AJ$2:$AJ${PE},">"&AJ{i})+1,"")')
    P.cell(i, 42, f"=MATCH(AD{i},'11 Deprivation'!$B$22:$B$26,1)")
    P.cell(i, 43, f"=SUM(Data!Z{s}:Z{e})")
    P.cell(i, 44, f"=SQRT(K{i}/100*(1-K{i}/100)/D{i})")
    P.cell(i, 45, f"=(J{i}-K{i})/100/AR{i}")
    P.cell(i, 46, f"=MIN(MAX(AS{i},'9 Funnel'!$B$60),'9 Funnel'!$B$61)")
    P.cell(i, 47, f"=1/AR{i}^2")
    P.cell(i, 48, f"=(J{i}-K{i})/100/SQRT(AR{i}^2+'9 Funnel'!$B$65)")
    P.cell(i, 49, f"=IF(AV{i}>3.09,1,0)")
    P.cell(i, 50, f"=IF(AND(AW{i}=1,M{i}>=9,Z{i}>=9),1,0)")
    P.cell(i, 51, f"=(SUMIFS($F$2:$F${PE},$C$2:$C${PE},C{i})-F{i})/(SUMIFS($D$2:$D${PE},$C$2:$C${PE},C{i})-D{i})*100")
    P.cell(i, 52, f"=AD{i}"); P.cell(i, 53, f"=N{i}"); P.cell(i, 54, f"=AF{i}"); P.cell(i, 55, f"=AY{i}")
    P.cell(i, 56, f"=IF(AND(AM{i}=1,AN{i}=0),J{i},NA())"); P.cell(i, 57, f"=IF(AN{i}=1,J{i},NA())")
    # out-of-sample: flag using Sep-Feb only, then look at Mar-Aug ('14 Out of sample' holds p0, winsor cut-offs and tau2)
    O = "'14 Out of sample'!"
    P.cell(i, 58, f"=SUM(Data!M{s}:M{h1e})"); P.cell(i, 59, f"=SUM(Data!L{s}:L{h1e})")
    P.cell(i, 60, f"=SUM(Data!M{h2s}:M{e})"); P.cell(i, 61, f"=SUM(Data!L{h2s}:L{e})")
    P.cell(i, 62, f"=SUM(Data!O{s}:O{h1e})"); P.cell(i, 63, f"=SUM(Data!Q{s}:Q{h1e})"); P.cell(i, 64, f"=SUM(Data!O{h2s}:O{e})")
    P.cell(i, 65, f"=SQRT({O}$B$5*(1-{O}$B$5)/BG{i})"); P.cell(i, 66, f"=(BF{i}/BG{i}-{O}$B$5)/BM{i}")
    P.cell(i, 67, f"=MIN(MAX(BN{i},{O}$B$6),{O}$B$7)"); P.cell(i, 68, f"=1/BM{i}^2")
    P.cell(i, 69, f"=(BF{i}/BG{i}-{O}$B$5)/SQRT(BM{i}^2+{O}$B$11)")
    P.cell(i, 70, f"=IF(AND(BQ{i}>3.09,BJ{i}>=5,BK{i}>=5),1,0)")
    P.cell(i, 71, f"=SQRT({O}$C$5*(1-{O}$C$5)/BI{i})"); P.cell(i, 72, f"=(BH{i}/BI{i}-{O}$C$5)/BS{i}")
    P.cell(i, 73, f"=MIN(MAX(BT{i},{O}$C$6),{O}$C$7)"); P.cell(i, 74, f"=1/BS{i}^2")
    P.cell(i, 75, f"=(BH{i}/BI{i}-{O}$C$5)/SQRT(BS{i}^2+{O}$C$11)"); P.cell(i, 76, f"=BH{i}/BI{i}*100")
P.freeze_panes = "D2"
for c in range(4, 23):
    for rr in (2,):
        pass
for c, fmt in zip("DEFGHIJKLMNOPQRSTUV", ["#,##0"] * 5 + ["0.0", "0.00", "0.00", "0.0", "0", "0.0", "0.0", "0.0", "0", "0", "0", "0.0", "0", "0"]):
    for rr in range(2, PE + 1):
        P[f"{c}{rr}"].number_format = fmt
for j, fmt in enumerate(["0.00", "0.00", "0.00", "0", "0.00", "#,##0", "0.0", "0.0", "0.0", "0.000", "0.00", "0.00000", "0.00", "0.00", "0.00",
                         "#,##0", "0", "0", "0", "0", "0", "0.00000", "0.00", "0.00", "#,##0", "0.00", "0", "0", "0.00", "0.0", "0.0", "0.000", "0.00"], start=23):
    for rr in range(2, PE + 1):
        P.cell(rr, j).number_format = fmt
P.conditional_formatting.add(f"J2:J{PE}", ColorScaleRule(start_type="percentile", start_value=5, start_color="E8F5E9",
                                                          mid_type="percentile", mid_value=50, mid_color="FFF59D",
                                                          end_type="percentile", end_value=95, end_color="EF9A9A"))
P.conditional_formatting.add(f"M2:M{PE}", ColorScaleRule(start_type="num", start_value=0, start_color="FFFFFF", end_type="num", end_value=12, end_color="EF9A9A"))

# ================= 3 ICB =================
I = wb.create_sheet("3 ICB")
title(I, "3 · ICB (local area) comparison over 12 months", "Adds up the practices in each ICB with SUMIFS on '2 Practices'. Sorted lowest to highest W+R %.")
header(I, 4, ["ICB", "ICB (short)", "Practices", "Classified items", "W+R items", "W+R %", "Patients", "Items per 1,000 per year", "Difference from England (points)"],
       [40, 30, 9, 13, 11, 8, 13, 12, 13])
pr = lambda c: f"'2 Practices'!${c}$2:${c}${PE}"
for k, row in enumerate(icbs.itertuples(index=False)):
    r = 5 + k
    I.cell(r, 1, row.icb); I.cell(r, 2, row.icb_short)
    I.cell(r, 3, f"=COUNTIF({pr('C')},A{r})"); I.cell(r, 4, f"=SUMIFS({pr('D')},{pr('C')},A{r})")
    I.cell(r, 5, f"=SUMIFS({pr('F')},{pr('C')},A{r})"); I.cell(r, 6, f"=E{r}/D{r}*100")
    I.cell(r, 7, f"=SUMIFS({pr('H')},{pr('C')},A{r})"); I.cell(r, 8, f"=D{r}/G{r}*1000"); I.cell(r, 9, f"=F{r}-Dashboard!$K$6")
    for c in range(3, 10):
        I.cell(r, c).fill = CALC; I.cell(r, c).number_format = "#,##0" if c in (3, 4, 5, 7) else "0.00"
I.conditional_formatting.add("F5:F40", ColorScaleRule(start_type="min", start_color="D7F0EC", end_type="max", end_color="EF9A9A"))
ic = BarChart(); ic.type = "bar"; ic.title = "Watch+Reserve % by ICB, Sep 2025–Aug 2026"; ic.height = 22; ic.width = 18; ic.legend = None
ic.add_data(Reference(I, min_col=6, min_row=4, max_row=40), titles_from_data=True); ic.set_categories(Reference(I, min_col=2, min_row=5, max_row=40))
ic.series[0].graphicalProperties.solidFill = RED; ic.dataLabels = dl(); ic.x_axis.tickLblPos = "low"; ic.y_axis.scaling.min = 0; ic.y_axis.scaling.max = 25; ic.y_axis.majorUnit = 5
ic.y_axis.numFmt = "0"
I.add_chart(ic, "K4")

# ================= 4 Consistency =================
C = wb.create_sheet("4 Consistency")
title(C, "4 · (Earlier approach, kept for comparison) Is a high Watch share a lasting habit or a one-month fluke?",
      "Each month the top fifth (20%) of practices by W+R % are flagged (Data column O). Here we count how many of the 12 months each practice was flagged.")
header(C, 4, ["Months in top fifth (out of 12)", "Practices (actual)", "Chance if pure luck", "Practices expected by luck"], [16, 14, 14, 16])
for k in range(13):
    r = 5 + k
    C.cell(r, 1, k); C.cell(r, 2, f"=COUNTIF({pr('M')},A{r})")
    C.cell(r, 3, f"=_xlfn.BINOM.DIST(A{r},12,0.2,FALSE)"); C.cell(r, 4, f"=C{r}*$B$20")
    for c in (2, 3, 4): C.cell(r, c).fill = CALC
    C.cell(r, 3).number_format = "0.000000"; C.cell(r, 4).number_format = "0.0"
C["A20"] = "Total practices"; C["B20"] = f"=SUM(B5:B17)"
C["A22"] = "In top fifth 9+ months"; C["B22"] = f"=COUNTIF({pr('M')},\">=9\")"
C["A23"] = "In top fifth all 12 months"; C["B23"] = f"=COUNTIF({pr('M')},12)"
C["A24"] = "Expected 9+ by luck alone"; C["B24"] = "=(1-_xlfn.BINOM.DIST(8,12,0.2,TRUE))*B20"; C["B24"].number_format = "0.00"
C["A26"] = "July top-15 still in 12-month top-15"; C["B26"] = f"=SUMPRODUCT(({pr('U')}<=15)*({pr('V')}<=15))"
for c in ("B20", "B22", "B23", "B24", "B26"): C[c].fill = CALC; C[c].font = Font(bold=True)
for c in ("A20", "A22", "A23", "A24", "A26"): C[c].font = Font(bold=True)
C.column_dimensions["A"].width = 34
C["A28"] = ("How to read 'chance if pure luck': if being in the top fifth were random, each month would be a 1-in-5 draw. "
            "BINOM.DIST(k, 12, 0.2) gives the chance of exactly k hits out of 12. Multiply by the number of practices to get how many you'd expect. "
            "WARNING: this is a weak test. It only shows that practices differ from each other, which nobody doubts. The stronger evidence "
            "is in sheet 8 (split-half r and noise share) and sheet 9 (adjusted funnel plot).")
C["A28"].font = note_font; C["A28"].alignment = Alignment(wrap_text=True); C.merge_cells("A28:H31")
cc = BarChart(); cc.title = "Practices by months in the top fifth"; cc.height = 8; cc.width = 18
cc.add_data(Reference(C, min_col=2, min_row=4, max_row=17), titles_from_data=True)
cc.add_data(Reference(C, min_col=4, min_row=4, max_row=17), titles_from_data=True)
cc.set_categories(Reference(C, min_col=1, min_row=5, max_row=17)); cc.series[0].graphicalProperties.solidFill = RED
cc.series[1].graphicalProperties.solidFill = GREY; cc.legend.position = "b"; cc.x_axis.title = "Months in top fifth"
C.add_chart(cc, "F4")

# ================= 5 Age =================
A = wb.create_sheet("5 Age")
title(A, "5 · Age: scatter with trendline, R², and age fifths", "x = % aged 65+ (July 2026 age bands), y = items per 1,000 patients per year.")
lab = [("Slope (how much y rises per +1% over-65s)", f"=SLOPE({pr('I')},{pr('N')})", "0.00"),
       ("Intercept (y when x = 0)", f"=INTERCEPT({pr('I')},{pr('N')})", "0.0"),
       ("R² (share of differences in rate lined up with age)", f"=RSQ({pr('I')},{pr('N')})", "0.00"),
       ("r: % aged 65+ vs rate", f"=CORREL({pr('N')},{pr('I')})", "0.00"),
       ("r: % aged 65+ vs W+R %", f"=CORREL({pr('N')},{pr('J')})", "0.00"),
       ("Slope standard error (LINEST)", f"=INDEX(LINEST({pr('I')},{pr('N')},TRUE,TRUE),2,1)", "0.000"),
       ("Slope 95% CI low", "=B4-1.96*B9", "0.00"), ("Slope 95% CI high", "=B4+1.96*B9", "0.00"),
       ("p-value for r(% 65+, W+R %): significant but tiny", f"=_xlfn.T.DIST.2T(ABS(B8)*SQRT((COUNT({pr('J')})-2)/(1-B8^2)),COUNT({pr('J')})-2)", "0.0000")]
for k, (t, f, fmt) in enumerate(lab):
    A.cell(4 + k, 1, t).font = Font(bold=True); A.cell(4 + k, 2, f).fill = CALC; A.cell(4 + k, 2).number_format = fmt
A["D4"] = '=\"Trendline:  y = \"&TEXT(B4,\"0.00\")&\"x + \"&TEXT(B5,\"0.0\")&\"     R² = \"&TEXT(B6,\"0.00\")'
A["D4"].font = Font(bold=True, color=RED, size=12)
A.column_dimensions["A"].width = 48; A.column_dimensions["B"].width = 12
header(A, 13, ["Age fifth", "Starts at % aged 65+", "Practices", "Average % aged 65+", "Classified items", "Patients",
               "W+R items", "Items per 1,000 per year", "W+R %"] + ["W+R %: " + h for h in BOX_HEAD])
for c, w in zip("CDEFGHI", [10, 10, 12, 12, 11, 12, 8]): A.column_dimensions[c].width = w
for c in range(10, 23): A.column_dimensions[CL(c)].width = 12
A.row_dimensions[13].height = 48; A.row_dimensions[21].height = 48
for k in range(5):
    r = 14 + k
    A.cell(r, 1, k + 1)
    A.cell(r, 2, f"=MIN({pr('N')})" if k == 0 else f"=_xlfn.PERCENTILE.INC({pr('N')},{k/5})")
    A.cell(r, 3, f"=COUNTIF({pr('Q')},A{r})"); A.cell(r, 4, f"=AVERAGEIFS({pr('N')},{pr('Q')},A{r})")
    A.cell(r, 5, f"=SUMIFS({pr('D')},{pr('Q')},A{r})"); A.cell(r, 6, f"=SUMIFS({pr('H')},{pr('Q')},A{r})")
    A.cell(r, 7, f"=SUMIFS({pr('F')},{pr('Q')},A{r})"); A.cell(r, 8, f"=E{r}/F{r}*1000"); A.cell(r, 9, f"=G{r}/E{r}*100")
    for c in range(2, 10):
        A.cell(r, c).fill = CALC; A.cell(r, c).number_format = "#,##0" if c in (3, 5, 6, 7) else "0.0"
    box_stats(A, r, f"A{r}", pr("Q"), pr("J"), 10)          # W+R % box numbers in J:U
    A.cell(r, 22, ["1 Youngest", "2", "3", "4", "5 Oldest"][k])
header(A, 21, ["Age fifth", "", "", "", "", "", "", "", ""] + ["Rate: " + h for h in BOX_HEAD])
for k in range(5):
    r = 22 + k
    A.cell(r, 1, k + 1)
    box_stats(A, r, f"A{r}", pr("Q"), pr("I"), 10)          # rate box numbers in J:U
    A.cell(r, 22, ["1 Youngest", "2", "3", "4", "5 Oldest"][k])
A["A28"] = ("How the box plots are drawn: Excel stacks three columns per group: an invisible one up to Q1, then Q1→Median, then Median→Q3 "
            "(the box). Error bars draw the whiskers down to the lower whisker and up to the upper whisker. Whiskers stop at 1.5 × IQR beyond the box; "
            "practices past that are 'unusual' (counted in the 'Unusual practices' column). The scatter title shows the same trendline as cell A10, which is the live formula version.")
A["A28"].font = note_font; A["A28"].alignment = Alignment(wrap_text=True); A.merge_cells("A28:U29")
sc = ScatterChart(); sc.title = "% aged 65+ vs items per 1,000 per year"; sc.style = 13; sc.height = 10; sc.width = 17
sc.x_axis.title = "% aged 65+ (x)"; sc.y_axis.title = "Items per 1,000 per year (y)"
s = Series(Reference(P, min_col=9, min_row=2, max_row=PE), Reference(P, min_col=14, min_row=2, max_row=PE), title="Practices")
s.marker.symbol = "circle"; s.marker.size = 3; s.graphicalProperties.line.noFill = True
s.marker.graphicalProperties.solidFill = TEAL; s.marker.graphicalProperties.line.solidFill = TEAL
s.trendline = Trendline(trendlineType="linear", dispEq=True, dispRSqr=True, spPr=GraphicalProperties(ln=LineProperties(solidFill=RED, w=25400)), trendlineLbl=TLBL())
sc.series.append(s); sc.legend = None; sc.x_axis.scaling.min = 0; sc.y_axis.scaling.min = 0
sc.x_axis.majorUnit = 10; sc.y_axis.majorUnit = 200; sc.x_axis.scaling.max = 60
A.add_chart(sc, "A31")
age_cats = Reference(A, min_col=22, min_row=14, max_row=18)
A.cell(13, 22, "Chart label"); A.cell(21, 22, "Chart label")
box_wr_age = box_chart(A, "Box plot: W+R % by age fifth (1 = youngest) — boxes stay level", age_cats, 14, 18, 10, "CDB6E3", PURP, "W+R %", 0, 35)
A.add_chart(box_wr_age, "J31")
box_rate_age = box_chart(A, "Box plot: items per 1,000 per year by age fifth — boxes climb", Reference(A, min_col=22, min_row=22, max_row=26),
                         22, 26, 10, "9EC5E8", BLUE, "Items per 1,000 per year", 0, 900)
A.add_chart(box_rate_age, "J50")

# ================= 6 Correlation =================
R = wb.create_sheet("6 Correlation")
title(R, "6 · Correlation matrix (12-month practice totals)", "Every cell is =CORREL(column A, column B) on '2 Practices'. Red = rise together, blue = one rises as the other falls.")
vars_ = [("Items per 1,000 per year", "I"), ("W+R %", "J"), ("% aged 65+", "N"), ("% aged 15-24", "O"),
         ("% aged 0-9", "P"), ("Practice size", "H"), ("Months in top fifth", "M"), ("IMD 2025 score", "AD")]
for j, (nme, _) in enumerate(vars_, 2):
    c = R.cell(4, j, nme); c.font = Font(bold=True, color="FFFFFF"); c.fill = HEAD; c.alignment = Alignment(wrap_text=True)
    R.column_dimensions[CL(j)].width = 12
R.row_dimensions[4].height = 32; R.column_dimensions["A"].width = 22
for i, (nme, ci) in enumerate(vars_, 5):
    R.cell(i, 1, nme).font = Font(bold=True)
    for j, (_, cj) in enumerate(vars_, 2):
        R.cell(i, j, f"=CORREL({pr(ci)},{pr(cj)})").number_format = "0.00"
        R.cell(i, j).alignment = Alignment(horizontal="center")
R.conditional_formatting.add("B5:I12", ColorScaleRule(start_type="num", start_value=-1, start_color="2F6FB5", mid_type="num", mid_value=0,
                                                        mid_color="F7F7F7", end_type="num", end_value=1, end_color="C0392B"))
R["A14"] = ("Be careful: correlation is not cause. The three age columns are shares of the same total, so they are partly linked by construction. "
            "'Months in top fifth' is built from W+R %, so those two are linked by construction too.")
R["A14"].font = note_font; R["A14"].alignment = Alignment(wrap_text=True); R.merge_cells("A14:I16")

# ================= 7 Top 15 =================
T = wb.create_sheet("7 Top 15")
title(T, "7 · (Earlier approach, kept for comparison) 15 largest 12-month gaps vs ICB average", "Rank 1 = the most Watch+Reserve items above what the ICB's average share would give. A list to look into, not a verdict.")
header(T, 4, ["Rank", "Practice", "ICB", "Gap (items)", "W+R %", "ICB W+R %", "Months in top fifth", "July-only rank"], [6, 34, 34, 11, 8, 9, 11, 10])
for k in range(1, 16):
    r = 4 + k
    T.cell(r, 1, k); mt = f"MATCH(A{r},{pr('U')},0)"
    for c, col in zip(range(2, 9), ["B", "C", "L", "J", "K", "M", "V"]):
        T.cell(r, c, f"=INDEX({pr(col)},{mt})").fill = CALC
    T.cell(r, 4).number_format = "#,##0"; T.cell(r, 5).number_format = "0.0"; T.cell(r, 6).number_format = "0.0"
tc = BarChart(); tc.type = "bar"; tc.title = "Gap vs ICB average (Watch+Reserve items, 12 months)"; tc.height = 10; tc.width = 20; tc.legend = None
tc.add_data(Reference(T, min_col=4, min_row=4, max_row=19), titles_from_data=True); tc.set_categories(Reference(T, min_col=2, min_row=5, max_row=19))
tc.series[0].graphicalProperties.solidFill = RED; tc.dataLabels = dl()
tc.y_axis.numFmt = "#,##0"; tc.x_axis.scaling.orientation = "maxMin"; tc.y_axis.majorUnit = 500; tc.y_axis.scaling.min = 0
T.add_chart(tc, "A22")

T["A20"] = ("Note: ranking by the item gap favours big practices (more items = bigger gap). Sheet 13 gives the fairer review shortlist, "
            "which also needs the practice to be unusual on the funnel plot (sheet 9) and high all year with and without lymecycline.")
T["A20"].font = note_font; T["A20"].alignment = Alignment(wrap_text=True); T.merge_cells("A20:H21")


def kv(ws, r, label, formula, fmt="0.00", bold=False):
    ws.cell(r, 1, label).font = Font(bold=True) if bold else Font()
    c = ws.cell(r, 2, formula); c.fill = CALC; c.number_format = fmt
    if bold: c.font = Font(bold=True)
    return c


def note(ws, cell, text, merge):
    ws[cell] = text; ws[cell].font = note_font; ws[cell].alignment = Alignment(wrap_text=True, vertical="top"); ws.merge_cells(merge)


# ================= 8 Reliability =================
Rl = wb.create_sheet("8 Reliability")
title(Rl, "8 · How reliable is a practice's Watch+Reserve share?",
      "Replaces the 'luck' comparison as the main evidence. Three checks: split-half correlation, month-to-month repeat, and how much is noise.")
Rl.column_dimensions["A"].width = 62; Rl.column_dimensions["B"].width = 14
Rl["A4"] = "1. Split-half: does the first half of the year predict the second half?"; Rl["A4"].font = Font(bold=True, color=INK, size=12)
kv(Rl, 5, "r: W+R % Sep–Feb vs W+R % Mar–Aug (per practice)", f"=CORREL({pr('W')},{pr('X')})", "0.000", True)
kv(Rl, 6, "Practices (n)", f"=COUNT({pr('W')})", "#,##0")
kv(Rl, 7, "95% CI lower (Fisher z)", "=TANH(ATANH(B5)-1.96/SQRT(B6-3))", "0.000")
kv(Rl, 8, "95% CI upper (Fisher z)", "=TANH(ATANH(B5)+1.96/SQRT(B6-3))", "0.000")
kv(Rl, 9, "Reliability of the full 12 months (Spearman-Brown: 2r ÷ (1+r))", "=2*B5/(1+B5)", "0.000")
Rl["A11"] = "2. Month to month: does a practice's top-fifth flag repeat?"; Rl["A11"].font = Font(bold=True, color=INK, size=12)
dr = lambda c: f"Data!${c}$2:${c}${DE}"
kv(Rl, 12, "In top fifth next month, if in top fifth this month", f'=COUNTIFS({dr("O")},1,{dr("R")},1)/COUNTIFS({dr("O")},1,{dr("R")},">=0")', "0.0%", True)
kv(Rl, 13, "In top fifth next month, if NOT in top fifth this month", f'=COUNTIFS({dr("O")},0,{dr("R")},1)/COUNTIFS({dr("O")},0,{dr("R")},">=0")', "0.0%")
kv(Rl, 14, "Same status next month (all practice-months)",
   f'=(COUNTIFS({dr("O")},1,{dr("R")},1)+COUNTIFS({dr("O")},0,{dr("R")},0))/COUNTIFS({dr("R")},">=0")', "0.0%")
kv(Rl, 15, "Same status if months were independent (0.2² + 0.8²)", "=0.2^2+0.8^2", "0.0%")
Rl["A17"] = "3. How much of the difference between practices is just noise?"; Rl["A17"].font = Font(bold=True, color=INK, size=12)
kv(Rl, 18, "One month: average noise share across the 12 months (from '1 Monthly' column AD)", "=AVERAGE('1 Monthly'!AD5:AD16)", "0.0%", True)
kv(Rl, 19, "Twelve months: average p(1-p)/n ÷ variance of 12-month shares",
   f"=SUMPRODUCT(({pr('J')}/100)*(1-{pr('J')}/100)/{pr('D')})/COUNT({pr('D')})/(_xlfn.VAR.S({pr('J')})/10000)", "0.0%", True)
note(Rl, "A21", "How to read this. Noise = the wobble you would expect from chance alone, given how many antibiotic items a practice writes "
     "(the binomial variance p(1-p)/n). If one month's differences between practices were all noise, the noise share would be 100%. "
     "About a third of one month's spread is noise, so a single month ranks practices badly. Over 12 months the noise share falls to about 5%, "
     "so the 12-month figures mostly reflect real differences. The split-half r says the same thing in plain words: a practice's share in the "
     "first six months predicts its share in the last six months well.", "A21:H26")
sp = ScatterChart(); sp.title = "W+R % first half vs second half (each dot = a practice)"; sp.style = 13; sp.height = 9; sp.width = 15
sp.x_axis.title = "W+R % Sep 2025–Feb 2026"; sp.y_axis.title = "W+R % Mar–Aug 2026"
s_ = Series(Reference(P, min_col=24, min_row=2, max_row=PE), Reference(P, min_col=23, min_row=2, max_row=PE), title="Practices")
s_.marker.symbol = "circle"; s_.marker.size = 2; s_.graphicalProperties.line.noFill = True
s_.marker.graphicalProperties.solidFill = TEAL; s_.marker.graphicalProperties.line.solidFill = TEAL
s_.trendline = Trendline(trendlineType="linear", dispEq=True, dispRSqr=True, spPr=GraphicalProperties(ln=LineProperties(solidFill=RED, w=25400)), trendlineLbl=TLBL())
sp.series.append(s_); sp.legend = None
for ax in (sp.x_axis, sp.y_axis): ax.scaling.min = 0; ax.scaling.max = 45; ax.majorUnit = 10
Rl.add_chart(sp, "D4")

# ================= 9 Funnel =================
Fn = wb.create_sheet("9 Funnel")
title(Fn, "9 · Funnel plot adjusted for over-dispersion (Spiegelhalter 2005)",
      "Which practices are further above the England share than size and normal between-practice spread would explain?")
Fn.column_dimensions["A"].width = 62; Fn.column_dimensions["B"].width = 14
kv(Fn, 5, "England W+R share as a proportion (target p0)", f"=SUM({pr('F')})/SUM({pr('D')})", "0.0000", True)
kv(Fn, 6, "Practices (n)", f"=COUNT({pr('D')})", "#,##0")
Fn["A7"] = "Step 1: plain z for each practice = (p − p0) ÷ √(p0(1−p0)/items)   → '2 Practices' column AI"; Fn["A7"].font = note_font
kv(Fn, 8, "z at 10th percentile (for winsorising)", f"=_xlfn.PERCENTILE.INC({pr('AI')},0.1)")
kv(Fn, 9, "z at 90th percentile (for winsorising)", f"=_xlfn.PERCENTILE.INC({pr('AI')},0.9)")
kv(Fn, 10, "Over-dispersion factor φ = average of winsorised z²", f"=SUMSQ({pr('AK')})/B6", "0.00", True)
kv(Fn, 11, "Sum of weights w = 1/SE²", f"=SUM({pr('AL')})", "#,##0")
kv(Fn, 12, "Sum of w²", f"=SUMSQ({pr('AL')})", "0.00E+00")
kv(Fn, 13, "τ² (extra between-practice variance) = (nφ − (n−1)) ÷ (Σw − Σw²/Σw)", "=MAX(0,(B6*B10-(B6-1))/(B11-B12/B11))", "0.000000", True)
kv(Fn, 14, "τ in percentage points", "=SQRT(B13)*100", "0.00")
Fn["A15"] = "Step 2: adjusted z = (p − p0) ÷ √(SE² + τ²)   → '2 Practices' column AJ"; Fn["A15"].font = note_font
kv(Fn, 17, "Plain funnel: practices above the 99.8% limit (z > 3.09)", f'=COUNTIF({pr("AI")},">3.09")', "#,##0")
kv(Fn, 18, "Adjusted funnel: practices above the 99.8% limit", f'=COUNTIF({pr("AJ")},">3.09")', "#,##0", True)
kv(Fn, 19, "Adjusted funnel: practices above the 95% limit (z > 1.96)", f'=COUNTIF({pr("AJ")},">1.96")', "#,##0")
kv(Fn, 20, "Adjusted funnel: practices below the lower 99.8% limit", f'=COUNTIF({pr("AJ")},"<-3.09")', "#,##0")
kv(Fn, 21, "Above 99.8% AND in the top fifth 9+ months (sheet 4)", f'=COUNTIFS({pr("AM")},1,{pr("M")},">=9")', "#,##0", True)
kv(Fn, 22, "Expected above 99.8% by chance alone (n × 0.1%)", "=B6*(1-_xlfn.NORM.S.DIST(3.09,TRUE))", "0.0")
Fn["A58"] = "Sensitivity: compare each practice with its OWN ICB instead of England"; Fn["A58"].font = Font(bold=True, color=INK, size=12)
Fn["A59"] = "Same steps as above, using the ICB W+R % as the target ('2 Practices' columns AR to AX)"; Fn["A59"].font = note_font
kv(Fn, 60, "z vs ICB at 10th percentile", f"=_xlfn.PERCENTILE.INC({pr('AS')},0.1)")
kv(Fn, 61, "z vs ICB at 90th percentile", f"=_xlfn.PERCENTILE.INC({pr('AS')},0.9)")
kv(Fn, 62, "φ vs ICB", f"=SUMSQ({pr('AT')})/B6", "0.00")
kv(Fn, 63, "Sum of weights", f"=SUM({pr('AU')})", "#,##0")
kv(Fn, 64, "Sum of weights²", f"=SUMSQ({pr('AU')})", "0.00E+00")
kv(Fn, 65, "τ² vs ICB", "=MAX(0,(B6*B62-(B6-1))/(B63-B64/B63))", "0.000000", True)
kv(Fn, 66, "Practices above 99.8% vs own ICB", f'=COUNTIF({pr("AV")},">3.09")', "#,##0", True)
kv(Fn, 67, "Shortlist using own-ICB funnel", f"=SUM({pr('AX')})", "#,##0", True)
kv(Fn, 68, "Of the main shortlist, also on the own-ICB shortlist", f"=COUNTIFS({pr('AN')},1,{pr('AX')},1)", "#,##0", True)
note(Fn, "A23", "Why adjust? With hundreds of items per practice the plain limits are very narrow, so the plain funnel flags over a thousand "
     "practices: real practices differ more than chance alone allows (φ far above 1). The adjustment adds that extra spread (τ²) to every "
     "practice's limits, so only practices that are unusual even allowing for normal variation are flagged. This is the method used for NHS "
     "performance indicators (Spiegelhalter, 2005). About 6 of the flagged practices could still be chance (row 22).", "A23:H28")
header(Fn, 30, ["Items (x)", "Lower 99.8%", "Lower 95%", "England", "Upper 95%", "Upper 99.8%"], None)
grid = [int(round(v, -1)) for v in np.geomspace(300, 60000, 25)]
for k, nn in enumerate(grid):
    r = 31 + k
    Fn.cell(r, 1, nn)
    for j, zz in enumerate([-3.09, -1.96, 0, 1.96, 3.09], start=2):
        Fn.cell(r, j, f"=($B$5+({zz})*SQRT($B$5*(1-$B$5)/A{r}+$B$13))*100").number_format = "0.0"
        Fn.cell(r, j).fill = CALC
# chart helper: each limit as ONE series (upper curve, a blank row, then lower curve) so the legend has one entry per limit
for j_, h_ in enumerate(["Chart: items", "Chart: 99.8% limit", "Chart: 95% limit", "Chart: England"]):
    c_ = Fn.cell(30, 8 + j_, h_); c_.font = Font(bold=True, color="FFFFFF"); c_.fill = HEAD; c_.alignment = Alignment(wrap_text=True)
NG = len(grid)
for k in range(NG):
    ru, rl, src = 31 + k, 32 + NG + k, 31 + k
    Fn.cell(ru, 8, f"=A{src}"); Fn.cell(ru, 9, f"=F{src}"); Fn.cell(ru, 10, f"=E{src}"); Fn.cell(ru, 11, f"=D{src}")
    Fn.cell(rl, 8, f"=A{src}"); Fn.cell(rl, 9, f"=B{src}"); Fn.cell(rl, 10, f"=C{src}")
    for c_ in range(8, 12):
        Fn.cell(ru, c_).number_format = "0.0"; Fn.cell(rl, c_).number_format = "0.0"
Fn.cell(31 + NG, 12, "← blank row = gap between upper and lower curve").font = note_font
fc = ScatterChart(); fc.title = "Adjusted funnel plot: W+R % against items prescribed"; fc.style = 13; fc.height = 11; fc.width = 18
fc.x_axis.title = "Classified antibiotic items (12 months)"; fc.y_axis.title = "Watch+Reserve %"
sp_ = Series(Reference(P, min_col=10, min_row=2, max_row=PE), Reference(P, min_col=4, min_row=2, max_row=PE), title="Practices within limits")
sp_.marker.symbol = "circle"; sp_.marker.size = 2; sp_.graphicalProperties.line.noFill = True
sp_.marker.graphicalProperties.solidFill = "8FA6A8"; sp_.marker.graphicalProperties.line.noFill = True  # made 70% see-through by src/chart_polish.py
fc.series.append(sp_)
for col_, nm_, colr, sz in [(56, "Above 99.8% (not shortlisted)", AMBER, 4), (57, "Review shortlist (106)", RED, 4)]:
    fs = Series(Reference(P, min_col=col_, min_row=2, max_row=PE), Reference(P, min_col=4, min_row=2, max_row=PE), title=nm_)
    fs.marker.symbol = "circle"; fs.marker.size = sz; fs.graphicalProperties.line.noFill = True
    fs.marker.graphicalProperties.solidFill = colr; fs.marker.graphicalProperties.line.solidFill = "FFFFFF"
    fc.series.append(fs)
LAST = 31 + 2 * NG
for col_, nm_, colr, dash, last in [(9, "99.8% limit", RED, "dash", LAST), (10, "95% limit", AMBER, "sysDot", LAST),
                                    (11, "England 18.5%", INK, None, 30 + NG)]:
    sl = Series(Reference(Fn, min_col=col_, min_row=31, max_row=last), Reference(Fn, min_col=8, min_row=31, max_row=last), title=nm_)
    sl.marker.symbol = "none"; sl.graphicalProperties.line.solidFill = colr; sl.graphicalProperties.line.width = 28575
    if dash: sl.graphicalProperties.line.dashStyle = dash
    sl.smooth = False; fc.series.append(sl)
fc.dispBlanksAs = "gap"
fc.x_axis.scaling.logBase = 10; fc.x_axis.scaling.min = 100; fc.x_axis.scaling.max = 100000; fc.y_axis.scaling.min = 0; fc.y_axis.scaling.max = 45; fc.legend.position = "b"
fc.x_axis.numFmt = "#,##0"; fc.x_axis.majorGridlines = None
fc.x_axis.title = "Classified antibiotic items in 12 months (log scale)"
fc.legend.position = "b"; fc.y_axis.numFmt = "0"; fc.y_axis.majorUnit = 5; fc.height = 12; fc.width = 20
fc.title = "Adjusted funnel: 117 practices above the 99.8% limit (106 shortlisted, red)"
Fn.add_chart(fc, "D4")

# ================= 10 Sensitivity =================
Sn = wb.create_sheet("10 Sensitivity")
title(Sn, "10 · Do the results survive different choices?", "Each row changes one choice and recomputes the headline. Teal = live formula; white = value from src/extended_analysis.py (the excluded practices are not in this workbook).")
header(Sn, 4, ["Version", "England W+R %", "Practices high 9+ of 12 months", "Same practices as main list", "Note"], [46, 14, 16, 16, 70])
mon = lambda c: f"'1 Monthly'!{c}5:{c}16"
rows_ = [("Main analysis (items, all Watch+Reserve, 5,791 practices)", f"=SUM({pr('F')})/SUM({pr('D')})*100", f'=COUNTIF({pr("M")},">=9")', f'=COUNTIF({pr("M")},">=9")', "Denominator = Access + Watch + Reserve + Other."),
         ("Without lymecycline (mostly long acne courses)", f"=(SUM({pr('F')})-SUM({pr('G')}))/(SUM({pr('D')})-SUM({pr('G')}))*100", f'=COUNTIF({pr("Z")},">=9")',
          f'=COUNTIFS({pr("M")},">=9",{pr("Z")},">=9")', "Lymecycline removed from top and bottom of the fraction; monthly top fifths recomputed ('1 Monthly' column AA)."),
         ("OpenPrescribing-style denominator (Access + Watch + Reserve only)", f"=SUM({pr('F')})/(SUM({pr('D')})-SUM({pr('AB')}))*100", RES["persistent_9plus_op_denominator"], RES["persistent_9plus_op_same"], "Persistence counts: values from extended_analysis.py. Explains why figures here are lower than OpenPrescribing's AWaRe measure."),
         ("By dose (ADQ) instead of items", f"=(SUM(Data!V2:V{DE})+SUM(Data!W2:W{DE}))/SUM(Data!U2:X{DE})*100", f'=COUNTIF({pr("AQ")},">=9")', f'=COUNTIFS({pr("M")},">=9",{pr("AQ")},">=9")',
          "ADQ = typical adult daily dose. Long courses weigh more. Not the same as the WHO DDD used for national targets."),
         ("Including the 59 atypical practices (student, digital-first)", RES["england_share_incl_atypical"], RES["persistent_9plus_incl_atypical"], RES["persistent_9plus_incl_atypical_same"],
          "Value from extended_analysis.py. Age R² would be " + f"{RES['age_r2_incl_atypical']:.2f} instead of {RES['age_r2']:.2f}.")]
for k, (lab_, f1, f2, f3, nt) in enumerate(rows_):
    r = 5 + k
    Sn.cell(r, 1, lab_)
    for j, f_ in enumerate([f1, f2, f3], start=2):
        c = Sn.cell(r, j, f_); c.number_format = "0.00" if j == 2 else "#,##0"
        if isinstance(f_, str) and f_.startswith("="): c.fill = CALC
    Sn.cell(r, 5, nt).font = note_font; Sn.cell(r, 5).alignment = Alignment(wrap_text=True)
kv(Sn, 12, "r between practice W+R % with and without lymecycline", f"=CORREL({pr('J')},{pr('Y')})", "0.00")
kv(Sn, 13, "r between practice W+R % by items and by dose (ADQ)", f"=CORREL({pr('J')},{pr('AA')})", "0.00")
kv(Sn, 14, "Access % of items", f"=SUM({pr('E')})/SUM({pr('D')})*100", "0.0")
kv(Sn, 15, "Access % by dose (ADQ)", f"=SUM(Data!U2:U{DE})/SUM(Data!U2:X{DE})*100", "0.0")
kv(Sn, 16, "Share of the main 9+ list that changes without lymecycline", "=1-D6/C5", "0.0%", True)
kv(Sn, 17, "Main shortlist practices also high 9+ months by dose (ADQ)", f'=COUNTIFS({pr("AN")},1,{pr("AQ")},">=9")', "#,##0", True)
kv(Sn, 18, "Main shortlist practices also on the own-ICB shortlist (sheet 9)", "='9 Funnel'!B68", "#,##0", True)
kv(Sn, 19, "ICBs with no shortlisted practice (England target)", f'=SUMPRODUCT(--(COUNTIFS({pr("C")},\'3 ICB\'!A5:A40,{pr("AN")},1)=0))', "0")
note(Sn, "A21", "Reading: the main findings hold, but lymecycline changes about a quarter of the 'high all year' list, so any review should look at "
     "lymecycline separately. Items and dose give similar rankings (r ≈ 0.76), but the dose-based W+R share is higher because acne courses are long. "
     "Neither items nor ADQ can be compared directly with the national target, which uses WHO DDDs. "
     "Comparing each practice with its own ICB keeps most of the shortlist, so the list is not just an area effect. "
     "By dose, fewer shortlisted practices stay high all year, so a dose-based review would rank some practices differently.", "A21:E25")
Sn.column_dimensions["A"].width = 60

# ================= 11 Deprivation =================
Dp = wb.create_sheet("11 Deprivation")
title(Dp, "11 · Deprivation (IMD 2025) and a model with several factors at once",
      "Practice IMD score = average of its patients' neighbourhood (LSOA) IMD 2025 scores, weighted by patients (method in 'IMD data'). Higher = more deprived.")
Dp.column_dimensions["A"].width = 50
kv(Dp, 4, "r: IMD score vs W+R %", f"=CORREL({pr('AD')},{pr('J')})", "0.00", True)
kv(Dp, 5, "p-value (t-test on r)", f"=_xlfn.T.DIST.2T(ABS(B4)*SQRT((B7-2)/(1-B4^2)),B7-2)", "0.0E+00")
kv(Dp, 6, "r: IMD score vs items per 1,000 per year", f"=CORREL({pr('AD')},{pr('I')})", "0.00")
kv(Dp, 7, "Practices", f"=COUNT({pr('AD')})", "#,##0")
kv(Dp, 8, "p-value for IMD vs rate", f"=_xlfn.T.DIST.2T(ABS(B6)*SQRT((B7-2)/(1-B6^2)),B7-2)", "0.00")
Dp["A10"] = "Multiple regression: W+R % on four factors at once (LINEST)"; Dp["A10"].font = Font(bold=True, color=INK, size=12)
header(Dp, 11, ["Factor", "Coefficient", "Standard error", "t", "p-value", "95% CI low", "95% CI high", "Effect of +1 SD (points)"], None)
Y_, X_ = pr("J"), f"'2 Practices'!$AD$2:$AG${PE}"
facts = [("IMD 2025 score (+1 point)", 4, "AD"), ("% aged 65+ (+1 point)", 3, "AE"), ("log10 practice size (+1 = 10× bigger)", 2, "AF"),
         ("ICB W+R % (+1 point)", 1, "AG"), ("Intercept", 5, None)]
for k, (lab_, col, pc_) in enumerate(facts):
    r = 12 + k
    Dp.cell(r, 1, lab_)
    Dp.cell(r, 2, f"=INDEX(LINEST({Y_},{X_},TRUE,TRUE),1,{col})")
    Dp.cell(r, 3, f"=INDEX(LINEST({Y_},{X_},TRUE,TRUE),2,{col})")
    Dp.cell(r, 4, f"=B{r}/C{r}")
    Dp.cell(r, 5, f"=_xlfn.T.DIST.2T(ABS(D{r}),$B$19)")
    Dp.cell(r, 6, f"=B{r}-_xlfn.T.INV.2T(0.05,$B$19)*C{r}"); Dp.cell(r, 7, f"=B{r}+_xlfn.T.INV.2T(0.05,$B$19)*C{r}")
    if pc_: Dp.cell(r, 8, f"=B{r}*_xlfn.STDEV.S('2 Practices'!{pc_}2:{pc_}{PE})")
    for j in range(2, 9):
        Dp.cell(r, j).fill = CALC; Dp.cell(r, j).number_format = "0.0E+00" if j == 5 else "0.000"
kv(Dp, 18, "R² (all four factors)", f"=INDEX(LINEST({Y_},{X_},TRUE,TRUE),3,1)", "0.000", True)
kv(Dp, 19, "Degrees of freedom", f"=INDEX(LINEST({Y_},{X_},TRUE,TRUE),4,2)", "#,##0")
kv(Dp, 20, "R² with ICB W+R % alone", f"=RSQ({Y_},{pr('AG')})", "0.000")
header(Dp, 21, ["IMD fifth", "Starts at IMD score", "Practices", "Average IMD", "Classified items", "W+R items", "W+R %", "Items per 1,000 per year"], None)
for k in range(5):
    r = 22 + k
    Dp.cell(r, 1, ["1 Least deprived", "2", "3", "4", "5 Most deprived"][k])
    Dp.cell(r, 2, f"=MIN({pr('AD')})" if k == 0 else f"=_xlfn.PERCENTILE.INC({pr('AD')},{k/5})")
    Dp.cell(r, 3, f"=COUNTIF({pr('AP')},{k+1})"); Dp.cell(r, 4, f"=AVERAGEIFS({pr('AD')},{pr('AP')},{k+1})")
    Dp.cell(r, 5, f"=SUMIFS({pr('D')},{pr('AP')},{k+1})"); Dp.cell(r, 6, f"=SUMIFS({pr('F')},{pr('AP')},{k+1})")
    Dp.cell(r, 7, f"=F{r}/E{r}*100"); Dp.cell(r, 8, f"=SUMIFS({pr('D')},{pr('AP')},{k+1})/SUMIFS({pr('H')},{pr('AP')},{k+1})*1000")
    for j in range(2, 9):
        Dp.cell(r, j).fill = CALC; Dp.cell(r, j).number_format = "#,##0" if j in (3, 5, 6) else "0.0"
for c_, w_ in zip("BCDEFGH", [13, 13, 10, 13, 13, 13, 16]): Dp.column_dimensions[c_].width = w_
Dp.row_dimensions[11].height = 32; Dp.row_dimensions[21].height = 32
note(Dp, "A28", "Reading: more deprived practices have a slightly LOWER W+R share (r ≈ −0.12). In the regression above it is p < 0.001 with ordinary errors, but practices in the same ICB are not independent: with errors clustered by ICB it is p = 0.10 (src/extended_analysis.py), so read it as no clear link. "
     "But all four factors together explain only about 14% of the differences, almost all of it from the ICB average. "
     "So deprivation does not explain away the high-share practices: most of the variation is practice-specific. "
     "Coefficients are associations, not causes. IMD describes where patients live, not the patients themselves.", "A28:H32")
Dp["A34"] = "Regression 2: items per 1,000 per year on IMD, age and size (why deprivation 'appears' unlinked to volume)"; Dp["A34"].font = Font(bold=True, color=INK, size=12)
header(Dp, 35, ["Factor", "Coefficient", "Standard error", "t", "p-value", "95% CI low", "95% CI high"], None)
Y2, X2 = pr("I"), f"'2 Practices'!$AD$2:$AF${PE}"
for k, (lab_, col) in enumerate([("IMD 2025 score (+1 point)", 3), ("% aged 65+ (+1 point)", 2), ("log10 practice size", 1), ("Intercept", 4)]):
    r = 36 + k
    Dp.cell(r, 1, lab_)
    Dp.cell(r, 2, f"=INDEX(LINEST({Y2},{X2},TRUE,TRUE),1,{col})"); Dp.cell(r, 3, f"=INDEX(LINEST({Y2},{X2},TRUE,TRUE),2,{col})")
    Dp.cell(r, 4, f"=B{r}/C{r}"); Dp.cell(r, 5, f"=_xlfn.T.DIST.2T(ABS(D{r}),$B$41)")
    Dp.cell(r, 6, f"=B{r}-_xlfn.T.INV.2T(0.05,$B$41)*C{r}"); Dp.cell(r, 7, f"=B{r}+_xlfn.T.INV.2T(0.05,$B$41)*C{r}")
    for j in range(2, 8): Dp.cell(r, j).fill = CALC; Dp.cell(r, j).number_format = "0.0E+00" if j == 5 else "0.000"
kv(Dp, 40, "R² (regression 2)", f"=INDEX(LINEST({Y2},{X2},TRUE,TRUE),3,1)", "0.000", True)
kv(Dp, 41, "Degrees of freedom", f"=INDEX(LINEST({Y2},{X2},TRUE,TRUE),4,2)", "#,##0")
kv(Dp, 42, "r: IMD score vs % aged 65+", f"=CORREL({pr('AD')},{pr('N')})", "0.00", True)
note(Dp, "A43", "Deprived practices have younger patients (r ≈ −0.46), and younger patients get fewer antibiotics. On its own, IMD looks unrelated to volume "
     "(B6); after controlling for % aged 65+ and log practice size, each IMD point goes with about 3.4 more items per 1,000 patients a year. "
     "This one is robust: 2.9 with ICB fixed effects and still p < 0.001 with errors clustered by ICB.", "A43:H45")
Dp["A47"] = "Robustness of regression 1: ICB share leaving the practice itself out"; Dp["A47"].font = Font(bold=True, color=INK, size=12)
X3 = f"'2 Practices'!$AZ$2:$BC${PE}"
kv(Dp, 48, "IMD coefficient (ICB share excluding the practice)", f"=INDEX(LINEST({Y_},{X3},TRUE,TRUE),1,4)", "0.000", True)
kv(Dp, 49, "Its standard error", f"=INDEX(LINEST({Y_},{X3},TRUE,TRUE),2,4)", "0.000")
kv(Dp, 50, "p-value", f"=_xlfn.T.DIST.2T(ABS(B48/B49),INDEX(LINEST({Y_},{X3},TRUE,TRUE),4,2))", "0.0E+00")
note(Dp, "A51", f"A version with a separate intercept for every ICB (fixed effects, run in src/extended_analysis.py) gives an IMD coefficient of "
     f"{RES['reg_imd_coef_fe']:.3f}: p < 0.001 with ordinary errors, but p = {RES['imd_share_fe_p_clustered']:.2f} with errors clustered by ICB, "
     f"and p = {RES['imd_share_quasibinomial_p_clustered']:.2f} in a binomial model with errors clustered by ICB. So the share result is fragile: read it as no clear link.", "A51:H52")
dc = BarChart(); dc.title = "W+R % by deprivation fifth"; dc.height = 7.5; dc.width = 13; dc.legend = None
dc.add_data(Reference(Dp, min_col=7, min_row=21, max_row=26), titles_from_data=True); dc.set_categories(Reference(Dp, min_col=1, min_row=22, max_row=26))
dc.series[0].graphicalProperties.solidFill = TEAL; dc.dataLabels = dl(); dc.y_axis.scaling.min = 0; dc.y_axis.scaling.max = 22; dc.y_axis.numFmt = "0"
Dp.add_chart(dc, "J4")

# ================= 12 Watch drugs =================
Wd = wb.create_sheet("12 Watch drugs")
title(Wd, "12 · Which Watch antibiotics make up the Watch items? (12 months, the same 5,791 practices)",
      "Items per substance came from a second API query (same months, same practices). The check cell proves the totals match the main data.")
header(Wd, 4, ["BNF code", "Substance", "Watch items (12 months)", "% of Watch items", "Cumulative %"], [12, 44, 16, 14, 14])
WE = 4 + len(drug_tab)
for k, row in enumerate(drug_tab.itertuples(index=False)):
    r = 5 + k
    Wd.cell(r, 1, row[0]); Wd.cell(r, 2, row.substance); Wd.cell(r, 3, int(row.items)).number_format = "#,##0"
    Wd.cell(r, 4, f"=C{r}/SUM($C$5:$C${WE})*100").number_format = "0.0"
    Wd.cell(r, 5, f"=SUM($C$5:C{r})/SUM($C$5:$C${WE})*100").number_format = "0.0"
    Wd.cell(r, 4).fill = Wd.cell(r, 5).fill = CALC
kv(Wd, WE + 2, "Check: total here", f"=SUM(C5:C{WE})", "#,##0")
kv(Wd, WE + 3, "Check: Watch items in 'Data' column H", f"=SUM({dr('H')})", "#,##0")
kv(Wd, WE + 4, "Totals match?", f"=IF(B{WE+2}=B{WE+3},\"YES\",\"NO\")", "@", True)
kv(Wd, WE + 6, "Clarithromycin + co-amoxiclav + azithromycin, % of Watch items", "=E7", "0.0", True)
Wd.column_dimensions["A"].width = 14
wc_ = BarChart(); wc_.type = "bar"; wc_.title = "Top 8 Watch antibiotics (% of Watch items)"; wc_.height = 8; wc_.width = 15; wc_.legend = None
wc_.add_data(Reference(Wd, min_col=4, min_row=4, max_row=12), titles_from_data=True); wc_.set_categories(Reference(Wd, min_col=2, min_row=5, max_row=12))
wc_.series[0].graphicalProperties.solidFill = RED; wc_.dataLabels = dl(); wc_.x_axis.scaling.orientation = "maxMin"; wc_.y_axis.numFmt = "0"
Wd.add_chart(wc_, "G4")

# ================= 13 Review shortlist =================
Sh = wb.create_sheet("13 Review shortlist")
title(Sh, "13 · Review shortlist: unusual, persistent, and not just lymecycline",
      "A practice is listed only if (1) it is above the adjusted 99.8% funnel limit, (2) in the top fifth 9+ of 12 months, and (3) still 9+ months without lymecycline. Sorted by adjusted z (how unusual), not by item gap, so big practices are not favoured.")
kv(Sh, 4, "Practices meeting all three screening criteria", f"=SUM({pr('AN')})", "#,##0", True)
header(Sh, 6, ["Rank", "Practice", "ICB", "Classified items", "W+R %", "ICB W+R %", "Gap (items)", "Adjusted z", "Months top fifth",
               "Months without lymecycline", "Lymecycline % of items"], [6, 34, 34, 11, 8, 9, 10, 10, 10, 12, 12])
for k in range(1, 21):
    r = 6 + k
    Sh.cell(r, 1, k); mt = f"MATCH(A{r},{pr('AO')},0)"
    for c, col, fmt in zip(range(2, 12), ["B", "C", "D", "J", "K", "L", "AJ", "M", "Z", "AC"],
                           ["@", "@", "#,##0", "0.0", "0.0", "#,##0", "0.00", "0", "0", "0.0"]):
        cell = Sh.cell(r, c, f"=INDEX({pr(col)},{mt})"); cell.fill = CALC; cell.number_format = fmt
Sh.column_dimensions["A"].width = 30
note(Sh, "A28", "This is a list of practices whose prescribing pattern is worth a conversation, not a judgement. There are no diagnoses in the data, "
     "and some Watch prescribing is clinically right (for example penicillin allergy). The first 20 of the shortlist are shown; "
     "column AO on '2 Practices' ranks all of them. About 6 of the practices above the funnel limit could be chance.", "A28:K30")

# ================= IMD data =================
Im = wb.create_sheet("IMD data")
header(Im, 1, ["Practice code", "IMD 2025 score (patient-weighted)", "Share of the practice's patients matched to an English LSOA"], [12, 18, 22])
for i, (pc_, row) in enumerate(imd_tab.reindex(pcs.pc).iterrows(), start=2):
    Im.cell(i, 1, pc_); Im.cell(i, 2, round(float(row.imd), 3)); Im.cell(i, 3, round(float(row.imd_coverage), 4)).number_format = "0.0%"
Im["E2"] = ("Method: for each practice, the NHS England July 2026 file 'Patients registered at a GP practice by LSOA 2021' gives how many patients "
            "live in each neighbourhood (LSOA). Each LSOA's IMD 2025 score comes from MHCLG File 5. Practice score = Σ(patients × LSOA score) ÷ Σ(patients), "
            "using patients with an English LSOA. Calculated in src/extended_analysis.py because the LSOA file has over a million rows.")
Im["E2"].font = note_font; Im["E2"].alignment = Alignment(wrap_text=True, vertical="top"); Im.merge_cells("E2:L10"); Im.column_dimensions["E"].width = 12

# ================= Age data =================
G = wb.create_sheet("Age data")
header(G, 1, ["Practice code"] + [f"Aged {b.replace('_','-')}" for b in bands] + ["Total", "% aged 65+", "% aged 15-24", "% aged 0-9"])
for i, row in enumerate(ag.itertuples(index=False), start=2):
    G.cell(i, 1, row[0])
    for j, v in enumerate(row[1:], start=2): G.cell(i, j, int(v))
    G.cell(i, 22, f"=SUM(B{i}:U{i})"); G.cell(i, 24, f"=SUM(O{i}:U{i})/V{i}*100")
    G.cell(i, 25, f"=SUM(E{i}:F{i})/V{i}*100"); G.cell(i, 26, f"=SUM(B{i}:C{i})/V{i}*100")
G.freeze_panes = "B2"
G.cell(1, 23, "(blank)")
for c in ("X", "Y", "Z"): G.column_dimensions[c].width = 10

# ================= Cleaning log + mapping =================
L = wb.create_sheet("Cleaning log")
title(L, "Cleaning log: rows kept at each step", "Done before loading into Excel. Each row is one practice in one month.")
header(L, 4, ["Step", "Rows kept"], [80, 12])
for k, (s_, n_) in enumerate(steps): L.cell(5 + k, 1, s_); L.cell(5 + k, 2, n_).number_format = "#,##0"
L.cell(11, 1, "Practices in final set"); L.cell(11, 2, NP)
notes = ["Why remove Y-codes: they are mostly care-home, walk-in and other non-standard services whose patients are not comparable.",
         "Why 1,000+ patients: tiny practices give jumpy percentages (2 Watch out of 4 = 50%).",
         "Why all 12 months: so every practice is compared over the same year.",
         f"Why remove atypical lists (under {MIN_RATE} items per 1,000 patients a year): {len(ATYP)} practices, mostly university student health centres and digital-first "
         "services (e.g. GP at Hand, GP Pathfinder Clinics). Their patients are not comparable with a typical practice. The results with them included are in sheet 10.",
         "Patient lists: we have Sep 2025, Dec 2025, Mar 2026, Apr 2026 and Jul 2026. Other months use the nearest list (max 1 month away). "
         "Median practice size changed by only -0.6% across the year, so the effect is small."]
for k, t in enumerate(notes): L.cell(13 + k, 1, t).font = note_font
Mp = wb.create_sheet("AWaRe mapping")
header(Mp, 1, list(mapping.columns), [14, 44, 14, 60])
for row in mapping.itertuples(index=False): Mp.append([("" if pd.isna(x) else x) for x in row])

# ================= Dashboard =================
B = wb.create_sheet("Dashboard", 0)
B.sheet_view.showGridLines = False
for c in range(1, 26): B.column_dimensions[CL(c)].width = 9.5
B.column_dimensions["L"].width = 14
B["B2"] = "Antibiotic Stewardship — England GP practices, Sep 2025 to Aug 2026 (12 months)"; B["B2"].font = Font(size=18, bold=True, color=INK)
B["B3"] = "Which practices use an unusually high share of Watch+Reserve antibiotics, is it the same practices year after year, and is it explained by their patients? Every number below is a formula; sheets 15-16 also use inputs computed in Python."
B["B3"].font = note_font
kpis = [("Practices (all 12 months)", f"=COUNTA({pr('A')})", "#,##0", BLUE),
        ("Patients covered (millions)", f"=SUM({pr('H')})/1000000", "0.0", TEAL),
        ("Items per 1,000 per year", f"=SUM({pr('D')})/SUM({pr('H')})*1000", "0.0", AMBER),
        ("Watch+Reserve share %", f"=SUM({pr('F')})/SUM({pr('D')})*100", "0.00", RED),
        ("Review shortlist (sheet 13)", "='13 Review shortlist'!B4", "#,##0", PURP)]
for k, (lab_, f, fmt, col) in enumerate(kpis):
    c0 = 2 + k * 3; L1, L2 = CL(c0), CL(c0 + 2)
    B.merge_cells(f"{L1}5:{L2}5"); B.merge_cells(f"{L1}6:{L2}7")
    B[f"{L1}5"] = lab_; B[f"{L1}6"] = f; B[f"{L1}6"].number_format = fmt
    for rr in (5, 6, 7):
        for cc_ in range(c0, c0 + 3): B.cell(rr, cc_).fill = PatternFill("solid", fgColor=col)
    B[f"{L1}5"].font = Font(bold=True, color="FFFFFF", size=10); B[f"{L1}6"].font = Font(bold=True, color="FFFFFF", size=22)
    B[f"{L1}5"].alignment = B[f"{L1}6"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
B.merge_cells("Q5:S5"); B.merge_cells("Q6:S7")
B["Q5"] = "Peak / lowest month"
B["Q6"] = "=INDEX('1 Monthly'!Z5:Z16,MATCH(MAX('1 Monthly'!H5:H16),'1 Monthly'!H5:H16,0))&\"  /  \"&INDEX('1 Monthly'!Z5:Z16,MATCH(MIN('1 Monthly'!H5:H16),'1 Monthly'!H5:H16,0))"
for rr in (5, 6, 7):
    for cc_ in range(17, 20): B.cell(rr, cc_).fill = PatternFill("solid", fgColor="455A64")
B["Q5"].font = Font(bold=True, color="FFFFFF", size=10); B["Q6"].font = Font(bold=True, color="FFFFFF", size=16)
B["Q5"].alignment = B["Q6"].alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
B["B9"] = "Key findings (each one comes from the sheet in brackets)"; B["B9"].font = Font(bold=True, size=12, color=INK)
finds = ['="1. Same practices year after year: "&\'15 Three years\'!V21&" practices are shortlisted in all three years (Sep 2023–Aug 2026). Of the 2024-25 shortlist, "&TEXT(\'15 Three years\'!V10,"0%")&" were still above the 99.8% limit a year later (others: "&TEXT(\'15 Three years\'!V13,"0.0%")&"); of the 2023-24 shortlist, "&TEXT(\'15 Three years\'!V18,"0%")&" two years later.  [15 Three years]"',
         '="2. Not explained by the disease registers available: after allowing for COPD, asthma, diabetes and four other registers plus age and deprivation, "&\'16 Patient need\'!P6&" of "&\'16 Patient need\'!P5&" shortlisted practices stay above the 99.8% limit.  [16 Patient need]"',
         '="3. Flags hold within the year too: of "&\'14 Out of sample\'!B13&" practices flagged on Sep–Feb only, "&TEXT(\'14 Out of sample\'!B14,"0%")&" were still above the 99.8% limit in Mar–Aug (all practices: "&TEXT(\'14 Out of sample\'!B15,"0.0%")&").  [14 Out of sample]"',
         '="4. Review shortlist: "&\'13 Review shortlist\'!B4&" practices are above the adjusted 99.8% funnel limit, in the top fifth 9+ of 12 months, and still 9+ without lymecycline.  [9, 13]"',
         '="5. A different mix, not more prescribing: shortlisted practices write "&TEXT(\'14 Out of sample\'!B50,"0")&" items per 1,000 patients vs "&TEXT(\'14 Out of sample\'!C50,"0")&", but "&TEXT(\'14 Out of sample\'!B52,"0")&" Watch+Reserve vs "&TEXT(\'14 Out of sample\'!C52,"0")&".  [14]"',
         '="6. The shortlist holds only "&TEXT(\'17 Sizing\'!G8,"0%")&"–"&TEXT(\'17 Sizing\'!G5,"0%")&" of the Watch+Reserve items above the benchmark, whichever benchmark is used; switching all of that excess to Access would add "&TEXT(\'17 Sizing\'!I5,"0.0")&"–"&TEXT(\'17 Sizing\'!I8,"0.0")&" points of Access. The wider gap needs system-wide action.  [17 Sizing]"',
         '="7. A practice\'s share is stable: first half vs second half r = "&TEXT(\'8 Reliability\'!B5,"0.00")&", but about "&TEXT(\'8 Reliability\'!B18,"0%")&" of one month\'s differences are noise, so rank on 12 months.  [8 Reliability]"',
         '="8. Age, size, deprivation and ICB explain "&TEXT(\'11 Deprivation\'!B18,"0%")&" of the differences in share, almost all of it ICB; older lists mean more prescribing (R² = "&TEXT(\'5 Age\'!B6,"0.00")&"), not a riskier mix.  [5, 11]"']
for k, f in enumerate(finds): B.cell(10 + k, 2, f).font = Font(size=10)
B["B18"] = "Limits: no diagnoses or penicillin-allergy records (some Watch use is right); items are not doses, so this does not track the dose-based national targets; age bands from July only; associations, not causes."
B["B18"].font = note_font
from copy import deepcopy
for chart, anchor in [(monthly_chart_bar, "B20"), (monthly_chart_line, "L20")]:
    B.add_chart(deepcopy(chart), anchor)
fc2 = deepcopy(fc); fc2.height = 8; fc2.width = 16; B.add_chart(fc2, "B36")
sp2 = deepcopy(sp); sp2.height = 8; sp2.width = 16; B.add_chart(sp2, "L36")
B["B54"] = "Spread and relationships"; B["B54"].font = Font(bold=True, size=12, color=INK)
B.add_chart(deepcopy(box_wr_age), "B56")
B.add_chart(deepcopy(box_month), "B76")
short = ["Rate/yr", "W+R %", "% 65+", "% 15-24", "% 0-9", "Size", "Top-fifth months", "IMD"]
B["L56"] = "Correlation matrix (r, from sheet 6)"; B["L56"].font = Font(bold=True, size=11, color=INK)
for j, nme in enumerate(short):
    c = B.cell(57, 13 + j, nme); c.font = Font(bold=True, color="FFFFFF", size=8); c.fill = HEAD; c.alignment = Alignment(wrap_text=True, horizontal="center")
    c = B.cell(58 + j, 12, nme); c.font = Font(bold=True, size=8); c.alignment = Alignment(horizontal="right")
    for i in range(8):
        cell = B.cell(58 + i, 13 + j, f"='6 Correlation'!{CL(2+j)}{5+i}")
        cell.number_format = "0.00"; cell.alignment = Alignment(horizontal="center"); cell.font = Font(size=9, bold=True)
B.row_dimensions[57].height = 30
B.conditional_formatting.add("M58:T65", ColorScaleRule(start_type="num", start_value=-1, start_color="2F6FB5", mid_type="num", mid_value=0,
                                                         mid_color="F7F7F7", end_type="num", end_value=1, end_color="C0392B"))
B["L67"] = "How to read: +1 = rise together (red), 0 = no link (white), −1 = one rises as the other falls (blue)."
B["L68"] = "Strongest real link: % aged 65+ with rate (≈0.6). Age with W+R % ≈ 0. Correlation is not cause."
B["L69"] = "W+R % with top-fifth months (≈0.86) is built in: one is made from the other."
for c in ("L67", "L68", "L69"): B[c].font = note_font
# make ICB difference column point to T6
for r in range(5, 41):
    pass

# ================= Start here =================
# ================= 14 Out of sample =================
Oo = wb.create_sheet("14 Out of sample")
title(Oo, "14 · Does a flag hold? Flag on Sep 2025–Feb 2026 only, then check Mar–Aug 2026",
      "Same rules as the shortlist, using 6 months: adjusted funnel z > 3.09, top fifth in 5+ of 6 months, and 5+ of 6 without lymecycline. Then look at the next 6 months, which were not used to make the flag.")
Oo.column_dimensions["A"].width = 64; Oo.column_dimensions["B"].width = 14; Oo.column_dimensions["C"].width = 14
for c_, h_ in [(2, "Sep–Feb"), (3, "Mar–Aug")]:
    x_ = Oo.cell(4, c_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD
rowsO = [(5, "England W+R share as a proportion (p0)", "=SUM({w})/SUM({n})", "0.0000"),
         (6, "z at 10th percentile (winsorising)", "=_xlfn.PERCENTILE.INC({z},0.1)", "0.00"),
         (7, "z at 90th percentile (winsorising)", "=_xlfn.PERCENTILE.INC({z},0.9)", "0.00"),
         (8, "φ = average of winsorised z²", "=SUMSQ({wz})/COUNT({z})", "0.00"),
         (9, "Sum of weights", "=SUM({wt})", "#,##0"), (10, "Sum of weights²", "=SUMSQ({wt})", "0.00E+00"),
         (11, "τ² (extra between-practice variance)", "=MAX(0,(COUNT({z})*{c}8-(COUNT({z})-1))/({c}9-{c}10/{c}9))", "0.000000")]
for r_, lab, f_, fm in rowsO:
    Oo.cell(r_, 1, lab)
    for c_, cols in [(2, ("BF", "BG", "BN", "BO", "BP")), (3, ("BH", "BI", "BT", "BU", "BV"))]:
        w_, n_, z_, wz_, wt_ = (pr(x) for x in cols)
        cell = Oo.cell(r_, c_, f_.format(w=w_, n=n_, z=z_, wz=wz_, wt=wt_, c=CL(c_)))
        cell.fill = CALC; cell.number_format = fm
kv(Oo, 13, "Practices flagged using Sep–Feb only", f"=SUM({pr('BR')})", "#,##0", True)
kv(Oo, 14, "…of these, still above the adjusted 99.8% limit in Mar–Aug", f"=COUNTIFS({pr('BR')},1,{pr('BW')},\">3.09\")/B13", "0.0%", True)
kv(Oo, 15, "Base rate: all practices above the 99.8% limit in Mar–Aug", f"=COUNTIF({pr('BW')},\">3.09\")/COUNT({pr('BW')})", "0.0%")
kv(Oo, 16, "…of the flagged, above the 95% limit in Mar–Aug", f"=COUNTIFS({pr('BR')},1,{pr('BW')},\">1.96\")/B13", "0.0%")
kv(Oo, 17, "…of the flagged, in the top fifth 4+ of 6 months in Mar–Aug", f"=COUNTIFS({pr('BR')},1,{pr('BL')},\">=4\")/B13", "0.0%")
kv(Oo, 18, "…of the flagged, below the England share in Mar–Aug", f"=COUNTIFS({pr('BR')},1,{pr('BX')},\"<\"&C5*100)/B13", "0.0%")
kv(Oo, 19, "Mean W+R % of the flagged, Sep–Feb", f"=AVERAGEIFS({pr('W')},{pr('BR')},1)", "0.0")
kv(Oo, 20, "Mean W+R % of the flagged, Mar–Aug", f"=AVERAGEIFS({pr('BX')},{pr('BR')},1)", "0.0")
kv(Oo, 21, "England W+R %, Mar–Aug", "=C5*100", "0.0")
note(Oo, "A23", "How to read this. If the flag were mostly chance, flagged practices would drift back towards England in the next six months "
     "and only about 2% would be flagged again (row 15). Instead more than half stay above the strict 99.8% limit and almost none fall below "
     "England. This is the most direct test of whether flagging a practice now tells you something about later.", "A23:H27")
Oo["A29"] = "How much does the shortlist size depend on the cut-offs? (12 months)"; Oo["A29"].font = Font(bold=True, color=INK, size=12)
header_cells = ["z cut-off \\ months in top fifth", "8+", "9+", "10+", "11+"]
for j_, h_ in enumerate(header_cells, 1):
    x_ = Oo.cell(30, j_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD
for r_, zc in [(31, 2.58), (32, 3.09), (33, 3.5)]:
    Oo.cell(r_, 1, f"Adjusted z > {zc}" + ("   (main analysis, 99.8%)" if zc == 3.09 else ""))
    for j_, m_ in enumerate([8, 9, 10, 11], 2):
        c_ = Oo.cell(r_, j_, f'=COUNTIFS({pr("AJ")},">{zc}",{pr("M")},">={m_}",{pr("Z")},">={m_}")'); c_.fill = CALC
note(Oo, "A35", "The months rule barely changes the list; the z cut-off roughly halves or doubles it. So 106 is the size at the standard 99.8% "
     "limit, not a precise count of problem practices: a stricter or looser cut-off gives about 70 to 180.", "A35:H38")
Oo["A40"] = "Dose check: shortlisted practices that drop out of the top fifth by dose (ADQ)"; Oo["A40"].font = Font(bold=True, color=INK, size=12)
kv(Oo, 41, "Shortlisted practices NOT high 9+ months by dose", f"=COUNTIFS({pr('AN')},1,{pr('AQ')},\"<9\")", "#,##0")
Oo["B42"] = ArrayFormula("B42", f"=MEDIAN(IF(({pr('AN')}=1)*({pr('AQ')}<9),{pr('AA')}))"); Oo["A42"] = "…their median W+R % by dose"
Oo["B42"].fill = CALC; Oo["B42"].number_format = "0.0"
kv(Oo, 43, "England W+R % by dose", "='10 Sensitivity'!B8", "0.0")
note(Oo, "A45", "They leave the top fifth by dose but stay well above England, so the dose view re-ranks practices rather than clearing them.", "A45:H46")
Oo["A48"] = "Share or volume? A share rises with more Watch+Reserve OR with less Access"; Oo["A48"].font = Font(bold=True, color=INK, size=12)
for c_, h_ in [(2, "Shortlist"), (3, "Other practices")]:
    x_ = Oo.cell(49, c_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD
_sl, _pt, _ac, _wr, _cl, _sh = pr("AN"), pr("H"), pr("E"), pr("F"), pr("D"), pr("J")
for r_, lab, num in [(50, "Median classified antibiotic items per 1,000 patients a year", _cl), (51, "Median Access items per 1,000 patients a year", _ac),
                     (52, "Median Watch+Reserve items per 1,000 patients a year", _wr)]:
    Oo.cell(r_, 1, lab)
    for c_, cond in [(2, "=1"), (3, "=0")]:
        ref = f"{CL(c_)}{r_}"
        Oo[ref] = ArrayFormula(ref, f"=MEDIAN(IF({_sl}{cond},{num}/{_pt}*1000))"); Oo[ref].fill = CALC; Oo[ref].number_format = "0"
Oo["A54"] = "80th percentile of Watch+Reserve items per 1,000 patients (all practices)"
Oo["B54"] = ArrayFormula("B54", f"=_xlfn.PERCENTILE.INC({_wr}/{_pt}*1000,0.8)"); Oo["B54"].fill = CALC; Oo["B54"].number_format = "0.0"
Oo["A55"] = "Shortlisted practices also in the top fifth on Watch+Reserve items per 1,000 patients"
Oo["B55"] = ArrayFormula("B55", f"=SUM(({_sl}=1)*({_wr}/{_pt}*1000>=B54))"); Oo["B55"].fill = CALC; Oo["B55"].font = Font(bold=True)
Oo["A56"] = "…shortlisted but NOT in that top fifth (high share partly because Access is low)"; Oo["B56"] = f"='13 Review shortlist'!B4-B55"; Oo["B56"].fill = CALC
Oo["A57"] = "Practices in the top fifth on Watch+Reserve per 1,000 but NOT in the top fifth on 12-month share (missed by a share measure)"
Oo["B57"] = ArrayFormula("B57", f"=SUM(({_wr}/{_pt}*1000>=B54)*({_sh}<_xlfn.PERCENTILE.INC({_sh},0.8)))"); Oo["B57"].fill = CALC
note(Oo, "A59", "Shortlisted practices do not prescribe more antibiotics overall: they prescribe less Access and more Watch+Reserve, which is the "
     "substitution stewardship teams look for. But some are on the list partly because they prescribe little Access, and a share cannot see "
     "heavy prescribers who use a lot of both. Read the shortlist alongside Watch+Reserve items per 1,000 patients.", "A59:H62")

# ================= 15 Two years =================
TY = pd.read_csv("outputs/tables/practices_two_years.csv", dtype={"pc": str}).set_index("pc")
CM = pd.read_csv("outputs/tables/practices_y2_casemix.csv", dtype={"pc": str}).set_index("pc")
Y2 = json.load(open("outputs/tables/results_y2_casemix.json"))
Ty = wb.create_sheet("15 Three years")
title(Ty, "15 · Is it the same practices every year? The screen run on Sep 2023–Aug 2024 and Sep 2024–Aug 2025 on their own, then compared with Sep 2025–Aug 2026",
      "White columns are the earlier years, computed in Python from the same NHSBSA API query and the same rules (src/second_year_casemix.py). Columns P–R point at this year's sheet 2. "
      "2022-23 is left out: the December 2022 Group A strep outbreak sharply raised Watch prescribing.")
tcols = ["Practice code"]
for yy in ("2023-24", "2024-25"):
    tcols += [f"{yy} W+R items", f"{yy} classified items", f"{yy} months in top fifth", f"{yy} months in top fifth without lymecycline",
              f"{yy} z adjusted (funnel fitted on all {yy} practices)", f"{yy} W+R %", f"{yy} shortlist? (z>3.09, 9+, 9+ without lymecycline)"]
tcols += ["2025-26 W+R %", "2025-26 z adjusted", "2025-26 shortlist?", "Years shortlisted (of 3)"]
header(Ty, 4, tcols, [10] + [9, 9, 9, 9, 11, 8, 11] * 2 + [9, 10, 10, 10])
Ty.row_dimensions[4].height = 80
TE = NP + 4
for i, pc_ in enumerate(pcs.pc, start=5):
    Ty.cell(i, 1, pc_)
    for c0_, sfx in ((2, "2324"), (9, "2425")):
        L_ = lambda k: CL(c0_ + k)
        if pc_ in TY.index and pd.notna(TY.at[pc_, f"cls_{sfx}"]):
            t_ = TY.loc[pc_]
            for k_, v_ in enumerate([int(t_[f"wr_{sfx}"]), int(t_[f"cls_{sfx}"]), int(t_[f"months_top_{sfx}"]), int(t_[f"months_top_nl_{sfx}"]), round(float(t_[f"z_od_{sfx}"]), 6)]):
                Ty.cell(i, c0_ + k_, v_)
            Ty.cell(i, c0_ + 5, f"={L_(0)}{i}/{L_(1)}{i}*100").fill = CALC
            Ty.cell(i, c0_ + 6, f"=IF(AND({L_(4)}{i}>3.09,{L_(2)}{i}>=9,{L_(3)}{i}>=9),1,0)").fill = CALC
        else:
            Ty.cell(i, c0_ + 5, '=""'); Ty.cell(i, c0_ + 6, '=""')
    r2_ = i - 3
    Ty.cell(i, 16, f"='2 Practices'!J{r2_}").fill = CALC
    Ty.cell(i, 17, f"='2 Practices'!AJ{r2_}").fill = CALC
    Ty.cell(i, 18, f"='2 Practices'!AN{r2_}").fill = CALC
    Ty.cell(i, 19, f'=IF(AND(ISNUMBER(H{i}),ISNUMBER(O{i})),H{i}+O{i}+R{i},"")').fill = CALC
tr = lambda c: f"${c}$5:${c}${TE}"
Ty.column_dimensions["U"].width = 74; Ty.column_dimensions["V"].width = 12
kvT = [(5, "Practices present in all three years", f"=COUNT({tr('S')})", "#,##0", True),
       (6, "Correlation of W+R %: 2024-25 vs 2025-26 (one year apart)", f"=CORREL({tr('N')},{tr('P')})", "0.00", True),
       (7, "Correlation of W+R %: 2023-24 vs 2025-26 (two years apart)", f"=CORREL({tr('G')},{tr('P')})", "0.00", False),
       (9, "Shortlisted in 2024-25 (and present in 2025-26)", f"=COUNTIF({tr('O')},1)", "#,##0", True),
       (10, "…still above the 99.8% limit one year later", f"=COUNTIFS({tr('O')},1,{tr('Q')},\">3.09\")/V9", "0%", True),
       (11, "…shortlisted again one year later", f"=COUNTIFS({tr('O')},1,{tr('R')},1)/V9", "0%", True),
       (12, "…above the 95% limit one year later", f"=COUNTIFS({tr('O')},1,{tr('Q')},\">1.96\")/V9", "0%", False),
       (13, "Comparison: NOT shortlisted in 2024-25, above the 99.8% limit in 2025-26", f"=COUNTIFS({tr('O')},0,{tr('Q')},\">3.09\")/COUNTIF({tr('O')},0)", "0.0%", True),
       (14, "Mean W+R % of the 2024-25 shortlist in 2024-25", f"=AVERAGEIFS({tr('N')},{tr('O')},1)", "0.0", False),
       (15, "…and the same practices in 2025-26", f"=AVERAGEIFS({tr('P')},{tr('O')},1)", "0.0", False),
       (17, "Shortlisted in 2023-24 (and present in all three years)", f"=COUNTIFS({tr('H')},1,{tr('S')},\">=0\")", "#,##0", True),
       (18, "…still above the 99.8% limit TWO years later", f"=COUNTIFS({tr('H')},1,{tr('S')},\">=0\",{tr('Q')},\">3.09\")/V17", "0%", True),
       (19, "Comparison: NOT shortlisted in 2023-24, above the 99.8% limit in 2025-26", f"=COUNTIFS({tr('H')},0,{tr('S')},\">=0\",{tr('Q')},\">3.09\")/COUNTIFS({tr('H')},0,{tr('S')},\">=0\")", "0.0%", True),
       (21, "Shortlisted in ALL THREE years", f"=COUNTIF({tr('S')},3)", "#,##0", True),
       (22, "Shortlisted in at least two of the three years", f"=COUNTIF({tr('S')},\">=2\")", "#,##0", False),
       (23, "On the shortlist in both 2024-25 and 2025-26", f"=COUNTIFS({tr('O')},1,{tr('R')},1)", "#,##0", False),
       (25, "Significantly LOW (below the lower 99.8% limit) in 2025-26", f"=COUNTIF({tr('Q')},\"<-3.09\")", "#,##0", False),
       (26, "…also significantly low in 2024-25", f"=COUNTIFS({tr('Q')},\"<-3.09\",{tr('M')},\"<-3.09\")", "#,##0", False)]
for r_, lab, f_, fm, bold in kvT:
    Ty.cell(r_, 21, lab).font = Font(bold=bold)
    c_ = Ty.cell(r_, 22, f_); c_.fill = CALC; c_.number_format = fm
    if bold: c_.font = Font(bold=True)
Ty.merge_cells("U28:U36")
Ty["U28"] = ("How to read this. Each earlier list was made without any later data. If being flagged were mostly chance, flagged practices "
             "would fall back to the rate of everyone else (rows 13 and 19). Instead many stay above the strict limit one and two years later. "
             "The effect fades with time (rows 10 and 18) because some flags in any one year are chance and some practices change, so a practice "
             "flagged in all three years (row 21) is the firmest signal. The low practices are less stable (rows 25-26).")
Ty["U28"].alignment = Alignment(wrap_text=True, vertical="top"); Ty["U28"].font = note_font

# ================= 16 Patient need =================
Pn = wb.create_sheet("16 Patient need")
title(Pn, "16 · Is it the patients? Recorded disease registers (QOF 2025-26) added to the model, then the funnel redrawn around each practice's expected share",
      "Prevalence = register ÷ the register's own list (QOF method). The expected share comes from a quasi-binomial model in Python (src/second_year_casemix.py): "
      "W+R share ~ % 65+, % 15-24, IMD, log size + COPD, asthma, diabetes, CKD, cancer, dementia, heart failure. ICB is NOT in it: a local area is not patient need.")
regs = [("copd", "COPD %"), ("ast", "Asthma % (6+)"), ("dm", "Diabetes % (17+)"), ("ckd", "CKD % (18+)"), ("can", "Cancer %"), ("dem", "Dementia %"), ("hf", "Heart failure %")]
pcols2 = ["Practice code"] + [l for _, l in regs] + ["Expected W+R % from case-mix model", "z adjusted vs case-mix expected share",
                                                     "Shortlisted? (sheet 2)", "Significantly low? (sheet 2)", "W+R % (sheet 2)"]
header(Pn, 4, pcols2, [10] + [9] * 7 + [12, 12, 10, 10, 9])
Pn.row_dimensions[4].height = 60
for i, pc_ in enumerate(pcs.pc, start=5):
    Pn.cell(i, 1, pc_)
    c_ = CM.loc[pc_]
    for j_, (k_, _) in enumerate(regs, start=2):
        Pn.cell(i, j_, round(float(c_[k_]), 3))
    Pn.cell(i, 9, round(float(c_.exp_cm) * 100, 3)); Pn.cell(i, 10, round(float(c_.z_cm), 4))
    r2_ = i - 3
    Pn.cell(i, 11, f"='2 Practices'!AN{r2_}").fill = CALC
    Pn.cell(i, 12, f"=IF('2 Practices'!AJ{r2_}<-3.09,1,0)").fill = CALC
    Pn.cell(i, 13, f"='2 Practices'!J{r2_}").fill = CALC
nr = lambda c: f"${c}$5:${c}${TE}"
Pn.column_dimensions["O"].width = 66; Pn.column_dimensions["P"].width = 12; Pn.column_dimensions["Q"].width = 12; Pn.column_dimensions["R"].width = 12
kvP = [(5, "Shortlisted practices (sheet 13)", f"=SUM({nr('K')})", "#,##0", True),
       (6, "…still above the 99.8% limit after allowing for recorded patient need", f"=COUNTIFS({nr('K')},1,{nr('J')},\">3.09\")", "#,##0", True),
       (7, "…still above the 95% limit", f"=COUNTIFS({nr('K')},1,{nr('J')},\">1.96\")", "#,##0", False),
       (8, "All practices above the 99.8% limit on the case-mix funnel", f"=COUNTIF({nr('J')},\">3.09\")", "#,##0", False),
       (9, "Significantly low practices (sheet 2)", f"=SUM({nr('L')})", "#,##0", False),
       (10, "…still below the lower 99.8% limit after allowing for patient need", f"=COUNTIFS({nr('L')},1,{nr('J')},\"<-3.09\")", "#,##0", False),
       (11, "Correlation of z before and after the adjustment (near 1 = the registers change little)", f"=CORREL({nr('J')},'2 Practices'!$AJ$2:$AJ${PE})", "0.00", True)]
for r_, lab, f_, fm, bold in kvP:
    Pn.cell(r_, 15, lab).font = Font(bold=bold)
    c_ = Pn.cell(r_, 16, f_); c_.fill = CALC; c_.number_format = fm
    if bold: c_.font = Font(bold=True)
Pn["O12"] = "How much of the variation in W+R % is explained? (R², ordinary least squares; computed in Python)"; Pn["O12"].font = Font(bold=True, color=INK)
for r_, lab, v_ in [(13, "% 65+, IMD, log size", Y2["ols_r2_age_imd_size"]), (14, "+ % 15-24 and seven disease registers", Y2["ols_r2_patient_all"]),
                    (15, "+ ICB average W+R % (local area)", Y2["ols_r2_patient_all_icb"])]:
    Pn.cell(r_, 15, lab); c_ = Pn.cell(r_, 16, round(v_, 4)); c_.number_format = "0.0%"
Pn["O17"] = "Median prevalence by group"; Pn["O17"].font = Font(bold=True, color=INK)
for c_, h_ in [(16, "Shortlist"), (17, "Low"), (18, "Other")]:
    x_ = Pn.cell(18, c_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD
for k_, (key_, lab_) in enumerate(regs):
    r_ = 19 + k_; Pn.cell(r_, 15, lab_)
    col_ = CL(2 + k_)
    for c_, cond in [(16, f"({nr('K')}=1)"), (17, f"({nr('L')}=1)"), (18, f"({nr('K')}=0)*({nr('L')}=0)")]:
        ref = f"{CL(c_)}{r_}"
        Pn[ref] = ArrayFormula(ref, f"=MEDIAN(IF({cond},{nr(col_)}))"); Pn[ref].fill = CALC; Pn[ref].number_format = "0.00"
Pn.merge_cells("O27:R34")
Pn["O27"] = ("How to read this. If shortlisted practices simply had sicker patients (more COPD, more asthma), their expected share would "
             "rise and most would drop below the limit. They do not: almost all stay above it. But this is a weak test: the registers explain so little "
             "that the z-scores barely move (row 11), and they do not measure infection rates. "
             "Caution: QOF has no register for penicillin allergy, bronchiectasis or acne, which are real reasons for Watch prescribing, so the "
             "claim is 'not explained by recorded patient need', not 'not explained by patients'.")
Pn["O27"].alignment = Alignment(wrap_text=True, vertical="top"); Pn["O27"].font = note_font

# ================= 17 Sizing =================
Sz = wb.create_sheet("17 Sizing")
title(Sz, "17 · How big is the prize? Watch+Reserve items above the England share, and the practices that are consistently low",
      "Excess = W+R items − classified items × England W+R share. A what-if upper bound in items, not doses: some practices are above England for good clinical reasons.")
Sz.column_dimensions["A"].width = 78; Sz.column_dimensions["B"].width = 14; Sz.column_dimensions["C"].width = 14
_d, _f, _sl, _e, _h, _z = pr("D"), pr("F"), pr("AN"), pr("E"), pr("H"), pr("AJ")
kvS = [(4, "England W+R share (proportion)", f"=SUM({_f})/SUM({_d})", "0.0000", False),
       (5, "Excess W+R items a year: the review shortlist", f"=SUMPRODUCT(({_sl}=1)*({_f}-{_d}*B4))", "#,##0", True),
       (6, "Excess W+R items a year: every practice above the England share", f"=SUMPRODUCT(({_f}-{_d}*B4>0)*({_f}-{_d}*B4))", "#,##0", True),
       (7, "Number of practices above the England share", f"=SUMPRODUCT(--({_f}-{_d}*B4>0))", "#,##0", False),
       (8, "Shortlist's part of all excess", "=B5/B6", "0%", True),
       (9, "England Access % by items", f"=SUM({_e})/SUM({_d})*100", "0.00", False),
       (10, "Access points gained if the shortlist's excess became Access", f"=B5/SUM({_d})*100", "0.00", True),
       (11, "Access points gained if ALL excess became Access", f"=B6/SUM({_d})*100", "0.00", True)]
for r_, lab, f_, fm, bold in kvS:
    Sz.cell(r_, 1, lab).font = Font(bold=bold); c_ = Sz.cell(r_, 2, f_); c_.fill = CALC; c_.number_format = fm
    if bold: c_.font = Font(bold=True)
Sz["E3"] = "Does the answer depend on the comparison point?"; Sz["E3"].font = Font(bold=True, color=INK, size=12)
for j_, h_ in enumerate(["Compared against", "Benchmark W+R %", "Shortlist's part of the excess", "Excess W+R items a year", "Access points if all excess became Access"]):
    x_ = Sz.cell(4, 5 + j_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD; x_.alignment = Alignment(wrap_text=True)
_j = pr("J")
for r_, lab_, bf_ in [(5, "England share", "=B4*100"), (6, "Median practice", f"=MEDIAN({_j})"),
                      (7, "Best quarter (25th percentile)", f"=_xlfn.PERCENTILE.INC({_j},0.25)"), (8, "Best tenth (10th percentile)", f"=_xlfn.PERCENTILE.INC({_j},0.1)")]:
    Sz.cell(r_, 5, lab_)
    Sz.cell(r_, 6, bf_).number_format = "0.0"
    Sz.cell(r_, 8, f"=SUMPRODUCT(({_f}-{_d}*F{r_}/100>0)*({_f}-{_d}*F{r_}/100))").number_format = "#,##0"
    Sz.cell(r_, 7, f"=SUMPRODUCT(({_sl}=1)*({_f}-{_d}*F{r_}/100))/H{r_}").number_format = "0%"
    Sz.cell(r_, 9, f"=H{r_}/SUM({_d})*100").number_format = "0.0"
    for c_ in range(6, 10): Sz.cell(r_, c_).fill = CALC
for c_, w_ in zip("EFGHI", [30, 12, 14, 14, 16]): Sz.column_dimensions[c_].width = w_
Sz.row_dimensions[4].height = 45
Sz["A13"] = "Practices significantly LOW (below the lower 99.8% limit): what do they do differently?"; Sz["A13"].font = Font(bold=True, color=INK, size=12)
for c_, h_ in [(2, "Low practices"), (3, "All practices")]:
    x_ = Sz.cell(14, c_, h_); x_.font = Font(bold=True, color="FFFFFF"); x_.fill = HEAD
Sz["A15"] = "Number"; Sz["B15"] = f"=COUNTIF({_z},\"<-3.09\")"; Sz["C15"] = f"=COUNT({_z})"
for r_, lab, num in [(16, "Median Access items per 1,000 patients a year", _e), (17, "Median W+R items per 1,000 patients a year", _f),
                     (18, "Median classified items per 1,000 patients a year", _d)]:
    Sz.cell(r_, 1, lab)
    Sz[f"B{r_}"] = ArrayFormula(f"B{r_}", f"=MEDIAN(IF({_z}<-3.09,{num}/{_h}*1000))")
    Sz[f"C{r_}"] = ArrayFormula(f"C{r_}", f"=MEDIAN({num}/{_h}*1000)")
for r_ in range(15, 19):
    for c_ in ("B", "C"): Sz[f"{c_}{r_}"].fill = CALC; Sz[f"{c_}{r_}"].number_format = "#,##0"
Sz.merge_cells("A20:C25")
Sz["A20"] = ("How to read this. Reviewing the shortlist is a cheap first step, but it holds only a small part of the excess (10% or less, "
             "whatever comparison point is used: columns E-I): most sits with thousands of ordinary practices, so moving the national figure needs "
             "system-wide action. How big that system-wide prize is depends on the benchmark: about 1 Access point against England, 4 against the best tenth. The low practices "
             "prescribe about as much Access as everyone else but far less Watch+Reserve, so they are not simply under-treating. They are "
             "worth learning from, but treat them with care: their patients are younger and more deprived, and only some are low in both years (sheet 15).")
Sz["A20"].alignment = Alignment(wrap_text=True, vertical="top"); Sz["A20"].font = note_font

S = wb.create_sheet("Start here", 0)
S.column_dimensions["A"].width = 120
lines = [("Project 1 — Antibiotic stewardship in English GP practices (12 months)", Font(bold=True, size=16, color=INK)),
         ("Authors: Ashish Agarwal and Aashish Gill  ·  Data: Sep 2025 – Aug 2026  ·  Version 3 (three years, recorded patient need, sizing)", note_font), ("", None),
         ("THE QUESTION", Font(bold=True, color=INK)),
         ("Which GP practices use a higher share of 'Watch' (riskier) antibiotics than expected, is that consistent across a whole year, and is it explained by age, size, deprivation or local area?", None),
         ("", None), ("HOW THIS WORKBOOK WORKS — read the sheets left to right", Font(bold=True, color=INK)),
         ("Dashboard — headline numbers, eight findings and charts. Every number is a formula pointing at the sheets below.", None),
         ("1 Monthly — one row per month (SUMIFS). Winter peak, Watch share trend, monthly top-fifth cut-offs and the monthly noise share.", None),
         (f"2 Practices — one row per practice ({NP:,}). Rate, W+R %, gap vs ICB, months in top fifth, halves of the year, without lymecycline, by dose, IMD, funnel z-scores, shortlist flag.", None),
         ("3 ICB — one row per local area. SUMIFS adds up its practices.", None),
         ("4 Consistency — EARLIER APPROACH, kept for comparison: months in the top fifth vs a pure-luck benchmark (BINOM.DIST). Superseded by sheets 8, 9 and 14.", None),
         ("5 Age — scatter, trendline, R², slope confidence interval, and box plots by age fifth.", None),
         ("6 Correlation — CORREL between every pair of measures, including IMD.", None),
         ("7 Top 15 — EARLIER APPROACH, kept for comparison: the largest 12-month gaps vs ICB (favours big practices). Superseded by sheet 13.", None),
         ("8 Reliability — split-half correlation, month-to-month repeat, and how much of the spread is noise.", None),
         ("9 Funnel — funnel plot adjusted for over-dispersion (Spiegelhalter, 2005).", None),
         ("10 Sensitivity — the headline with lymecycline removed, by dose (ADQ), with OpenPrescribing's denominator, and with atypical practices kept.", None),
         ("11 Deprivation — IMD 2025 correlations, IMD fifths, and a multiple regression with confidence intervals (LINEST).", None),
         ("12 Watch drugs — which Watch antibiotics make up the Watch items, with a check that totals match.", None),
         ("13 Review shortlist — practices that meet three screening criteria: unusual, persistent and not just lymecycline.", None),
         ("14 Out of sample — flag on Sep–Feb only and check Mar–Aug; how the shortlist size depends on the cut-offs; the dose check.", None),
         ("15 Three years — the same screen on Sep 2023–Aug 2024 and Sep 2024–Aug 2025, followed into this year: are the flagged practices the same?", None),
         ("16 Patient need — QOF 2025-26 disease registers (COPD, asthma, diabetes and more) and a funnel redrawn around each practice's case-mix-expected share.", None),
         ("17 Sizing — how many Watch+Reserve items sit above the England share, and what the consistently low practices do differently.", None),
         ("Data, Age data, IMD data, Cleaning log, AWaRe mapping — the inputs. Light-teal cells are formulas; white cells are data.", None),
         ("", None), ("KEY FORMULAS", Font(bold=True, color=INK)),
         ("Items per 1,000 patients = items ÷ patients × 1,000", None),
         ("Watch+Reserve % = (Watch + Reserve items) ÷ classified items × 100     (classified = Access + Watch + Reserve + Other)", None),
         ("Gap vs ICB = practice W+R items − practice items × ICB W+R % ÷ 100", None),
         ("Top fifth = practice W+R % is at or above that month's 80th percentile (PERCENTILE.INC)", None),
         ("Split-half r = CORREL(W+R % Sep–Feb, W+R % Mar–Aug)   ·   Noise share = average p(1−p)/n ÷ variance of practice shares", None),
         ("Adjusted funnel z = (p − p0) ÷ √(p0(1−p0)/n + τ²), flagged if z > 3.09 (99.8%)", None),
         ("", None), ("DATA SOURCES", Font(bold=True, color=INK)),
         ("NHS Business Services Authority (2025–2026) English Prescribing Dataset (EPD) with SNOMED code, Sep 2025–Aug 2026. Queried through the NHSBSA Open Data Portal API, BNF 5.1 only (items, ADQ usage, and items per Watch substance).", None),
         ("NHS England (2025–2026) Patients Registered at a GP Practice: totals (Sep 25, Dec 25, Mar 26, Apr 26, Jul 26), 5-year age bands (Jul 26), and patients by LSOA 2021 (Jul 26).", None),
         ("Ministry of Housing, Communities and Local Government (2025) English Indices of Deprivation 2025, File 5 (scores by LSOA).", None),
         ("UK Health Security Agency (2025) UK-AWaRe antibiotic classification. 2 judgement calls are noted in 'AWaRe mapping'.", None),
         ("NHS Business Services Authority (2023–2025) EPD, Sep 2023–Aug 2025 (same API query; sheet 15). NHS England (2026) Quality and Outcomes Framework 2025-26, prevalence by practice (sheet 16).", None),
         ("", None), ("LIMITATIONS", Font(bold=True, color=INK)),
         ("No diagnosis or penicillin-allergy data, so some Watch prescribing will be clinically right. QOF registers (sheet 16) cover COPD, asthma and other conditions, not allergy, bronchiectasis or acne. Results show associations, not causes.", None),
         ("Items count prescriptions equally; ADQ (sheet 10) weights by dose but is not the WHO DDD used for national targets.", None),
         ("Age bands and IMD are from July 2026 only. Patient lists for 7 of the 12 months use the nearest available month (median change −0.6%).", None),
         ("IMD describes the neighbourhoods patients live in, not the patients themselves. Rurality and care-home share were not tested.", None),
         ("Practice names and NHS codes are kept in this workbook so every result can be checked against the public NHS data. The report figures and the public dashboard do not name practices (the data are public, so this is not anonymity): a flag is a prompt for a conversation with a practice, not a public judgement of it.", None)]
for k, (t, f) in enumerate(lines, 1):
    c = S.cell(k, 1, t); c.alignment = Alignment(wrap_text=True)
    if f: c.font = f

wb.move_sheet("Start here", offset=-wb.index(wb["Start here"]))
wb.active = 0
order = ["Start here", "Dashboard", "1 Monthly", "2 Practices", "3 ICB", "4 Consistency", "5 Age", "6 Correlation", "7 Top 15",
         "8 Reliability", "9 Funnel", "10 Sensitivity", "11 Deprivation", "12 Watch drugs", "13 Review shortlist", "14 Out of sample", "15 Three years", "16 Patient need", "17 Sizing",
         "Data", "Age data", "IMD data", "Cleaning log", "AWaRe mapping"]
wb._sheets = [wb[n] for n in order]
for n, col in [("Dashboard", INK), ("1 Monthly", BLUE), ("2 Practices", TEAL), ("3 ICB", TEAL), ("4 Consistency", RED),
               ("5 Age", PURP), ("6 Correlation", PURP), ("7 Top 15", RED), ("8 Reliability", RED), ("9 Funnel", RED),
               ("10 Sensitivity", AMBER), ("11 Deprivation", PURP), ("12 Watch drugs", AMBER), ("13 Review shortlist", RED), ("14 Out of sample", RED), ("15 Three years", RED), ("16 Patient need", PURP), ("17 Sizing", AMBER), ("IMD data", GREY), ("Data", GREY), ("Age data", GREY), ("Cleaning log", GREY), ("AWaRe mapping", GREY)]:
    wb[n].sheet_properties.tabColor = col

from openpyxl.chart.title import Title
from openpyxl.chart.text import RichText, Text
from openpyxl.drawing.text import Paragraph, ParagraphProperties, CharacterProperties, RegularTextRun
SLOPE_, INTERCEPT_, R2_ = RES["age_slope"], RES["age_intercept"], RES["age_r2"]
SHORT = {  # chart titles state the takeaway; the numbers are already on the chart
    "Antibiotic items per 1,000 patients": "Antibiotic use rises sharply in winter",
    "Watch+Reserve share % (lowest in winter)": "…but the Watch+Reserve share dips: the extra winter prescriptions are mostly Access",
    "Box plot: practice W+R % each month — the whole spread, not just the average": "Practices differ far more than the monthly average moves",
    "Watch+Reserve % by ICB, Sep 2025–Aug 2026": "Some local areas lean on Watch+Reserve antibiotics far more than others",
    "Practices by months in the top fifth": "Far more practices stay in the top fifth than luck would allow",
    "% aged 65+ vs items per 1,000 per year": "Practices with older patients prescribe more antibiotics",
    "Box plot: W+R % by age fifth (1 = youngest) — boxes stay level": "Patient age does not change which antibiotics are chosen",
    "Box plot: items per 1,000 per year by age fifth — boxes climb": "Older patient lists mean more prescriptions",
    "Gap vs ICB average (Watch+Reserve items, 12 months)": "Earlier approach: ranking by item gap favours large practices",
    "W+R % first half vs second half (each dot = a practice)": "A practice's share in one half of the year predicts the other",
    "Adjusted funnel: 117 practices above the 99.8% limit (106 shortlisted, red)": "A small group of practices sits well above what chance and normal variation allow",
    "W+R % by deprivation fifth": "Deprivation makes little difference to the Watch+Reserve share",
    "Top 8 Watch antibiotics (% of Watch items)": "Three antibiotics make up most Watch prescribing"}


def rich(size, bold=False):
    return RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(sz=size, b=bold)),
                                 endParaRPr=CharacterProperties(sz=size, b=bold))])


def set_title(ch, text):
    ch.title = Title(tx=Text(rich=RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(sz=1200, b=True)),
                                                         r=[RegularTextRun(rPr=CharacterProperties(sz=1200, b=True), t=text)])])),
                     overlay=False)


def title_text(ch):
    try:
        return "".join(r.t for r in ch.title.tx.rich.p[0].r)
    except Exception:
        return None


for ws in wb.worksheets:
    for ch in ws._charts:
        t = title_text(ch)
        if t: set_title(ch, SHORT.get(t, t))
        for ax in (ch.x_axis, ch.y_axis):
            if ax.majorGridlines is not None:
                ax.majorGridlines.spPr = GraphicalProperties(ln=LineProperties(solidFill="E3E3E3", w=6350))
            ax.delete = False
            ax.txPr = rich(900)
            if ax.title is not None:
                tt = "".join(r.t for r in ax.title.tx.rich.p[0].r)
                ax.title = Title(tx=Text(rich=RichText(p=[Paragraph(pPr=ParagraphProperties(defRPr=CharacterProperties(sz=900)),
                                                                     r=[RegularTextRun(rPr=CharacterProperties(sz=900), t=tt)])])), overlay=False)
        if ch.legend is not None:
            ch.legend.overlay = False
        if getattr(ch, 'dataLabels', None) is not None:
            ch.dataLabels.txPr = rich(800)

from openpyxl.worksheet.errors import IgnoredErrors, IgnoredError
# Lymecycline (column K) is already inside Watch items, so SUM(G:J) deliberately leaves it out - tell Excel not to flag it
D.ignored_errors = IgnoredErrors(ignoredError=[IgnoredError(sqref=f"L2:L{DE}", formulaRange=True)])
from openpyxl.workbook.properties import CalcProperties
wb.calculation = CalcProperties(fullCalcOnLoad=True)
wb.save(OUT)
print("saved", OUT, "practices", NP, "data rows", ND, "age rows", NA)
