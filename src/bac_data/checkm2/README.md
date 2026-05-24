# CheckM2 env for assembly cohorts

A dedicated `pixi` env for running [CheckM2](https://github.com/chklovski/CheckM2)
uniformly across an assembly cohort. The first caller is the **LRA cohort**
(2,571 LR-GCAs from `related_lr_all_gca.tsv` + 3,513 is_refseq RefSeq
genomes, ~6,200 assemblies total) — replaces NCBI's CheckM v1 with our own
uniform CheckM2 estimates and removes the apologetics for the 834 LR-GCAs
and 277 is_refseq rows NCBI didn't compute CheckM for.

This subpackage sits at `src/bac_data/checkm2/` (not under `lr_data/`)
because the env + Slurm wrapper are cohort-agnostic — any future cohort
adds a sibling `prep_<cohort>_inputs.py` next to `prep_checkm2_inputs.py`.

## One-time HPC setup

```bash
# 0. Make sure pixi is on PATH (>=0.68):
curl -fsSL https://pixi.sh/install.sh | bash    # skip if installed

# 1. Install the env (linux-64; runs only on HPC):
cd ~/workspace/BacHGT/src/bac_data/checkm2
pixi install

# 2. Make the DB dir on RDS (3 GB lives outside the env — once).
DB_DIR=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/CheckM2/Zenodo_db
mkdir -p "$DB_DIR"

# 3. Download CheckM2's Zenodo DB into it.
pixi run checkm2 database --download --path "$DB_DIR"
# → installs into $DB_DIR/CheckM2_database/uniref100.KO.1.dmnd
```

## Running on the LRA cohort

Two steps — first build the input manifest + symlinks (cheap, runs on login
node), then submit the Slurm job (heavy, runs on icelake-himem).

```bash
# Build symlinks at <RDS>/processed/checkm2_lra/links/<sample_id>.fna.gz
# and inputs.tsv with (sample_id, tier, source_path, link_path).
cd ~/workspace/BacHGT
uv run python -m bac_data.checkm2.prep_checkm2_inputs   # uses the shared uv env, NOT this pixi env

# Submit the array. Output → <RDS>/processed/checkm2_lra/quality_report.tsv
sbatch src/bac_data/checkm2/slurm_scripts/run_checkm2.sh
```

Re-runs are cheap: `checkm2 predict` is restartable on the same output dir, and
the prep script is idempotent on its symlinks.

## Why a separate env (not the shared uv env)?

CheckM2 is a bioconda-only stack (Python + diamond binary + a tensorflow-lite
classifier). Keeping it out of the BacHGT shared uv env avoids dragging its
heavy deps into every other subpackage's resolve. Same separation rationale
as `bac_ariba/pixi.toml`, but simpler — CheckM2 is actively maintained, so
no apptainer indirection needed.

## DB location

`/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/raw/CheckM2/Zenodo_db/`

3 GB, downloaded once. The Slurm script exports `CHECKM2DB` from this path so
every run picks it up automatically without per-user config.
