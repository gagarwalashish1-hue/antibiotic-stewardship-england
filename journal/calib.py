import pandas as pd, numpy as np
d=pd.read_csv("outputs/journal/prac.csv",dtype={"pc":str})
ire=pd.read_csv("outputs/journal/icb_re.csv").set_index("icb").u
n=d.cls.values.astype(int); icb=d.icb.map(ire).fillna(0).values
def tau_z(x,n,scale=1.0):
    p=x/n; p0=x.sum()/n.sum(); se=np.sqrt(p0*(1-p0)/n); z=(p-p0)/se
    zw=np.clip(z,np.quantile(z,.1),np.quantile(z,.9)); phi=(zw**2).mean(); w=1/se**2; k=len(z)
    t2=max(0,(k*phi-(k-1))/(w.sum()-(w**2).sum()/w.sum()))*scale**2
    return (p-p0)/np.sqrt(se**2+t2), np.sqrt(t2)
# 1) calibration: simulate 2025/26 from the fitted model (normal practice effects, no special outliers)
b0=-1.495592155-0.019374147; sp=0.033645511+0.004874473; rng=np.random.default_rng(7); cnt=[]; taus=[]
for _ in range(500):
    l=b0+icb+rng.normal(0,np.sqrt(sp),len(n)); x=rng.binomial(n,1/(1+np.exp(-l)))
    z,t=tau_z(x,n); cnt.append((z>3.09).sum()); taus.append(t)
cnt=np.array(cnt); print(f"calibration: mean above 99.8% {cnt.mean():.1f} (2.5-97.5%: {np.percentile(cnt,2.5):.0f}-{np.percentile(cnt,97.5):.0f}); nominal {0.001*len(n):.1f}; mean tau {100*np.mean(taus):.2f} pp")
# 2) tau sensitivity on observed data
sh=d.shortlisted.astype(str)=="True"
for s in [0.8,0.9,1.0,1.1,1.25,1.5]:
    z,t=tau_z(d.wr.values,d.cls.values,s); print(f"tau x{s}: tau {100*t:.2f} pp, above 99.8% {int((z>3.09).sum())}, shortlisted still above {int((z[sh.values]>3.09).sum())}")
