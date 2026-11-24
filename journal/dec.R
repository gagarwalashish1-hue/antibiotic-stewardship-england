suppressMessages(library(lme4))
d <- read.csv("outputs/journal/prac.csv", stringsAsFactors=FALSE); d$fail<-d$cls-d$wr
m <- glmer(cbind(wr,fail)~1+(1|pc), data=d, family=binomial, control=glmerControl(optimizer="bobyqa"))
v <- as.data.frame(VarCorr(m))$vcov; p<-d$wr/d$cls
z <- (qlogis(p)-fixef(m)[1])/sqrt(v+1/(d$cls*p*(1-p)))
sh <- d$shortlisted=="True"
cat("No ICB, no casemix ML: sd_pc", sqrt(v), " >3.09 all:", sum(z>3.09), " shortlist:", sum(z[sh]>3.09), "\n")
p0 <- plogis(fixef(m)[1]); cat("sd in pp at p0:", 100*sqrt(v)*p0*(1-p0), " p0", p0, "\n")
# robust (winsorised) tau on logit scale for comparison
zz <- (qlogis(p)-qlogis(sum(d$wr)/sum(d$cls)))*sqrt(d$cls*p*(1-p))
zw <- pmin(pmax(zz, quantile(zz,.1)), quantile(zz,.9)); phi<-mean(zw^2); w<-d$cls*p*(1-p); k<-length(zz)
t2 <- max(0,(k*phi-(k-1))/(sum(w)-sum(w^2)/sum(w))); cat("winsorised DL tau logit", sqrt(t2), "\n")
z2 <- (qlogis(p)-qlogis(sum(d$wr)/sum(d$cls)))/sqrt(t2+1/w); cat("logit winsorised funnel >3.09:", sum(z2>3.09), " shortlist:", sum(z2[sh]>3.09), "\n")
