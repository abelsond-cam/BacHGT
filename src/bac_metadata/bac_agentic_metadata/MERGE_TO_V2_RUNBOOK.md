# Runbook — combine the agentic Klebsiella metadata into metadata_v2

**Status: scoped, ready to run on CSD3 (where v2 lives). Not yet executed.** State authority:
[`PROJECT_STATE.md`](../../../PROJECT_STATE.md) Layer B. Policy decisions of record (2026-07-22): combine =
**blank-fill + adjudicated overwrites**; re-normalisation = **v2's hardcoded `pp/metadata_curation.py`
parse/categorise**; this round is **Klebsiella-only**.

> ⚠️ **Gates before any write into production metadata_v2** (`METADATA_v2_README.md` §16 = contact David before
> a rebuild): (1) the study-level **adjudication sign-off** must be complete (`david_verdict` filled in
> `diagnostics/adjudication_review_queue.tsv`, 16 rows); (2) the per-sample overwrite policy must be chosen
> (see Decisions). Run the prototype/demo steps first; treat the parse/categorise rebuild as the careful step.

## Inputs & the v2 target
- Agent master (regenerable, gitignored): `…/klebsiella/data/curated/metadata_curated_master.tsv`
  (96,291 samples / 1,912 studies) + its `study_type_excluded` removal flag (78 studies / 1,489 samples).
- The reference v1 overlay already built: `…/curated/metadata_curated_master_merged.tsv` (90,903 rows,
  human > agent > ENA) — proves the mechanism; it is **not** v2.
- **v2 target (CSD3):** `/home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv`
  (86,398 rows × 505 cols; row key `Sample`; SR↔LR via `sr_biosample`).
- On CSD3, ensure the master is present first (it is gitignored, so regenerate if the checkout lacks it):
  `python -m …engine.cli.accumulate --tags train,test,tail100,tail50_99,tail25_49,tail10_24,sub10`.

## Step 1 — Blank-fill onto v2 (safe; the prototype)
Reuse `engine.accumulate.merge_into_canonical` (joins on `sample_accession`, human `_parsed` > agent > ENA,
writes the agent's raw value into the bare field column, flags each with `<field>_agent_filled`):

```bash
python -m bac_metadata.bac_agentic_metadata.engine.cli.accumulate \
  --tags train,test,tail100,tail50_99,tail25_49,tail10_24,sub10 \
  --canonical /home/dca36/rds/rds-floto-bacterial-4k08a2yyQLw/david/final/metadata_v2_all_samples_and_columns.tsv \
  --gold-suffix _parsed
```
**Verify:** output row count == 86,398 (unchanged); the linkage/typing/AST columns (`sr_biosample`,
`lra_gca`/`lra_gcf`, `sr_*`/`lr_*`, `IS_*`, `*_AST`) are byte-identical to the input v2 (diff the column set +
a checksum of those columns); `<field>_agent_filled` flags present; agent fills land only where the v2
`_parsed` cell was blank AND a `sample_accession` matched (orphan-LR rows, ~2,581, and RefSeq/NCTC untouched).
Confirm `sr_shadow_for_lra.tsv` reconciliation (README §9) is undisturbed.

## Step 2 — Study-level overlay + removal flag
`merge_into_canonical` overlays only the four per-sample fields. Separately overlay, keyed by
`study_accession`: `study_setting`, `amr_study` (v2 already carries these — README §10), and add the
`study_type_excluded` removal flag (78 studies / 1,489 samples). Precedence per the overwrite policy below.

## Step 3 — Adjudicated overwrites (gated on sign-off; policy TBD)
Blank-fill (Step 1) never touches a curated value. To also apply the agent's **proven** improvements:
- **Study-level (16 candidates):** finish `review_adjudication --interactive` so `david_verdict` is filled in
  `diagnostics/adjudication_review_queue.tsv`; apply only the rows David ruled for the agent.
- **Per-sample (3,105 candidates:** isolation_source 2,037 · collection_date 1,014 · host 38 · country 16 —
  the gated vague→specific overwrites from §5c of the wrap-up). These need a per-cell review policy (Decisions)
  before any are applied over a curated v2 value.

## Step 4 — Re-run v2's parse/categorise (the careful step; README §16)
Agent fills are RAW, so v2's `*_parsed` / `*_category` / `region` / `year_parsed` / `collection_year` are stale
for every filled cell. Re-normalise with **v2's own** `pp/metadata_curation.py` (`parse_country`/
`categorise_region`, `parse_collection_date`, `parse_host`/`categorise_host`, `parse_isolation_source`/
`categorise_isolation_source`, incl. the cross-field host←iso inference) — keeps v2's documented vocabulary
byte-stable. **Two architectures — David decides (Decisions):**
- **A. Inject-then-rebuild (recommended):** put the agent fills in at the v1 stage and run the idempotent
  `pp/rebuild_v2.sh` cascade — it re-derives *all* v2 extra columns (pairing, Kleborate, ISEScan, AST) and
  re-parses consistently, so nothing is lost. It IS a full v2 rebuild → **contact-David gate (README §16)**.
- **B. In-place re-parse:** blank-fill the existing v2 (Steps 1–3) and re-run only the parse/categorise
  functions over the changed cells. Avoids a full rebuild but is surgical and must be validated cell-by-cell.

## Step 5 — Demonstrate improvement (already tooled)
```bash
python -m bac_metadata.bac_agentic_metadata.evaluation.completeness_by_split \
  --truth /home/dca36/rds/.../david/final/metadata_v2_all_samples_and_columns.tsv
```
→ `scorecard/final_completeness_raw_agent_gold.{md,tsv}` (raw → agent → v2 deltas). Expect agent ≥ v2 per field
(headline already: country +3.6, date +7.9, iso +6.3, host +10.4 pp) with no regression outside the RefSeq
carve-out. Also `validate_backfill_values` for the blank-fill vs overwrite split.

## Decisions for David
1. **Parse/categorise architecture** — A (inject-then-`rebuild_v2.sh`, clean but a full rebuild) vs B (in-place
   surgical re-parse). Recommended: **A**, gated per README §16.
2. **Per-sample overwrite policy** — which of the 3,105 gated overwrites qualify to replace a curated v2 value
   (e.g. only where an independent review confirms the agent's vague→specific move). Blank-fill alone needs no
   decision.
3. **Where the run happens** — CSD3 (v2 is there). Heavy steps (rebuild cascade) → `sbatch`, not the login node.

## Verification (end state)
Row count 86,398 preserved · all v2-only columns intact · `*_parsed`/`region`/`*_category` populated for
agent-filled cells · completeness agent ≥ v2 (no regression outside RefSeq) · escalation-conservation +
overwrite-radius still green on the agent side.
