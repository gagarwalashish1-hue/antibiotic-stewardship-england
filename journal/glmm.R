suppressMessages(library(lme4))
d <- read.csv("outputs/journal/prac.csv", stringsAsFactors=FALSE)
d$fail <- d$cls - d$wr
for (v in c("pct65","pct1524","imd","ast","can","ckd","copd","dem","dm","hf")) d[[paste0("s_",v)]] <- as.numeric(scale(d[[v]]))
d$s_size <- as.numeric(scale(log(d$pat)))
f0 <- cbind(wr,fail) ~ 1 + (1|icb) + (1|pc)
f1 <- cbind(wr,fail) ~ s_pct65+s_pct1524+s_imd+s_size+s_ast+s_can+s_ckd+s_copd+s_dem+s_dm+s_hf + (1|icb) + (1|pc)
ctl <- glmerControl(optimizer="bobyqa", optCtrl=list(maxfun=2e5))
m0 <- glmer(f0, data=d, family=binomial, control=ctl, nAGQ=1)
m1 <- glmer(f1, data=d, family=binomial, control=ctl, nAGQ=1)
vc <- function(m){v<-as.data.frame(VarCorr(m)); setNames(v$vcov, v$grp)}
v0 <- vc(m0); v1 <- vc(m1)
cat("NULL  var icb", v0["icb"], " var pc", v0["pc"], " ICB share of between-practice var", v0["icb"]/(v0["icb"]+v0["pc"]), "\n")
cat("ADJ   var icb", v1["icb"], " var pc", v1["pc"], " ICB share", v1["icb"]/(v1["icb"]+v1["pc"]), "\n")
cat("Reduction in practice-level variance with covariates:", 1 - v1["pc"]/v0["pc"], "\n")
cat("Reduction in total RE variance:", 1-(v1["icb"]+v1["pc"])/(v0["icb"]+v0["pc"]), "\n")
cf <- summary(m1)$coefficients
ci <- confint(m1, method="Wald", parm="beta_")
out <- data.frame(term=rownames(cf), OR=exp(cf[,1]), lo=exp(ci[rownames(cf),1]), hi=exp(ci[rownames(cf),2]), p=cf[,4])
print(format(out, digits=3), row.names=FALSE)
# residual funnel on logit scale, conditional on ICB effect + case mix
eta_fix <- predict(m1, re.form=~(1|icb))      # fixed + ICB, excludes practice effect
p <- d$wr/d$cls
y <- qlogis(p); vi <- 1/(d$cls*p*(1-p))
z_ml <- (y - eta_fix)/sqrt(v1["pc"] + vi)
d$z_ml <- z_ml
# also null model (ICB only) z
eta0 <- predict(m0, re.form=~(1|icb)); d$z_ml0 <- (y-eta0)/sqrt(v0["pc"]+vi)
# practice random effect standardised (BLUP / sd)
re <- ranef(m1, condVar=TRUE)$pc; d$b <- re[d$pc,1]
cat("Above 99.8% (z>3.09) adjusted multilevel:", sum(z_ml>3.09), " of which shortlisted:", sum(z_ml>3.09 & d$shortlisted=="True"), "\n")
cat("Shortlist still >3.09 adjusted ML:", sum(z_ml[d$shortlisted=="True"]>3.09), "/", sum(d$shortlisted=="True"), "  >2.58:", sum(z_ml[d$shortlisted=="True"]>2.58), "  >1.96:", sum(z_ml[d$shortlisted=="True"]>1.96), "\n")
cat("Shortlist still >3.09 ICB-only ML:", sum(d$z_ml0[d$shortlisted=="True"]>3.09), "\n")
cat("Below -3.09 adjusted:", sum(z_ml < -3.09), "\n")
cat("cor z_ml vs z_od:", cor(z_ml, d$z_od), "\n")
cat("AIC null", AIC(m0), " adj", AIC(m1), "\n")
write.csv(d[,c("pc","shortlisted","z_od","z_ml","z_ml0","b")], "outputs/journal/ml_scores.csv", row.names=FALSE)
saveRDS(list(m0=m0,m1=m1), "outputs/journal/models.rds")
