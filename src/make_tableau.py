"""Build the Tableau Public workbook (.twbx with embedded Hyper extracts) from the revised analysis outputs.
Run after src/extended_analysis.py and src/make_charts.py:   python src/make_tableau.py"""
import csv, os, shutil, sys, zipfile, json
from xml.sax.saxutils import quoteattr as q, escape
import numpy as np
import pandas as pd
from tableauhyperapi import (HyperProcess, Telemetry, Connection, CreateMode, TableDefinition,
                             SqlType, TableName, Inserter)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load_clean, ROOT
os.chdir(ROOT)
SRC = "Data/Datasources"   # the CSVs are packaged inside the .twbx, so the Data Source tab shows the data
NAME = "Antibiotic_Stewardship_Dashboard"
OUT = "/tmp/twbx_build"
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT + "/Data/Extracts")
R = json.load(open("outputs/tables/results.json"))
Y2 = json.load(open("outputs/tables/results_y2_casemix.json"))

# ---------------------------------------------------------------- data
P = pd.read_csv("outputs/tableau/tableau_practices_12m.csv")
# Public dashboard: practices are shown by an ID, not by name or NHS code (not anonymous: the public data can be matched back). The data is public, but labelling
# named surgeries as outliers without diagnoses would be unfair; the workbook keeps codes so the analysis can be checked.
_codes = sorted(P.practice_code)
_perm = np.random.default_rng(2026).permutation(len(_codes))
ANON = {c: f"P{k + 1:04d}" for c, k in zip(_codes, _perm)}
P["practice_code"] = P.practice_code.map(ANON)
P["practice_name"] = P.practice_code
practices = P[["practice_code", "practice_name", "icb_short", "cls", "wr", "pat", "rate", "share", "share_h1", "share_h2", "share_2425",
               "icb_share", "gap", "z_od", "months_top", "pct65", "imd", "age_group", "imd_group", "pattern"]].rename(
    columns={"cls": "items", "rate": "items_per_1000_per_year", "share": "wr_pct", "pct65": "pct_65plus", "pat": "avg_patients"})
practices["extra_vs_england"] = (practices.wr - practices["items"] * R["england_share"] / 100).round(1)
practices["zord"] = practices.pattern.map({"Review shortlist": 1, "Above funnel limit": 2, "Top fifth 9+ months": 3}).fillna(4)
practices["z_limit"] = 3.09; practices["zero_line"] = 200.0   # constant fields for the priority chart's reference lines (200 extra items ~ shortlist median)
for c in ["items_per_1000_per_year", "wr_pct", "share_h1", "share_h2", "share_2425", "icb_share", "gap", "z_od", "pct_65plus", "imd", "avg_patients"]:
    practices[c] = practices[c].round(3)

rx, _, _ = load_clean(True)
rx["wr_pct"] = ((rx.watch_items + rx.reserve_items) / rx.cls * 100).round(1)
short = P[P.pattern == "Review shortlist"].sort_values("z_od", ascending=False).head(15).reset_index(drop=True)
short["rank"] = range(1, 16)
short["label"] = "Practice " + short["rank"].astype(str)
short["gap_label"] = "z = " + short.z_od.round(1).astype(str)
rx["pc"] = rx.pc.map(ANON)
t15 = rx.merge(short[["practice_code", "rank", "label", "gap_label"]], left_on="pc", right_on="practice_code")
top15 = t15[["rank", "label", "gap_label", "ym", "wr_pct", "practice_code"]].copy()
_ms = sorted(top15.ym.unique())
top15["wr_lbl"] = top15.wr_pct.map(lambda v: f"{v:.1f}")   # cell text "36.2": Tableau shows 2 decimals by default
top15["mi"] = top15.ym.map({m: i + 1 for i, m in enumerate(_ms)})   # month order for sorting
top15["ym"] = pd.to_datetime(top15.ym + "-01").dt.strftime("%b %y")   # "Sep 25" fits the column; "2025-09" was cut off


import numpy as np
p0 = R["england_share"] / 100; tau2 = R["funnel_tau"] ** 2
fp = practices[["practice_code", "practice_name", "icb_short", "items", "wr_pct", "z_od", "months_top", "pattern"]].copy()
grid_n = np.geomspace(max(300, fp["items"].min()), fp["items"].max() * 1.02, 120)
lim = []
for icb in sorted(fp.icb_short.unique()):
    for nm, z, side in [("99.8% limit", 3.09, "upper"), ("95% limit", 1.96, "upper"), ("England", 0, "mid"),
                        ("95% limit", -1.96, "lower"), ("99.8% limit", -3.09, "lower")]:
        for k_, nn in enumerate(grid_n):
            lim.append({"practice_code": f"{nm} {z:+.2f} {nn:.0f}", "practice_name": "", "icb_short": icb, "items": float(round(nn, 1)),
                        "wr_pct": round((p0 + z * np.sqrt(p0 * (1 - p0) / nn + tau2)) * 100, 3), "z_od": None, "months_top": None,
                        "pattern": nm, "line": f"{nm} {side}", "pt": f"{k_:03d}"})
funnel = pd.concat([fp.assign(items=fp["items"].astype(float)), pd.DataFrame(lim)], ignore_index=True)
funnel["z_od"] = funnel.z_od.astype(float); funnel["months_top"] = funnel.months_top.astype(float)
is_lim = funnel["line"].notna()
funnel["pts"] = funnel.wr_pct.where(~is_lim); funnel["lim"] = funnel.wr_pct.where(is_lim)
funnel["line"] = funnel["line"].fillna(""); funnel["pt"] = funnel["pt"].fillna("")
funnel["pattern"] = funnel["pattern"].replace({"Top fifth 9+ months": "Within limits", "Other": "Within limits",
                                               "Above funnel limit": "Above 99.8% (not shortlisted)"})
funnel["zord"] = funnel.pattern.map({"Review shortlist": 1, "Above 99.8% (not shortlisted)": 2, "Within limits": 3}).fillna(4)

# three-year persistence: practices open all three years, by number of years on the review shortlist
_t = pd.read_csv("outputs/tables/practices_two_years.csv").dropna(subset=["z_od_2324", "z_od_2425", "z_od_2526"])
_n = _t[["short_2324", "short_2425", "short_2526"]].astype(bool).sum(axis=1)
assert int((_n == 3).sum()) == Y2["shortlisted_all_three_years"] and int((_n >= 2).sum()) == Y2["shortlisted_two_plus_years"]
# chart counts only this year's shortlist (the 106 on the KPI card), by how many of the three years each was shortlisted
_cur = _t.short_2526.astype(bool); _y0 = _t.short_2324.astype(bool); _y1 = _t.short_2425.astype(bool)
years3 = pd.DataFrame({"years_label": ["2023-24 to 2025-26", "2024-25 and 2025-26", "2023-24 and 2025-26", "2025-26 only"],
                       "n": [int((_cur & _y0 & _y1).sum()), int((_cur & ~_y0 & _y1).sum()), int((_cur & _y0 & ~_y1).sum()),
                             int((_cur & ~_y0 & ~_y1).sum())], "ord3": [1, 2, 3, 4]})
assert years3.n.sum() == R["shortlist_n"]
N_OPEN3 = len(_t)

TABLES = {
    "funnel": (funnel, "Funnel (practices and limits)", {"practice_code": "Practice ID", "practice_name": "Practice (not named)", "icb_short": "ICB",
               "items": "Antibacterial items (12 months)", "wr_pct": "Watch+Reserve share (%)", "z_od": "Adjusted z",
               "months_top": "Months in top fifth", "pattern": "Group", "pts": "W+R share (%)", "lim": "Limit (%)",
               "line": "Line", "pt": "Point"}),
    "practices": (practices, "Practices (12 months)", {
        "practice_code": "Practice ID", "practice_name": "Practice (not named)", "icb_short": "ICB",
        "items": "Antibacterial items (12 months)", "items_per_1000_per_year": "Antibiotic items per 1,000 patients per year",
        "wr_pct": "W+R share 2025-26 (%)", "share_h1": "W+R % Sep 2025 to Feb 2026", "share_h2": "W+R % Mar to Aug 2026",
        "share_2425": "W+R share 2024-25 (%)",
        "pct_65plus": "Patients aged 65+ (%)", "imd": "IMD 2025 score", "age_group": "Age group (fifths, youngest to oldest)",
        "imd_group": "Practices grouped by area deprivation", "pattern": "Pattern", "gap": "Extra W+R items vs ICB",
        "months_top": "Months in top fifth", "z_od": "Adjusted funnel z", "avg_patients": "Patients",
        "extra_vs_england": "Extra W+R items vs England",
        "z_limit": "99.8% limit (z = 3.09)", "zero_line": "200 extra items"}),
    "top15": (top15, "Review shortlist by month", {"label": "Practice", "gap_label": "Adjusted z", "practice_code": "Practice ID",
                                                   "ym": "Month", "wr_pct": "W+R share (%)"}),
    "years3": (years3, "Years on the review shortlist", {"years_label": "Years shortlisted", "n": "Practices"}),
}

def dtype(s):
    if pd.api.types.is_bool_dtype(s): return "boolean"
    if pd.api.types.is_integer_dtype(s): return "integer"
    if pd.api.types.is_float_dtype(s): return "real"
    return "string"


HT = {"string": SqlType.text(), "integer": SqlType.big_int(), "real": SqlType.double(), "boolean": SqlType.bool()}
with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hp:
    for key, (df, _, _) in TABLES.items():
        with Connection(hp.endpoint, f"{OUT}/Data/Extracts/{key}.hyper", CreateMode.CREATE_AND_REPLACE) as con:
            con.catalog.create_schema("Extract")
            td = TableDefinition(TableName("Extract", "Extract"),
                                 [TableDefinition.Column(c, HT[dtype(df[c])]) for c in df.columns])
            con.catalog.create_table(td)
            with Inserter(con, td) as ins:
                for row in df.itertuples(index=False):
                    ins.add_row([None if (isinstance(v, float) and v != v) else
                                 (v.item() if hasattr(v, "item") else v) for v in row])
                ins.execute()
        df.to_csv(f"{OUT}/{key}.csv", index=False)

# ---------------------------------------------------------------- datasources
DS = {k: f"federated.{k}" for k in TABLES}
CALCS = {
    "practices": [],
    "month": [
        ("Calc_Rate", "Antibiotic items per 1,000 patients (month)", "real",
         "ROUND(SUM([classified]) / SUM([patients]) * 1000, 1)", "measure", "quantitative"),
        ("Calc_MWR", "Watch+Reserve share (%)", "real",
         "ROUND(SUM([watch_items] + [reserve_items]) / SUM([classified]) * 100, 1)", "measure", "quantitative"),
        ("Calc_Mon", "Month name", "string",
         "CASE RIGHT([ym],2) WHEN '01' THEN 'Jan' WHEN '02' THEN 'Feb' WHEN '03' THEN 'Mar' WHEN '04' THEN 'Apr' "
         "WHEN '05' THEN 'May' WHEN '06' THEN 'Jun' WHEN '07' THEN 'Jul' WHEN '08' THEN 'Aug' WHEN '09' THEN 'Sep' "
         "WHEN '10' THEN 'Oct' WHEN '11' THEN 'Nov' ELSE 'Dec' END + ' ' + MID([ym],3,2)", "dimension", "nominal"),
        ("Calc_Season", "Season", "string",
         "CASE RIGHT([ym],2) WHEN '12' THEN 'Winter' WHEN '01' THEN 'Winter' WHEN '02' THEN 'Winter' "
         "WHEN '03' THEN 'Spring' WHEN '04' THEN 'Spring' WHEN '05' THEN 'Spring' "
         "WHEN '06' THEN 'Summer' WHEN '07' THEN 'Summer' WHEN '08' THEN 'Summer' ELSE 'Autumn' END",
         "dimension", "nominal"),
    ],
    "practices_extra": [],
}
CALCS["practices"] = [("Calc_WR", "Watch+Reserve share (%)", "real",
                       "ROUND(SUM([wr]) / SUM([items]) * 100, 1)", "measure", "quantitative")]


def role(dt, col):
    if col in ("months", "months_top", "rank", "months_in_top_fifth", "ord_a", "ord_b"):
        return ("dimension", "ordinal") if col in ("months", "months_in_top_fifth") else ("measure", "quantitative")
    return ("dimension", "nominal") if dt in ("string", "boolean") else ("measure", "quantitative")


def datasource(key):
    df, cap, caps = TABLES[key]
    name = DS[key]
    o = [f"<datasource caption={q(cap)} inline='true' name={q(name)} version='18.1'>",
         "<connection class='federated'><named-connections>",
         f"<named-connection caption={q(cap)} name={q('textscan.' + key)}>",
         f"<connection class='textscan' directory={q(SRC)} filename={q(key + '.csv')} password='' server='' />",
         "</named-connection></named-connections>",
         f"<relation connection={q('textscan.' + key)} name={q(key + '.csv')} table={q('[' + key + '#csv]')} type='table'>",
         "<columns character-set='UTF-8' header='yes' locale='en_GB' separator=','>"]
    for i, c in enumerate(df.columns):
        o.append(f"<column datatype='{dtype(df[c])}' name={q(c)} ordinal='{i}' />")
    o.append("</columns></relation></connection><aliases enabled='yes' />")
    for c in df.columns:
        dt = dtype(df[c]); r, t = role(dt, c)
        capattr = f" caption={q(caps[c])}" if c in caps else ""
        o.append(f"<column{capattr} datatype='{dt}' name={q('[' + c + ']')} role='{r}' type='{t}' />")
    for cid, ccap, dt, f, r, t in CALCS.get(key, []):
        o.append(f"<column caption={q(ccap)} datatype='{dt}' name='[{cid}]' role='{r}' type='{t}'>"
                 f"<calculation class='tableau' formula={q(f)} /></column>")
    if key in DSPAL:
        _c = DSPAL[key][0].split(":")[1]
        o.append(f"<column-instance column='[{_c}]' derivation='None' name='[none:{_c}:nk]' pivot='key' type='nominal' />")
    o.append(f"<extract count='-1' enabled='true' units='records'><connection access_mode='readonly' "
             f"author-locale='en_GB' class='hyper' dbname='Data/Extracts/{key}.hyper' default-settings='hyper' "
             f"schema='Extract' sslmode='' tablename='Extract' update-time='16/11/2026 04:00:00' "
             f"username='tableau-internal-user'><relation name='Extract' table='[Extract].[Extract]' type='table' />"
             f"</connection></extract>")
    if key in DSPAL:
        fld, mapping = DSPAL[key]
        m = "".join(f"<map to='{c}'><bucket>&quot;{escape(v)}&quot;</bucket></map>" for v, c in mapping.items())
        o.append("<layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />")
        o.append(f"<style><style-rule element='mark'><encoding attr='color' field='[{fld}]' type='palette'>{m}</encoding></style-rule></style>")
    o.append("</datasource>")
    return "\n".join(o)


# ---------------------------------------------------------------- worksheet helpers
def colspec(key, c):
    """Return (column xml) for a base column or calc."""
    df, _, caps = TABLES[key]
    for cid, ccap, dt, f, r, t in CALCS.get(key, []):
        if cid == c:
            return (f"<column caption={q(ccap)} datatype='{dt}' name='[{cid}]' role='{r}' type='{t}'>"
                    f"<calculation class='tableau' formula={q(f)} /></column>")
    dt = dtype(df[c]); r, t = role(dt, c)
    capattr = f" caption={q(caps[c])}" if c in caps else ""
    return f"<column{capattr} datatype='{dt}' name={q('[' + c + ']')} role='{r}' type='{t}' />"


def inst(der, c, t):
    pre = {"None": "none", "Sum": "sum", "User": "usr", "Min": "min", "Avg": "avg", "CountD": "ctd"}[der]
    suf = {"nominal": "nk", "ordinal": "ok", "quantitative": "qk"}[t]
    return f"{pre}:{c}:{suf}"


# NOTE on "Æ&#10;": this is how Tableau itself stores a line break inside formatted text (Tableau Desktop writes
# <run>Æ&#10;</run> in every workbook it saves). Tableau does not display the "Æ"; it marks the newline as a hard break.
# Without it Tableau ignores the break and runs the title and subtitle together on one line.
def legend(items):
    """Colour key written as coloured dots and labels, e.g. ● Review shortlist (in red)."""
    out = ""
    for it in items:
        t, c = it[0], it[1]; sym = it[2] if len(it) > 2 else "●"
        out += f"<run fontcolor='{c}' fontsize='12'>{sym}</run><run bold='true' fontcolor='{c}' fontsize='9'> {escape(t)}   </run>"
    return out


def sheet(name, title, subtitle, key, fields, rows, cols, mark, enc="", pane_style="", table_style="",
          extra_view="", pane_extra="", hide=""):
    """fields: list of (col, derivation, type)"""
    ds = DS[key]
    seen, colxml, instxml = set(), [], []
    for c, der, t in fields:
        if c not in seen:
            colxml.append(colspec(key, c)); seen.add(c)
        instxml.append(f"<column-instance column={q('[' + c + ']')} derivation='{der}' "
                       f"name={q('[' + inst(der, c, t) + ']')} pivot='key' type='{t}' />")
    F = lambda s: s.replace("@", f"[{ds}].")
    sub = ("<run>Æ&#10;</run>" + legend(subtitle)) if isinstance(subtitle, list) else \
          (f"<run>Æ&#10;</run><run fontcolor='#5b6b6c' fontsize='10'>{escape(subtitle)}</run>" if subtitle else "")
    return f"""<worksheet name={q(name)}>
<layout-options><title><formatted-text><run bold='true' fontcolor='#1f2d2e' fontsize='12'>{escape(title)}</run>{sub}</formatted-text></title></layout-options>
<table><view><datasources><datasource caption={q(TABLES[key][1])} name='{ds}' /></datasources>
<datasource-dependencies datasource='{ds}'>{''.join(colxml)}{''.join(instxml)}</datasource-dependencies>
{F(extra_view)}<aggregation value='true' /></view>
<style>{F(table_style)}{F(hide)}</style>
<panes><pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view>
<mark class='{mark}' />{F(enc)}{F(pane_extra)}<style><style-rule element='mark'>{pane_style}</style-rule></style></pane></panes>
<rows>{F(rows)}</rows><cols>{F(cols)}</cols></table></worksheet>"""


def palette(field, mapping):
    m = "".join(f"<map to='{c}'><bucket>&quot;{escape(v)}&quot;</bucket></map>" for v, c in mapping.items())
    return f"<style-rule element='mark'><encoding attr='color' field='{field}' type='palette'>{m}</encoding></style-rule>"


def ramp(field, colors, diverging=False):
    ty = "ordered-diverging" if diverging else "ordered-sequential"
    cs = "".join(f"<color>{c}</color>" for c in colors)
    return (f"<style-rule element='mark'><encoding attr='color' field='{field}' type='custom-interpolated'>"
            f"<color-palette custom='true' name='' type='{ty}'>{cs}</color-palette></encoding></style-rule>")


def fmt(transp=255, size=None, color=None, labels=False):
    s = f"<format attr='mark-transparency' value='{transp}' />"
    if size is not None: s += f"<format attr='size' value='{size}' />"
    if color: s += f"<format attr='mark-color' value='{color}' />"
    if labels: s += "<format attr='mark-labels-show' value='true' /><format attr='mark-labels-cull' value='true' />"
    return s


RED, GREY, TEAL = "#c0392b", "#b7c2c3", "#0f7c7e"
sheets = {}

# Option 2 (agreed 17 Nov): background practices in a light grey so the cloud reads as a soft shade; flagged groups drawn on top
HI_RED, HI_ORG, MID, BG = "#d62d20", "#f28c1a", "#7c97a6", "#dfe5e6"
PAT = {"Review shortlist": HI_RED, "Above funnel limit": HI_ORG, "Top fifth 9+ months": MID, "Other": BG}

PATF = {"Within limits": BG, "Above 99.8% (not shortlisted)": HI_ORG, "Review shortlist": HI_RED,
        "99.8% limit": RED, "95% limit": "#e08e0b", "England": "#0f3d3e"}
LEG_F = [("Review shortlist", HI_RED), ("Above 99.8% limit only", HI_ORG), ("Within limits", "#9aa7aa")]
LEG_P = [("Shortlist", HI_RED), ("Above limit only", HI_ORG), ("High 9+ months", MID), ("Other", "#9aa7aa")]
# draw order: group listed first is drawn on top, so red/orange are never hidden under the grey
ZORD = "<sort class='computed' column='@[none:pattern:nk]' direction='ASC' using='@[min:zord:qk]' />"
PAT3 = {"2023-24 to 2025-26": RED, "2024-25 and 2025-26": "#e08e0b", "2023-24 and 2025-26": "#f2b45c", "2025-26 only": "#9aa7aa"}
DSPAL = {"funnel": ("none:pattern:nk", PATF), "practices": ("none:pattern:nk", PAT), "years3": ("none:years_label:nk", PAT3)}
TREND = ("<trendline enable-confidence-bands='false' enable-instant-analytics='true' enabled='true' "
         "exclude-color='true' exclude-intercept='false' fit='linear' />")
F_FILTER = ("<filter class='categorical' column='@[none:icb_short:nk]' filter-group='2'>"
            "<groupfilter function='level-members' level='[none:icb_short:nk]' user:ui-enumeration='all' user:ui-marker='enumerate' />"
            "</filter><slices><column>@[none:icb_short:nk]</column></slices>")
F_FILTER_Z = F_FILTER.replace("<slices>", ZORD + "<slices>")   # Tableau needs <sort> after <filter>, before <slices>
def funnel_sheet():
    """Dual axis: practices as dots (pane 1) and the funnel limits as smooth lines (pane 2); log x axis."""
    key, ds = "funnel", DS["funnel"]
    flds = [("items", "Sum", "quantitative"), ("pts", "Sum", "quantitative"), ("lim", "Min", "quantitative"),
            ("practice_code", "None", "nominal"), ("practice_name", "None", "nominal"), ("icb_short", "None", "nominal"),
            ("pattern", "None", "nominal"), ("line", "None", "nominal"), ("pt", "None", "nominal"), ("zord", "Min", "quantitative")]
    seen, colxml, instxml = set(), [], []
    for c, der, t in flds:
        if c not in seen: colxml.append(colspec(key, c)); seen.add(c)
        instxml.append(f"<column-instance column={q('[' + c + ']')} derivation='{der}' name={q('[' + inst(der, c, t) + ']')} pivot='key' type='{t}' />")
    F = lambda x: x.replace("@", f"[{ds}].")
    title = ("<run bold='true' fontcolor='#1f2d2e' fontsize='12'>A small group of practices sits well above what chance and normal variation allow</run>"
             "<run>Æ&#10;</run>" + legend(LEG_F))
    axis = ("<style-rule element='axis'>"
            "<encoding attr='space' class='0' field='@[sum:items:qk]' field-type='quantitative' max='150000' min='300' range-type='fixed' scale='log' scope='cols' type='space' />"
            "<encoding attr='space' class='0' field='@[min:lim:qk]' field-type='quantitative' fold='true' scope='rows' synchronized='true' type='space' />"
            "<format attr='display' class='0' field='@[min:lim:qk]' scope='rows' value='false' />"
            "</style-rule><style-rule element='table'><format attr='show-null-value-warning' value='false' /></style-rule>")
    return f"""<worksheet name='Funnel plot'>
<layout-options><title><formatted-text>{title}</formatted-text></title></layout-options>
<table><view><datasources><datasource caption={q(TABLES[key][1])} name='{ds}' /></datasources>
<datasource-dependencies datasource='{ds}'>{''.join(colxml)}{''.join(instxml)}</datasource-dependencies>
{F(F_FILTER_Z)}<aggregation value='true' /></view>
<style>{F(axis)}</style>
<panes>
<pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view><mark class='Automatic' /></pane>
<pane id='1' selection-relaxation-option='selection-relaxation-allow' y-axis-name='{F("@[sum:pts:qk]")}'><view><breakdown value='auto' /></view>
<mark class='Circle' /><encodings>{F("<color column='@[none:pattern:nk]' /><lod column='@[none:practice_code:nk]' /><lod column='@[none:practice_name:nk]' /><lod column='@[none:icb_short:nk]' />")}</encodings>
<style><style-rule element='mark'>{fmt(200, 0.3)}</style-rule></style></pane>
<pane id='2' selection-relaxation-option='selection-relaxation-allow' y-axis-name='{F("@[min:lim:qk]")}'><view><breakdown value='auto' /></view>
<mark class='Line' /><encodings>{F("<color column='@[none:pattern:nk]' /><lod column='@[none:line:nk]' /><lod column='@[none:icb_short:nk]' /><path column='@[none:pt:nk]' /><text column='@[none:pattern:nk]' />")}</encodings>
<style><style-rule element='mark'><format attr='size' value='0.3' /><format attr='mark-labels-show' value='true' />
<format attr='mark-labels-cull' value='false' /><format attr='mark-labels-line-first' value='false' /><format attr='mark-labels-line-last' value='true' /></style-rule></style></pane>
</panes>
<rows>({F("@[sum:pts:qk]")} + {F("@[min:lim:qk]")})</rows><cols>{F("@[sum:items:qk]")}</cols></table></worksheet>"""


sheets["Funnel plot"] = funnel_sheet()

sheets["Year to year"] = sheet(
    "Year to year", "The same practices stand out a year later",
    LEG_P,
    "practices", [("share_2425", "Sum", "quantitative"), ("wr_pct", "Sum", "quantitative"),
                  ("practice_code", "None", "nominal"), ("practice_name", "None", "nominal"), ("pattern", "None", "nominal"),
                  ("icb_short", "None", "nominal"), ("zord", "Min", "quantitative")],
    "@[sum:wr_pct:qk]", "@[sum:share_2425:qk]", "Circle",
    enc="<encodings><color column='@[none:pattern:nk]' /><lod column='@[none:practice_code:nk]' /><lod column='@[none:practice_name:nk]' /></encodings>",
    pane_style=fmt(170, 0.25), table_style=palette("@[none:pattern:nk]", PAT)
    + "<style-rule element='table'><format attr='show-null-value-warning' value='false' /></style-rule>",   # 5 practices did not exist in 2024-25
    pane_extra=TREND, extra_view=F_FILTER_Z)

sheets["Review shortlist"] = sheet(
    "Review shortlist", "The most unusual practices are high month after month",
    "",
    "top15", [("label", "None", "nominal"), ("gap_label", "None", "nominal"), ("ym", "None", "nominal"),
              ("wr_pct", "Sum", "quantitative"), ("rank", "Min", "quantitative"), ("mi", "Min", "quantitative"),
              ("wr_lbl", "None", "nominal"), ("practice_code", "None", "nominal")],
    "(@[none:label:nk] / @[none:gap_label:nk])", "@[none:ym:nk]", "Square",
    enc="<encodings><color column='@[sum:wr_pct:qk]' /><text column='@[none:wr_lbl:nk]' /><lod column='@[none:practice_code:nk]' /></encodings>",
    pane_style=fmt(255, labels=True), table_style=ramp("@[sum:wr_pct:qk]", ["#fdecea", "#e57368", "#8e1b12"]),
    extra_view="<sort class='computed' column='@[none:label:nk]' direction='ASC' using='@[min:rank:qk]' />"
               "<sort class='computed' column='@[none:ym:nk]' direction='ASC' using='@[min:mi:qk]' />")

sheets["Three years"] = sheet(
    "Three years", "The same practices, year after year",
    "",
    "years3", [("years_label", "None", "nominal"), ("n", "Sum", "quantitative"), ("ord3", "Min", "quantitative")],
    "@[none:years_label:nk]", "@[sum:n:qk]", "Bar",
    enc="<encodings><color column='@[none:years_label:nk]' /><text column='@[sum:n:qk]' /></encodings>",
    pane_style=fmt(255, labels=True),
    table_style=palette("@[none:years_label:nk]", PAT3),
    extra_view="<sort class='computed' column='@[none:years_label:nk]' direction='ASC' using='@[min:ord3:qk]' />",
    hide="<style-rule element='axis'><format attr='display' class='0' field='@[sum:n:qk]' scope='cols' value='false' /></style-rule>"
         "<style-rule element='worksheet'><format attr='display-field-labels' scope='rows' value='false' /></style-rule>")

sheets["Age and prescribing"] = sheet(
    "Age and prescribing", "Practices with older patients prescribe more antibiotics",
    LEG_P,
    "practices", [("pct_65plus", "Sum", "quantitative"), ("items_per_1000_per_year", "Sum", "quantitative"),
                  ("practice_code", "None", "nominal"), ("pattern", "None", "nominal"),
                  ("icb_short", "None", "nominal"), ("zord", "Min", "quantitative")],
    "@[sum:items_per_1000_per_year:qk]", "@[sum:pct_65plus:qk]", "Circle",
    enc="<encodings><color column='@[none:pattern:nk]' /><lod column='@[none:practice_code:nk]' /></encodings>",
    pane_style=fmt(210, 0.25), table_style=palette("@[none:pattern:nk]", PAT), pane_extra=TREND, extra_view=F_FILTER_Z)

sheets["Deprivation groups"] = sheet(
    "Deprivation groups", "Deprivation barely changes the share",
    "",
    "practices", [("imd_group", "None", "nominal"), ("wr_pct", "Sum", "quantitative"), ("practice_code", "None", "nominal"),
                  ("icb_short", "None", "nominal")],
    "@[sum:wr_pct:qk]", "@[none:imd_group:nk]", "Circle",
    enc="<encodings><lod column='@[none:practice_code:nk]' /></encodings>", pane_style=fmt(60, 0.2, TEAL),
    pane_extra="<reference-line axis-column='@[sum:wr_pct:qk]' boxplot-mark-exclusion='false' boxplot-whisker-type='standard' "
               "enable-instant-analytics='true' formula='average' id='refline0' label-type='none' probability='95' scope='per-cell' "
               "symmetric='false' value-column='@[sum:wr_pct:qk]' z-order='1' />", extra_view=F_FILTER)

sheets["Priority"] = sheet(
    "Priority", "Review first: practices that are both unusual and high-volume (top right)",
    LEG_P + [("200 extra items a year", "#7a7a7a", "—")],
    "practices", [("z_od", "Sum", "quantitative"), ("extra_vs_england", "Sum", "quantitative"), ("practice_code", "None", "nominal"),
                  ("practice_name", "None", "nominal"), ("icb_short", "None", "nominal"), ("pattern", "None", "nominal"),
                  ("months_top", "Sum", "quantitative"), ("z_limit", "Avg", "quantitative"), ("zero_line", "Avg", "quantitative"),
                  ("zord", "Min", "quantitative")],
    "@[sum:extra_vs_england:qk]", "@[sum:z_od:qk]", "Circle",
    enc="<encodings><color column='@[none:pattern:nk]' /><lod column='@[none:practice_code:nk]' /><lod column='@[none:practice_name:nk]' />"
        "<lod column='@[none:icb_short:nk]' /><lod column='@[sum:months_top:qk]' /><lod column='@[avg:z_limit:qk]' /><lod column='@[avg:zero_line:qk]' /></encodings>",
    pane_style=fmt(170, 0.3), table_style=palette("@[none:pattern:nk]", PAT), extra_view=F_FILTER_Z,
    pane_extra="<reference-line axis-column='@[sum:z_od:qk]' enable-instant-analytics='false' formula='average' id='refline1' "
               "label-type='none' probability='95' scope='per-table' symmetric='false' value-column='@[avg:z_limit:qk]' z-order='1' />"
               "<reference-line axis-column='@[sum:extra_vs_england:qk]' enable-instant-analytics='false' formula='average' id='refline2' "
               "label-type='none' probability='95' scope='per-table' symmetric='false' value-column='@[avg:zero_line:qk]' z-order='1' />")

# ---------------------------------------------------------------- dashboard
W, H = 1400, 1320
def px(y): return int(y / H * 100000)
def pw(x): return int(x / W * 100000)
CARD = ("<zone-style><format attr='border-color' value='#d9e0e1' /><format attr='border-style' value='solid' />"
        "<format attr='border-width' value='1' /><format attr='background-color' value='#ffffff' /><format attr='margin' value='4' /></zone-style>")
kpis = [(f"{R['n_practices']:,}", "GP practices in England, Sep 2025 – Aug 2026"),
        (f"{R['england_share']:.1f}%", "of antibiotic items were Watch or Reserve"),
        (f"{Y2['shortlisted_all_three_years']}", "practices on the review shortlist in all three years (Sep 2023 – Aug 2026)"),
        (f"{R['shortlist_n']}", "practices on the review shortlist")]
zones = []; zid = [10]
def nid():
    zid[0] += 1; return zid[0]
title = ("<formatted-text><run bold='true' fontcolor='#0f3d3e' fontsize='20'>Antibiotic stewardship in English GP practices</run>"
         "<run fontcolor='#5b6b6c' fontsize='11'>   ·   Ashish Agarwal and Aashish Gill</run></formatted-text>")
zones.append(f"<zone h='{px(46)}' id='{nid()}' type-v2='text' w='{pw(1360)}' x='{pw(20)}' y='{px(10)}'>{title}</zone>")
kw = (1360 - 3 * 14) / 4
for i, (big, small) in enumerate(kpis):
    t = (f"<formatted-text><run bold='true' fontcolor='{RED if i == 3 else '#0f3d3e'}' fontsize='24'>{escape(big)}</run>"
         f"<run>Æ&#10;</run><run fontcolor='#3d4b4c' fontsize='10'>{escape(small)}</run></formatted-text>")
    zones.append(f"<zone h='{px(90)}' id='{nid()}' type-v2='text' w='{pw(kw)}' x='{pw(20 + i * (kw + 14))}' y='{px(60)}'>{t}{CARD}</zone>")
zones.append(f"<zone h='{px(40)}' id='{nid()}' mode='dropdown' name='Funnel plot' param='[federated.funnel].[none:icb_short:nk]' type-v2='filter' values='relevant' w='{pw(300)}' x='{pw(20)}' y='{px(160)}' />")
grid = [("Funnel plot", 20, 208, 672, 440), ("Review shortlist", 708, 208, 672, 440),
        ("Year to year", 20, 662, 444, 320), ("Age and prescribing", 478, 662, 444, 320), ("Deprivation groups", 936, 662, 444, 320),
        ("Priority", 20, 996, 900, 262), ("Three years", 934, 996, 446, 262)]
for n_, x, y, w, h in grid:
    zones.append(f"<zone h='{px(h)}' id='{nid()}' name={q(n_)} w='{pw(w)}' x='{pw(x)}' y='{px(y)}'>{CARD}</zone>")
foot = ("<formatted-text><run fontcolor='#6b7a7b' fontsize='9'>Data: NHSBSA English Prescribing Dataset (Sep 2023 – Aug 2026), NHS England practice lists, "
        "QOF 2025-26, IMD 2025, UKHSA UK-AWaRe 2025. Associations, not causes: the data has no diagnoses, and some Watch prescribing is clinically right. "
        "Practices are not named, to keep the focus on patterns: a flag is a prompt for a conversation, not a judgement. Methods, limitations and code: full report and GitHub repository.</run></formatted-text>")
zones.append(f"<zone h='{px(44)}' id='{nid()}' type-v2='text' w='{pw(1360)}' x='{pw(20)}' y='{px(1268)}'>{foot}</zone>")
# equation boxes drawn on top of the two scatter charts (like the report figures)
_yy = practices.dropna(subset=["share_2425"])
rel = np.polyfit(_yy.share_2425, _yy.wr_pct, 1); rel_r2 = np.corrcoef(_yy.share_2425, _yy.wr_pct)[0, 1] ** 2
for (bx, by), l1, l2 in [((85, 730), f"y = {rel[0]:.2f}x + {rel[1]:.2f}", f"R² = {rel_r2:.2f}   (r = {Y2['r_share_year_to_year']:.2f})"),
                         ((548, 730), f"y = {R['age_slope']:.2f}x + {R['age_intercept']:.1f}", f"R² = {R['age_r2']:.2f}")]:
    t = (f"<formatted-text><run bold='true' fontcolor='#c0392b' fontsize='10'>{escape(l1)}</run><run>Æ&#10;</run>"
         f"<run bold='true' fontcolor='#c0392b' fontsize='10'>{escape(l2)}</run><run>Æ&#10;</run>"
         f"<run fontcolor='#5b6b6c' fontsize='8'>All practices (not filtered by ICB)</run></formatted-text>")
    zones.append(f"<zone h='{px(64)}' id='{nid()}' type-v2='text' w='{pw(210)}' x='{pw(bx)}' y='{px(by)}'>{t}"
                 "<zone-style><format attr='border-color' value='#c0392b' /><format attr='border-style' value='solid' />"
                 "<format attr='border-width' value='1' /><format attr='background-color' value='#ffffff' />"
                 "<format attr='margin' value='4' /></zone-style></zone>")
dashboard = (f"<dashboards><dashboard name='Dashboard'><style />"
             f"<size maxheight='{H}' maxwidth='{W}' minheight='{H}' minwidth='{W}' sizing-mode='fixed' />"
             f"<zones><zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>{''.join(zones)}"
             "<zone-style><format attr='background-color' value='#eef2f3' /></zone-style></zone></zones>"
             f"</dashboard></dashboards>")

cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' />"
         "</strip></edge><edge name='top'><strip size='2147483647'><card type='columns' /></strip>"
         "<strip size='2147483647'><card type='rows' /></strip><strip size='31'><card type='title' /></strip></edge>"
         "<edge name='right'><strip size='160'><card pane-specification-id='0' param='[x]' type='color' /></strip></edge></cards>")
cards = cards.replace("<edge name='right'><strip size='160'><card pane-specification-id='0' param='[x]' type='color' /></strip></edge>", "")
windows = "<windows source-height='30'>"
for n_ in sheets:
    windows += f"<window class='worksheet' name={q(n_)}>{cards}<viewpoint><zoom type='entire-view' /></viewpoint></window>"
windows += ("<window class='dashboard' maximized='true' name='Dashboard'><viewpoints>" +
            "".join(f"<viewpoint name={q(n_)}><zoom type='entire-view' /></viewpoint>" for n_ in sheets) +
            "</viewpoints><active id='-1' /></window></windows>")

xml = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook locale='en_GB' original-version='18.1' source-build='2024.1.0 (20241.24.0312.0830)' source-platform='mac' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
<preferences><preference name='ui.encoding.shelf.height' value='24' /><preference name='ui.shelf.height' value='26' /></preferences>
<datasources>{''.join(datasource(k) for k in TABLES)}</datasources>
<actions><action caption='Highlight the same practices in every chart' name='[Action1_highlight]'>
<activation auto-clear='true' type='on-select' /><source dashboard='Dashboard' type='sheet' />
<command command='tsc:brush'><param name='field-captions' value='Practice ID' /><param name='target' value='Dashboard' /></command>
</action></actions>
<worksheets>{''.join(sheets.values())}</worksheets>
{dashboard}
{windows}
</workbook>"""
open(f"{OUT}/{NAME}.twb", "w").write(xml)
import xml.dom.minidom; xml.dom.minidom.parse(f"{OUT}/{NAME}.twb")
os.makedirs("tableau", exist_ok=True); dst = f"tableau/{NAME}.twbx"
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
    z.write(f"{OUT}/{NAME}.twb", f"{NAME}.twb")
    for k in TABLES:
        z.write(f"{OUT}/Data/Extracts/{k}.hyper", f"Data/Extracts/{k}.hyper")
        z.write(f"{OUT}/{k}.csv", f"Data/Datasources/{k}.csv")
print("ok", dst, os.path.getsize(dst))
for k, (df, _, _) in TABLES.items(): df.to_csv(f"tableau/{k}.csv", index=False)
