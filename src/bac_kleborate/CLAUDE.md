# CLAUDE.md — bac_kleborate

The `bac_kleborate` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md`
for the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

Vendored [Kleborate](https://github.com/klebgenomics/Kleborate) reference data
(virulence + AMR allele FASTAs and metadata TSVs), held in one canonical
location so consumers — ARIBA-DB builders, minimap-based Panaroo-node
annotators, anything else — don't re-derive or duplicate them. Pure data; no
Python logic beyond a tiny path-constants module.

Also hosts the **LRA-cohort Kleborate runner** (Phase G.2), since the
KpSC typing call is the natural domain of this subpackage.

## Layout

```
src/bac_kleborate/
  __init__.py
  run_kleborate_lra.py       — Phase G.2: prepare/worker/collate over the LRA cohort
  slurm_scripts/
    run_kleborate_lra.sh     — Slurm array wrapper (icelake, 4 CPU/task, 1.5 h)
  refs/
    __init__.py
    paths.py                 — KLEB_VIRULENCE_INPUTS_DIR, KLEB_AMR_INPUTS_DIR
    kleb_virulence/inputs/   — per-locus subdirs (klebsiella__ybst/ …) + allele FASTAs
    kleb_amr/inputs/         — Kleborate KpSC AMR module data (CARD FASTA + class TSVs)
```

Per-DB `manifest.json` / `metadata.tsv` (ARIBA build artefacts) live under
`src/bac_ariba/refs/<db>/`, **not** here. `bac_kleborate` owns vendored
source data + the LRA-cohort runner.

## LRA-cohort Kleborate runner (Phase G.2)

`run_kleborate_lra.py` runs Kleborate v3 (`-p kpsc`) over every assembly in
`metadata_v2` where `lra_final_set=True` (~5,521 genomes). Designed as a
Slurm-array job — three subcommands:

| Subcommand | Where | Purpose |
|---|---|---|
| `prepare` | login node, ~5 s | Filter `metadata_v2` → `lra_inputs.tsv` (Sample, fasta_path) |
| `worker`  | Slurm task | Kleborate on one chunk of `lra_inputs.tsv` (rows `[i*N : (i+1)*N]`) |
| `collate` | login node | Concatenate per-chunk Kleborate output by module name |

Uses the `bac_isescan/pixi.toml` env (already pins `kleborate >= 3.1`); not
a separate env. The Slurm wrapper `cd`s into `src/bac_isescan` and runs
`pixi run python -m bac_kleborate.run_kleborate_lra worker …`.

End-to-end pattern:

```bash
# 1. Build the input list (login node):
uv run python -m bac_kleborate.run_kleborate_lra prepare

# 2. Submit the Slurm array (~56 chunks @ 100 genomes each):
sbatch --array=0-55 src/bac_kleborate/slurm_scripts/run_kleborate_lra.sh

# 3. Collate per-chunk output:
uv run python -m bac_kleborate.run_kleborate_lra collate

# 4. Merge back into metadata_v2 + KPSC cascade
#    (lives in bac_metadata since it edits the curated TSV):
uv run python -m bac_metadata.pp.merge_kleborate_into_metadata_v2
```

The cascade updates `species`, `is_kpsc`, and `kpsc_final_list` on every
`lra_final_set=True` row (full detail in
`src/bac_metadata/pp/merge_kleborate_into_metadata_v2.py`).

## Consumers

| Consumer | Purpose |
|---|---|
| `bac_ariba.pp.build_ariba_ref` | Reads vendored FASTAs → runs `ariba prepareref` → DB under `bac_ariba/refs/<db>/` |
| `bac_panaroo.tl.annotate_panaroo_nodes_minimap` | minimap2's Panaroo-cluster representatives against the vendored references — labels Panaroo nodes with virulence / AMR hits |

## Provenance

Each `<db>/inputs/` was vendored from Kleborate's installed `modules/<module>/data/`
at a specific Kleborate version. ARIBA-built DBs additionally record this in
`src/bac_ariba/refs/<db>/manifest.json`; for non-ARIBA consumers a short
`source.json` may sit alongside the data.
