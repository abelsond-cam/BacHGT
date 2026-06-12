# BacHGT — plans & tracker

Living plan for the BacHGT monorepo, organised by current workstream. Light capture
for now — faithful record of what needs doing; subpackage-level detail (and the
relevant `src/bac_*/CLAUDE.md` additions) get fleshed out in a later pass. Global
conventions: root [CLAUDE.md](CLAUDE.md). Supersedes the retired
[`~/.claude/PROGRAM_PLAN_2026-05-30.md`](../../.claude/PROGRAM_PLAN_2026-05-30.md)
(still-live ARIBA / reverse-IS detail carried forward below).

Recorded 2026-06-12. Items are not yet started unless noted.

---

## 1. M. abscessus metadata — new species, new effort

Lives in [`src/bac_metadata/m_abs/`](src/bac_metadata/m_abs/). First non-KPSC effort.
Source file deposited: `ATB_metadata_Mabs_2025_release.xlsx`.

- [ ] Collate **`host_CF`** — CF vs non-CF — from the metadata.
- [ ] Also target **collection date**, **country**, and **isolation source**.

*Open: David to describe the exact collation method before building anything.*

## 2. Re-run complete-genome vs short-read analysis (Kleborate, ISEScan, geNomad)

> ⚠️ **Corruption finding.** The assembly + GFF file set used for the CG-vs-SR
> comparison was corrupted — roughly **half the "long-read" rows actually pointed at
> short reads**. Every LR-vs-SR difference conclusion (Kleborate, ISEScan, geNomad)
> is therefore erroneous and must be regenerated. This invalidates the retired
> program plan's "10–20 % per-locus pickup deficit" headline.

Touches `bac_complete_genomes` (+ `bac_metadata` for the clean collation).

- [ ] Re-collate assembly + GFF **from `metadata_v2`**, keeping only rows where **all
  four files exist** — `sr_assembly_file`, `sr_gff_file`, `lr_assembly_file`,
  `lr_gff_file` — then filter to `is_complete` etc.
- [ ] Regenerate the histograms, comparison ratios, and relative-frequency
  tables/plots (e.g. AMR-gene frequencies; geNomad virus relative frequencies).
- [ ] Re-derive and revisit the LR-vs-SR conclusions on the clean comparison set.

## 3. Invasive disease (blood vs faeces isolation source first)

- [ ] **Hotspot rates by isolation source.** Compare per-source hotspot rates against
  the whole-population background mutation rate at each locus as control → Chi-sq for
  hotspots strongly associated with invasive disease. *Blocked on Aaron uploading
  hotspots to HPC.*
- [ ] **Pyseer unitig GWAS (KPSC-wide).** From variant calls, tabulate mutation loci
  vs the reference genome per sample; filter low-frequency loci; compute pairwise
  Jaccard distances. Combined with unitigs → whole-of-KPSC GWAS on unitigs.
- [ ] **Pyseer presence/absence GWAS.** Same variant calls + the per-SL Panaroo we
  have → presence/absence GWAS.
- [ ] **Gubbins vs phage/virus families.** Compare Gubbins trees against the
  phage/virus families being detected.

## 4. MGE characterisation (geNomad / ISEScan / ICEberg)

Shared effort — **Wendy** on geNomad-driven characterisation, **Dave** on the
comparative / conjugative-element side.

- [ ] *(Wendy)* Characterise arrangements / clusters / families of both **virus and
  plasmids** from the geNomad results.
- [ ] *(Dave)* Analyse how different these are across **SLs / CGs**.
- [ ] *(Dave)* Download the **ICEberg** dataset for conjugative elements; run HMM /
  BLAST against it to check conjugative regions in the chromosome and inside
  plasmids / viruses.
- [ ] *(Dave)* Classify ISEScan + ICEberg hits by whether they are part of plasmids /
  viruses.
- [ ] *(Dave)* Locate the **AMR genes** relative to ICE, ISE, and geNomad calls, and
  against Panaroo neighbourhoods / contig boundaries.
- [ ] *(Dave)* Assess how **contig boundaries** fragment these sections, compared to
  reference / complete genomes.

## 5. MGEfinder on complete vs short-read genomes

- [ ] Run MGEfinder on complete vs short-read genomes; measure the **extra pickup
  rate** and compare it to ISEScan and others.
- [ ] If improved, consider running it more broadly.

## 6. Whole-genome ARIBA

- [ ] Same comparison as item 5, applied across the **whole genome with ARIBA**.
  (Carries forward the retired program plan's ARIBA-rescue intent.)
