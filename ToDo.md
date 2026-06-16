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

## 1b. Agentic metadata-curation engine (`bac_agentic_metadata`)

Reusable species-agnostic engine; Klebsiella is the validation site (test fold sealed).
Stages 1–2 built + validated on train+val — full walkthrough, results and design in
[`src/bac_metadata/bac_agentic_metadata/PIPELINE_PLAN.md`](src/bac_metadata/bac_agentic_metadata/PIPELINE_PLAN.md)
§6b and [`STAGE2.md`](src/bac_metadata/bac_agentic_metadata/STAGE2.md). Current results:
grading **amr_study 0.94 / study_setting 0.98**; finding **0.62→0.75 adjudicated**; method-(a)
backfill recall **country 0.78 / host 0.83** (date/source → method-b backlog).

Forward plan (in order):

- [ ] **1 — Apply method-(a) `country`/`host` backfill** (the covered cases) to the table — first write-back.
- [ ] **2 — Value-correctness**: bring in per-sample `metadata_v2` to verify proposed raw values, not just targeting.
- [ ] **3 — Method-(b)**: per-sample-table extraction for the ~44 `collection_date`/`isolation_source` gaps
  (needs sample-accession↔paper-table mapping; the deferred `partial` path).

Deferred follow-ups (smaller):

- [ ] 2 rubric over-steers (`PRJEB58136` mixed→surveillance; `PRJNA604975` mixed→hospital) + a study_setting wording tweak.
- [ ] 2 new GT-correction candidates to verify + add to the overlay (`PRJNA789565`→surveillance, `PRJEB30134`→mixed).
- [ ] `PRJEB28400` sample counts → ENA-deposit (1950); audit other screened-but-subset-deposited studies.
- [ ] Re-grade *with* `sizing_first` (postdates the last re-grade); multi-organism-umbrella taxon-aware finder rule.
- [ ] Eventually: sealed **test-fold** final measured-agreement run; the ~7k *M. abscessus* application (§1).

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

## 3. Invasive disease GWAS — moved to BacPredict

The hotspot-rate and pyseer GWAS analyses (the blood-vs-faeces invasive-disease
signal) now live in **BacPredict** under `src/bac_pyseer/` — tracked in
[`BacPredict/ToDo.md`](../BacPredict/ToDo.md). This is variant-call / GWAS work, so
it is compartmentalised there alongside the rest of the pyseer effort. The related
phage/virus inheritance comparison stays in BacHGT under §4.

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
- [ ] *(Dave)* Compare **Gubbins trees** against the detected phage/virus families —
  the order of inheritance of phage / virus from geNomad.

## 5. MGEfinder on complete vs short-read genomes

- [ ] Run MGEfinder on complete vs short-read genomes; measure the **extra pickup
  rate** and compare it to ISEScan and others.
- [ ] If improved, consider running it more broadly.

## 6. Whole-genome ARIBA

- [ ] Same comparison as item 5, applied across the **whole genome with ARIBA**.
  (Carries forward the retired program plan's ARIBA-rescue intent.)
