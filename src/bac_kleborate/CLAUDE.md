# CLAUDE.md — bac_kleborate

The `bac_kleborate` subpackage of the BacHGT monorepo. See `BacHGT/CLAUDE.md`
for the monorepo and `~/.claude/CLAUDE.md` for global guidance.

## Purpose

Vendored [Kleborate](https://github.com/klebgenomics/Kleborate) reference data
(virulence + AMR allele FASTAs and metadata TSVs), held in one canonical
location so consumers — ARIBA-DB builders, minimap-based Panaroo-node
annotators, anything else — don't re-derive or duplicate them. Pure data; no
Python logic beyond a tiny path-constants module.

## Layout

```
src/bac_kleborate/
  __init__.py
  refs/
    __init__.py
    paths.py                 — KLEB_VIRULENCE_INPUTS_DIR, KLEB_AMR_INPUTS_DIR
    kleb_virulence/inputs/   — per-locus subdirs (klebsiella__ybst/ …) + allele FASTAs
    kleb_amr/inputs/         — Kleborate KpSC AMR module data (CARD FASTA + class TSVs)
```

Per-DB `manifest.json` / `metadata.tsv` (ARIBA build artefacts) live under
`src/bac_ariba/refs/<db>/`, **not** here. `bac_kleborate` is source data only.

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
