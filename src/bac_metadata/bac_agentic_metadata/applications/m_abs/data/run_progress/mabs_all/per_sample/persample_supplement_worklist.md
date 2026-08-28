# Per-sample supplementary worklist — which studies need a manual supp-table fetch

1 studies with a per-sample backlog > 50. The LLM read the paper we hold and judged whether it carries a per-isolate table (iso/host/date keyed by an ID); `mech` is the engine's mechanical reason per-sample yielded 0. **Download the supplementary file of the FETCH_SUPP rows as `<acc>.xlsx` into `manual_download_supp/`.**

- **FETCH_SUPP** — paywalled + has a per-isolate table → fetch its supplementary file by hand.
- **OA_INVESTIGATE** — open-access + has a table but per-sample extracted nothing → a fetch/parse bug.
- **SKIP** — paper has no per-isolate table (no per-sample data to recover).
- **NO_PAPER** — no full text yet (resolve the paper first).
- **SUPP_PRESENT** — a manual supp file is already on disk; per-sample consumes it next run.

| action | study | gap | fields short | mech | has table | table fields | ref | paper | save as |
|---|---|---|---|---|---|---|---|---|---|
| SKIP | PRJNA1209868 | 57 | cf_status,host,isolation_source | no_supp | no |  |  | europepmc_fulltext / PMC12057340 | `PRJNA1209868.xlsx` |
