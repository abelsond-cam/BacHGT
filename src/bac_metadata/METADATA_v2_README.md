# `metadata_v2` — README

*Snapshot: 2026-08-27 (agentic-enriched; base v2 2026-06-03) · `metadata_v2_all_samples_and_columns.tsv` ·
86,398 rows × 558 columns*

*(558 columns span: ENA Portal metadata, NCBI Datasets assembly info, Kleborate v3.2.4 typing
(species/MLST/virulence/AMR/Kaptive/wzi), ISEScan IS-family counts, CheckM2 QC, Bakta annotation
stats, parsed/categorised clinical metadata, file-path pointers, cohort flags,
`EBI_*_AST` binary truth values for 22 antibiotics (BacPredict step 9), and the 9 agentic re-curation
provenance columns added 2026-08-27 — see §10.)*

> **⚡ 2026-08-27 — agentic clinical re-curation is LIVE in v2.** The four clinical fields were blank-filled +
> selectively overwritten from an LLM-agent re-curation of the source papers, and 1,489 experimental-evolution
> lab samples were de-listed from the cohort. This added 9 provenance columns (505 → 558) and raised clinical
> completeness (country 91→96 %, collection_date 82→90 %, isolation_source 73→78 %, host 80→92 %). Full
> mechanics + provenance flags: **§10**. The pre-agentic v2 is archived at
> `…/david/final/archive/metadata_v2_all_samples_and_columns.tsv.20260827T165822.bak`.

Authoritative description of the Klebsiella **metadata_v2** table for BacHGT, BacPredict, and
external collaborators. Read this before consuming the table — it explains how rows are keyed,
what each flag means, where each column came from, and what to do if the data needs to change.

The canonical TSV lives on HPC at:
```
/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv
```
*(That's `<project_k>/david/final/`. See `~/.claude/hpc_storage_overview.md` for storage roots.)*

---

## 1. The cohort

- **~90,000** Klebsiella-annotated assemblies were curated from **All The Bacteria (ATB)** as the
  starting set (downloaded by `bac_data` via the bakrep + ENA pipelines).
- Extra QC was performed with **CheckM2** and specialist scripts. The final QC whitelist for the
  short-read cohort lives in the QC Excel (`klebsiella_qc_NCTC.xlsx`, sheet `FINAL_LIST`), now at
  `<project_k>/david/raw/klebsiella_qc_NCTC.xlsx` on HPC (migrated 2026-06-03; a safety copy is
  preserved on the Weimann shared OneDrive).
- In addition to ATB, **long-read assemblies from RefSeq** were downloaded plus the **NCTC**
  historic Klebs set (`is_nctc=97`).
- Species had to match Klebsiella via **Kleborate v3.2.4**. The Kp species complex (KPSC) covers
  the 7 phylogroups Kp1-Kp7 per Long et al. 2017:
  - **Kp1** — *Klebsiella pneumoniae*
  - **Kp2 / Kp4** — *K. quasipneumoniae* subsp. similipneumoniae / quasipneumoniae
  - **Kp3** — *K. variicola* subsp. *variicola*
  - **Kp5** — *K. variicola* subsp. *tropica* (also known as *K. tropica*)
  - **Kp6** — *K. quasivariicola*
  - **Kp7** — *K. africana*

  Implementation rule (`_is_kpsc` in `merge_kleborate_into_metadata_v2.py`): species name
  **contains** `variicola` OR **contains** `quasi`, OR starts with *Klebsiella pneumoniae* /
  *africana* / *tropica*. Catches all 7 phylogroups including hyphenated subspecies.

  v2 `is_kpsc=True` = **79,153**; curated final list `kpsc_final_list=True` = **79,153**.
  v2 carries 75 fewer KPSC rows than v1 — clean-up of orphan long-read assemblies (CheckM2
  QC drops + a few Kleborate species reclassifications).
- **~7,246** non-KPSC Klebsiella (e.g. *K. oxytoca*, *K. aerogenes*) are present in v2 but **not**
  in `is_kpsc`. They were not put through the full extra QC.

**Snapshot counts** (2026-06-03):

| | rows |
|---|---:|
| Total v2 rows | **86,398** |
| `is_kpsc=True` | 79,153 |
| `kpsc_final_list=True` | **79,153** |
| `is_variant_called=True` *(NEW)* | **76,574** |
| `lra_final_list=True` | **5,519** |
| `is_complete=True` | 4,017 |
| `is_hybrid=True` | 2,618 |
| `is_reference_genome=True` | **1,777** (1,684 KPSC + 93 non-KPSC) |
| `is_nctc=True` | 97 |
| `is_mgh78578=True` | 1 |
| Paired (LR + SR partner) | 3,075 |
| Orphan LR-only | 2,581 |
| SR-only | 80,742 |

---

## 2. Structure of the table — **the important bit for most users**

Each v2 row refers to **one biosample**. The `Sample` column resolves as:

- **Long-read assembly** when one exists (the LR is the canonical row key for that isolate).
  Long-read `Sample` is a **versioned** NCBI assembly accession (`GCF_…\.\d+` for RefSeq,
  `GCA_…\.\d+` for GenBank). Zero bare GC accessions. Most are `.1` (5,444 of 5,771);
  `.2`/`.3`/`.4` appear when NCBI has reissued an assembly (327 rows, mostly `.2`).
- **Short-read BioSample** otherwise (e.g. `SAMN…`, `SAME…`, `SAMD…`). These are SR-only rows.

### Quick column families

Full lists + descriptions in §4 and §5.

- **SR columns** — refer to the short-read partner:
  `sample_accession`, `run_accession`, `sr_run_accession`, `fastq_ftp`, `fastq_md5`,
  `sr_assembly_file`, `sr_gff_file`, `instrument_platform`, `instrument_model`,
  `study_accession`, `secondary_sample_accession`, `sr_biosample`.
- **LR columns** — refer to the long-read assembly:
  `lra_gca`, `lra_gcf`, `lr_assembly_file`, `lr_gff_file`, `lr_run_accession`,
  `lr_instrument_platform`, `lr_instrument_model`, `level`, `library_class`,
  `scoring_accession`, `checkm2_*`.

### Three row archetypes

| Archetype | `Sample` is… | rows | SR columns | LR columns | `sr_biosample` |
|---|---|---:|---|---|---|
| **SR-only** | a BioSample (`SAMN…`/`SAME…`/`SAMD…`) | **80,742** | filled | empty | empty |
| **Paired LR+SR** | an LR accession (`GCF_…`/`GCA_…`) | **3,075** | filled (SR partner's values copied in) | filled | original SR BioSample |
| **LR-only / orphan LRA** | an LR accession (`GCF_…`/`GCA_…`) | **2,581** | empty | filled | empty |

Per-archetype KPSC and variant-call breakdown:

| Archetype | rows | `is_kpsc=T` | `kpsc_final_list=T` | `is_variant_called=T` |
|---|---:|---:|---:|---:|
| SR-only | 80,742 | 73,754 | 73,754 | 73,754 |
| Paired LR+SR | 3,075 | 2,820 | 2,820 | 2,820 |
| Orphan LR-only | 2,581 | 2,579 | 2,579 | **0** *(no SR data → no variant calls)* |

Sample-prefix breakdown: SAME 38,913 / SAMN 38,542 / GCF_ 4,363 / SAMD 3,287 / GCA_ 1,293.

### Filter recipes — how to access the rows you want

All recipes start with the same load. The path columns store paths **relative to the
`project_k` root** — resolve them with `bac_metadata.path_resolve.resolve_v2_path()` (or just
prepend the root manually) before opening on disk.

```python
import pandas as pd
from bac_metadata.path_resolve import resolve_v2_path  # adds <project_k>/ to a stored path

V2 = "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv"
v2 = pd.read_csv(V2, sep="\t", low_memory=False)
samp = v2["Sample"].astype(str)
```

**By row archetype** (mutually exclusive, sum to v2 total):

```python
# SR-only — Sample is a BioSample, no LR overlay. SR paths populated, lr_* empty.
sr_only = v2[~samp.str.startswith(("GCF_", "GCA_"))]                       # 80,742

# Paired LR+SR — Sample is LR accession AND sr_biosample carries the SR partner.
paired = v2[samp.str.startswith(("GCF_", "GCA_")) & v2["sr_biosample"].notna()]   # 3,075

# Orphan LR-only — Sample is LR accession with no SR partner.
orphan_lr = v2[samp.str.startswith(("GCF_", "GCA_")) & v2["sr_biosample"].isna()] # 2,581
```

**By assembly availability** (what's actually on disk):

```python
# Any row with a usable SR assembly (SR-only + paired with files on disk).
has_sr = v2[v2[["sr_assembly_file", "sr_gff_file"]].notna().all(axis=1)]

# Any row with a usable LR assembly (paired + orphan with files on disk).
has_lr = v2[v2[["lr_assembly_file", "lr_gff_file"]].notna().all(axis=1)]

# Rows with BOTH sides on disk — entry gate for paired LR-vs-SR comparison. See §9.
both_sides = v2[v2[["sr_assembly_file", "sr_gff_file",
                    "lr_assembly_file", "lr_gff_file"]].notna().all(axis=1)]
```

**By analysis cohort:**

```python
# The curated KPSC cohort (= the species-complex working set).
kpsc = v2[v2["kpsc_final_list"].fillna(False).astype(bool)]                # 79,153

# The variant-calling cohort: rows whose SR data passed v1's KPSC QC. Always
# excludes orphan LR-only rows (they have no SR data).
vc_cohort = v2[v2["is_variant_called"].fillna(False).astype(bool)]         # 76,574

# The LRA cohort: every LR-bearing row that passed CheckM2 QC.
lra = v2[v2["lra_final_list"].fillna(False).astype(bool)]                  # 5,519

# The reference set (highest-confidence closed genomes — modern hybrid + RefSeq).
refs = v2[v2["is_reference_genome"].fillna(False).astype(bool)]            # 1,777
```

**Open the assemblies on disk:**

```python
for _, row in paired.head(5).iterrows():
    sr_fa  = resolve_v2_path(row["sr_assembly_file"])
    sr_gff = resolve_v2_path(row["sr_gff_file"])
    lr_fa  = resolve_v2_path(row["lr_assembly_file"])
    lr_gff = resolve_v2_path(row["lr_gff_file"])
    # sr_fa / sr_gff / lr_fa / lr_gff are absolute pathlib.Paths under project_k.
```

For the **paired LR-vs-SR comparison default** (use this when asked to "compare long and short
reads of the same isolate"), see §9 — it pairs the 4-path filter above with the
`is_reference_genome` (best) or `is_complete` (broader) sub-cohort.

---

## 3. Key flags

| Flag | Definition | Count |
|---|---|---:|
| `is_kpsc` | Kp species complex (Kp1-Kp7): species **contains** `variicola` OR `quasi`, OR starts with *K. pneumoniae* / *africana* / *tropica*. See §1. | **79,153** |
| `kpsc_final_list` | Curated KPSC cohort. SR-only rows inherit v1's curated list; LR-bearing rows are admitted if Kleborate confirms KPSC and either v1 had them on the list OR the LR passes CheckM2. Equals `is_kpsc` in v2. | **79,153** |
| `is_variant_called` *(NEW)* | True iff the row has SR data that passed v1's KPSC QC (the cohort variant calling was performed against). Computed as `(NOT orphan LRA) AND v1's kpsc_final_list=True`. Always False on orphan LRA rows. | **76,574** |
| `is_mgh78578` | The historic *K. pneumoniae* MGH 78578 reference used for variant calling (Sample `GCF_000016305.1`, ST38). **Complete but NOT hybrid-assembled** → not in `is_reference_genome` | 1 |
| `lra_final_list` | LR assemblies passing CheckM2 (completeness ≥ 99.0%, contamination ≤ 5.0%, genome size ≤ max RefSeq observed). Derivation: [`build_lra_set.py:120`](../bac_data/lr_data/build_lra_set.py#L120) | 5,519 |
| `is_complete` | NCBI `assembly_level == "Complete Genome"` (chromosome + plasmids closed/circular) | 4,017 |
| `is_hybrid` | NCBI `library_class == "hybrid"` — **any LR sequenced with both long and short read tech**. Includes drafts; NOT gated on `is_complete`. Derivation: [`build_lra_set.py:123`](../bac_data/lr_data/build_lra_set.py#L123) | 2,618 |
| `is_reference_genome` | **Strict** intersection: `is_complete ∧ is_hybrid ∧ Sample starts with GCF_` (RefSeq). Highest-confidence reference set. Derivation: [`build_lra_set.py:126-127`](../bac_data/lr_data/build_lra_set.py#L126-L127) | 1,777 |
| `is_nctc` | Historic NCTC Klebs assembly | 97 |

**Important nuances:**

- `is_hybrid` does **not** require `is_complete`. A draft assembly built with hybrid technology is
  `is_hybrid=True`, `is_complete=False`, `is_reference_genome=False`.
- `is_reference_genome` requires **RefSeq** (`GCF_` prefix) — GenBank-only hybrids (`GCA_`) are
  excluded even if complete.
- `is_mgh78578` is `is_complete=True` but `is_hybrid=False`, so it is **not** a reference genome
  under this scheme.
- `is_reference_genome` species composition: 1,681 KPSC + 96 non-KPSC. Non-KPSC includes
  *K. aerogenes* (31), *K. michiganensis* (21), *K. oxytoca* (15), *K. grimontii* (12), and a tail
  of other Klebsiella species (~14 more, ≤ 3 each).

---

## 4. Short-read assembly columns

Populated on SR-only rows and paired rows (copied from the SR partner during the v2 build).
Empty on LR-only orphan rows.

| Column | Source | Notes |
|---|---|---|
| `sample_accession` | ENA Portal | BioSample (SAMN/SAME/SAMD) |
| `run_accession` | ENA Portal | SR Illumina run accession. On paired rows this is the SR partner's run (the LR run lives in `lr_run_accession`). |
| `sr_run_accession` | renamed from v1 `related_sr_accession` | Mirror of the SR run on paired rows for unambiguous SR pickup |
| `fastq_ftp`, `fastq_md5` | ENA Portal | SR fastq URLs + checksums. ⚠ NOT copied onto the ~957 merged paired rows during the SR↔RefSeq merge — those rows have `run_accession` but no `fastq_ftp`. Resolve via the ENA API from `run_accession` if needed. |
| `sr_assembly_file` | `add_paths_gff_fna_to_metadata.py` | SR assembly FASTA path on HPC. |
| `sr_gff_file` | `add_paths_gff_fna_to_metadata.py` | SR GFF path. |
| `instrument_platform`, `instrument_model` | ENA Portal | SR sequencer info |
| `study_accession`, `secondary_sample_accession` | ENA Portal | Standard ENA accessions |

The LR↔SR pairing logic lives in [`build_metadata_v2.py`](pp/build_metadata_v2.py) — see
`_pair_refseq_sr` and the merge of 957 SR+RefSeq pairs at lines 565-589.

---

## 5. Long-read assembly columns

Populated on `lra_final_list=True` rows (and on the LR-only orphan rows).

| Column | Source | Notes |
|---|---|---|
| `lra_gca`, `lra_gcf` | NCBI Datasets | The LR assembly's GCA / GCF accessions (versioned). One of these is the row's `Sample`. |
| `lr_assembly_file` | `add_paths_gff_fna_to_metadata.py --mode lra` | LR FASTA path, relative to `<project_k>`. |
| `lr_gff_file` | `add_paths_gff_fna_to_metadata.py --mode lra` | LR GFF path, relative to `<project_k>`. |
| `lr_run_accession` | ENA / NCBI Datasets | LR run accession (ONT/PacBio); separate from SR's `run_accession` |
| `lr_instrument_platform`, `lr_instrument_model` | ENA / NCBI Datasets | LR sequencer info |
| `level` | NCBI Datasets | NCBI `assembly_level` (used to derive `is_complete`) |
| `library_class` | NCBI Datasets (derived) | hybrid / long-read / short-read (used to derive `is_hybrid`) |
| `scoring_accession` | `build_lra_discovery.py` | The assembly used for CheckM2 scoring (GCF preferred, else GCA) |
| `checkm2_completeness`, `checkm2_contamination`, `checkm2_genome_size`, `checkm2_*` (~13 cols) | `bac_data/checkm2/` | CheckM2 v1.x results on the LR FASTA |

---

## 6. Kleborate columns

All from **Kleborate v3.2.4** run on the LR assembly via
[`run_kleborate_lra.py`](../bac_kleborate/run_kleborate_lra.py) with `-p kpsc` preset, then merged
into v2 by [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py).

| Column | Notes |
|---|---|
| `species` (lowercase) | Kleborate species call |
| `scientific_name` | mirror of `species` |
| `ST` | Kp 7-locus MLST sequence type (e.g. `ST258`) |
| `gapA`, `infB`, `mdh`, `pgi`, `phoE`, `rpoB`, `tonB` | MLST allele numbers |
| `Sublineage`, `Clonal group`, `LINcode`, `Phylogroup` | **From v1 QC Excel LINcode sheet (Pasteur BIGSdb LIN-typing)** — NOT Kleborate v3 output. See §12 note on the 124-row gap. |
| `K_locus`, `K_type`, `K_locus_confidence`, `K_Missing_expected_genes` | Kaptive K typing |
| `O_locus`, `O_type`, `O_locus_confidence`, `O_Missing_expected_genes` | Kaptive O typing |
| `wzi` | wzi-type K-antigen prediction |
| Virulence MLSTs + loci | `YbST`, `CbST`, `AbST`, `SmST`, `RmST`, `Yersiniabactin`/`Colibactin`/`Aerobactin`/`Salmochelin`/`RmpADC`, per-locus genes (`ybt*`, `clb*`, `iuc*`, `iro*`, `rmp*`, `rmpA2`), `virulence_score`, `spurious_virulence_hits` |
| AMR — acquired | `<class>_acquired` (AGly, Col, Fcyn, Flq, Gly, MLS, Phe, Rif, Sul, Tet, Tgc, Tmt, Bla, Bla_inhR, Bla_ESBL, Bla_ESBL_inhR, Bla_Carb) |
| AMR — chromosomal + mutations | `Bla_chr`, `SHV_mutations`, `Omp_mutations`, `Col_mutations`, `Flq_mutations`, `truncated_resistance_hits`, `spurious_resistance_hits` |
| AMR — scores + predictions | `resistance_score`, `num_resistance_classes`, `num_resistance_genes`, `Ciprofloxacin_prediction`, `Ciprofloxacin_profile`, `Ciprofloxacin_MIC_prediction` |

**Parsing helpers** — virulence and AMR call strings can be parsed with
[`src/bac_kleborate/parsing.py`](../bac_kleborate/parsing.py) (Kleborate's `;`-separated /
`-`-no-hit syntax → structured tokens).

> **Note:** the Kleborate Sublineage call is missing from **~124** rows — 121 newly-added orphan
> LRA + Norway rows, 3 SR with a v1 LINcode-sheet gap. Closing this requires the Pasteur BIGSdb
> LIN-typing service (Kleborate v3.2.4 does **not** include a LIN-coding module). Tracked in §12.

---

## 7. Bakta annotation columns

Bakta annotation outputs from the bakrep pipeline (`<project_k>/bakrep/`), joined into v1 via
[`qc_add_metadata.py`](pp/qc_add_metadata.py) (`bakrep` sheet of the QC Excel) and carried into v2.

| Column | Notes |
|---|---|
| `bakta.genome.genus` | Bakta-classified genus |
| `bakta.genome.species` | Bakta-classified species |
| `bakta.genome.strain` | Bakta-classified strain identifier |
| `bakta.stats.no_sequences` | Number of contigs |
| `bakta.stats.size` | Total genome size (bp) |
| `bakta.stats.gc` | GC content |
| `bakta.stats.n_ratio` | Fraction of N bases |
| `bakta.stats.n50` | Assembly N50 |
| `bakta.stats.coding_ratio` | Coding density |
| `bakta_gbff_downloaded` | Flag — whether the Bakta `.gbff` is on disk for the SR row |

---

## 8. ISEScan IS-family columns (`IS_*`)

Per-genome IS-family copy counts from **ISEScan**, run on LR assemblies via
[`run_isescan_lra.py`](../bac_isescan/run_isescan_lra.py) and merged into v2 by
[`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py).

- One `IS_<family>` column per family detected across the LRA cohort (e.g. `IS_IS1`, `IS_IS3`,
  `IS_IS5`, `IS_IS6`, `IS_IS21`, `IS_IS66`, `IS_IS110`, `IS_IS200/IS605`, `IS_ISKRA4`, … ~24 families).
- Value = copy count from ISEScan; `0` on matched LR rows with no detection of that family;
  `NaN` on non-LR rows.

---

## 9. Paired long+short read subset — the LR-vs-SR comparison cohort

> **TL;DR — when asked to compare long-read and short-read assemblies of the same isolate:**
> filter v2 to the rows that carry both sides (4 paths populated) and then sub-select to
> `is_reference_genome` (or `is_complete` if you want the wider set). v2 is the single source of
> truth; no auxiliary join file is needed. The recipe is verbatim below.

### Step 1 — entry filter (the 4-path archetype gate)

```python
import pandas as pd
v2 = pd.read_csv(
    "/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/"
    "metadata_v2_all_samples_and_columns.tsv",
    sep="\t", low_memory=False,
)

# A row is part of the paired set iff:
#   - its Sample is a GCF/GCA accession (LR-keyed, the canonical row form for paired isolates)
#   - it carries an SR partner BioSample (sr_biosample), and
#   - all four assembly/GFF paths are on disk.
samp   = v2["Sample"].astype(str)
paired = v2[samp.str.startswith(("GCF_", "GCA_")) & v2["sr_biosample"].notna()]
paired = paired[paired[[
    "sr_assembly_file", "sr_gff_file",
    "lr_assembly_file", "lr_gff_file",
]].notna().all(axis=1)]
```

`paired` is `2,675 rows` (post-rebuild, 2026-06-03). This is the largest set on which BOTH the
long- and short-read assembly + GFF resolve on disk — the prerequisite for any per-isolate
LR-vs-SR comparison.

| Filter step | Rows |
|---|---:|
| GCF/GCA `Sample` + `sr_biosample.notna()` | **3,075** |
| above + all 4 paths populated | **2,675** |
| (the 400-row gap is paired isolates whose assemblies haven't been staged on disk yet) | |

### Step 2 — choose the cohort

Within the 2,675-row paired set, sub-select with one of the cohort flags below. Counts on the
post-rebuild v2 (2026-06-03):

| Flag | Rows | Meaning | LR-vs-SR comparison quality |
|---|---:|---|---|
| `is_reference_genome` | **709** | complete ∧ hybrid ∧ `GCF_` (RefSeq) — built with modern hybrid tech, NCBI-closed | **best** |
| `is_complete` | **1,454** | NCBI `assembly_level == "Complete Genome"` (closed circular chromosome) | very good |
| `is_hybrid` | 1,451 | `library_class == "hybrid"` — assembled from combined SR+LR reads | much weaker (drafts allowed) |
| `lra_final_list` | 2,648 | LR passed CheckM2 (≥ 99% completeness, ≤ 5% contamination, size ≤ max RefSeq) | weakest (drafts dominate) |

So the **default when asked to "compare long and short reads":** filter for the 4 paths populated
and then `is_reference_genome` (best) or `is_complete` (broader). Avoid `is_hybrid` /
`lra_final_list` for this purpose — they admit draft assemblies that aren't directly comparable
to a finished SR partner.

### Two notes on edge cases

- **`is_mgh78578`** (1 row): is_complete=True, is_hybrid=False, is_reference_genome=False. It's a
  closed genome assembled with **older Sanger sequencing**, not hybrid SR+LR — so it's not a
  reference under this scheme and is not in the `is_reference_genome` cohort.
- **Why `lra_final_list` (2,648) < paired+4paths (2,675):** the 27-row gap is paired isolates
  whose LR assembly didn't pass our CheckM2 QC. Without the 4-paths gate, the unfiltered count
  difference is 36 (3,075 paired vs 3,039 in lra_final_list) — those are the long reads that
  failed QC for the LRA cohort overall. They remain in v2 as paired rows because the SR side is
  fine; they just shouldn't be used as the LR reference.

### Companion artefact: `sr_shadow_for_lra.tsv`

A construction-time sidecar at `<project_k>/david/processed/complete_vs_sr_genomes/` that keeps
a frozen snapshot of the SR-side Kleborate / ISEScan typing for every paired row, so v2's
LR-overlay step doesn't overwrite the SR-side values when the row's `Sample` flips from
SR BioSample to LR accession. **Not the right entry point for analysis** — read v2 directly with
the recipe above. The shadow's value is downstream typing reconciliation (it pairs `sr_*` typing
columns alongside v2's unprefixed LR-side typing for the same row), and it sits at:

```
<project_k>/david/processed/complete_vs_sr_genomes/sr_shadow_for_lra.tsv
```

Downstream paired analyses in [`src/bac_complete_genomes/`](../bac_complete_genomes/) consume v2
directly via the 4-path filter and only reach for the shadow when SR-side typing reconciliation
is needed.

---

## 10. Curated clinical metadata

The four primary fields curated for research, processed in
[`metadata_curation.py`](pp/metadata_curation.py):

`collection_date` · `country` · `host` · `isolation_source`

Each goes through (1) **parse** (regex + lookup tables for spelling, language, synonyms — e.g.
*Homo sapiens* → `"human"`) and then (2) **categorise**.

### Agentic re-curation (added 2026-08-27) — provenance columns

The four clinical fields were enriched by an LLM-agent re-curation of the source papers
(`bac_agentic_metadata`), combined into v2 on 2026-08-27 (architecture B — injected directly onto v2,
preserving every other column byte-identical). Precedence is **human-curated (`_parsed`) > agent > ENA**, so no
previously-curated value was overwritten by a blank-fill. Three operations, each with a provenance flag:

- **Blank-fill** — the agent value fills a cell that was blank (or held only a raw-but-unparsed ENA value).
  Flag: **`<field>_agent_filled`** (True/False), one per field. Counts: country 4,375 · collection_date 6,974 ·
  isolation_source 7,868 · host 10,482. Raised completeness to country 96.3 / date 90.1 / iso 77.7 / host 92.1 %.
- **Gated overwrite** — an *approved* agent value replaced an existing ENA value (vague→specific, e.g.
  `"clinical material"`→`"BLOOD"`, or a same-year `collection_date` refinement, or a paper-corrected country).
  Flag: **`<field>_agent_overwrote`** (True/False). 2,922 rows written (David-reviewed;
  `data/v2_overwrite_candidates.{tsv,md}` in the repo is the reviewed candidate list).
- **Evolutionary de-list** — **`evolutionary_lab_sample`** (True/False): True for 1,489 experimental-evolution
  lab samples (1,055 present in v2). These are removed from the analysis cohort
  (`kpsc_final_list`/`lra_final_list`/`is_variant_called` set False) but **`is_kpsc` is kept True** (they are
  genuinely KPSC, used for the evolutionary analysis), and the 10 that are closed reference genomes **keep**
  their `is_complete`/`is_hybrid`/`is_reference_genome` flags.

For blank-filled/overwritten rows the derived columns below (`*_parsed`, `*_category`, `region`,
`collection_year`) were re-generated with `metadata_curation.py`'s own parse/categorise functions, so v2's
vocabulary stays consistent. Full mechanics: [`PROJECT_STATE.md`](../../PROJECT_STATE.md) Layer B +
[`bac_agentic_metadata/MERGE_TO_V2_RUNBOOK.md`](bac_agentic_metadata/MERGE_TO_V2_RUNBOOK.md).

> ⚠️ **The category-distribution tables in this section are the pre-agentic 2026-06-03 snapshot** and now
> understate coverage by the ~30k agentic fills above — recompute from the live table before quoting them.

### Parsed columns (cleaned canonical strings)

`country_parsed` · `host_parsed` · `isolation_source_parsed` · `collection_date_parsed` ·
`collection_year`.

### Category columns (categorical buckets)

#### `region` (WHO/geographic regions)

| Region | Rows |
|---|---:|
| W. Europe | 25,287 |
| N. America | 19,177 |
| E. Asia | 15,119 |
| Africa | 7,062 |
| M. East, Central Asia | 4,967 |
| Oceania | 3,018 |
| Central & S. America | 2,787 |
| E. Europe | 2,451 |
| (NaN) | 6,650 |

#### `host_category`

| Category | Rows |
|---|---:|
| human | 66,351 |
| wastewater & water | 2,129 |
| grazing livestock & horses | 1,350 |
| poultry livestock | 598 |
| domestic animals | 558 |
| vegetable, plant or soil | 466 |
| clinical environment or surface | 409 |
| meat products | 405 |
| wild animals | 307 |
| insect | 157 |
| wild birds | 46 |
| (NaN) | 13,742 |

#### `isolation_source_category`

| Category | Rows |
|---|---:|
| blood | 13,339 |
| urine | 13,100 |
| faeces & rectal swabs | 12,702 |
| lower respiratory, endotracheal | 6,821 |
| wound & pus, abscess, surgical drain, body tissue, bone, biopsy | 3,175 |
| wastewater & water | 2,129 |
| invasive gut & organs | 1,160 |
| body fluid (ascites / peritoneal / pleural) | 636 |
| vegetable, plant or soil | 466 |
| urinary catheter | 438 |
| upper airway | 423 |
| clinical environment or surface | 409 |
| meat products | 405 |
| skin swabs (skin, groin, vaginal, genital, eye, ear) | 303 |
| insect | 157 |
| (NaN) | 30,760

### Category composition notes

A few categories are heterogeneous — worth knowing what each rolls up:

- **`wound & pus, abscess, surgical drain, body tissue, bone, biopsy`** — wound, pus, abscess,
  surgical drain, bone/biopsy tissue. **Liver abscess** lands here (66/67 rows).
- **`body fluid (ascites / peritoneal / pleural)`** — separate from wound. **CSF** lands here
  (24/25 rows; not in wound).
- **`urine`** (13,100) vs **`urinary catheter`** (438) — separate categories. The catheter
  bucket is matched via `(?=.*catheter)(?=.*urin)` regex in `metadata_curation.py:1525`.
- **`lower respiratory, endotracheal`** — tracheal aspirates, tracheostomy, sputum, bronchial
  lavage. **`upper airway`** is a separate category (423 rows).
- **`skin swabs (skin, groin, vaginal, genital, eye, ear)`** — dedicated category for surface
  swabs; not in wound.

### Study-level columns

Annotated manually during study review (see §11):

- **`amr_study`** — what the study selected for:

  | Value | Rows |
  |---|---:|
  | `AMR` | 41,056 |
  | (NaN) | 19,121 |
  | `Surveillance` | 16,447 |
  | `AMR plus control` | 9,894 |

- **`study_setting`** — where the samples were collected:

  | Value | Rows |
  |---|---:|
  | `Hospital` | 51,245 |
  | (NaN) | 23,688 |
  | `Mixed` | 7,883 |
  | `Community` | 3,702 |

- **`study_accession`, `secondary_study_accession`, `study_alias`, `study_title`** — ENA-side
  identifiers and titles for the source study; carried from the ENA Portal collation step.

---

## 11. How the metadata was collected + study-level annotation

For the ~90,000 ATB samples, **ENA project accessions** were screened: studies with > 130
samples were reviewed manually (nearly 75% of the assembly set). Reviewed studies had:

- Number of Klebsiella samples in the study (vs other species) checked.
- Country, host, isolation source, collection dates verified against the publication / metadata.
- **`amr_study`** — what the study selected for (AMR / `AMR plus control` / Surveillance / NaN),
  based on whether sequencing was limited to AMR-resistant samples (typically 3rd-gen cephalosporins
  or carbapenems detected by AST or ARG PCR). Annotated on ~80% of reviewed studies. See §10 counts.
- **`study_setting`** — Hospital / Community / Mixed (current column; see §10 counts).
- For studies without per-sample metadata: if all samples were from one country, isolation
  source, host, or within a two-year window, the key variables were back-filled from that
  study-level assumption.

**Sources** (per pipeline stage):

| Source | Used for | Joined in |
|---|---|---|
| ENA Portal API + ready_to_merge patches | SR sample/run metadata, fastq URLs, study fields | [`metadata_collation.py`](pp/metadata_collation.py) |
| NCBI Datasets API | RefSeq/GenBank LR assemblies, NCTC, assembly_level, library_class | [`bac_data/lr_data/`](../bac_data/lr_data/) |
| Bakrep | Bakta annotation stats (`bakta.*`) | [`qc_add_metadata.py`](pp/qc_add_metadata.py) (`bakrep` sheet of QC Excel) |
| QC Excel `LINcode` sheet (Pasteur BIGSdb) | `Sublineage`, `LINcode`, `Clonal group`, `Phylogroup` | [`qc_add_metadata.py`](pp/qc_add_metadata.py) |
| Kleborate v3.2.4 (run on LR) | Species, MLST, virulence, AMR, Kaptive, wzi | [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py) |
| ISEScan (run on LR) | `IS_<family>` copy counts | [`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py) |
| Google Sheet (study-level review) | `amr_study`, `study_setting` | [`metadata_curation.py`](pp/metadata_curation.py) |
| CheckM2 (run on LR) | `checkm2_*` QC stats; cohort gate | [`bac_data/checkm2/`](../bac_data/checkm2/) |

---

## 12. Known issues + open To Do

### Known data issues

- **`Sublineage` missing on 124 KPSC rows** (121 LRA orphan/Norway + 3 SR with v1 LINcode-sheet
  gaps). Kleborate v3.2.4 does not emit `Sublineage`/`LINcode` — those came from a separate
  Pasteur BIGSdb LIN-typing layer in v1. Closing this requires running BIGSdb LIN-typing or a
  manual LIN-typing pass. **Not currently scheduled.**
- **~957 paired rows lack `fastq_ftp`/`fastq_md5`** even though `run_accession` is populated.
  The SR↔RefSeq merge in [`build_metadata_v2.py:570-574`](pp/build_metadata_v2.py#L570-L574)
  doesn't copy fastq columns onto the merged row. Workaround: resolve via the ENA API from
  `run_accession`.

### Open cleanups

- **Path-relative rewrite** — helper module
  [`src/bac_metadata/path_resolve.py`](path_resolve.py) provides `resolve_v2_path(value, root=None)`
  (absolute paths pass through unchanged) and `to_relative_v2_path(absolute, root=None)`. The
  cascade's `add_paths_gff_fna --mode lra` step is wired to strip the `<project_k>` prefix from
  `lr_*` / `sr_*` columns at write time, but activation is gated on updating the 7 consumers that
  open these paths (`run_kleborate_lra.py`, `run_isescan_lra.py`, `panaroo_run_strain.py`,
  `run_genomad.py`, `stage_lra_extras_for_tf.py`, `download_lra_gffs.py`,
  `stage_sr_for_related_lr.py`) to call `resolve_v2_path`. Activate by sweeping the consumers,
  then re-running `rebuild_v2.sh`.
- **`is_refseq` legacy sweep** — six modules in `bac_isescan`, `bac_panaroo` (mgefinder selector),
  and `bac_ariba` still read the dropped `is_refseq` flag and the slimmed v1 TSV. Repoint by
  intent: cohort-arm → `lra_final_list`; reference-bucket → `is_reference_genome`; SR-exclusion
  → SR-side signal (e.g. `run_accession` populated).

### Bacformer-predicted AST + EBI ground-truth columns

Three column families per panel drug, populated by
[`merge_predicted_and_ebi_ast_into_metadata_v2.py`](pp/merge_predicted_and_ebi_ast_into_metadata_v2.py)
(rebuild_v2 step 9 — see §13).

| Column | Type | Source | Domain |
|---|---|---|---|
| `predicted_{drug}_AST` | str | BacPredict (Bacformer Stage C) | `"R"` / `"S"` / NaN |
| `predicted_{drug}_AST_prob` | float | same | `[0, 1]` or NaN |
| `EBI_{drug}_AST` | str | BacPredict's `binary_ast.csv` (curated EBI / publication AST), translated 1→R / 0→S | `"R"` / `"S"` / NaN |

**Panel (22 drugs):** `gentamicin, ceftazidime, meropenem, ciprofloxacin,
trimethoprim-sulfamethoxazole, amikacin, ceftriaxone, piperacillin-tazobactam,
cefoxitin, aztreonam, cefazolin, tobramycin, cefepime, imipenem, levofloxacin,
cefotaxime, cefuroxime, ampicillin-sulbactam, ertapenem, tetracycline,
azithromycin, colistin`. (Top-23 by EBI-labelled count, minus ampicillin —
intrinsic Kp resistance — and `pentizidone` — unverified drug-name parsing
artefact — plus colistin, the canonical chromosomal-mechanism bellwether.)

**Coverage.** `predicted_*` columns are populated for every `kpsc_final_list` row
that has an ESM-C embedding on disk; NaN otherwise (~5 % of `kpsc_final_list`
lacks embeddings as of the 2026-05-29 snapshot, per `find_missing_embeddings.py`).
`EBI_*` columns are populated only for the subset that has curated EBI AST
testing — a few thousand isolates, mostly post-2010.

**R/S threshold.** Per drug, the **Youden-J operating point** (max sens+spec)
selected on the model's validation fold and recorded in
`<checkpoint>/eval_results.json::operating_point.threshold`. This is the unbiased
threshold; AUROC/AUPRC are threshold-independent and live in the same JSON.
Six drugs have **extreme thresholds** at deployment (worth knowing when
interpreting `predicted_*`):

| Drug | Youden threshold | Interpretation |
|---|---|---|
| meropenem | 0.000 | model probabilities cluster near zero; tiny cut separates R/S |
| amikacin | 0.058 | likewise |
| colistin | 0.066 | likewise — also the chromosomal-mechanism floor (AUROC 0.81) |
| cefuroxime | 1.000 | model overconfident; only top tail called R |
| cefazolin | 1.000 | likewise |
| imipenem | 1.000 | likewise |

For these, `predicted_<drug>_AST_prob` is the more nuanced signal than the R/S
call. Reasoning: in the panel evaluation the Youden-tuned call still beats the
0.5 default for balanced accuracy on the held-out evaluate set; we keep the
same calibration in deployment for consistency.

**See also:** per-drug rolling resistance-rate-over-time plots
(predicted thick + EBI dashed) live at
`<project_k>/david/processed/train_kleb_ast/predicting_AST_over_time/<drug>.png`,
produced by BacPredict's
[`src/kleb_ast/plot_resistance_over_time.py`](../../../BacPredict/src/kleb_ast/plot_resistance_over_time.py)
(login-node CPU). Default rolling window is 100 samples by `collection_date_parsed`.

---

## 13. Changing metadata — full rebuild pipeline

**Don't run the rebuild ad-hoc.** Contact David first. Changes should land in the production
pipeline so the table is reproducible.

The chain:

1. **Collate ENA metadata** — [`metadata_collation.py`](pp/metadata_collation.py). Reads ENA TSV
   exports + per-project `ready_to_merge` patches → writes
   `intermediate_collated_metadata_wo_qc_or_kleborate.tsv`.
2. **Run QC + KPSC pipeline** — [`qc_add_metadata.py`](pp/qc_add_metadata.py). Joins the QC Excel
   sheets (`bakrep`, `Refseq`, `NCTC`, `kleborate`, `LINcode`, `FINAL_LIST`).
3. **Curate** — [`metadata_curation.py`](pp/metadata_curation.py). Parse + categorise `host` /
   `isolation_source` / `country` / `collection_date`; emit
   `metadata_final_curated_all_samples_and_columns.tsv` (= "v1").
4. **Add file paths** — [`add_paths_gff_fna_to_metadata.py`](pp/add_paths_gff_fna_to_metadata.py).
   Default mode walks the SR pools to fill `sr_assembly_file` / `sr_gff_file` on v1 (GC-prefixed
   Samples are skipped — they're LR-only and have no SR path). `--mode lra` fills
   `lr_assembly_file` / `lr_gff_file` on v2 from the `related_lr` pools. All four columns are
   stored relative to `<project_k>`.
5. **Rebuild v2** — [`rebuild_v2.sh`](pp/rebuild_v2.sh) (8-step cascade, all idempotent; each
   merge step renames the existing TSV to `.bak.<UTC>.tsv` before writing):
   1. `build_metadata_v2.py` — **always rebuilds from v1** (no auto-skip if a v2 file already
      exists; the existing v2 is renamed to `.bak.<UTC>.tsv` before write). Ingests orphan LRAs,
      drops `is_refseq`, adds LR/SR pairing columns.
   2. `merge_norway_pairs_into_v2.py`
   3. `merge_kleborate_into_metadata_v2.py` ← Kleborate output
   4. `merge_isescan_into_metadata_v2.py` ← ISEScan output
   5. `import_sr_kleborate.py`
   6. `import_sr_isescan.py`
   7. `build_sr_shadow_for_lra.py` ← writes `sr_shadow_for_lra.tsv`
   8. `add_paths_gff_fna_to_metadata.py --mode lra`
   9. `merge_predicted_and_ebi_ast_into_metadata_v2.py` ← BacPredict-side Bacformer AST
      predictions (Youden-tuned R/S calls + probabilities) and EBI ground-truth AST,
      joined onto v2 by `Sample`. See §12 for column families. Prereq: the BacPredict GPU
      array `predict_amr_panel_on_slurm.sh` has produced per-drug parquets under
      `<project_k>/david/processed/train_kleb_ast/predictions_for_metadata/<drug>.parquet`.
      Idempotent (drops `predicted_*` / `EBI_*` columns before each merge); safe to re-run
      against a stale or partial parquet directory.

   Use `--skip-g1` / `--skip-isescan` / `--skip-sr-import` / `--skip-predicted-ast` to skip
   subsections when only downstream changes are needed.

---

## 14. Downloading assemblies / GFFs / reads

See [`src/bac_data/`](../bac_data/) — scripts that automate downloads from v2 metadata:

- `download_bakrep_gbff_files.py` — Bakta `.gbff` fetcher.
- `download_lra_gffs.py` — LR GFF backfill.
- `download_related_lr_complete_genomes.py` — LR FASTA fetcher for the related-LR cohort.
- `gca_to_gcf_lookup.py` — accession resolver.
- Slurm scripts: `slurm_scripts/collect_bakrep_samples.py`,
  `slurm_scripts/collect_ncbi_datasets_samples.py`, `slurm_scripts/download_bakrep.sh`,
  `slurm_scripts/download_ncbi_datasets.sh`.

---

## 15. Reference scripts (one-look index)

| Script | Purpose |
|---|---|
| [`metadata_collation.py`](pp/metadata_collation.py) | ENA TSV + ready_to_merge → intermediate |
| [`qc_add_metadata.py`](pp/qc_add_metadata.py) | + QC Excel sheets (bakrep, Refseq, NCTC, kleborate, LINcode, FINAL_LIST) |
| [`metadata_curation.py`](pp/metadata_curation.py) | parse + categorise (host, isolation source, country, date) |
| [`add_paths_gff_fna_to_metadata.py`](pp/add_paths_gff_fna_to_metadata.py) | fill assembly/gff path columns |
| [`build_metadata_v2.py`](pp/build_metadata_v2.py) | v1 → v2 scaffold + pairing |
| [`merge_kleborate_into_metadata_v2.py`](pp/merge_kleborate_into_metadata_v2.py) | Kleborate overlay |
| [`merge_isescan_into_metadata_v2.py`](pp/merge_isescan_into_metadata_v2.py) | ISEScan overlay |
| [`build_paired_features.py`](pp/build_paired_features.py) | paired_index + lra_features + sr_features |
| [`rebuild_v2.sh`](pp/rebuild_v2.sh) | 8-step cascade orchestrator |
| [`run_kleborate_lra.py`](../bac_kleborate/run_kleborate_lra.py) | LRA Kleborate Slurm runner |
| [`run_isescan_lra.py`](../bac_isescan/run_isescan_lra.py) | LRA ISEScan Slurm runner |
| [`parsing.py`](../bac_kleborate/parsing.py) | Kleborate virulence/AMR call-string parsers |

History of the v2 build is archived in
[`bac_data/completed_pipelines/`](../bac_data/completed_pipelines/).

---

## 16. Contact

For metadata changes: **contact David**. Pipeline edits should land in the canonical scripts
above; ad-hoc TSV edits will be overwritten on the next cascade run.

---

## 17. Where this file lives + cross-refs (for maintenance)

**Canonical source of truth** (the file you're reading):

- Local repo: `~/developer/BacHGT/src/bac_metadata/METADATA_v2_README.md`
- HPC checkout (mirrored via git push/pull): `~/workspace/BacHGT/src/bac_metadata/METADATA_v2_README.md`

**Mirror sitting next to the data** (so colleagues landing on HPC find it):

- HPC sibling of the TSV: `<project_k>/david/final/METADATA_v2_README.md`
  *(= `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/METADATA_v2_README.md`)*
- HPC stub (short pointer file): `<project_k>/david/final/README.md` — directs readers here.

**Cross-references** (places that link to this README — update these if the README is renamed
or moved):

| File | Section / context |
|---|---|
| [`~/.claude/CLAUDE.md`](~/.claude/CLAUDE.md) | global BacHGT ecosystem block — link to canonical |
| [`~/developer/BacHGT/CLAUDE.md`](~/developer/BacHGT/CLAUDE.md) | monorepo CLAUDE.md — "Metadata" section |
| [`~/developer/BacHGT/src/bac_metadata/CLAUDE.md`](~/developer/BacHGT/src/bac_metadata/CLAUDE.md) | subpackage CLAUDE.md — "Read first" callout |
| [`~/developer/BacPredict/CLAUDE.md`](~/developer/BacPredict/CLAUDE.md) | sibling repo — §0.3 "Metadata source" |
| `<project_k>/david/final/README.md` (HPC stub) | HPC-side discoverability — points at this canonical doc |

**Maintenance flow.** If the README is **edited in place**: re-rsync to the HPC sibling
(`<project_k>/david/final/METADATA_v2_README.md`) so colleagues see the latest. If the README is
**renamed or moved**: update each of the cross-refs above. If a new cross-ref is added (e.g. a
new sibling repo's CLAUDE.md), append it to this table so future moves stay synchronised.
