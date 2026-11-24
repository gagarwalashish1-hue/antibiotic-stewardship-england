# Builds the core priority list (shortlisted AND beyond 99.8% in multilevel model, OR shortlisted all three years)
import pandas as pd, numpy as np
R="outputs/tables/"; J="outputs/journal/"
u=pd.read_csv(J+"stable_re.csv",dtype={"pc":str}); sd=0.18342713  # practice SD from stab.R
d=pd.read_csv(J+"prac.csv",dtype={"pc":str}); m=pd.read_csv(J+"ml_scores.csv",dtype={"pc":str})
a3=set(pd.read_csv(R+"shortlisted_all_three_years.csv",dtype=str).practice_code)
x=d[["pc","shortlisted","wr","cls","pat","share"]].merge(m[["pc","z_ml"]],on="pc").merge(u,on="pc")
x["zs"]=x.u/sd; sh=x.shortlisted.astype(str)=="True"; x["a3"]=x.pc.isin(a3)
core=x.a3|(sh&(x.z_ml>3.09)); print("core list:",core.sum())
p0=x.wr.sum()/x.cls.sum(); x["exc"]=(x.wr-p0*x.cls).clip(lower=0)
print("excess total",round(x.exc.sum())," shortlist",round(x.exc[sh].sum())," core",round(x.exc[core].sum()))
x.to_csv(J+"tiers.csv",index=False)
