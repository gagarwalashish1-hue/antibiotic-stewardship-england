import pandas as pd, numpy as np
from statsmodels.stats.proportion import proportion_confint as ci
P=""
keep=set(pd.read_csv("outputs/journal/prac.csv",dtype={"pc":str}).pc)
def agg(f):
    m=pd.read_csv(f,dtype={"pc":str}); m=m[m.pc.isin(keep)]
    g=m.groupby("pc")[["access_items","watch_items","reserve_items","other_items","lyme_items"]].sum()
    g["cls"]=g.access_items+g.watch_items+g.reserve_items+g.other_items; g["wr"]=g.watch_items+g.reserve_items; return g
a=agg(P+"data/raw/y2425/abx_12m_practice_month.csv"); b=agg(P+"data/raw/abx_12m_practice_month.csv")
ix=a.index.intersection(b.index); a=a.loc[ix]; b=b.loc[ix]; a=a[a.cls>0]; b=b.loc[a.index]
def odz(x,n):
    p=x/n; p0=x.sum()/n.sum(); se=np.sqrt(p0*(1-p0)/n); z=(p-p0)/se
    zw=z.clip(z.quantile(.1),z.quantile(.9)); phi=(zw**2).mean(); w=1/se**2; k=len(z)
    t2=max(0,(k*phi-(k-1))/(w.sum()-(w**2).sum()/w.sum())); return (p-p0)/np.sqrt(se**2+t2)
for lab,f in [("all items",lambda g:(g.wr,g.cls)),("excl lymecycline",lambda g:(g.wr-g.lyme_items,g.cls-g.lyme_items))]:
    za=odz(*f(a)); zb=odz(*f(b)); fl=za>3.09; s=(zb[fl]>3.09).sum(); lo,hi=ci(s,fl.sum(),method="wilson")
    print(f"{lab}: n={len(za)} flagged 2024/25 {fl.sum()} -> 2025/26 {s} ({s/fl.sum():.0%}, {lo:.0%}-{hi:.0%}); others {(zb[~fl]>3.09).mean():.2%}; r={np.corrcoef(f(a)[0]/f(a)[1], f(b)[0]/f(b)[1])[0,1]:.2f}")
