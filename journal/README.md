# Journal analysis (JAC-Antimicrobial Resistance submission)

Code for the additional analyses in the journal version of the paper: *Persistence of high Watch and Reserve antibiotic prescribing in English general practices: a national observational study, 2023–26*. An earlier version is on medRxiv: https://doi.org/10.64898/2026.11.18.26368426

These scripts build on the practice-level tables in `outputs/tables/` (produced by the main pipeline in `src/`). Run them from the repository root, in this order. Intermediate files are written to `outputs/journal/`.

| Step | Script | What it does |
| --- | --- | --- |
| 1 | `prep.py` | Joins the 12-month practice table with case-mix data (5,791 practices) |
| 2 | `glmm.R` | Multilevel binomial model with ICB and practice random effects, with and without case mix; multilevel z-scores |
| 3 | `dec.R` | Model without ICB or covariates, to show why the multilevel model flags fewer practices |
| 4 | `yr.R` | Multilevel z-scores for each of the three years (persistence test) |
| 5 | `stab.R` | Three-year model with practice and practice-by-year random effects; share of variation that is stable (parametric bootstrap CI) |
| 6 | `adq.py` | Dose-based (ADQ) funnel plot sensitivity analysis |
| 7 | `tiers.py` | Core priority list: shortlisted and beyond 99.8% in the multilevel model, or shortlisted in all three years |
| 8 | `figs.py` | Figures 1–3 of the journal manuscript |

Requirements: Python 3 (pandas, numpy, matplotlib, statsmodels) and R with lme4.

## Main results

- Of the 106 shortlisted practices, 24 remain beyond the 99.8% limit in the multilevel model (51 beyond 99%, 95 beyond 95%).
- 87% (95% CI 87–88%) of between-practice variation is stable across three years.
- The core list has 52 practices and holds about 5% of England's excess Watch+Reserve items.

The portfolio report in the repository root uses the funnel plot only. The journal analysis supersedes its outlier counts (for example "101 of 106 remain after case-mix adjustment"), while its persistence findings are unchanged.
