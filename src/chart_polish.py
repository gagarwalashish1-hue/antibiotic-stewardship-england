"""Last step after recalculation: make the grey 'within limits' funnel dots see-through.
openpyxl cannot write colour transparency, so this edits the chart XML inside the .xlsx directly.
Run:  python src/chart_polish.py"""
import re, shutil, zipfile, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT
os.chdir(ROOT)
SRC = "Project1_Antibiotic_Stewardship_12m.xlsx"; TMP = SRC + ".tmp"
pat = re.compile(r'<a:srgbClr val="8FA6A8"\s*/>', re.I)
n = 0
with zipfile.ZipFile(SRC) as zin, zipfile.ZipFile(TMP, "w", zipfile.ZIP_DEFLATED) as zout:
    for item in zin.infolist():
        data = zin.read(item.filename)
        if item.filename.startswith("xl/charts/chart") and item.filename.endswith(".xml"):
            txt, k = pat.subn('<a:srgbClr val="8FA6A8"><a:alpha val="30000"/></a:srgbClr>', data.decode("utf-8"))
            n += k; data = txt.encode("utf-8")
        zout.writestr(item, data)
shutil.move(TMP, SRC)
print("transparent marker fills:", n)
