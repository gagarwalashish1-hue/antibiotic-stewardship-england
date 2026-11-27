suppressMessages(library(lme4))
m <- readRDS("outputs/journal/stab.rds")
print(fixef(m)); v<-as.data.frame(VarCorr(m)); print(v[,c("grp","vcov")])
ri <- ranef(m)$icb; write.csv(data.frame(icb=rownames(ri), u=ri[,1]), "outputs/journal/icb_re.csv", row.names=FALSE)
