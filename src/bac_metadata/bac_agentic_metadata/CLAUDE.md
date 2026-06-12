# CLAUDE.md — bac_agentic_metadata

The **reusable, species-agnostic agentic metadata-curation engine** inside `bac_metadata`.
The engine is the product; *Klebsiella* and *M. abscessus* are **application sites** of it.
Parent guidance: [`../CLAUDE.md`](../CLAUDE.md) (bac_metadata),
[`../../../CLAUDE.md`](../../../CLAUDE.md) (monorepo), `~/.claude/CLAUDE.md` (global).

> **Read first**, in order:
> 1. [`STAGE0_kleb_curation_map.md`](STAGE0_kleb_curation_map.md) — how the manual
>    Klebsiella curation worked (the thing we generalise).
> 2. [`PIPELINE_PLAN.md`](PIPELINE_PLAN.md) — the engine architecture, attribute-spec
>    model, ground-truth rule, iteration discipline, and staged build.
> **Before building any grading step, ask David for the grading definitions — do not
> invent grading criteria.** The `attributes.yaml` files are name/value scaffolds with
> definitions marked TBD.

## Layout

```
bac_agentic_metadata/
  engine/                 # application-agnostic engine (built from Stage 1 on; empty now)
  applications/
    klebsiella/           # attributes.yaml, frozen ground truth, split, make_kleb_splits.py
      data/               # frozen study-sheet snapshot + kleb_project_splits.tsv
    m_abs/                # attributes.yaml, ATB_metadata_Mabs_2025_release.xlsx, CLAUDE.md
  STAGE0_kleb_curation_map.md
  PIPELINE_PLAN.md
```

## Core ideas (one line each)

- **Unit of work = project accession** (`study_accession`); process biggest-first.
- **Attribute spec is the rubric**, one `attributes.yaml` per application, three classes:
  study filters, study-level judgements (read from the paper), per-sample completeness/backfill.
- **Hybrid ground truth**: generalised spec + a *frozen* Klebsiella instance. Validate only
  against `study_level` cols A–K + the `parsed_per_project` tab; never `*_added`/`ATB_*_prop`.
- **Iteration discipline**: tune on train+val; the test fold stays sealed.

## Re-running the split

```bash
uv run python src/bac_metadata/bac_agentic_metadata/applications/klebsiella/make_kleb_splits.py
```

Seeded and reproducible; built from the committed frozen CSV snapshot (not the live sheet).

## Environment

Shared monorepo uv env (`uv run …`). Heavy ENA/EBI lookups and any model fan-out belong in
SLURM, not the login node (see global CLAUDE.md). Prefer structured JSON/YAML for every
grading step; keep the rubric in the single-source-of-truth `attributes.yaml`.
