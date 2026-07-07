# M. abscessus — final curated + categorised master

`data/curated/metadata_curated_master_final.tsv` — **6455 samples × 133 studies × 34 columns**.
Produced by `engine.cli.categorise reconcile` (Phase D): agentic host/isolation_source categories
+ cross-column reconcile + binary `cf_status` + `pp.metadata_curation` country/date normalisation.

## New fields created (vs the fill master)
`host_parsed`, `host_category`, `isolation_source_parsed`, `isolation_source_category`
(agentic categoriser) · `country_parsed`, `region`, `collection_date_parsed`, `year_parsed`,
`collection_year` (legacy geo/date parsers). `cf_status` reconciled in place (binary).

## cf_status (binary — CF vs non-CF)
| value | n | % |
|---|---|---|
| CF | 3721 | 57.6% |
| (blank) | 1729 | 26.8% |
| non-CF | 1005 | 15.6% |

Phase D recovered 31 previously-blank samples from host strain codes (CF*→CF ×17; BX/COPD/NCF/NON→non-CF ×14)
and folded the `Non-CF` case variant (×320) into `non-CF`.

## host_category
| value | n | % |
|---|---|---|
| human | 6115 | 94.7% |
| (blank) | 257 | 4.0% |
| environment | 82 | 1.3% |
| wild animals | 1 | 0.0% |

The 82 `water_environment` samples (household plumbing) were relabelled `human`→`environment`;
their host strain codes are preserved in `host_parsed`, and CF-household water keeps `cf_status=CF`.

## isolation_source_category
| value | n | % |
|---|---|---|
| sputum | 2462 | 38.1% |
| respiratory_unspecified | 2184 | 33.8% |
| (blank) | 913 | 14.1% |
| NA | 321 | 5.0% |
| skin_soft_tissue_wound | 263 | 4.1% |
| water_environment | 82 | 1.3% |
| lower_respiratory_bronchoscopy | 80 | 1.2% |
| pleural_body_fluid | 51 | 0.8% |
| lung_tissue | 20 | 0.3% |
| lymph_node | 19 | 0.3% |
| eye_ear | 17 | 0.3% |
| bone_joint_deep_tissue | 12 | 0.2% |
| extrapulmonary_unspecified | 11 | 0.2% |
| blood | 9 | 0.1% |
| clinical_device_surface | 6 | 0.1% |
| gastrointestinal_urinary | 5 | 0.1% |

## region
| value | n | % |
|---|---|---|
| W. Europe | 2036 | 31.5% |
| N. America | 1853 | 28.7% |
| (blank) | 969 | 15.0% |
| E. Asia | 914 | 14.2% |
| Oceania | 435 | 6.7% |
| Central & S. America | 210 | 3.3% |
| E. Europe | 31 | 0.5% |
| M. East, Central Asia | 4 | 0.1% |
| Holland | 3 | 0.0% |

## Audit trail
- `study_lv_attributes/categorisation/reconcile_audit.tsv` — every cross-column + normalise reassignment.
- `study_lv_attributes/categorisation/reconcile_escalations.tsv` — fill conflicts (0 this run).
