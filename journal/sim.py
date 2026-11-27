import pandas as pd, numpy as np
P="outputs/tables/"
t=pd.read_csv(P+"practices_two_years.csv",dtype={"pc":str})
d=pd.read_csv("outputs/journal/prac.csv",dtype={"pc":str})
t=t.merge(d[["pc","icb","wr","cls"]],on="pc").dropna(subset=["wr_2425","cls_2425"])
t=t[t.cls_2425>0]
ire=pd.read_csv("outputs/journal/icb_re.csv").set_index("icb").u
def odz(x,n):
    p=x/n; p0=x.sum()/n.sum(); se=np.sqrt(p0*(1-p0)/n); z=(p-p0)/se
    zw=np.clip(z,np.quantile(z,.1),np.quantile(z,.9)); phi=(zw**2).mean(); w=1/se**2; k=len(z)
    t2=max(0,(k*phi-(k-1))/(w.sum()-(w**2).sum()/w.sum())); return (p-p0)/np.sqrt(se**2+t2)
def pers(x1,n1,x2,n2,thr=3.09):
    z1=odz(x1,n1); z2=odz(x2,n2); f=z1>thr; return f.sum(), (z2[f]>thr).mean(), (z2[~f]>thr).mean()
n1=t.cls_2425.values; n2=t.cls.values
obs=pers(t.wr_2425.values,n1,t.wr.values,n2); print("observed: flagged %d, persist %.1f%%, others %.2f%%"%(obs[0],100*obs[1],100*obs[2]))
b0=-1.495592155; y1=-0.001366154; y2=-0.019374147; spc=0.033645511; spy=0.004874473
icb=t.icb.map(ire).fillna(0).values; rng=np.random.default_rng(1)
def run(sp,sy,R=300):
    out=[]
    for _ in range(R):
        u=rng.normal(0,np.sqrt(sp),len(t))
        l1=b0+y1+icb+u+rng.normal(0,np.sqrt(sy),len(t)); l2=b0+y2+icb+u+rng.normal(0,np.sqrt(sy),len(t))
        x1=rng.binomial(n1.astype(int),1/(1+np.exp(-l1))); x2=rng.binomial(n2.astype(int),1/(1+np.exp(-l2)))
        out.append(pers(x1,n1,x2,n2))
    o=np.array(out); return o.mean(0), np.percentile(o[:,1],[2.5,97.5])
for lab,sp,sy in [("fitted model (87% stable)",spc,spy),("no stable practice effect",0,spc+spy)]:
    m,ci=run(sp,sy); print(f"{lab}: flagged {m[0]:.0f}, persist {100*m[1]:.1f}% (sim 95% range {100*ci[0]:.0f}-{100*ci[1]:.0f}%), others {100*m[2]:.2f}%")
