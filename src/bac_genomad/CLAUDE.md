# CLAUDE.md — bac_genomad

The `bac_genomad` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md` for
the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

`bac_genomad` runs [**geNomad**](https://portal.nersc.gov/genomad/) over every
Klebsiella assembly we have — both long-read (LRA: GCA/GCF) and short-read (SR:
SPAdes/Unicycler) — to produce per-contig **plasmid** and **provirus/prophage**
calls. Results feed downstream HGT / pangenome analyses by giving us
per-contig MGE classifications for the full ~90 k assembly set.

For samples that have both an LRA and a paired SR assembly, geNomad is run on
**both** so the calls can be cross-checked across assembly types; the paired-SR
row is keyed `<Sample>__sr` in the inputs TSV and the `per_sample/` tree.

## Layout

Flat package — one CLI module. Runs in this subpackage's own pixi env
(`src/bac_genomad/pixi.toml`), not the monorepo's shared uv env, because
geNomad's bioconda toolchain (MMseqs2, ARAGORN, neural-net weights) would
perturb library deps.

**HPC env placement (important):** geNomad depends on **TensorFlow** (its NN
classifier), making the env ~4–5 GB — too big for the `/home` quota where pixi
installs by default. On the HPC the env + package cache are **detached onto
project_k**:
- `src/bac_genomad/.pixi/config.toml` (git-ignored, HPC-only absolute path) sets
  `detached-environments = ".../david/processed/genomad/pixi_env"`.
- `PIXI_CACHE_DIR=.../david/processed/genomad/pixi_cache` (same filesystem so
  packages hardlink) — exported in `slurm_scripts/run_genomad.sh`; export it too
  for any manual `pixi install` / `pixi run` on the login node.

On the local Mac, pixi installs to the default home location as usual (the
`.pixi/config.toml` is not committed).

| Module | Purpose |
|---|---|
| `genomad_constants.py` | Default paths (metadata_v2, output root, DB dir), chunk size, threads, `SR_PAIRED_SUFFIX` |
| `run_genomad.py` | **prepare / worker / collate** CLI — the whole pipeline |
| `slurm_scripts/run_genomad.sh` | Slurm-array wrapper that invokes `worker` per chunk |

## Pipeline

Three-phase **prepare → worker (Slurm array) → collate** pattern mirroring
[`bac_isescan.run_isescan_lra`](../bac_isescan/run_isescan_lra.py):

### 1. Database (one-time)

```bash
cd src/bac_genomad
pixi install
pixi run genomad download-database \
    /home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/db
# → creates .../genomad/db/genomad_db/  (~2 GB)
```

### 2. `prepare` — build the inputs TSV

```bash
pixi run python -m bac_genomad.run_genomad prepare
```

Reads `metadata_v2_all_samples_and_columns.tsv` and emits
`<OUT_DIR>/inputs/genomad_inputs.tsv` with columns `Sample | fasta_path | source`:

| source     | rows | from column | Sample id |
|---|---|---|---|
| `lra`       | every row where `lr_assembly_file` exists on disk      | `lr_assembly_file` | metadata `Sample` |
| `sr`        | every row where `sr_assembly_file` exists AND no LRA       | `sr_assembly_file`     | metadata `Sample` |
| `sr_paired` | every row where BOTH `lr_assembly_file` and `sr_assembly_file` exist | `sr_assembly_file` | metadata `Sample` + `__sr` suffix |

Reports per-source counts and the chunk plan.

### 3. `worker` — Slurm array task

```bash
sbatch --array=0-888 src/bac_genomad/slurm_scripts/run_genomad.sh
```

Per task:
- Slices rows `[chunk_idx * CHUNK_SIZE : (chunk_idx + 1) * CHUNK_SIZE]`
- For each row: skip if `<sample>/.genomad.done` exists, else gunzip the FASTA
  to scratch and run `genomad end-to-end --cleanup --threads N --splits 0 <fa>
  <sample_dir> <db_dir>`
- `--cleanup` deletes intermediate module subdirs (`*_annotate/`,
  `*_find_proviruses/`, etc.) on success, keeping only `<sample>_summary/`
  (~1–5 MB per genome instead of 50–200 MB)
- Writes `.genomad.done` sentinel on success; per-chunk log in
  `<OUT_DIR>/chunk_logs/chunk_NNNNN.log`

**Measured (2026-06-02 run, 88,810 samples):** ~3.5 min/sample × 100 ≈ 5–6 h
per chunk (16 h walltime is ample). 8 CPUs / **64 GB** per task on
`icelake-himem` (peak MaxRSS ~20 GB — MMseqs2 `prefilter` is the spike; 16 GB
OOM'd in the first smoke test). The Slurm script redirects `$TMPDIR` to
personal RDS (1 TB) — geNomad's MMseqs2 annotate step writes large
intermediates that don't fit in worker `/tmp`.

### 4. `collate` — concatenate summaries

```bash
pixi run python -m bac_genomad.run_genomad collate [--workers 16] [--limit N]
```

Walks every `per_sample/<Sample>/` with a `.genomad.done` sentinel, reads
`<sample>_summary/<sample>_plasmid_summary.tsv` and
`<sample>_summary/<sample>_virus_summary.tsv` (direct path — no `rglob`),
tags rows with `Sample`, and writes:

- `<OUT_DIR>/genomad_plasmid_summary_long.tsv` — one row per plasmid contig
- `<OUT_DIR>/genomad_virus_summary_long.tsv`  — one row per virus/prophage region

`--workers N` (default 16) uses a thread pool for the I/O-bound Lustre reads;
`--limit N` collates only the first N per-sample dirs (subset inspection — pair
with a separate `--out-dir` so it doesn't clobber the real long TSVs).
**Measured (2026-06-02):** ~13 min full collate of 88,810 samples at 16 workers.

**"No-call" samples are silent in the long TSVs.** A sample with sentinel +
header-only summary TSVs (geNomad processed but classified nothing as plasmid
or virus — e.g. chromosome-only RefSeq deposits) does not appear in either
long TSV. The 2026-06-02 run had **94 such samples** (22 LRA, 21 paired SR, 51
SR — almost all `kpsc_final_list=True`). To list them downstream:
`set(genomad_inputs.Sample) − set(plasmid_long.Sample ∪ virus_long.Sample)`.

## Output layout

Under `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/processed/genomad/`:

```
db/genomad_db/                      # ~2 GB, downloaded once
inputs/genomad_inputs.tsv           # produced by `prepare`
per_sample/<Sample>/
    <Sample>_summary/               # KEEPERS (~1–5 MB)
        <Sample>_plasmid.fna
        <Sample>_plasmid_genes.tsv
        <Sample>_plasmid_proteins.faa
        <Sample>_plasmid_summary.tsv
        <Sample>_virus.fna
        <Sample>_virus_genes.tsv
        <Sample>_virus_proteins.faa
        <Sample>_virus_summary.tsv
        <Sample>_summary.json
    .genomad.done                    # sentinel
chunk_logs/chunk_NNNNN.log
slurm_logs/
genomad_plasmid_summary_long.tsv    # produced by `collate`
genomad_virus_summary_long.tsv
```

## Run history

| Date | Cohort | Outcome |
|---|---|---|
| 2026-06-02 | 88,810 samples (5,557 LRA + 77,985 SR-only + 5,268 paired SR) | 88,810/88,810 sentinels; 94 zero-call (legit, see above); 2,005,368 plasmid contig rows, 607,352 virus region rows |

Settings used in that run: `--partition=icelake-himem`, `--cpus-per-task=8`,
`--mem=64G`, `--time=16:00:00`, `CHUNK_SIZE=100`, geNomad 1.12.0, DB v1.9.
17 chunks had a single-sample JSONDecodeError each on Jun 1 (cluster restart
window) — retried cleanly in a 1-task array.

## Knobs

In `genomad_constants.py`:

- `DEFAULT_CHUNK_SIZE = 100` — drop to ~50 for shorter walltime if MaxArraySize
  on CSD3 turns out to be higher than expected, or raise to 150 if you need to
  cut the number of array tasks.
- `DEFAULT_THREADS = 8` — geNomad scales near-linearly to ~8–16 threads.
- Slurm walltime / mem live in the `#SBATCH` block at the top of
  `slurm_scripts/run_genomad.sh`.

## Smoke test (login node)

After `pixi install` + DB download + `prepare`:

```bash
# Trim inputs to a handful of mixed-source samples:
head -1 $OUT/inputs/genomad_inputs.tsv > $OUT/inputs/genomad_inputs.smoke.tsv
grep -m1 -P "\tlra$"       $OUT/inputs/genomad_inputs.tsv >> $OUT/inputs/genomad_inputs.smoke.tsv
grep -m1 -P "\tsr$"        $OUT/inputs/genomad_inputs.tsv >> $OUT/inputs/genomad_inputs.smoke.tsv
grep -m1 -P "\tsr_paired$" $OUT/inputs/genomad_inputs.tsv >> $OUT/inputs/genomad_inputs.smoke.tsv

# Run a 3-sample chunk in foreground (be polite to the login node):
pixi run python -m bac_genomad.run_genomad worker \
    --inputs $OUT/inputs/genomad_inputs.smoke.tsv \
    --chunk-idx 0 --chunk-size 3 --threads 2 \
    --out-dir $OUT/smoke
```

Expected: each `per_sample/<sample>/` contains only `<sample>_summary/` (no
intermediate subdirs left behind), `.genomad.done` present, chunk log shows
3/3 ok.
