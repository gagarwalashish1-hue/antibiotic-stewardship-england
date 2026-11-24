import pandas as pd, numpy as np, matplotlib
matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams.update({"font.family":"serif","font.serif":["Times New Roman","Liberation Serif","Nimbus Roman","DejaVu Serif"],
 "font.size":8,"axes.linewidth":0.5,"xtick.major.width":0.5,"ytick.major.width":0.5,"lines.linewidth":0.8,
 "axes.spines.top":False,"axes.spines.right":False,"savefig.dpi":600})
R="outputs/tables/"
x=pd.read_csv("outputs/journal/tiers.csv",dtype={"pc":str}); sh=x.shortlisted.astype(str)=="True"
core=x.a3|(sh&(x.z_ml>3.09))
p0=x.wr.sum()/x.cls.sum(); tau=0.022479642634130895; mm=1/25.4
# Figure 1
fig,ax=plt.subplots(figsize=(180*mm,95*mm))
o=~sh; ax.scatter(x.cls[o],x.share[o],s=2,c="#BBBBBB",lw=0,label="Other practices",rasterized=True)
ax.scatter(x.cls[sh&~core],x.share[sh&~core],s=7,c="#E69F00",lw=0,label="Shortlisted (n = 54)")
ax.scatter(x.cls[core],x.share[core],s=9,c="#B2182B",lw=0,label="Core list: both methods or all three years (n = 52)")
n=np.logspace(np.log10(x.cls.min()*0.9),np.log10(x.cls.max()*1.1),300)
for z,ls in [(1.96,"--"),(3.09,"-")]:
    se=np.sqrt(p0*(1-p0)/n+tau**2)
    ax.plot(n,100*(p0+z*se),"k",ls=ls); ax.plot(n,100*(p0-z*se),"k",ls=ls)
ax.axhline(100*p0,color="k",lw=0.5,ls=":")
ax.set_xscale("log"); import matplotlib.ticker as tk; ax.xaxis.set_major_formatter(tk.FuncFormatter(lambda v,p: f"{v:,.0f}")); ax.set_xticks([500,1000,2000,5000,10000,20000,50000]); ax.set_xlabel("Antibiotic items prescribed, September 2025 to August 2026 (log scale)"); ax.set_ylabel("Watch+Reserve share of items (%)")
ax.plot([],[],"k--",label="95% limit"); ax.plot([],[],"k-",label="99.8% limit"); ax.plot([],[],"k:",label=f"England ({100*p0:.1f}%)")
ax.legend(frameon=False,loc="upper right",fontsize=7,markerscale=1.5)
fig.tight_layout(); fig.savefig("outputs/journal/Figure 1.png"); fig.savefig("outputs/journal/Figure 1.tif")
# Figure 2
t=pd.read_csv(R+"practices_two_years.csv",dtype={"pc":str}).dropna(subset=["share_2425","share_2526"])
s1=t.short_2425.astype(str)=="True"; s2=t.short_2526.astype(str)=="True"
fig,ax=plt.subplots(figsize=(88*mm,88*mm))
f=lambda v: v*100 if v.max()<=1 else v
a,b=f(t.share_2425),f(t.share_2526)
ax.scatter(a[~(s1|s2)],b[~(s1|s2)],s=2,c="#BBBBBB",lw=0,rasterized=True,label="Neither year")
ax.scatter(a[s1^s2],b[s1^s2],s=6,c="#E69F00",lw=0,label="Shortlisted in one year")
ax.scatter(a[s1&s2],b[s1&s2],s=8,c="#B2182B",lw=0,label="Shortlisted in both years")
lim=[0,max(a.max(),b.max())+2]; ax.plot(lim,lim,"k:",lw=0.5); ax.set_xlim(lim); ax.set_ylim(lim)
r=np.corrcoef(a,b)[0,1]; ax.text(0.04,0.96,f"r = {r:.2f}",transform=ax.transAxes,va="top")
ax.set_xlabel("Watch+Reserve share, 2024/25 (%)"); ax.set_ylabel("Watch+Reserve share, 2025/26 (%)")
ax.legend(frameon=False,loc="lower right",fontsize=6.5); fig.tight_layout(); fig.savefig("outputs/journal/Figure 2.png"); fig.savefig("outputs/journal/Figure 2.tif")
print("fig2 r",r, len(t))
# Figure 3
top=x.share>=x.share.quantile(0.8); above=x.share>100*p0
g=[("Core list (52 practices)",x.exc[core].sum()),("Rest of shortlist (54)",x.exc[sh&~core].sum()),
   (f"Other practices in highest fifth ({(top&~sh).sum():,})",x.exc[top&~sh].sum()),(f"Other practices above England ({(above&~top).sum():,})",x.exc[above&~top].sum())]
tot=x.exc.sum()
fig,ax=plt.subplots(figsize=(180*mm,55*mm))
lab=[k for k,_ in g][::-1]; val=[v/1000 for _,v in g][::-1]
cols=["#B2182B","#E69F00","#7F7F7F","#BBBBBB"][::-1]
ax.barh(lab,val,color=cols,height=0.6)
for i,v in enumerate(val): ax.text(v+2,i,f"{v:.0f}k ({v*1000/tot*100:.0f}%)",va="center")
ax.set_xlabel("Watch+Reserve items above the England share (thousands)"); ax.set_xlim(0,max(val)*1.2)
fig.tight_layout(); fig.savefig("outputs/journal/Figure 3.png"); fig.savefig("outputs/journal/Figure 3.tif")
for k,v in g: print(k, round(v), f"{v/tot:.1%}")
