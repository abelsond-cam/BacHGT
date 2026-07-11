# PROGRESS REPORT — bac_agentic_metadata

*Agentic metadata curation for the* Klebsiella pneumoniae *species complex (KPSC): the aim, the engine
design, the human-in-the-loop steps, the Klebsiella application (its pathway, its benchmark vs. manual
curation, and the accumulated whole-set result), and the forward plan. Written to be shareable with
collaborators.*

> *Maintainer note: this is a **state-and-plan** document, not a changelog (`git log` is the changelog).
> Keep it lean — describe the current state and the plan; do not accumulate per-commit "update" entries.
> Engine/runtime specifics (how to run, backends, the byte-for-byte reference gate, editing gotchas) live in
> [`CLAUDE.md`](CLAUDE.md); the rubric itself lives in `applications/klebsiella/attributes.yaml`.*

---

## 1. The aim

We hold ~90,000 KPSC genomes (96,291 samples in the working base table; 90,117 match the *Klebsiella*
taxon). Their metadata, as deposited in the ENA, is patchy: the four clinical fields we most need —
**country, collection date, isolation source, host** — are frequently blank, and the study-level context
that matters most (was this a hospital or community study? were isolates chosen *because* they were
resistant?) is never in the structured data at all.

Over several years we have **manually curated ~75% of this dataset by hand** — collecting each study's
paper, reading it, and filling the clinical fields study by study. That manual curation (captured as the
gold-standard table `metadata_v2`) is both the **model for the engine and its benchmark**: the agent is built
to *replicate what the manual curators did*, is *scored against their results* field by field, and — because
the manual sheet is itself imperfect — every agent-vs-curator disagreement is put to a **final adjudicator**
to decide who is actually right (an independent, stronger model rules each case on the evidence, with the
human curator as the final arbiter). Filling the remaining cohort by hand does not scale — hence the engine.
The benchmark is reported in **§4b**.

**The engine reproduces — and improves on — that manual curation.** For each study it finds the describing
paper, reads it, and:

- **fills the four per-sample clinical fields** where ENA left them blank, in **two steps**: **(i)**
  per-isolate values read from a metadata table in the study's paper, wherever one exists; and **(ii)** where
  no such table exists, a single **whole-study** value applied to all of that study's samples.
- **grades the study-level attributes** that never appear in structured data (care setting, AMR-selection
  design).

**Why it matters.** The downstream research questions all depend on these fields: an invasiveness phenotype
(isolation source / host), deep lineage dating (collection date — especially pre-2010 isolates), plasmid
pathoadaptation, and geography (country). Better, more complete metadata is the prerequisite for all of them.

The engine is **species-agnostic** — *Klebsiella* is the first application site; *M. abscessus* is the next.

---

## 2. The engine design

- **Unit of work = the project accession** (`study_accession`), processed **biggest-first** — the largest
  studies fix the most cells per paper read.
- **The rubric is a spec file** — `attributes.yaml`, one per application (the single source of truth;
  detailed in §4a). It declares three kinds of attribute: **study filters** (exclude a study from the
  cohort), **study-level judgements** (one value for the whole study, read from the paper), and the **four
  per-sample fields** to backfill.
- **What "grading" is.** The agent reads the describing paper (full text where accessible) and, for each
  study-level attribute, assigns a single value plus a **confidence grade** — `gradeable` (a single value is
  supported for the whole study), `partial` (applies to only part of the study and cannot be attributed to
  specific samples), or `not_gradeable` (cannot be determined). Grading is **grounded** (the agent must
  support its answer from the paper), **abstains** when the evidence is insufficient, and every disagreement
  with the manual sheet is ruled by an **independent, stronger adjudicator model**.
- **Deterministic vs. judgement.** Sizing, grouping, and completeness measurement are deterministic; paper-
  finding, grading, and field backfill are agent judgement (grounded, abstaining, adjudicated).
- **How it runs.** A single in-process driver runs every stage. The agent is Claude — Sonnet as the curator,
  Opus as the independent adjudicator — driven either on a Claude subscription (default; no API cost) or the
  paid API. All model calls are cached, so reruns are fast, free, and reproducible.

---

## 3. The human-in-the-loop steps

Two points in the pipeline require a human. **A run is not "done" until both are complete** — every run ends
with a loud sign-off banner stating the status of each, so a partially-curated run can never be mistaken for
a finished one.

**a. Finding papers — manual download of paywalled text.** The finder retrieves candidate papers and the
agent picks the one covering the largest part of the study. Where the full text is paywalled, the agent can
work only from the abstract. The engine emits a **missing-papers worklist**; the curator downloads the PDF,
drops it in `manual_download/<accession>.pdf`, and the next run reads it automatically.

**b. Escalating high-leverage / uncertain decisions.** Some whole-study field values are too consequential,
or too uncertain, to fill automatically. Two triggers send a decision to the curator:

- **Big decisions** — any study that is **≥1% of the whole cohort's *Klebsiella* samples**. Its value would
  touch thousands of isolates, so a human confirms it regardless of the agent's confidence.
- **Tight near-misses** — borderline whole-field calls that the triage flags for review.

The curator answers each in an **interactive terminal queue** (accept a value, or skip). These answers are
precious: they are versioned, **accumulate across runs, and are never re-asked**.

**Why escalation rather than a silent whole-fill.** In one large study (SpARK, ~17% of the test fold) the
isolates are ~85% Italy but ~13% Ghana — a blanket "Italy for all" would have mislabelled ~568 isolates. The
honest resolution is to put the decision to the curator, not to guess; the pipeline is built so a large
silent mis-fill of this kind cannot slip through unflagged.

---

## 4. The Klebsiella application

### 4a. The Klebsiella pathway

**The pipeline (per accession, biggest-first).** find the paper → grade the paper → **fill per-sample fields
FIRST** → guarded whole-field fill → escalate → apply curator answers → score. Per-sample runs *before*
whole-field so that an accurate per-isolate table is never pre-empted by a coarse study-wide value;
whole-field then fills only the cells per-sample left blank, and never overwrites a per-isolate value or fills
a field that a study has proved to be heterogeneous.

**Finding papers.** A three-tier finder — deterministic retrieval → secondary-accession lookup → web-search
fallback — proposes candidates; the agent only *picks* among what was retrieved (grounded; it abstains rather
than guess). Matching is by paper **identity**, not URL. Performance on train/val: raw 0.70 → **adjudicated
0.87**, with ~0.94 precision when it commits; abstentions fell 24 → 7 once the web-search tier was added. A
recurring, useful by-product: ~20% of the manually-curated paper links are wrong/misattributed — the engine
surfaces these rather than trusting them.

**Filling the four per-sample fields — two steps, in order:**

- **(i) Per-sample table** — per-isolate values pulled from a metadata table in the study's paper (xlsx / csv
  / DOCX / PDF supplementary), keyed back to our sample accessions. This is the accurate, high-granularity
  source and is **always tried first**.
- **(ii) Whole-study value** — where the paper has **no usable per-isolate table**, a single value is applied
  to *all* of the study's samples for each attribute. Allowed only when the chosen paper covers **>75%** of
  the study's *Klebsiella* records (or the ENA title/description covers the whole study).

Where a value is filled, it is correct: per-sample `collection_date` 0.999 (year-level), `isolation_source`
0.957 (carriage-vs-invasive granularity preserved), `country` 0.999, `host` 1.0; whole-study fills are
~0.99–1.0 where that is the right model. **Raw values only** — the deterministic parse/categorise step stays
downstream. (*Pathogenwatch was investigated as an extra per-sample source and dropped — its collections hold
only genomics/typing, no country/date/source metadata.*)

**Grading the study-wide attributes.** The two curated study-level attributes — **`study_setting`** (hospital
/ community / mixed) and **`amr_study`** (amr / mixed / surveillance) — are graded from the paper and
broadcast to every sample in the study when `gradeable` (left blank when `not_gradeable`).

**How grading works, and the rules in `attributes.yaml`.** The grader builds its prompt **straight from
`attributes.yaml`**: the allowed values are the YAML value sets and the instructions are each attribute's
`definition`, so changing the rubric is a YAML edit, not a code change. The rules currently in force:

- **Sizing first.** Before grading, establish the true size of the accession from ENA and reconcile it
  against the article; grade on the *deposited* set, not the parent screened cohort. (A screened cohort of
  thousands that deposits only its resistant subset is sized — and graded — by the deposit.)
- **Whole-project applicability.** A single study-wide value may be applied to all samples only when the
  chosen paper covers **>75%** of the study's *Klebsiella* records, or the ENA title/description itself
  covers the whole study; otherwise the attribute is `partial` (left unattributed).
- **`study_setting`** — *hospital* = human inpatient care (blood / respiratory / deep specimens, "patients"
  by default, hospital wastewater); *community* = human sampled outside hospital (clinics, carriage surveys,
  primary/long-term care) **or** a non-human host; *mixed* = the study deliberately samples both settings.
- **`amr_study`** — the *sampling rule* that decided which isolates were sequenced: *amr* = every isolate had
  to be resistant (a non-susceptible AST result or a resistance-gene hit, including AMR-selective screening);
  *surveillance* = a non-AMR sampling frame (all positive blood cultures, all carriers, all clinical isolates
  of the taxon); *mixed* = both (e.g. resistant cases plus susceptible matched controls). A study merely
  *titled* "AMR" is not `amr` — the per-isolate selection gate decides.
- **The four per-sample fields:**
  - **country** — one study country → all samples; the funding body, language, journal, and author
    affiliation do **not** establish the collection country.
  - **isolation_source** — the specimen / site, **specific** ("rectal swab", not "swab"); "lab" / "in vitro"
    / a culture-medium name is not a source → leave **blank**.
  - **host** — the organism or environment (human for clinical patient studies, unless environmental or a
    non-human host); "lab" / "in vitro" is not a host → leave **blank**.
  - **collection_date** — a **≤2-year** span → fill the **midpoint** (automatic); a **2–5-year** span →
    escalate to the curator **only if its midpoint is before ~2010** (old genomes are scarce and valuable for
    lineage dating), otherwise leave blank; a span **wider than 5 years** → leave blank.

    *(The ≤2-year auto-fill is applied at grading; the 2–5-year escalation trigger is already active in the
    engine. The `attributes.yaml` wording is being brought into line so the full rule also governs the
    remaining uncurated cohort — see §5. The already-curated folds and tail follow this rule and are not
    re-graded.)*

### 4b. Benchmarking of results vs. manual curation

The benchmark set is the **manually-curated studies**, split at paper-group level into **train/val** (used
for tuning) and a **sealed test fold** (held back for one final measurement). Two things are measured: how
much of each field we complete, and how accurate our study-level grading is.

**Completeness** — fraction of samples carrying a real value — agent vs. the manual gold (`metadata_v2`),
with the ENA baseline for context. The agent is **≥ manual on all four fields in both folds**, and the
*residual gap* (what manual still has that we do not) is **0.00**:

*Test fold (sealed; 31,604 samples)*

| field | ENA baseline | **agent** | manual (v2) |
|---|---|---|---|
| country | 0.67 | **0.96** | 0.85 |
| collection_date | 0.64 | **0.94** | 0.76 |
| isolation_source | 0.60 | **0.74** | 0.70 |
| host | 0.53 | **0.84** | 0.77 |

*Train + val (34,288 samples)*

| field | ENA baseline | **agent** | manual (v2) |
|---|---|---|---|
| country | 0.62 | **0.92** | 0.88 |
| collection_date | 0.55 | **0.87** | 0.75 |
| isolation_source | 0.45 | **0.71** | 0.67 |
| host | 0.44 | **0.89** | 0.79 |

The gains come from different sources per field — e.g. country is lifted mostly by curator escalation, date
by per-sample tables plus escalation, host mostly by whole-study fill (nearly all hosts are human) — but in
every case the agent closes the entire ENA→manual gap and then exceeds it.

**Grading quality** — agent vs. manual. Every disagreement is adjudicated by an independent, stronger model
(Opus) on verbatim quotes from the paper, with the curator's own verified corrections taking precedence — the
final manual arbiter:

| fold | N judged | agreement | **agent acc** | manual acc | Δ |
|---|---|---|---|---|---|
| train + val | 274 | 0.82 | **0.97** | 0.86 | **+0.11** |
| test (sealed) | 117 | 0.86 | **0.97** | 0.91 | **+0.06** |

By attribute on test: `amr_study` 0.97 vs 0.89, `study_setting` 1.00 vs 0.90, paper-finding 0.94 = 0.94.
Where agent and manual disagree, the agent is right far more often — it is correcting genuine errors in the
manual sheet, not merely matching it.

### 4c. Accumulated metadata for the whole set (incl. smaller, not-previously-curated studies)

Beyond the benchmarked ~75%, the engine now extends curation to the **whole set**. All three folds (train,
val, test) **plus every uncurated study larger than 100 samples** have been run, and their curation is
integrated into **one growing master table** — curation now **accumulates across batches** rather than being
recomputed and discarded each run (the smaller, <100-sample uncurated studies are the remaining work — §5):

- **master table** — 96,291 samples × 121 columns (the full base + the backfilled fields +
  `study_setting`/`amr_study`).
- **92,704 cells filled** (host 26,721 / collection_date 24,575 / country 23,230 / isolation_source 18,178)
  across **206 graded studies**.
- **55 curator decisions** resolved so far (31 answered, 24 skipped-as-wide) — versioned and carried forward.
- a **canonical merge onto the manual gold** (`human > agent > ENA`): the agent fills only cells the human
  left blank (country 4,856 / date 9,121 / iso 7,218 / host 7,410); human curation is never overwritten
  (merged table 90,903 rows).

---

## 5. Forward plan

The benchmarked folds + the whole >100-sample tail are done and accumulated (§4b, §4c). Active work, in order:

1. **Collection-date rule for the downstream cohort.** Bring the `attributes.yaml` wording into line with the
   hardened `collection_date` rule (§4a) so it governs the remaining uncurated studies. Small but *gating* —
   editing the rubric re-grades everything, so it is applied **before** the at-scale runs below, so they grade
   under the hardened rule once. The already-curated folds and >100-sample tail are **left as they are** —
   their dates already follow this rule (it is the one the manual curator applied), and the difference is far
   too small to justify re-running them.
2. **M. abscessus — first exploratory pass.** The second application, now running (biggest studies first) to
   **iron out / refine the `applications/m_abs/attributes.yaml` definitions** (CF status, smoking, the AST
   panel) before scaling to all ~133. Engine work done: the per-sample extractor is now **spec-driven** over
   the fields (was hardcoded to the four *Klebsiella* fields), with an AST **compact-list sub-schema**
   (`ast_columns: [{drug, mic_column, resistance_column}]` → verbatim `ast_<drug>_*` long-format fills;
   off-panel → `ast_other`) that keeps the ~40-drug panel from ballooning into fixed columns; `run_m_abs.sh`
   + an `export_base_table.py` (xlsx → full-width base) added; all **Klebsiella byte-identical** (gate green).

   > **⚠️ CRITICAL FIRST STEP FOR ANY NEW SPECIES — per-sample identifier (anchor) columns.** The extractor
   > is anchor-**agnostic**: it builds an id→`sample_accession` map from a declared set of base columns and
   > finds whichever supplementary-table column matches **by value** (never by column name). That column set
   > is now **spec-driven** (`per_sample_completeness.sample_identifier_columns` in `attributes.yaml`;
   > *Klebsiella* declares none → the engine's built-in default). **If the set is too thin, per-isolate
   > extraction silently yields NOTHING** — the M.abs first pass produced **0 fills** until we reviewed *all*
   > input columns and added strain / isolate / sequencing-lane IDs alongside the accessions/aliases. So the
   > first onboarding step for a new species is: **review every column of the input table and declare ALL
   > per-sample identifiers a paper might key a table on** (deposited accessions, ENA aliases, strain/isolate
   > names, lane IDs). **Exclude per-patient / per-study identifiers** (e.g. a `Patient` column) — they
   > collide across samples. Verified on M.abs PRJDB10566: with strain added, its per-isolate table
   > (`Isolate | Country | Diagnosed Year | Disease status | Isolated from`) anchors 217/217 rows.

   *cf_status backfill uses a 95% majority rule* (fill all blanks with the majority category when ≥95% of the
   known set is one way — tolerates mislabelling <5% for much more complete cf_status for phenotyping/GWAS;
   never overwrites a sample's own known value). *AST design: keep the wide canonical drug panel and prove
   per-isolate extraction works on an AST-reporting study before thinning — the panel width is near-free.*
3. **Klebsiella — a publishable per-study-accession table.** One consolidated row per study accession for
   release: paper link · number of *Klebsiella* samples · total study size · the study-wide grades
   (`amr_study`, `study_setting`, `experimental_study`) · and the **pre- and post-fill completeness** of each
   per-sample field. The publication-facing summary of what the engine achieved per study.
4. **Klebsiella — collaborator plots.** Figures for this report showing the **raw → manual-curated →
   agent-curated** stepwise improvement in both **completeness** and **accuracy**, to send to collaborators.
5. **The rest of the cohort at scale.** Run the smaller uncurated studies, accumulating onto the master,
   biggest-first — the **[50, 99] band (95 studies / ~6.8k samples) runs overnight** (small, relatively), then
   the <50-sample studies; the curator answers the (now much smaller) escalation queues.
6. **Downstream** — run the deterministic parse/categorise step over the master, then regenerate the
   completeness plots.

*Loose ends:* accept the one aggregate-only study (no per-isolate table) as complete → ALL CLEAR; build the
"unlinkable-table" classifier that separates a genuinely aggregate supplement (auto-discard) from a
per-isolate table we simply failed to link (a real linkage target).

## 6. Agentic categorisation sub-engine (replaces hardcoded parse/categorise) + current workstream

**Why.** Running the M.abs master through the Klebsiella `pp/metadata_curation.py` (~860 hardcoded parse/
categorise rules) exposed two problems on the two messy fields (`host`, `isolation_source`): (a) field-
specific placeholder junk (`0`, `unclear`, `others`, `laboratory` variants) survives into the base table
and *blocks* the fill agent (it looks like a real value); (b) real signal is discarded (strain codes leaked
into `host` encode disease/cf_status; uncategorised iso values like `volcanic ash` carry info, some implying
*another* column). Replaced the hardcoded rules with a **data-driven agentic categoriser** — one scheme per
species, induced + human-approved, not 860 hand rules.

**Built — `engine/categorise/`** (+ `engine/cli/categorise.py` `induce`|`apply`; `spec.py` parses
`attributes.categorisation`; `llm.make_llm(timeout=…)`):
- `preclean.py` — in-memory wipe of per-field `null_tokens` (whole-cell) + `null_patterns` (regex, incl.
  `\blaborator`/`\blab\b`/`\bin[ -]?vitro\b`) **before** the fill stages so the agent gets an honest blank.
  Verified byte-for-byte safe on the Klebsiella train,val gate (per_sample/grades/backfill unchanged; junk →
  honest blanks). Wired into `run_full_metadata_agent.py` right after base selection.
- `value_frequencies.py` — distinct informative values + counts (shared null handling).
- `induce_categories.py` — **two-stage** induction (names → per-category detail) so large fields don't time
  out; each category gets detailed `includes`/`excludes` boundary rules + examples; seeded (non-binding) by
  the existing scheme; emits `cross_field_notes` (leakage detection). Writes `*_categories_proposed.yaml`.
- `apply_categories.py` — maps each **distinct** value → `{parsed, category, na_reason}` (batched, cached,
  temperature=0 → deterministic) and joins back; emits a full **reassignment audit** (every value → category,
  NA reason, poor-fit flags — nothing silently dropped).

**Approval mechanism.** David reviews `*_categories_proposed.yaml`; the approved scheme is saved as
`study_lv_attributes/categorisation/<field>_categories_approved.yaml` (verbose scheme kept in its own file so
`attributes.yaml` stays hand-editable). `categorise apply` loads it (yaml inline `categories` win if present).
`attributes.yaml categorisation.fields.<field>` holds only `null_tokens`/`null_patterns`/`cross_column`.

**Decisions (David).** Keep the agent's split of **`sterile_body_fluid`** (bile/CSF/pleural/peritoneal/joint)
vs **`wound_abscess_tissue`** (solid tissue/organ abscess incl. liver) — he explicitly likes not collapsing
sterile fluids onto the tissue axis. `laboratory` → NA pre-grading (tautology). Cross-column fills = hybrid
(auto-fill blank target, escalate overrides) — **deferred** to a second pass. Induction = from-scratch, seeded.

**State (2026-07-07).**
- Klebsiella schemes **induced + approved**: host 15 cats, isolation_source 12 cats (with includes/excludes +
  cross-field notes). Saved as `*_categories_approved.yaml`.
- **M.abs categorisation DONE** (first new-species proof): host 3 cats (human/wild/NA; strain codes → human,
  their cf_status signal left for Phase D), isolation_source **15 cats** (respiratory split sputum/bronch/
  unspecified/lung_tissue; disseminated skin/bone_joint/lymph_node/blood/pleural_body_fluid/eye_ear/GI-urinary;
  water_environment incl. volcanic ash; clinical_device; **extrapulmonary_unspecified** — David's add; NA).
  **100% of iso values placed** — 5,221/5,542 (94.2%) into a real category, 321 (5.8%) → NA with reasons; vs
  the hardcoded Klebsiella rules that stranded 579 in 30 ad-hoc "Other" + 1,232 not-filled. Output:
  `applications/m_abs/data/study_lv_attributes/categorisation/{categorised_mabs.tsv,*_reassignment_audit.tsv}`.

**Remaining plan** (full detail: `~/.claude/plans/hidden-wiggling-stream.md`):
- **Klebsiella size-≥10 tail** (436 studies / 14,592 samples not yet done — `[50,99]` 87/6.2k · `[25,49]`
  142/5.1k · `[10,24]` 207/3.3k; `<10` = 1,106 studies/2.5k excluded). Run three **carry-forward** bands
  overnight (subscription): `run_klebsiella.sh --min-study-size {50/25/10} --max-study-size {99/49/24}
  --tag tail{50_99/25_49/10_24} --web-fallback --carry-forward`. Answer escalations (incl. 3 pending tail100).
- **Accumulate** all tags (`accumulate --tags train,test,tail100,tail50_99,tail25_49,tail10_24 --canonical
  <gold>`) → run `validate_backfill_completeness.py` for the **final whole-cohort completeness number**
  (raw ENA → agent → metadata_v2 gold). Prior per-fold: test host .53→.84, country .67→.96, date .64→.94,
  iso .60→.74.
- **Apply** approved schemes over the final Klebsiella master (~1,900 iso distinct → ~32 cached batches);
  **build `evaluation/validate_categories.py`** to benchmark agent `host_category`/`isolation_source_category`
  vs metadata_v2 gold category columns (bulk agreement, uncategorised-tail reduction, adjudicated diffs).
- **Deferred Phase D — `reconcile_cross_column.py`** (hybrid): M.abs host codes `CF*`/`COPD*`/`NCF` →
  `cf_status`; env iso (`volcanic ash`, taps) → `host=environment`; normalise `Non-CF`→`non-CF`.

## 7. Silent-failure hardening (2026-07-10/11) — the curator-loop no longer drops work

Re-gating the folds to prove the curator-table pipeline surfaced a chain of **silent failures** — steps that
skipped without any error, so a curator's paper/table/decision was quietly lost. All are now fixed + committed;
the **deterministic** logic of each is locked by `tests/test_agentic_metadata_fixes.py` (7 tests, no LLM — run
`uv run --group test pytest tests/test_agentic_metadata_fixes.py` after any refactor / compaction to re-verify).

**The fixes (commits):**
- **`7b39c42`** — per_sample honours `--paper-source curated`: a study whose PMCID the finder missed but the
  curated snapshot names is resolved via `europepmc.pmcid_for_link` (DOI/PMID/URL→PMCID), not written off
  `NO_PMCID`. A curator table is always *opened* even when ENA looks complete.
- **`b1d9a88`** — escalation candidacy is **deterministic** (declined-and-still-<75%-after-per-sample), not a
  volatile LLM-triage veto + cohort-size-dependent big-decision line that dropped studies between runs; the
  version-controlled `curated_escalations.tsv` is **always** consulted and answers are **sticky** — re-applied
  to any still-gated study even when it no longer freshly detects (fixed a ~3.7k-cell drop).
- **`b8bc8cf`** — "limbo" fields (grader proposed a value but set `applies_whole_project=false`) were filled by
  neither whole-field backfill nor escalation → now escalated with the grader's value as the suggestion.
- **`a1ac874` + `5d2ec9e`** — grader whole-project fill accepts a **~95% predominant value** (and, with no exact
  % stated, a likely-vast-majority single description — e.g. 16 of 17 regions of the Philippines → country =
  Philippines).

**Curation-fidelity policy (David, 2026-07-11), all in `5d2ec9e`:**
- **(i)** `clinical` / `surveillance` are isolation_source **null tokens** (a sampling context, not a specimen)
  — blanked pre-fill so the table supplies the real specimen (carriage-vs-invasive).
- **(ii)** **ENA-complete-field overwrite guard** (per FIELD, every study): per_sample fills any blank freely
  but overwrites a non-blank ENA cell only when the field is itself gated *or* `judge_overwrite_fidelity` rules
  the table a substantial improvement — so a good ENA value is never degraded by a lateral/coded table value,
  while a specific specimen still supersedes a vague one. **Completeness-neutral** (only changes the value in
  already-filled cells). The judge also catches vague values a token list would miss (`clinical material`).
- **Latent bug fixed:** the extractor hardcoded `ena_value=""` on every fill, so the guard had been a **no-op**
  (every fill looked blank → the table overwrote ENA freely). per_sample now backfills the true base value onto
  each fill before the guard runs.

**Canonical edge cases (the regression targets):**
- **PRJEB29738** (Philippines, 862 samples): host auto-fills whole-project (97.7% inpatients → human);
  country auto-fills via the vast-majority rule; a field the grader still declines is escalated, not dropped.
- **PRJNA633565** (USA, 176): isolation_source `clinical`/`Surveillance` blanked → table refills specific
  specimens (blood / urine / perirectal surveillance swab); country/date **keep ENA** over the table's coded
  `Maryland Hospital A` values (guard).
- **PRJNA922900 / PRJEB57159** (norwegian_poultry): PMCID recovered from the curated DOI, not `NO_PMCID`.

**Still to harden (in progress):** `evaluation/regression_edge_cases.py` (asserts the above against committed
test-fold outputs); a pipeline-wide **no-silent-fail coverage audit** (every selected study has an outcome row;
every declined-and-incomplete field escalates; every missing paper is on the worklist; every table is
linked-or-flagged); and archiving the test/val/train caches+grades+queues+papers so reruns stay cheap and
deterministic. Then re-grade+accumulate train under the new rules and re-freeze `engine/reference_outputs/`.
