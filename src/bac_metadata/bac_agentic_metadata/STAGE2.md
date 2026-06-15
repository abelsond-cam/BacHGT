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
- `run_stage2_grade.py` — 2A runner. Maps each accession to its curated `paper_link` (frozen
  snapshot), fetches text, grades, biggest-first over `--fold train,val`. Flags: `--fold`,
  `--accessions`, `--limit`, `--model`, `--cache-dir`, `--output-prefix`, `--max-chars`.
- `validate_stage2_grade.py` — agreement vs trusted ground truth (train+val), recording
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
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_stage2_grade.py \
    --accessions PRJEB39943,PRJDB5929,PRJNA845975 --output-prefix stage2_grades_dryrun
# Full train+val pass (biggest-first). Add --backend api to use the paid key instead:
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/run_stage2_grade.py --fold train,val
# Validate (add --study-setting-from-sheet to also score study_setting against the live tab):
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/validate_stage2_grade.py
```

Outputs in `applications/klebsiella/data/`: `stage2_grades.{jsonl,tsv}`,
`stage2_validation_report.{tsv,md}`. The LLM + full-text caches
(`llm_cache/`, `fulltext_cache/`) and the API key are gitignored.

## Results

_To be filled after the train+val agreement run (per-attribute accuracy, confusion matrices,
recorded disagreements)._

## Out of scope (later)
Stage 2B paper-finding (`europepmc.py`, `paper_finder.py`); Stage 3 opposing evaluator; Stage 4
MCP; backfill **method (b)** per-sample table extraction (the deferred `partial` path); the
small-study tail + the ~7k *M. abscessus* run.
