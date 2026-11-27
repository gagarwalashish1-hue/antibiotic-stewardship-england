suppressMessages(library(lme4))
t <- read.csv("outputs/tables/practices_two_years.csv", stringsAsFactors=FALSE)
d <- read.csv("outputs/journal/prac.csv", stringsAsFactors=FALSE)
t <- merge(t, d[,c("pc","icb","cls","wr")], by="pc")
L <- rbind(data.frame(pc=t$pc,icb=t$icb,yr="2023/24",w=t$wr_2324,n=t$cls_2324),
           data.frame(pc=t$pc,icb=t$icb,yr="2024/25",w=t$wr_2425,n=t$cls_2425),
           data.frame(pc=t$pc,icb=t$icb,yr="2025/26",w=t$wr,n=t$cls))
L <- L[!is.na(L$w) & !is.na(L$n) & L$n>0,]
f <- function(x){vv<-as.data.frame(VarCorr(x)); s<-setNames(vv$vcov,vv$grp); s["pc"]/(s["pc"]+s["pc:yr"])}
t0<-Sys.time(); m0 <- glmer(cbind(w,n-w) ~ yr + (1|icb) + (1|pc) + (1|pc:yr), data=L, family=binomial, nAGQ=0)
cat("nAGQ0 fit", format(Sys.time()-t0), " ratio", f(m0), "\n"); print(as.data.frame(VarCorr(m0))[,c("grp","vcov")])
set.seed(1); y<-simulate(m0,1)[[1]]; t0<-Sys.time(); r<-refit(m0,y); cat("refit", format(Sys.time()-t0), f(r), "\n")
saveRDS(m0,"outputs/journal/m0.rds")
