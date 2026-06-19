# PROGRESS REPORT — bac_agentic_metadata

**Single source for current status + measured results + the forward plan.** The framework/why is in
[`PIPELINE_PLAN.md`](PIPELINE_PLAN.md); per-stage method + how-to-run is in
[`STAGE0_kleb_curation_map.md`](STAGE0_kleb_curation_map.md), [`STAGE1.md`](STAGE1.md),
[`STAGE2.md`](STAGE2.md). Those docs no longer carry results — they point here.

_Scope: Klebsiella validation site, **train+val only (109 accessions)**; the 47-accession test fold
stays sealed until a single final run. Last updated 2026-06-18._

---

## 1. Where we are

The engine runs end-to-end on a project accession: **deterministic sizing → grade the paper into the
`attributes.yaml` schema → opposing-Opus adjudication of every disagreement → independently FIND the
describing paper (LLM picks among API-retrieved candidates, grounded) → propose sample-level
backfill.** All five steps are built and measured on train+val. Two LLM backends sit behind
`engine.llm.LLMClient`: **`subscription`** (`claude -p`, zero API spend, default) and **`api`** (paid,
forced tool use); a backend-independent disk cache makes reruns byte-identical and free.

The headline, reframed as **agent vs manual curation** (the sheet is curation, not ground truth — so
agent-vs-sheet is *agreement*): the agent and manual curation **agree 84%**, and on disagreements the
agent is right **~5× more often (34 vs 7)** → **adjudicated agent accuracy 0.97 vs manual-curation 0.88,
a +0.10 improvement** (§2 lead table; model-robust — Opus identical). In stage terms: **grading
agreement is ~0.94–0.98** after adjudication+GT-correction; **paper-finding is
raw 0.70 / adjudicated 0.87** with the full three-tier pipeline (deterministic + secondary-accession +
web-search fallback) now entirely **inside the finder**, at **~0.94 precision when it commits** and only
**7 of 102 abstaining**. Per-sample backfill is **run and value-checked** on train+val
end-to-end: whole-field fills country/host (`country` 0.99, `host` ~1.0 semantic), and **method-b**
per-sample extraction from OA supplementary tables fills the genuinely-varying date/source (collection_date
**0.999** year-level, isolation_source **0.959** fidelity, on the 9 of 15 joinable studies recovered). The engine is also **model-robust**: re-running the finder+grader with an
**Opus 4.8** agent (vs the default Sonnet 4.6) agrees within noise (adjudicated finding 0.86 vs 0.87) —
two independent models converge, so the results are not a single-model artifact. A recurring secondary
finding: the gold-standard sheet itself has **~20% wrong/misattributed `paper_link`s** — the engine
surfaces these rather than trusting them.

---

## 2. Measured results by stage

### Agent vs manual curation — agreement, then adjudicated accuracy of each (headline framing)

The frozen sheet is **manual curation, not ground truth**, so an agent-vs-sheet number is really
**agreement**, not accuracy. Reframed that way (`summarise_agent_vs_manual.py`), across paper-finding +
the two primary grading attributes the agent and the manual curation **agree 84%** of the time; on the
disagreements the opposing **Opus adjudicator** ruled, **the agent is right ~5× more often than the
manual curation (34 vs 7)**:

**agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement corrected for chance
(categorical raters only — N/A for finding/TOTAL, where there is no fixed shared label set):

| item | N judged | agreement | agent right | manual right | tie | undet | **Cohen κ** | **agent acc** | **manual acc** | **Δ** |
|---|---|---|---|---|---|---|---|---|---|---|
| paper-finding | 95 | 71 (0.75) | 16 | 6 | 2 | 0 | — | **0.94** | 0.83 | **+0.11** |
| amr_study | 85 | 70 (0.82) | 12 | 1 | 1 | 1 | 0.66 | **0.99** | 0.86 | **+0.13** |
| study_setting | 94 | 88 (0.94) | 6 | 0 | 0 | 0 | 0.74 | **1.00** | 0.94 | **+0.06** |
| **TOTAL** | **274** | **229 (0.84)** | **34** | **7** | **3** | **1** | — | **0.97** | **0.88** | **+0.10** |

So the engine runs at **~0.97 adjudicated accuracy and improves on the existing manual curation by ~10
points (0.88 → 0.97)**, correcting 34 curation errors (misattributed `paper_link`s, mis-graded
`amr_study`/`study_setting`) at the cost of 7. Chance-corrected agreement is **substantial** (Cohen κ
0.66 / 0.74; κ reads below p₀ on `study_setting` because the `hospital` label dominates — the prevalence
effect). **Model-robust:** the Opus agent gives the same picture (agent 0.97 / manual 0.87 / Δ +0.10;
κ 0.68 / 0.70). _Caveat:_ agreements are assumed jointly correct (only disagreements are adjudicated), so
both accuracies are upper bounds on undetected joint error; the adjudicator is the independent Opus critic
with verbatim quotes, and the grading manual-errors are David-verified (`gt_corrections.tsv`). Per-item +
re-runnable on any model/fold: `summarise_agent_vs_manual.py` → `data/agent_vs_manual_{sonnet,opus}.{md,tsv}`.

### Stage 1 — deterministic sizing & completeness (no LLM)

Per accession: ENA total + taxon sample/run counts (from `read_run`, deduped to sample level — the
calibrated unit, see STAGE1), `umbrella_suspected`, three-state completeness. Of 150 curation rows:
**109 cleanly explained** (67 whole-project + 26 subsample + 15 shared-accession + 1 umbrella), 22 ENA
under-labelling (curation more complete — not errors), 15 genuine review-queue. Base→post-merge
completeness gain the later stages must reproduce: country +0.16, collection_date +0.10,
isolation_source +0.14, host +0.23.

### Stage 2A — grading (LLM) + opposing adjudication

The grader renders the rubric straight from `attributes.yaml` (definitions are **David's to edit**).
Primary checks vs the (imperfect) frozen ground truth:

| check | raw | adjudicated/corrected | n |
|---|---|---|---|
| `amr_study` | 0.78 | **0.94** | 86 |
| `study_setting` | 0.90 | **0.98** | 94 |

`cohort_age` is **not scored** (no reliable GT). The lift comes from the opposing **Opus adjudicator**
(`engine.adjudicator`): on the first full pass, **28 grader-vs-sheet disagreements → 20 model_correct
(sheet wrong), 3 sheet_correct, 5 undetermined**. Verified sheet errors became a GT-correction overlay
(`data/gt_corrections.tsv`, 19 rows, applied at scoring time; the frozen snapshot stays immutable). The
gain is partly mechanical (truth corrected to match verified findings); raw pre-correction was
0.78/0.90.

### Stage 2B — paper finding (LLM picks among retrieved candidates; never invents)

102 of 109 accessions have a curated `paper_link` (7 have none). The finder is now a **complete
three-tier pipeline, all inside the finder**: deterministic retrieval (ENA-desc id-mining → NCBI
BioProject elink → Europe PMC accession text-mining **incl. the secondary accessions** ERP/SRP → EPMC
title) → on abstention, a **web-search fallback** (Anthropic API `web_search`, fires only on the tail).
The LLM only ever picks an index; the pick is **grounded** (the accession or an alias must appear in
the paper); unconfident picks **abstain**; mismatches are then **adjudicated by the opposing Opus critic**.

- **Raw find-accuracy 0.62 → 0.70** (71/102 matched).
- **Adjudicated 0.75 → 0.87** (89/102): 24 mismatches → **16 `found_correct` + 2 `both_describe` +
  1 `same_paper` + 6 genuine finder errors** (`curated_correct`).
- **Precision when the finder commits: ~0.94** (89 of ~95 picks correct) — when it picks, it is almost
  always right.
- **Abstentions 24 → 7.** Of the 7 residual: **6 are findable only with the curated link as a hint**
  (blind web search — even a direct one — does not surface them from the generic ENA title; e.g.
  PRJNA271899, PRJEB42462, PRJNA549322, PRJNA396774), and **1 genuinely has no describing paper**
  (PRJNA982859). This is the honest blind ceiling.

**Matching is by paper IDENTITY, not URL** (one paper has many links): union of all curated rows + EPMC
cross-id `{pmid,pmcid,doi}` canonicalization + a `same_paper` adjudicator verdict + always prefer the
published version. Re-running the full pipeline left **all 82 previously-verified picks unchanged** (the
new tiers only add candidates / fire on abstention), so David's Tier 1–4 hand-verification stands.

**The 6 genuine finder errors** (`curated_correct`): PRJDB5929, PRJEB38289, PRJEB15226, PRJNA278886,
PRJEB58018 (the original 5) + PRJEB37378 (the web tier picked the DRUM *protocol* paper; the adjudicator
correctly preferred the curated cohort paper).

**Recovery of the 24 abstentions, by finder tier:**

| tier (inside the finder) | recovered | examples |
|---|---|---|
| secondary-accession (ERP/SRP search + verify) | 3 | PRJEB1563 (ERP002304), PRJNA767944 (SRP340092), PRJEB22252 (ERP024601) |
| web-search fallback (API `web_search`) | ~11 | PRJEB6574 → **Holt 2015 PNAS**, PRJEB20799 → Okomo, PRJEB28400 → Roberts, PRJNA845975 → medRxiv |
| still abstaining | 7 | 6 blind-unfindable + PRJNA982859 (no paper) |

Notably the blind web tier **beat the agent proxy** on PRJEB6574 (it found Holt 2015, which the agent
had marked "not-found"), and the adjudicator **caught its one over-reach** (PRJEB37378). Channel
pull-through: `europepmc_accession` workhorse; `web_search` 6 winning finds; `europepmc_secondary` 2;
NCBI 3. Per-mismatch verdicts + verbatim quotes: `data/find_adjudication_report.{md,tsv}`.

### Model robustness — Opus 4.8 (agent) vs Sonnet 4.6 (agent)

To test whether the results depend on the specific agent model — the precondition for trusting the
engine without per-study oversight — the full finder + grader were re-run with **Opus 4.8** as the
agent (Opus stays the *independent* adjudicator throughout). The two land within noise of each other:

| metric | Sonnet 4.6 | Opus 4.8 |
|---|---|---|
| find-accuracy, raw | 0.70 | 0.70 |
| **find-accuracy, adjudicated** | **0.87** (89/102) | **0.86** (88/102) |
| genuine finder errors (`curated_correct`) | 6 | 8 |
| `amr_study` | 0.94 (n=85) | 0.97 (n=78) |
| `study_setting` | 0.98 (n=94) | 0.98 (n=88) |
| genuine grading errors (`sheet_correct`) | 2 | 1 |

Both models do very well and the differences are small — **Sonnet 4.6 is perfectly adequate**. Opus is
**occasionally more deliberative**: it abstains slightly more (lower scored `n`) and is marginally more
precise where it commits (`amr_study` 0.97 vs 0.94; one genuine grading error vs two), but it is no
better on finding — in fact marginally lower (0.86 vs 0.87, two more genuine paper-misses). Crucially,
two *independent* models — Sonnet as finder/grader, Opus as adjudicator — converge to **~0.86–0.87
adjudicated finding** and **~0.97 `amr_study`**, so the result is **model-robust, not a Sonnet
artifact**. **Decision: Sonnet 4.6 stays the default agent; Opus 4.8 stays the independent adjudicator**
(its judgment is most valuable, and cheapest, where the call volume is low). Opus outputs are the
`*_opus.*` / `{find,grading}_opus_*` files under `data/`.

### Sample-level backfill — steps 1–2 (gate + whole-field), run + value-checked on train+val

The completeness-gated whole-field pass (`engine/backfill.py`) ran on the **raw, uncurated ENA**
per-sample table (`load_collated_metadata`; train+val = 45 studies) → **24,351 fills**. A study×field
goes to whole-field only when ENA is <75% complete (placeholder-stripped); genuinely-varying fields
fall through to the **method-b** backlog. Coverage matches the Stage-1 prediction — country/host are
largely whole-field-solvable, date/source mostly vary:

| field | studies covered (whole-field) | studies residual (→ method-b) | cells filled |
|---|---|---|---|
| `host` | 38 | 12 | 14,396 |
| `country` | 23 | 8 | 5,450 |
| `collection_date` | 4 | 35 | 3,610 |
| `isolation_source` | 5 | 48 | 895 |

**Value-correctness vs the curated gold** (`metadata_final_curated_all_samples_and_columns.tsv`, via
`validate_backfill_values.py`). The comparison must be **parse/category-aware** — our fills are RAW and
the gold is curated (David's alignment point), so a naive raw-string match badly understates host/source:

| field | value-accuracy | reading |
|---|---|---|
| `country` | **0.99** (4435/4472 vs `_parsed`) | whole-field country is essentially always right |
| `host` | **~1.00 semantic** (11,672/11,672 gold = `human`) | every fill is `Homo sapiens` = human; the raw-string 0.11 is a `Homo sapiens`≠`human` **categorisation artifact**, not an error |
| `isolation_source` | **~0.76 category-level** (stool→faeces, blood→blood; raw-string 0.17) | whole-field fired on only **5 studies** (48 heterogeneous studies correctly gated to method-b); the entire shortfall is **one study (PRJEB36486)** where the grader's `stool` is faithful to the paper ("serial stool sampling") but the gold curated `intestinal`→`invasive gut & organs` — a gold categorisation quirk, not an engine error. Fidelity-to-source on the checkable subset is ~100% |
| `collection_date` | 0.00 exact | the ≤2-yr midpoint is a coarse proxy, never equals the exact per-sample date → method-b |

So **where whole-field is the right model (country, host) it is ~99–100% correct**, and where the field
genuinely varies (date, source) the gate correctly defers most of it to method-b while the fraction it
does fill is right for the uniform subset — validating the two-step gated design. RAW values only; the
parse/categorise rule-system stays downstream (a separate later workstream). `collection_date` rule:
midpoint of a ≤2-year span, else blank.

### Sample-level backfill — method-b (per-sample extraction from supplementary tables)

The genuinely-varying residual (`collection_date`/`isolation_source`) is recovered per-sample from the
paper's OA supplementary tables (`engine/supplementary.py` + `engine/sample_extractor.py`): the **LLM
maps columns→fields** from a header preview, then **deterministic code joins each table row to a
`sample_accession`** (via the study's ENA accession set) and copies the cell **verbatim** — grounded,
faithful, abstaining. Feasibility over the 59 residual studies: 22 have an OA table, **15 directly
joinable** (table carries ENA accessions). Run on those 15 → **9 recovered, 13,900 per-sample fills**;
the other 6 correctly abstain (accession-manifest-only tables, several flagging *two-hop* strain-keyed
field tables → deferred tier). Value-correctness vs the curated gold (the 9 recovered):

| field | method-b accuracy | reading |
|---|---|---|
| `country` | **0.999** (3998/4003) | per-sample country, essentially perfect |
| `collection_date` | **0.999** year-level | the payoff method-a could not give: real per-sample dates (whole-field midpoint was 0.00). Exact-string 0.00 only because the gold parser *imputes* a day/month (`2019`→`2019/06/30`); method-b keeps the true granularity |
| `isolation_source` | **0.959** fidelity | per-sample specimen matches the gold raw 96%; **carriage-vs-invasive granularity preserved** (`Screen swab`→carriage vs `Wound swab`/`Pus`/`Aspirates`→invasive); +377 fills where the gold itself was blank (new data) |

Method-b is **deterministic + one small LLM call per table** (disk-cached, reruns free). Combined, the
backfill now fills country/host via whole-field (~0.99 / ~1.0) and date/source via method-b (~1.0 / ~0.96)
on the recoverable subset. Artifacts: `methodb_{feasibility,mappability,applied}.tsv`,
`methodb_value_report.*`.

---

## 3. Improvements made this round

1. **Robust paper-match by identity** (commit `d17a8d3`) — union all curated rows per study, EPMC
   cross-id canonicalization, `same_paper` adjudicator verdict. Recovered matches previously lost to
   URL-only comparison (e.g. PRJEB27256).
2. **Always prefer published over preprint** — `europepmc.published_version_of` promotes a preprint to
   its peer-reviewed article before the LLM sees the list.
3. **Secondary-accession expansion** (commit `4bbd89d`) — describing papers often cite the ENA/SRA
   **secondary** study accession (`ERP…`/`SRP…`), not the BioProject. The finder now searches *and*
   grounds-verifies on `study_aliases(PRJ) → [PRJ, ERP/SRP]`. **+3 recovered** (PRJEB1563, PRJNA767944,
   PRJEB22252); confirmed the diagnosis, with EPMC's text-mining index the limit for the rest.
4. **Abstention rescue + diagnosis** — web-search agents over the 20 abstentions showed the recall gap
   is (a) secondary-accession blindness [fixed] and (b) papers EPMC doesn't text-mine for the accession
   [needs the web tier]. The agent rescue (which had the curated link as a cross-check) was an
   *optimistic* proxy — the blind pipeline recovers fewer, which the canonical numbers now report.
5. **Web-search fallback tier — BUILT and measured.** `engine/websearch.py` runs the **web search on
   the paid API** (`web_search` server tool, fires only on the abstaining tail) and returns candidates;
   the **pick stays on the `claude -p` subscription** and still passes grounded-verify. It **recovered
   ~11 of the residual tail** (abstentions 24 → 7) and lifted adjudicated find-accuracy 0.78 → **0.87**
   — including PRJEB6574 → Holt 2015 PNAS, which the agent proxy had missed.

---

## 4. Ground-truth quality finding

The frozen Klebsiella sheet is the validation target but is **imperfect, and we record disagreements
rather than trusting it.** The canonical adjudication ruled **18 of 24 finder/curated mismatches in the
finder's favour** (16 `found_correct` + 2 `both_describe`), i.e. **~20 of 102 curated `paper_link`s are
wrong or misattributed (~20%)** — data-reuse/secondary papers, an unrelated SARS-CoV-2 paper
(PRJNA982859), an unrelated fosfomycin paper (PRJNA398288), a DOI that resolves to the wrong article
(PRJEB22252). Per-case verdicts + verbatim quotes: `data/find_adjudication_report.{md,tsv}`; verified
grading corrections in `data/gt_corrections.tsv`. The confirmed finding GT-corrections await David's
sign-off before folding into a finding overlay. **Note:** PRJNA767944 was *not* a GT error — its curated
mSphere paper correctly cites the accession as SRP340092 (a "suspect" flag that was a false alarm).

---

## 5. What's left (forward plan)

**A. Finding — essentially done; small follow-ups:**
- ✅ Web-search fallback tier built + measured (raw 0.70 / adjudicated **0.87**; abstentions 24 → 7).
- Fold the confirmed **finding GT-corrections** into a finding overlay (David signs off the
  `found_correct` rows in `find_adjudication_report.tsv`).
- The **7 residual abstentions** are the honest blind ceiling (6 findable only with the curated link
  as a hint; PRJNA982859 has no paper) — accept as abstentions, revisit only if needed. Two web-tier
  hygiene items: the title-only degenerate pick (PRJEB22890, no DOI/PMID captured) and tightening the
  abstention gate for unverified web-only picks.

**B. Sample-level backfill — steps 1–2 DONE; method-b is the remaining workstream:**
1. ✅ Gate + whole-field fill **run on train+val** (24,351 fills, 45 studies) — `backfill_applied.tsv`.
2. ✅ **Value-correctness** checked vs the curated gold: `country` **0.99**, `host` **~1.0 semantic**,
   `isolation_source` ~0.76 category-level, `collection_date` 0.00 exact (coarse proxy). The comparison
   is parse/category-aware (raw fills vs curated gold).
3. ✅ **Method-(b)** built + run: per-sample extraction from OA supplementary tables
   (`engine/{supplementary,sample_extractor}.py`). 15 joinable studies → 9 recovered (13,900 fills);
   country **0.999**, collection_date **0.999** year-level, isolation_source **0.959** fidelity.
4. **Method-b two-hop tier** (next): the 6 abstentions are accession-manifest-only tables; several flag
   strain-keyed field tables (`mmc6.xlsx`, the `MOESM` set …) that need a **manifest→strain→fields**
   two-hop join. Plus DOCX/PDF-only supplements (14) and paywalled (13) remain `needs_manual`.
5. Optional: write-back of the high-confidence fills into the table (after sign-off).

**C. Deferred (smaller):** 2 rubric over-steers (`PRJEB58136`, `PRJNA604975`) + a study_setting wording
tweak; a re-grade *with* `sizing_first`; the multi-organism-umbrella taxon-aware finder rule;
`PRJEB28400` sizing → ENA deposit. **Eventually:** the sealed **test-fold** final measured run; the
~7k *M. abscessus* application.

---

## 6. Where things live

- **Engine:** `engine/{ena_sizing,europepmc,ncbi,paper_finder,grader,adjudicator,llm,fulltext,
  websearch,backfill,sources}.py`.
- **Klebsiella runners:** `applications/klebsiella/{run_stage1,run_study_grading,run_find_papers,
  run_backfill,validate_*,summarise_agent_vs_manual}.py`; rubric `attributes.yaml` (**David edits**).
- **Key outputs** (`applications/klebsiella/data/`): `stage1_sizing.tsv`, `study_grades.{jsonl,tsv}`,
  `grading_*_report.*`, `found_papers.{jsonl,tsv}`, `find_validation_report.*`,
  `find_adjudication_report.*`, `abstention_rescue_review.tsv`, `gt_corrections.tsv`,
  `backfill_applied.tsv`, `backfill_gate_report.tsv`, `backfill_value_report.*` (+ `_raw`),
  `agent_vs_manual_{sonnet,opus}.*`, `methodb_feasibility.tsv`, `methodb_mappability.tsv`.
- **Opus-comparison outputs** (default model stays Sonnet): `found_papers_opus.{jsonl,tsv}`,
  `study_grades_opus.{jsonl,tsv}`, `{find,grading}_opus_validation_report.*`,
  `{find,grading}_opus_adjudication_report.*`.
- Caches (`llm_cache/`, `fulltext_cache/`, `find_cache/`, `ena_cache/`) and the API key are gitignored.
