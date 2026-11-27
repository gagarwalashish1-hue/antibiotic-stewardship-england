import pandas as pd, numpy as np
P=""
prac=pd.read_csv("outputs/journal/prac.csv",dtype={"pc":str})
keep=set(prac.pc)
m=pd.read_csv(P+"data/raw/abx_12m_practice_month.csv",dtype={"pc":str}); m=m[m.pc.isin(keep)]
w=pd.read_csv(P+"data/abx_12m_adq_watchdrug.csv",dtype={"pc":str,"ym":str}); w["ym"]=w.ym.str[:4]+"-"+w.ym.str[4:]
m=m.merge(w[["ym","pc","w_0501050A0"]],on=["ym","pc"],how="left").fillna({"w_0501050A0":0})
m["cls"]=m.access_items+m.watch_items+m.reserve_items+m.other_items
m["wr"]=m.watch_items+m.reserve_items
m["az"]=m.w_0501050A0; m["ly"]=m.lyme_items
def odz(x,n,p0=None):
    p=x/n; p0=x.sum()/n.sum() if p0 is None else p0
    se=np.sqrt(p0*(1-p0)/n); z=(p-p0)/se
    zw=z.clip(z.quantile(.1),z.quantile(.9)); phi=(zw**2).mean(); wt=1/se**2; k=len(z)
    t2=max(0,(k*phi-(k-1))/(wt.sum()-(wt**2).sum()/wt.sum())); return (p-p0)/np.sqrt(se**2+t2)
h1=m.ym<"2026-03"
out={}
for name,(num,den) in {"main":(m.wr,m.cls),"excl_lyme":(m.wr-m.ly,m.cls-m.ly),"excl_lyme_azith":(m.wr-m.ly-m.az,m.cls-m.ly-m.az)}.items():
    d=pd.DataFrame({"pc":m.pc,"h1":h1,"x":num,"n":den})
    a=d[d.h1].groupby("pc")[["x","n"]].sum(); b=d[~d.h1].groupby("pc")[["x","n"]].sum()
    za=odz(a.x,a.n); zb=odz(b.x,b.n).reindex(za.index)
    f=za>3.09; s=(zb[f]>3.09).sum()
    from statsmodels.stats.proportion import proportion_confint as ci
    lo,hi=ci(s,f.sum(),method="wilson")
    r=np.corrcoef(a.x/a.n,(b.x/b.n).reindex(a.index))[0,1]
    print(f"{name}: England share {100*num.sum()/den.sum():.1f}% | H1 flagged {f.sum()} -> H2 still {s} ({s/f.sum():.0%}, {lo:.0%}-{hi:.0%}); unflagged {(zb[~f]>3.09).mean():.2%}; split-half r {r:.2f}")
print("azithro share of watch items:", m.az.sum()/m.watch_items.sum(), " lyme:", m.ly.sum()/m.watch_items.sum())
