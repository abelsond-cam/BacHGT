# Whole-field declines: why the grader didn't fire where the curator filled uniform

13 (study, field) pairs the curator annotated whole-field-uniform but our step-a missed — **4238 gap samples**. The grader justified each decline in its current pitch (Sonnet); an adversarial adjudicator (Opus) then ruled whether it is a fixable rubric **rule_gap** or a fetch/coverage/correct-decline cause.

## by grader blocking_category

| blocking_category | pairs | gap samples |
|---|---|---|
| no_paper_text | 7 | 1628 |
| value_below_coverage_threshold | 1 | 1167 |
| value_not_uniform_in_paper | 3 | 1059 |
| value_absent_from_evidence | 1 | 258 |
| value_multi_token_or_range | 1 | 126 |

## by adjudicator verdict

| verdict | pairs | gap samples |
|---|---|---|
| fetch_limited | 9 | 2259 |
| curator_overcollapsed | 3 | 1428 |
| rule_gap | 1 | 551 |

## actionable rule gaps (1 pairs, 551 gap samples)

Bring these to David for an `attributes.yaml` decision (rubric changes are his call):

- **PRJNA845975 / isolation_source** (gap 551, curator=`bacteremia`): The rule only fires when every isolate literally shares one identical source token; it gives no way to assign a single whole-project value when all isolates come from a fixed compound clinical specime
  - proposed clause: _If all isolates are drawn from the same fixed set of sterile clinical specimen types describing one invasive-disease cohort (e.g. 'blood and/or CSF'), treat that shared specimen description as a singl_

## per-decline detail

| study | field | gap | curator | fulltext | would_now | category | verdict |
|---|---|---|---|---|---|---|---|
| PRJEB42462 | isolation_source | 1167 | blood | pdf | False | value_below_coverage_threshold | curator_overcollapsed |
| PRJNA845975 | isolation_source | 551 | bacteremia | pdf | False | value_not_uniform_in_paper | rule_gap |
| PRJNA603790 | isolation_source | 445 | intestinal | none | False | no_paper_text | fetch_limited |
| PRJEB33565 | isolation_source | 373 | blood | none | False | value_not_uniform_in_paper | fetch_limited |
| PRJEB46513 | isolation_source | 258 | blood | none | False | value_absent_from_evidence | fetch_limited |
| PRJNA341927 | isolation_source | 243 | stool | none | False | no_paper_text | fetch_limited |
| PRJEB1563 | isolation_source | 170 | blood | none | False | no_paper_text | fetch_limited |
| PRJNA804332 | isolation_source | 135 | rectal swab | europepmc_fulltext | False | value_not_uniform_in_paper | curator_overcollapsed |
| PRJEB20799 | isolation_source | 37 | blood | none | False | no_paper_text | fetch_limited |
| PRJEB29143 | collection_date | 496 | 2016/06/30 | none | False | no_paper_text | fetch_limited |
| PRJEB36486 | collection_date | 200 | 2018-02-01 | none | False | no_paper_text | fetch_limited |
| PRJEB12699 | collection_date | 126 | 2003/01/01 | none | False | value_multi_token_or_range | curator_overcollapsed |
| PRJEB20799 | collection_date | 37 | 2016/06/01 | none | False | no_paper_text | fetch_limited |
