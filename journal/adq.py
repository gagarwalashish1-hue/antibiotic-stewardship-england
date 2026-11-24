import pandas as pd, numpy as np, json
R=""
d=pd.read_csv("outputs/journal/prac.csv",dtype={"pc":str}).set_index("pc")
res=json.load(open(R+"outputs/tables/results.json"))
print({k:v for k,v in res.items() if "adq" in k.lower()})
# recompute ADQ share check against stored adq_share
p=d.adq_share/100; n=d.cls
p0=None
# England ADQ share from stored results
p0=res["england_adq_share"]/100
def odz(pobs,pexp,n):
    se=np.sqrt(pexp*(1-pexp)/n); z=(pobs-pexp)/se
    zw=z.clip(z.quantile(.1),z.quantile(.9)); phi=(zw**2).mean(); w=1/se**2; k=len(z)
    t2=max(0,(k*phi-(k-1))/(w.sum()-(w**2).sum()/w.sum())); return (pobs-pexp)/np.sqrt(se**2+t2), np.sqrt(t2)
z,tau=odz(p,p0,n); sh=d.shortlisted.astype(str)=="True"
print("ADQ England W+R %",p0*100,"tau pp",tau*100)
print("ADQ funnel >3.09 all",(z>3.09).sum()," shortlisted",(z[sh]>3.09).sum(),"/",sh.sum(), " >1.96", (z[sh]>1.96).sum())
print("ADQ share median shortlisted vs others", d.adq_share[sh].median(), d.adq_share[~sh].median())
print("r item share vs adq share", np.corrcoef(d.share,d.adq_share)[0,1])
a3=set(pd.read_csv(R+"outputs/tables/shortlisted_all_three_years.csv",dtype=str).practice_code)
x=z[z.index.isin(a3)]; print("all3 ADQ >3.09",(x>3.09).sum(),"/",len(x))
