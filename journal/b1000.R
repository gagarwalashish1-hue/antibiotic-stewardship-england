suppressMessages(library(lme4))
m0 <- readRDS("outputs/journal/m0.rds")
f <- function(x){vv<-as.data.frame(VarCorr(x)); s<-setNames(vv$vcov,vv$grp); s["pc"]/(s["pc"]+s["pc:yr"])}
set.seed(2026); t0<-Sys.time()
b <- bootMer(m0, f, nsim=1000, type="parametric", parallel="multicore", ncpus=2)
x <- as.numeric(b$t); x <- x[!is.na(x)]
cat("valid", length(x), " est", b$t0, " 95% CI", quantile(x,c(.025,.975)), " SD", sd(x), " time", format(Sys.time()-t0), "\n")
