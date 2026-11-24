import pandas as pd, numpy as np
import os; os.makedirs("outputs/journal", exist_ok=True)
P="outputs/tables/"
a=pd.read_csv(P+"practices_12m_v2.csv",dtype={"pc":str})
c=pd.read_csv(P+"practices_y2_casemix.csv",dtype={"pc":str})
d=a.merge(c[["pc","ast","can","ckd","copd","dem","dm","hf","z_cm","exp_cm"]],on="pc",how="inner")
print(len(a),len(c),len(d), d.shortlisted.sum(), d[["pct65","pct1524","imd","pat"]].isna().sum().to_dict())
print("check share", np.allclose(d.share, d.wr/d.cls*100))
d.to_csv("outputs/journal/prac.csv",index=False)
