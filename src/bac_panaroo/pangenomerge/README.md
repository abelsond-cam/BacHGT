# bac_panaroo/pangenomerge

Orchestration glue for [pangenomerge](https://github.com/qtoussaint/pangenome_merge)
runs from the BacHGT monorepo. **No vendored source.**

## What lives where

- **pangenomerge source + env on HPC:** `~/workspace/pangenome_merge` (kept up to
  date with the upstream `dev` branch — the user's earlier fixes
  (`fix/mmseqs-missing-node-guard`, `patch-1`) have since been absorbed upstream).
- **`pangenomerge` micromamba env:** holds only the runtime deps (mmseqs2,
  biopython, networkx, numpy, pandas, scipy, scikit-learn, edlib, matplotlib).
  pangenomerge itself is imported from the source dir via `PYTHONPATH=".:pangenomerge"`
  set by the sbatch wrappers. **No `pip install` step.**
- **This directory:** holds only orchestration glue:
  - `pangenomerge-runner.py` — minimal `from pangenomerge.__main__ import main; main()`
    wrapper, the canonical entry-point the sbatch scripts invoke.
- **sbatch wrappers:** `src/bac_panaroo/slurm_scripts/pangenomerge_merge.sh` and
  `src/bac_panaroo/slurm_scripts/pangenomerge_postprocess.sh`.

## Usage

```bash
# 1. Build a 2-line input TSV of Panaroo output dirs (one per line)
PANAROO_ROOT=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/panaroo_with_reference_genome
MERGE_OUT=/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/pangenomerge/SL147
mkdir -p "$MERGE_OUT"
printf '%s\n' "$PANAROO_ROOT/SL147_part_0" "$PANAROO_ROOT/SL147_part_1" \
  > "$MERGE_OUT/component_graphs.tsv"

# 2. Submit the merge (icelake-himem, 16 threads, 4h cap)
sbatch src/bac_panaroo/slurm_scripts/pangenomerge_merge.sh \
  --component-graphs "$MERGE_OUT/component_graphs.tsv" \
  --outdir "$MERGE_OUT"

# 3. Postprocess once the merge has completed (name resolves under
#    /home/dca36/rds/.../processed/pangenomerge/<name>/)
sbatch src/bac_panaroo/slurm_scripts/pangenomerge_postprocess.sh SL147
```

## Refreshing the HPC checkout to upstream/dev

```bash
cd ~/workspace/pangenome_merge
git fetch upstream
git checkout main
git reset --hard upstream/dev   # fix/mmseqs-missing-node-guard stays as a local archive
# Smoke (env provides deps; source is on disk — no install needed):
micromamba activate pangenomerge
export PYTHONPATH=".:pangenomerge"
python -c "import pangenomerge; print(pangenomerge.__file__)"
```
