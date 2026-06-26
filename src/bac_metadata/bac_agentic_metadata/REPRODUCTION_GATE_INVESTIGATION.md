# Reproduction-gate investigation — why whole-field country/date backfill collapsed on the clean rerun

**Status: RESOLVED + RE-GATED (2026-06-26).** All five holes fixed (commit `5fc7ee4`); the test fold
re-gated through the corrected pipeline (per-sample-first → guarded whole-field → human escalation → apply →
completeness → run-health). **Agent ≥ v2 on ALL FOUR fields, residual_gap 0.0:** country **0.959** (v2 0.848;
was 0.788 broken), collection_date **0.936** (v2 0.764; was 0.838), isolation_source **0.742** (v2 0.702),
host **0.836** (v2 0.766). Composition is now honest — country's gain is escalation 0.171 (human-confirmed,
incl. PRJEB27342 Italy) not silent whole-field; date is per-sample 0.105 + escalation 0.160. Run-health:
**0 ACTIONABLE**, 172 FILLED, 15 EXHAUSTED, 1 BLOCKED (PRJEB29738 isolation_source — supplement is aggregate-
only, no per-isolate table ever published; awaiting curator accept-as-unrecoverable). The original failure
(a 5,413-sample silent drop reading ALL CLEAR) is now structurally impossible. Remaining: Phase D accounting,
Phase E (`method b`→`per sample`) rename, then resume M. abscessus.

## Framing (the lens this investigation used)

The completeness collapse is a **SYMPTOM**. The question was: **at which pipeline step is the rerun failing
to pursue / pick up data — silently recording 0 fills where it should have a value?** Working prior: a
**CODE / DESIGN hole**, found by open-minded, step-by-step assessment; model non-determinism is the *trigger*
that exposes the hole, **not** an acceptable explanation on its own. The robustness / run-health / escalation
layer was treated as a **prime suspect, not a trusted tool** — and it is indeed where the holes live.

## The measured symptom (test fold, 47 studies / 31,604 samples)

Grading quality reproduced (agent-vs-manual 0.974); **country fell 0.957→0.788 (below v2 0.848)** and
**collection_date 0.908→0.838**, entirely in study-level WHOLE-FIELD backfill (per-sample stable).

## What the per-stage cache replay proved (token-free; method below)

The whole-field backfill is a **pure function of (raw ENA, grades)**; raw ENA — hence the gate (which studies
need backfill + how many blank cells) — is **fixed** between baseline and rerun. So the collapse is entirely
in the grades' `whole_project` proposals. Reconstructing the baseline grades (replay archived cache under HEAD
code, **0 cache misses** ⇒ grading prompt byte-identical baseline↔HEAD, no grading-code regression) and
diffing against the rerun grades localised the **entire** collapse to **ONE study: PRJEB27342 (SpARK), 5,413
samples = 17 % of the fold**, ENA country completeness 0.000:

| field | baseline fills | rerun fills | Δ | driver |
|---|---|---|---|---|
| country | 9,233 | 3,879 | **5,354** | PRJEB27342 alone −5,413 (net −5,354 after PRJEB1271 +59) |
| collection_date | 6,266 | 853 | **5,413** | PRJEB27342 alone −5,413 |
| host | 5,757 | 4,682 | −1,075 | PRJEB48268 −1,104 + PRJEB57159 −30 (but per-sample/escalation rescued host overall) |
| isolation_source | 69 | 69 | 0 | — |

## Root cause — a non-determinism TRIGGER that exposed three real holes

**For PRJEB27342 the grading prompt is byte-identical between runs (same cache key), but the cached grades
differ** — baseline `country=(Italy, whole_project=True)`, rerun `(None, False)`; same for date. Both are
well-formed, fully-reasoned grades (baseline cited "5,900 samples … in Pavia (Northern Italy)"; rerun cited
"samples from France and elsewhere" and abstained). So **Sonnet is non-deterministic on this borderline
whole-project call at temperature 0**, and that single coin-flip swings 5,413 fills (country ±0.17). That is
the *trigger*. The defects it exposed:

- **HOLE 1 — escalation triage runs BLIND on paywalled (local-PDF) studies (deterministic CODE BUG).**
  `applications/klebsiella/run_escalations.py::_make_evidence_fn` (≈ lines 104-106) calls only
  `fetch_fulltext(link)` and **omits the `resolve_local_fulltext` PDF fallback that grading uses**
  (`run_study_grading.py:147-151`). For PRJEB27342 (graded from a manual PDF) the triage saw
  `evidence source=none, text_len=0` — it judged tight-vs-wide with **no paper at all**, leaning on the EBI
  "France and elsewhere" blurb, and returned `wide_mix_skip`. Affects **all 54 PDF-only studies**.
- **HOLE 2 — uncertainty is silently RESOLVED-as-skip instead of escalated (design hole; David: "escalation
  should be the norm for any uncertainty").** A high-gap (5,413) whole-field decline must survive a *second*
  stochastic/blind LLM gate (`classify_escalation_candidate` → `wide_mix_skip`) to ever reach the human — and
  it didn't. No human saw a 5,413-sample decision. Asymmetry: when grading *fills* the value lands; when
  grading *declines*, the value can vanish through two silent LLM calls.
- **HOLE 3 — `per_sample_covered` suppresses escalation of the residual gap.** PRJEB27342 date: per-sample
  filled 3,227 / 5,413 cells (≥ the 0.5 `--per-sample-frac`), so `(PRJEB27342, collection_date)` counted
  "resolved" and escalation skipped it — leaving the remaining **2,186** blank date cells unfilled and
  unescalated. Half-coverage silences the rest.
- **HOLE 4 — run-health / no-silent-failures did not flag any of this.** A 5,413-sample whole-field drop with
  country falling below v2 read ~clear. The audit must flag high-gap whole-field declines that were neither
  escalated nor per-sample-resolved.

**Note on "chasing baseline 0.957" — the baseline fill was PARTLY WRONG.** v2 gold for PRJEB27342 country is
**Italy ~3,345 (85 %) + Ghana ~568 (13 %) + blank ~451** — NOT uniform Italy. The baseline's "Italy
whole_project=True" fill mislabelled the ~568 Ghana isolates, so baseline's higher 0.957 was inflated with
~568 wrong cells. PRJEB27342 is a **Pattern-C aggregate** (the paper's ~3,227 Pavia/Italy SpARK isolates +
extra Ghana isolates deposited under the same accession). The anchored per-sample supp table
(`41564_2022_1263_MOESM3_ESM.xlsx`, Table_S2) has `place_sampling`/`ORIGIN`/`GROUP` but **no country column**,
and covers only the Italian SpARK isolates — so country here is neither cleanly whole-fillable NOR fully
per-sample-recoverable from the anchored table. **Implication for the gate:** "reproduce baseline 0.957
country" is the WRONG target (it re-introduces errors); the honest resolution is to **escalate this
high-leverage, genuinely-mixed call to a human** (now fires, suggesting Italy for the SpARK subcohort) and
accept a correct, possibly-lower completeness rather than a wrong-but-higher one. Gate criterion needs David's
steer (see below).

## HOLE 5 — pipeline ORDERING inverted (David, 2026-06-26): whole-field pre-empted per-sample

David's check of the ordering/logic confirmed a structural inversion contradicting the engine's stated
design ("per-sample runs first"):
- **Run order was whole-field (Stage 5) → per-sample (Stage 6).** The coarse study-wide guess ran first;
  per-sample only targeted whole-field's `residual` leftovers (study-level), so a study whole-field "covered"
  was never visited by per-sample — the guess **pre-empted** the accurate per-isolate step.
- **No parsimony / no precedence.** `apply_whole_field` never overwrote *raw ENA* but never checked
  per-sample/table data, and nothing merged the two (completeness is a value-blind union) — so "all = Italy"
  could sit on cells a per-isolate table resolves differently, unreconciled.

**FIX 5 (implemented): per-sample FIRST + parsimony guard.** Reordered `run_pipeline.sh` to per-sample
(Stage 5, grade-independent ENA-incompleteness gate) → whole-field (Stage 6, fills only post-per-sample
blanks). `engine.backfill.per_sample_guards` + `apply_whole_field(per_sample=…)`: whole-field now (a) never
overwrites a cell per-sample filled, and (b) is **blocked** for any `(study, field)` where per-sample
extracted ≥2 distinct values (genuine heterogeneity). `run_backfill` loads `--per-sample` and marks the gate
report `covered` for per-sample-resolved fields too; `run_per_sample_extract` computes its own gate (drops
`--gate-report`). **Validated:** on baseline grades the guard blocks PRJEB27342 date (5,413→0, per-sample
has the 340 real dates) and host, keeps country (per-sample captured none), and blocks PRJEB34643 +
PRJNA252957 country whole-fills (per-sample detected multiple countries — the Ghana-type error prevented
generally). 20 (study×field) blocked as heterogeneous on the test fold.

## Fix status (2026-06-26) — implemented + validated at detection

FIX 1–4 implemented (`run_study_grading.resolve_fulltext_for_accession` shared resolver;
`engine.escalation` big-decision rule + per-sample-covered bypass + `escalate_trigger`; `run_escalations`
cohort-size wiring + PDF-aware evidence_fn; `report_run_health` big-decision audit). Re-running escalation
detect on the test fold (quick — only PDF-study declines needed fresh triage) now QUEUES PRJEB27342:
country `big_decision(6354)+tight_cluster_escalate → Italy`, date `→ 2018-01-01`, iso/host `big_decision`
(wide, left to per-sample). FIX 1 alone flipped the country triage wide→tight once it could read the PDF.
The queue grew 11→22 items (every >1 % study's whole-field decline now surfaces for human confirmation).
**Open decision (David):** the gate's country/date "agent ≥ v2" target, given v2 itself partly reflects
per-sample Ghana country the engine cannot extract from the anchored table.

## Method (reproducible, token-free) — assets + scripts

- Archived baseline cache: `~/.bachgt_rerun_stash/cache_archive_2026-06-24/cache/` (llm/ena/fulltext/find/…).
- Replay reconstruction: swap a **copy** of the archived cache into `data/cache/` (preserve the live rerun
  cache by `mv`), run `run_study_grading.py --fold test --backend api` with `BAC_ANTHROPIC_KEY_FILE=/nonexistent`
  + `ANTHROPIC_API_KEY` unset → a cache **hit** needs no key (zero spend); a **miss** aborts before any network
  call (and signals a prompt change). Restore the live cache afterwards. **Never mutate the archive.**
- Investigation scripts (kept under `~/bachgt_gate_investigation/`): `diff_grades.py` (baseline vs rerun fills
  per field/study vs the gate), `probe_key.py` (grading cache-key membership → identical-prompt proof),
  `probe_classify.py` (escalation-triage cached verdict). The baseline-replay grades are at
  `data/study_lv_attributes/grading/study_grades_test_basecache.{tsv,jsonl}`; the baseline replay cache is
  preserved at `data/cache.basereplay/` for re-inspection.

## Fix plan (Phase F — exit criterion: country + date reproduce, agent ≥ v2 on all four)

1. **HOLE 1:** give `run_escalations._make_evidence_fn` the same `resolve_local_fulltext` fallback grading
   uses (factor the grader's fulltext-resolution into one shared helper so they can never diverge again).
2. **HOLE 2:** make escalation the default for uncertainty — a high-gap whole-field decline is **queued for
   the human regardless of the wide/tight triage** (the triage label + theme + quotes ride along as advice,
   not as a silent gate). Decide the gap threshold with David.
   - **BIG-DECISION SAFETY RULE (David, 2026-06-26):** *in addition to* the tight/wide rules, **always
     escalate any whole-field decision for a study accounting for > 1 % of the whole metadata set** — a
     deterministic, LLM-free leverage gate. Such a study's whole-field call moves the global metric
     materially, so a human always confirms it, with the paper, any per-sample table, and the grade's value
     + reasoning presented. (PRJEB27342 at 5,413 samples is ~17 % of the test fold — would always escalate.)
     Denominator = total taxon samples across the whole curated cohort (from ENA sizing), TBC with David.
3. **HOLE 3:** escalate (or per-sample-target) the **residual** blank cells when per-sample covers only part
   of a field's gap, instead of treating partial coverage as fully resolved.
4. **HOLE 4:** extend the run-health / no-silent-failures audit to FLAG every high-gap whole-field decline
   that was neither escalated nor per-sample-resolved (ACTIONABLE, never silently EXHAUSTED/clear). Add a
   whole-field fill-count-per-(study,field) regression guard so a large fill can't silently halve again.
5. **(stability, optional/secondary)** for the highest-leverage whole-field proposals, reduce single-call
   variance (self-consistency vote or Opus escalation) — likely unnecessary once 1–4 make every uncertain
   high-leverage call escalate to a human.

## Working rules
- Never mutate `~/.bachgt_rerun_stash/`; cache replay spends no tokens; commit explicit paths for David to
  review. Production grading stays on `claude -p` (subscription); the `--backend api` no-key trick is only a
  zero-spend replay/fail-on-miss guard.
