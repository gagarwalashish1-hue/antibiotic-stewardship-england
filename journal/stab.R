suppressMessages(library(lme4))
t <- read.csv("outputs/tables/practices_two_years.csv", stringsAsFactors=FALSE)
d <- read.csv("outputs/journal/prac.csv", stringsAsFactors=FALSE)
t <- merge(t, d[,c("pc","icb","cls","wr")], by="pc")
L <- rbind(data.frame(pc=t$pc,icb=t$icb,yr="2023/24",w=t$wr_2324,n=t$cls_2324),
           data.frame(pc=t$pc,icb=t$icb,yr="2024/25",w=t$wr_2425,n=t$cls_2425),
           data.frame(pc=t$pc,icb=t$icb,yr="2025/26",w=t$wr,n=t$cls))
L <- L[!is.na(L$w) & !is.na(L$n) & L$n>0,]
cat("rows",nrow(L)," practices",length(unique(L$pc))," all3",sum(table(L$pc)==3),"\n")
m <- glmer(cbind(w,n-w) ~ yr + (1|icb) + (1|pc) + (1|pc:yr), data=L, family=binomial, control=glmerControl(optimizer="bobyqa"))
v <- as.data.frame(VarCorr(m)); print(v[,c("grp","vcov","sdcor")])
s <- setNames(v$vcov, v$grp)
cat("Stable share of practice variation:", s["pc"]/(s["pc"]+s["pc:yr"]), "\n")
cat("ICB share of total RE:", s["icb"]/sum(s), " stable practice share of total:", s["pc"]/sum(s), " year-specific:", s["pc:yr"]/sum(s), "\n")
print(fixef(m))
# CIs for variance components via profile is slow; use parametric bootstrap small
set.seed(1)
b <- bootMer(m, function(x){vv<-as.data.frame(VarCorr(x)); s<-setNames(vv$vcov,vv$grp); s["pc"]/(s["pc"]+s["pc:yr"])}, nsim=100, type="parametric")
cat("Stable share 95% CI (parametric bootstrap, 100 sims):", quantile(b$t, c(.025,.975)), "\n")
re <- ranef(m)$pc; write.csv(data.frame(pc=rownames(re), u=re[,1]), "outputs/journal/stable_re.csv", row.names=FALSE)
saveRDS(m,"outputs/journal/stab.rds")
