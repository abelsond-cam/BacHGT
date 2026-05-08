# HPC Storage Overview

Canonical map of the four storage locations used across the user's HPC workspaces, plus the shorthand vocabulary referenced from `CLAUDE.md` and other docs. Whenever a script in this repo hard-codes `/home/dca36/rds/...` or `/home/dca36/rcs/...`, it resolves to one of the four roots below — read those literal paths in light of this map.

There is no Python config file pretending to be the source of truth; it's this doc.

## Storage roots

| Shorthand     | Path                                       | Size  | Purpose                                                                                       |
|---------------|--------------------------------------------|-------|-----------------------------------------------------------------------------------------------|
| `project_k`   | `~/rds/rds-floto-bacterial-4k08a2yyQLw/`   | 20 TB | Shared team space (Floto lab). Contains per-team-member subfolders (`david/`, `seb/`, …).     |
| `personal_rds`| `~/rds/hpc-work/`                          | 1 TB  | Personal scratch space.                                                                       |
| `bacformer_rds`| `~/rds/rds-flotolab-9X9gY1OFt4M/`         | 13 TB | Bacformer project mount (Flotolab); used by `predict_kleb_by_bacformer`.                      |
| `cold_storage`| `~/rcs/rcs-vgm23-lcms/David/`              | —     | RCS cold storage. Backups + final published outputs.                                          |

`project_k` is the working data home for everything in this repo. `cold_storage` mirrors selected subtrees of `project_k` plus root-directory backups (see "Backup mechanism" below).

## Vocabulary

Canonical names used in conversation and across the docs. Each is just a path under one of the four roots above.

- `project_k/david` → `~/rds/rds-floto-bacterial-4k08a2yyQLw/david/` — our (David's) working directory; primary location for everything Bacotype touches.
- `project_k/seb` → `~/rds/rds-floto-bacterial-4k08a2yyQLw/seb/` — Seb's directory; contains assemblies + ISEscan outputs Bacotype consumes.
- `project_k/david/{final, processed, raw}` — the three top-level subfolders we use within David's tree.
- `cold_storage/bacterial-klebsiella/david/{final, processed, raw}` — cold-storage mirror of the same tree.
- `cold_storage/workspace` — backups of `~/workspace/` directories (i.e. the sibling project repos under `~/workspace/`).

Short forms like "project_k/david/processed/panaroo_with_reference_genome" used in chat / commit messages refer to these literal paths via the shorthand.

## Project K layout (`project_k/`)

Top-level subfolders inside `~/rds/rds-floto-bacterial-4k08a2yyQLw/`:

- `david/` — our team member subfolder (us). All Bacotype outputs live here.
- `seb/` — Sebastian's subfolder. Contains assemblies + results from ISEscan and other tools we read from.
- *(other team members)* — additional per-person folders exist alongside; not consumed by this repo.

Inside `project_k/david/`:

- `final/` — curated metadata and reference bucket TSVs (e.g. `metadata_final_curated_slimmed.tsv`, `reference_bucket.tsv`). Stable inputs to downstream analyses.
- `processed/` — pipeline outputs: Panaroo runs (`panaroo_with_reference_genome/`, see [`panaroo_run_inventory.md`](panaroo_run_inventory.md)), pangenome analysis, ESM/Bacformer embeddings, AnnData objects, MGEFinder outputs.
- `raw/` — assemblies, GFFs, gbff (Bakta annotation outputs), fastq.

## Cold storage layout (`cold_storage/`)

Inside `~/rcs/rcs-vgm23-lcms/David/`:

- `bacterial-klebsiella/david/{final, processed, raw}` — mirror of `project_k/david/`. Synced by the rsync script described below.
- `workspace/` — backups of `~/workspace/` directories (snapshots of sibling project repos).
- *(other archived projects)* — additional folders for unrelated archived work.

## Backup mechanism

`~/storage_mgt/backup_rds_to_rcs.sh` is the rsync-based script that mirrors selected subtrees of `project_k/david` and `~/workspace/` into `cold_storage`. It is wired into `~/.bashrc` so it runs on every login, keeping cold storage warm without manual triggering. That script is the source of truth for *what* gets mirrored where; this doc only summarises.

## Lazy-loaded deep dives

When a question needs more detail than this overview covers, read one of:

- [`panaroo_run_inventory.md`](panaroo_run_inventory.md) — full Panaroo run-by-run inventory under `project_k/david/processed/panaroo_with_reference_genome/`. Already exists.
- *(placeholders, written when concrete questions surface)*
  - `project_k_david_layout.md` — granular listing of every subfolder under `project_k/david/{final, processed, raw}`.
  - `cold_storage_layout.md` — granular listing of every cold-storage tree.
  - `seb_data_layout.md` — what's in `project_k/seb/` (assemblies, ISEscan results, ...).
