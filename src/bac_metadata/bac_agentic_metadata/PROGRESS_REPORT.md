# PROGRESS REPORT — bac_agentic_metadata

**Single source for current status + measured results + the forward plan.** The framework/why is in
[`PIPELINE_PLAN.md`](PIPELINE_PLAN.md); per-stage method + how-to-run is in
[`STAGE0_kleb_curation_map.md`](STAGE0_kleb_curation_map.md), [`STAGE1.md`](STAGE1.md),
[`STAGE2.md`](STAGE2.md). Those docs no longer carry results — they point here.

_Scope: Klebsiella validation site, **train+val only (109 accessions)**; the 47-accession test fold
stays sealed until a single final run. Last updated 2026-06-17._

---

## 1. Where we are

The engine runs end-to-end on a project accession: **deterministic sizing → grade the paper into the
`attributes.yaml` schema → opposing-Opus adjudication of every disagreement → independently FIND the
describing paper (LLM picks among API-retrieved candidates, grounded) → propose sample-level
backfill.** All five steps are built and measured on train+val. Two LLM backends sit behind
`engine.llm.LLMClient`: **`subscription`** (`claude -p`, zero API spend, default) and **`api`** (paid,
forced tool use); a backend-independent disk cache makes reruns byte-identical and free.

The headline: **grading agreement is ~0.94–0.98** after adjudication+GT-correction; **finding precision
is ~0.94 when the finder commits**, with the remaining work being **recall** (closing the abstention
tail) and **per-sample backfill** (method-b). A recurring secondary finding is that the gold-standard
sheet itself has **~17% wrong/misattributed `paper_link`s** — the engine surfaces these rather than
trusting them.

---

## 2. Measured results by stage

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

102 of 109 accessions have a curated `paper_link` (7 have none). Deterministic retrieval (ENA-desc
id-mining → NCBI BioProject elink → Europe PMC accession text-mining → EPMC title) unions candidates;
the LLM only picks an index; the pick is grounded (the accession must appear in the paper) with
abstain-over-guess.

- **Raw find-accuracy 0.62 → 0.64** after the secondary-accession fix (65/102 matched).
- **Adjudicated 0.75 → 0.78** (80/102): folding in the Opus critic's `same_paper`/`found_correct`/
  `both_describe` verdicts on mismatches.
- **Precision when the finder commits: ~0.94** (80 of 85 picks correct) — i.e. *when it picks, it is
  almost always right*. The open problem is **recall** (the abstention tail), not precision.

**Matching is by paper IDENTITY, not URL** (one paper has many links): union of all curated rows +
EPMC cross-id `{pmid,pmcid,doi}` canonicalization + a `same_paper` adjudicator verdict + always
prefer the published version over a preprint.

**The 19 mismatches, hand-verified by David (Tiers 1–4):** 12 `found_correct` (curated link was a
data-reuse/secondary paper — finder right), 2 `both_describe`, 5 genuine finder errors
(`curated_correct`: PRJDB5929, PRJEB38289, PRJEB15226, PRJNA278886, PRJEB58018). So when finder and
curated link disagree, the finder is right >2× as often as wrong.

**The 20 abstentions, rescued via web-search agents + the secondary-accession fix:**

| outcome | n | notes |
|---|---|---|
| recovered by secondary-accession fix | **3** | PRJEB1563, PRJNA767944 (match curated), PRJEB22252 (curated was wrong) |
| findable but still abstaining → need the **web-search tier** | ~12 | e.g. PRJNA271899, PRJEB28400, PRJNA549322 — EPMC doesn't text-mine their accession→paper link |
| genuinely unfindable | ~5 | no describing paper (Sanger pre-pub release PRJEB6574; umbrella PRJEB37378; no primary PRJNA982859/PRJEB21277) |

So **~15 of 20 abstentions had a findable primary** — the finder was right to abstain rather than guess,
but recall is recoverable. Per-accession detail + David's GT-decision column:
`data/abstention_rescue_review.tsv`.

Channel pull-through (matched finds): `europepmc_accession` is the workhorse; `ncbi_bioproject` 3 sole
wins; preprint→published promotion 2; `europepmc_secondary` (new) 3 rescues.

### Sample-level backfill (method-a) — targeting/recall vs `parsed_per_project`

| field | needs backfill | covered by method-a | recall vs curation |
|---|---|---|---|
| `country` | 18 | 14 | **0.78** |
| `host` | 28 | 22 | **0.83** |
| `collection_date` | 20 | 3 | 0.17 |
| `isolation_source` | 31 | 4 | 0.14 |

Method-(a) (whole-project value) handles country/host; collection_date/isolation_source are the
per-sample-table **method-(b)** backlog (44 residual accession-fields). Value correctness is **not yet
checked** (needs per-sample `metadata_v2`). `collection_date` rule: midpoint of a ≤2-year span, else
blank.

---

## 3. Improvements made this round

1. **Robust paper-match by identity** (commit `d17a8d3`) — union all curated rows per study, EPMC
   cross-id canonicalization, `same_paper` adjudicator verdict. Recovered matches previously lost to
   URL-only comparison (e.g. PRJEB27256).
2. **Always prefer published over preprint** — `europepmc.published_version_of` promotes a preprint to
   its peer-reviewed article before the LLM sees the list.
3. **Secondary-accession expansion** (commit `4bbd89d`) — describing papers often cite the ENA/SRA
   **secondary** study accession (`ERP…`/`SRP…`), not the BioProject. The finder now searches *and*
   grounds-verifies on `study_aliases(PRJ) → [PRJ, ERP/SRP]`. **Measured +3 recovered**; confirmed the
   diagnosis but also showed EPMC's text-mining index is the limiting factor for the rest.
4. **Abstention rescue + diagnosis** — web-search agents over the 20 abstentions showed ~15 are
   findable; root causes are (a) secondary-accession blindness [now fixed for the EPMC-indexed subset]
   and (b) papers EPMC simply doesn't text-mine for the accession [needs the web tier].
5. **Web-search architecture decided** — the residual-tail fallback will route the **web search
   through the API** (`web_search` server tool, metered, fires only on the abstaining tail) and the
   **candidate pick through `claude -p` subscription** (zero API spend). Not yet built.

---

## 4. Ground-truth quality finding

The frozen Klebsiella sheet is the validation target but is **imperfect, and we record disagreements
rather than trusting it.** Across the mismatch pass (12) + the abstention rescue (≥5), **~17 of 102
curated `paper_link`s are wrong or misattributed (~17%)** — data-reuse/secondary papers, an unrelated
SARS-CoV-2 paper (PRJNA982859), an unrelated fosfomycin paper (PRJNA398288), a DOI that resolves to the
wrong article (PRJEB22252). Verified corrections live in `data/gt_corrections.tsv` (grading) and the
finding overlay (to be added). **5 new finding GT-corrections** await David's confirm in
`abstention_rescue_review.tsv`. **Note:** PRJNA767944 was *not* a GT error — its curated mSphere paper
correctly cites the accession as SRP340092 (a "suspect" flag that turned out to be a false alarm).

---

## 5. What's left (forward plan)

**A. Finding — close recall (after current work):**
- Build the **web-search fallback tier** (API search → subscription pick), firing only on the
  abstaining tail. Expected to recover ~12 of the 17 remaining abstentions.
- Fold the **5 confirmed finding GT-corrections** into the overlay (David's calls on
  `abstention_rescue_review.tsv`).
- Write the **verified find-accuracy summary** (precision/recall split) once the web tier lands.

**B. Sample-level backfill — the NEXT major workstream (per-sample recovery):**
1. Apply method-(a) `country`/`host` backfill (the covered cases) — first write-back to the table.
2. **Value-correctness**: bring in per-sample `metadata_v2` to verify proposed raw values, not just
   targeting.
3. **Method-(b)**: per-sample-table extraction for the ~44 `collection_date`/`isolation_source` gaps
   (the deferred `partial` path; needs sample-accession ↔ paper-table mapping).

**C. Deferred (smaller):** 2 rubric over-steers (`PRJEB58136`, `PRJNA604975`) + a study_setting wording
tweak; a re-grade *with* `sizing_first`; the multi-organism-umbrella taxon-aware finder rule;
`PRJEB28400` sizing → ENA deposit. **Eventually:** the sealed **test-fold** final measured run; the
~7k *M. abscessus* application.

---

## 6. Where things live

- **Engine:** `engine/{ena_sizing,europepmc,ncbi,paper_finder,grader,adjudicator,llm,fulltext}.py`.
- **Klebsiella runners:** `applications/klebsiella/{run_stage1,run_study_grading,run_find_papers,
  validate_*}.py`; rubric `attributes.yaml` (**David edits**).
- **Key outputs** (`applications/klebsiella/data/`): `stage1_sizing.tsv`, `study_grades.{jsonl,tsv}`,
  `grading_*_report.*`, `found_papers.{jsonl,tsv}`, `find_validation_report.*`,
  `find_adjudication_report.*`, `abstention_rescue_review.tsv`, `gt_corrections.tsv`,
  `backfill_validation_report.*`.
- Caches (`llm_cache/`, `fulltext_cache/`, `find_cache/`, `ena_cache/`) and the API key are gitignored.
