# Runbook — combine the agentic Klebsiella metadata into metadata_v2

**Status: tooling BUILT + verified locally (B1–B3, 2026-08-27); the CSD3 run is NOT yet executed.** State
authority: [`PROJECT_STATE.md`](../../../PROJECT_STATE.md) Layer B. Policy decisions of record (2026-07-22):
combine = **blank-fill + adjudicated overwrites**; re-normalisation = **v2's hardcoded `pp/metadata_curation.py`
parse/categorise**; architecture = **A (inject at v1 + `rebuild_v2.sh`, separate + reviewable)**; this round is
**Klebsiella-only**. David approved the overwrite candidates — including the country changes — on 2026-08-27.

> ⚠️ **Gate before any write into production metadata_v2** (`METADATA_v2_README.md` §16 = contact David before a
> rebuild). The inject → `rebuild_v2.sh` IS a full v2 rebuild. Run the two-step order below; treat the rebuild as
> the careful step; heavy steps via `sbatch`.

## The two-step design (David, 2026-08-26)
1. **Step (i) — blank-fill first**, a reviewable v2 pass with all the numbers. Blank-fills are safe (they only
   populate empty cells) and need no sign-off.
2. **Step (ii) — surface the overwrites** as a reviewable artefact (the only writes that replace an existing
   value). **Done + reviewed.**
3. **Step (iii) — apply the approved overwrites** only after David's check.

## Built tooling (all committed, ruff clean, unit-tested; verified on the local v1 mirror)
- **B1 `evaluation/report_v2_overwrites.py`** → `data/v2_overwrite_candidates.{tsv,md}` — step (ii). Every
  per-sample overwrite (ENA value non-blank) with `ENA old → agent new` + evidence + paper link, classified
  (date same-year refinement vs year-changed/unparsed; categorical vs no-change; neutral `shortened`).
  **Reconciles EXACT to wrap-up §5c: 3,105 candidates** (iso 2,037 · date 1,014 · host 38 · country 16), 3,015
  genuine changes. **This is the artefact David reviewed.**
- **B2 `combine/inject_agentic_into_v1.py`** → injected v1 + `_numbers.md` — step (i). Blank-fill (via engine
  `merge_into_canonical`, human `_parsed` > agent > ENA) + re-parse of the filled rows only (v1's own
  parse/categorise, `main` order) + evolutionary handling (`evolutionary_lab_sample`, `kpsc_final_list=False`,
  SR-only vs LRA-bearing split). Verified: row count preserved, blast radius = filled rows only, no curated
  value overwritten.
- **B3a `combine/apply_gated_overwrites.py`** → step (iii). Applies David's approved subset over existing values
  (`<field>_agent_overwrote` flag) + re-parses the changed rows. Refuses non-clinical fields; reports unmatched.
- **B3b `combine/delist_evolutionary.py`** → the post-Kleborate re-clamp. Dry-run by default; `--apply` forces
  `kpsc_final_list`/`lra_final_list`/`is_variant_called=False` and counts-then-clears
  `is_complete`/`is_hybrid`/`is_reference_genome` on `evolutionary_lab_sample` rows; leaves `is_kpsc` (taxonomic).

## Inputs & the v2 target
- Agent master (regenerable, gitignored): `…/klebsiella/data/curated/metadata_curated_master.tsv`
  (96,291 samples / 1,912 studies) + its `study_type_excluded` removal flag (78 studies / 1,489 samples).
- v1 canonical (the base of v2; on the OneDrive mirror, 444 cols, 90,903 rows):
  `…/project_k/data/final/metadata/metadata_final_curated_all_samples_and_columns.tsv`.
- **v2 target (CSD3):** `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv`
  (86,398 rows × 505 cols; row key `Sample`; SR↔LR via `sr_biosample`). **HPC-only — not on the mirror.**
- On CSD3, ensure the master is present first (gitignored — regenerate if the checkout lacks it):
  `python -m …engine.cli.accumulate --tags train,test,tail100,tail50_99,tail25_49,tail10_24,sub10`.

## CSD3 run order (architecture A; heavy steps → `sbatch`; README §16 gate before starting)
```bash
# 0. master present? else accumulate (above). Point BACHGT_PROJECT_K_ROOT at the project_k tree.

# 1. STEP (i) — inject blank-fills + re-parse filled rows + evolutionary handling, at the v1 stage.
python -m bac_metadata.bac_agentic_metadata.combine.inject_agentic_into_v1 \
    --out <work>/metadata_v1_injected.tsv
#    → review <work>/metadata_v1_injected_numbers.md (blank-fills per field, evolutionary SR-only/LRA split).

# 2. REBUILD — run the idempotent cascade on the injected v1 (re-derives ALL v2-only columns: pairing,
#    Kleborate, ISEScan, AST). rebuild_v2.sh step 1 is build_metadata_v2, which reads --metadata-v1
#    (default DEFAULT_METADATA_V1 = DATA_ROOT/david/final/metadata_final_curated_all_samples_and_columns.tsv)
#    and does NOT re-parse bulk rows — it copies v1's *_parsed columns through (v2 = meta.copy()). So the
#    injected v1 MUST be the --metadata-v1 input. rebuild_v2.sh does not forward that arg, so either:
#      (a) stage the injected file at DEFAULT_METADATA_V1 (back up the original first), then run rebuild_v2.sh; OR
#      (b) run build_metadata_v2 --metadata-v1 <injected> manually, then the remaining rebuild_v2.sh steps.
#    Decide the staging with David.  (heavy → sbatch; README §16 gate)
bash src/bac_metadata/pp/rebuild_v2.sh

# 3. STEP 2b — post-Kleborate evolutionary delist (the additive kpsc rule re-admits LRA-bearing evo rows).
python -m bac_metadata.bac_agentic_metadata.combine.delist_evolutionary --v2 <rebuilt_v2.tsv>          # dry-run: SURFACE the quality-flag counts
python -m bac_metadata.bac_agentic_metadata.combine.delist_evolutionary --v2 <rebuilt_v2.tsv> --apply   # after reviewing the counts

# 4. DEMONSTRATE — completeness raw ENA → agent → v2, no regression outside the RefSeq carve-out.
python -m bac_metadata.bac_agentic_metadata.evaluation.completeness_by_split --truth <rebuilt_v2.tsv>

# 5. STEP (iii) — apply the approved overwrites (David reviewed v2_overwrite_candidates.md → an approved subset).
python -m bac_metadata.bac_agentic_metadata.combine.apply_gated_overwrites \
    --canonical <rebuilt_v2.tsv> --approved <approved_overwrites.tsv> --out <v2_final.tsv>
# 6. RE-DEMONSTRATE completeness on <v2_final.tsv>.
```
> **Note on ordering:** `apply_gated_overwrites` writes + re-parses in place on the rebuilt v2, so step 5 does
> not need a second full `rebuild_v2.sh`. If David prefers the overwrites to also flow through the cascade,
> apply them at the v1 stage (step 1's output) instead and re-run the rebuild — decide with David.

## Columns touched + how overwrites are checked
- **Blank-filled** (agent fills only v2-BLANK cells; never a curated value — human `_parsed` > agent > ENA):
  `country`, `collection_date`, `isolation_source`, `host`. (Where the bare cell held a raw-but-unparsed ENA
  value, the agent value wins per human > agent > ENA — surfaced in the B2 numbers report, still not a curated
  overwrite.)
- **Study-level overlay** (blank-fill; NO overwrites — the adjudication ruled `manual` on all 16): `study_setting`,
  `amr_study`.
- **New / flag columns written:** `evolutionary_lab_sample`; `<field>_agent_filled`; `<field>_agent_overwrote`;
  and the flag flips on evolutionary rows (`kpsc_final_list`, `lra_final_list`, `is_variant_called`,
  `is_complete`, `is_hybrid`, `is_reference_genome`).
- **Potentially overwritten** (curated value replaced — the per-sample gated fills, ONLY the subset David
  approved): `isolation_source` 2,037 · `collection_date` 1,014 · `host` 38 · `country` 16 (3,105 candidates;
  3,015 genuine). See `data/v2_overwrite_candidates.{tsv,md}`.
- **Re-derived, not merged** (parse/categorise on changed rows + rebuild cascade): `*_parsed`, `*_category`,
  `region`, `year_parsed`, `collection_year`.
- **Untouched** (pass through / re-derived by the cascade): all SR↔LR linkage, Kleborate, Bakta, ISEScan, AST,
  CheckM2 columns.

**How overwrites are checked — three layers:** (1) blank-fill structurally cannot overwrite a curated value
(human always wins — verified: 0 curated bare cells changed); (2) each candidate is surfaced in the B1 artefact
with evidence + paper for David's sign-off, and `apply_gated_overwrites` writes ONLY the approved subset with a
`_agent_overwrote` provenance flag; (3) the overwrite-radius gate (`engine/overwrite_radius.py`) confirms no
protected value changed beyond the sanctioned exceptions.

## Decisions
1. **Parse/categorise architecture** — ✅ **A** (inject at v1 + `rebuild_v2.sh`, separate + reviewable).
2. **Per-sample overwrites** — ✅ David approved the candidates (incl. the 16 `Switzerland→…` country changes,
   PRJNA744003) on 2026-08-27. The exact approved subset (a filtered copy of `v2_overwrite_candidates.tsv`) is
   what step 5 applies. Study-level: adjudication fully reviewed (16 rows: 14 `manual`, 2 `skip`) → **none**.
3. **`is_kpsc` on evolutionary rows** — ⚠ OPEN: the runbook Step 2b + B2 leave `is_kpsc` alone (taxonomic — a
   lab-evolved K. pneumoniae is still KPSC; only cohort membership is removed). The earlier plan text mentioned
   clamping `is_kpsc=False` too; `delist_evolutionary` deliberately does NOT. **Confirm with David.**
4. **Where it runs** — CSD3 (v2 is there). Heavy steps → `sbatch`.

## Verification (end state)
Row count 86,398 preserved · all v2-only columns intact · `*_parsed`/`region`/`*_category`/`collection_year`
populated for changed cells · completeness agent ≥ v2 (no regression outside RefSeq) · `evolutionary_lab_sample`
rows out of the cohort with quality flags cleared · escalation-conservation + overwrite-radius green.
