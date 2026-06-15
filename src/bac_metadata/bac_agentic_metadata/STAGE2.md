# Stage 2 — Paper lookup & structured grading (LLM)

The first **LLM** layer of the engine. Stage 1 gave each project accession a deterministic
context row (sizing + completeness); Stage 2 reads the **paper** and grades the accession into the
`attributes.yaml` schema. Built in two parts:

- **2A — grading** (done): grade the *known* curated paper for each accession → earliest
  measurable agreement against the gold standard. This is what the modules below implement.
- **2B — paper-finding** (next): find the best paper *independently* (Europe PMC accession
  text-mining) and compare to the curated `paper_link`.

Validated on **train+val only**; the test fold stays sealed (`kleb_project_splits.tsv`:
78 train / 31 val / 47 test).

## Backend & secrets

Two interchangeable backends sit behind the thin `engine.llm.LLMClient` protocol, selected with
`--backend` (or env `BAC_LLM_BACKEND`); the grader/runner code is identical for both. The disk
cache key is **backend-independent** (hash of model + system + user + schema), so a result graded
once on either backend is reused verbatim by the other — reruns are deterministic, offline and free.

- **`subscription` (default) — `ClaudeCliClient`.** Drives the installed `claude -p` CLI in
  headless single-turn mode on David's **Claude Max** plan → **zero API spend**. No forced
  tool-use on the CLI, so the JSON schema is embedded in the prompt and the reply is parsed +
  **validated against the schema** (`engine.llm.schema_errors`) with one retry. One-time setup is
  just the interactive `claude` login (already done); for a headless/HPC run, mint a token with
  `claude setup-token` and export `CLAUDE_CODE_OAUTH_TOKEN`. When the Max usage window (rolling
  5-hour / weekly) is exhausted, the runner catches `UsageLimitError`, writes the partial results,
  and prints a resume hint — rerun the same command and the cache fills the rest.
- **`api` (opt-in) — `AnthropicClient`.** Paid Messages API with **forced tool use** (the tool's
  `input_schema` *is* our JSON schema, `tool_choice` pins it) → server-validated structured JSON.
  Use when you have credit and want the strongest structured-output guarantee, or in CI without a
  subscription login. Key (off-OneDrive, outside the repo, like the Google secret):

  ```bash
  umask 077; printf '%s' 'sk-ant-…' > ~/.config/bac_metadata/anthropic_api_key
  ```

  Resolution order: `ANTHROPIC_API_KEY` env → `BAC_ANTHROPIC_KEY_FILE` → the file above
  (`engine.llm.resolve_api_key`). The key never enters the repo (gitignored) or the chat.

Both default to Sonnet (`claude-sonnet-4-6`); escalate per-call to Opus where agreement needs it.
`temperature=0` on the API backend; the CLI exposes no temperature, so the **disk cache** is the
reproducibility mechanism (which it is anyway).

## Modules

### `engine/` (application-agnostic)
- `http_utils.py` — one polite retry/backoff `GET` (generalised from `ena_sizing`), reused by
  `fulltext` / `ena_sizing`.
- `llm.py` — `LLMClient` protocol + `AnthropicClient` (forced tool use, disk cache, key resolver).
- `fulltext.py` — `fetch_fulltext(ref)` resolves a curated URL/PMID/PMCID/DOI to text in strict
  preference order: **Europe PMC OA full text** (`{PMCID}/fullTextXML`, flattened with stdlib
  `xml.etree`, ref-list dropped) → **PDF** (direct/OA link/medRxiv-bioRxiv `.full.pdf`, via
  `pdfplumber`) → **abstract** → else `needs_manual_download`. Raw responses cached on disk.
- `ena_sizing.py` — added `study_title_and_description()` (`result=study`): the EBI
  title/description is the second evidence source (often states a whole-project value directly).
- `grader.py` — the core. Renders the rubric **straight from `attributes.yaml`**: both the
  forced-tool JSON schema (enums = the YAML value sets) and the prompt (each attribute's
  `definition` + the shared `grading_basis`). Per accession returns, from the paper text + EBI
  title/description + Stage-1 sizing only: `study_type` (filter; `exclude_if` → excluded flag);
  each study-level attribute `{value, grade, evidence_quote}`; `paper_coverage_for_taxon`
  (model gives the paper's taxon-sample count → engine divides by Stage-1 `ena_taxon_samples`);
  method-(a) whole-project backfill proposals for the four standard fields; `needs_manual_download`.
  Output → JSONL (full, with evidence quotes) + flat TSV (one row/accession).

### `applications/klebsiella/`
- `run_study_grading.py` — 2A runner. Maps each accession to its curated `paper_link` (frozen
  snapshot), fetches text, grades, biggest-first over `--fold train,val`. Flags: `--fold`,
  `--accessions`, `--limit`, `--model`, `--cache-dir`, `--output-prefix`, `--max-chars`.
- `validate_study_grading.py` — agreement vs trusted ground truth (train+val), recording
  disagreements rather than assuming the sheet is right.

## Ground-truth mapping (what we score, and what we don't)

| attribute | ground truth | how |
|---|---|---|
| `amr_study` | frozen `sample_selection` | normalised → {amr, surveillance, mixed} (`AMR plus control`→mixed; `Surveilance`/`lifestock surveillance`→surveillance) |
| `cohort_age` | frozen `newborn_cohort` (free text) | parsed → {newborn_young_child, adult, mixed}; "not provided"/unclear → skipped |
| `study_setting` | **live** `study_level` Google tab | opt-in `--study-setting-from-sheet` (absent from the frozen snapshot); skipped otherwise |
| `amr_target`, `amr_method` | none (wanted, not curated) | **spot-check list only**, no claimed accuracy |
| backfill (country/source/host/date) | Stage-1 completeness deltas + `parsed_per_project` | proposal counts + sanity, not scored here |

## How to run

```bash
unset VIRTUAL_ENV
# Dry-run on contrasting accessions (default backend = subscription, zero API spend):
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_study_grading.py \
    --accessions PRJEB39943,PRJDB5929,PRJNA845975 --output-prefix study_grades_dryrun
# Full train+val pass (biggest-first). Add --backend api to use the paid key instead:
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_study_grading.py --fold train,val
# Validate (add --study-setting-from-sheet to also score study_setting against the live tab):
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/validate_study_grading.py
```

Outputs in `applications/klebsiella/data/`: `study_grades.{jsonl,tsv}`,
`grading_validation_report.{tsv,md}`. The LLM + full-text caches
(`llm_cache/`, `fulltext_cache/`) and the API key are gitignored.

## Results (2A grading, train+val, Sonnet on the subscription backend)

Full train+val population = **109 accessions**. Raw agreement vs the (imperfect) frozen ground
truth, on the two primary checks (cohort_age is **not scored** — no reliable GT):

| primary check | raw accuracy | n | note |
|---|---|---|---|
| `amr_study` | **0.78** | 86 | vs frozen `sample_selection` |
| `study_setting` | **0.90** | 94 | vs frozen `study_setting_frozen.tsv` |

**Adjudication reframes this upward.** The Opus critique agent (`validate_study_grading
--adjudicate`) re-reads the paper for each disagreement and rules which label is right with a
verbatim quote. On the 25-accession iteration set, **8 of 10 disagreements were *sheet* errors**
(the grader was correct, the gold standard wrong), implying a *true* grader accuracy of **~0.96 on
both primary checks**, with only 2 genuine grader errors (a hard amr_study case the rubric tweak
did not flip, and a veterinary study_setting case). Full-population adjudication is the next step.

The `amr_study` definition in `attributes.yaml` was tightened from adjudicator-found rule gaps:
judge the isolates actually *deposited* (not the parent survey); a project named "AMR" ≠ AMR
selection; routine MDRO/infection-control screening → surveillance; deliberately-added susceptible
matched controls → mixed; selection on non-susceptible R *or* I counts.

Determinism: every grade is disk-cached (backend-independent key), so reruns are byte-identical and
free; a 300→600s subprocess timeout + per-accession skip keep one slow paper from killing a batch.

## Stage 2B — paper-finding (built)

`engine/europepmc.py` + `engine/ncbi.py` + `engine/paper_finder.py` find the describing paper from
the accession alone (`run_find_papers.py` / `validate_find_papers.py`). Finding is a **deterministic
retrieval problem** — the LLM only picks `chosen_index` among API-retrieved candidates, never an id —
then the pick is **grounded** (the accession must appear in the paper text) with abstain-over-guess.

**Matching the find to the curated `paper_link` is by paper IDENTITY, not by URL** (one paper has
many links). Three measures make "same paper, different link" a match rather than a false mismatch:

- **Union of all curated rows.** A study's curated entry unions *every* paper row the sheet lists for
  it (studies legitimately list several), so the find is scored against the whole set — not whichever
  row happens to be first. (This alone recovered PRJEB27256, whose correct `PMC8865009` match had been
  discarded in favour of an id-less OUP link.)
- **Europe PMC cross-id canonicalization.** Each curated id is expanded to its full `{pmid,pmcid,doi}`
  triple via a cached EPMC lookup, so a curated PubMed link matches a found DOI for the same article.
- **Always favour the published version.** `europepmc.published_version_of` promotes every preprint
  candidate (Europe PMC `source=PPR` or a `10.1101/` DOI) to its peer-reviewed article — via the
  authoritative bioRxiv/medRxiv `published` DOI, else a title-matched EPMC sibling — *before* the LLM
  sees the list, so the finder never picks a preprint when the publication exists.

Residual mismatches go to the **opposing adjudicator** (`adjudicate_find`, Opus), which returns
`same_paper` (the two links are the same work — incl. preprint↔published — so not a finding error) and
a `verdict` of which paper actually *describes* the project, with a verbatim quote. On the dry-run it
showed two "mismatches" were in fact the finder being right and the curated link wrong (a data-reuse
follow-up; an umbrella-program co-paper), lifting adjudicated find-accuracy to 6/8.

## Out of scope (later)
Stage 3 opposing evaluator (general); Stage 4 MCP; backfill **method (b)** per-sample table
extraction (the deferred `partial` path); the small-study tail + the ~7k *M. abscessus* run.
