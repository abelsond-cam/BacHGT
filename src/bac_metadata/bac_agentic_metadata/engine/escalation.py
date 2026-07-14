"""Human-in-the-loop escalation tier for whole-field backfill — ask the curator on a *tight* near-miss.

When the grader declines a single whole-project (whole-field) value, the field's values fall into two very
different shapes, and only one is worth a human's time:

* a **tight, closely-related cluster** that just misses one clean rubric label — all-invasive specimens
  (blood + CSF), countries in one close region, a short *older* date span — where a human could reasonably
  accept one representative value;
* a **genuinely wide mix** — isolates from 37 countries; UK + Malawi + Argentina; blood + urine +
  respiratory + wound; urine + sputum + blood + rectal — which has no single label and belongs to
  per-sample extraction (per-sample), not a whole-field value.

The order David set is: **per-sample runs first** — if per-sample data is available the question is already
answered. Every still-incomplete declined field is then surfaced for review; the tight near-misses carry a
suggested value, the wide mixes are surfaced with a blank suggestion (David wants to confirm they are all
handled correctly before any auto-skip). Each is packaged as an :class:`EscalationItem` (the grader's quote,
a paper excerpt, the candidate value, the gap it closes) so the curator decides once; those decisions later
become rubric clauses.

Detection, per ``(study, field)`` the grader declined whole-field:

1. **Gate by gap** (cheap, deterministic): blank ENA cells for that field, placeholder-stripped. Skip at
   or below the threshold.
2. **Gate by per-sample**: skip if per-sample extraction already resolved the field (sample-level data
   answers it).
3. **Resolve** the near-miss (David, 2026-07-13):
   * **collection_date** — DETERMINISTIC, no LLM: the span was resolved at grade time
     (:func:`value_validity.resolve_date_span`); only a pre-2010 mid-range span carries a midpoint
     suggestion, everything else surfaces blank for review.
   * **country** — if the study's ENA countries collapse to ONE region (legacy
     :func:`pp.metadata_curation.categorise_region` buckets), DETERMINISTIC: adopt the dominant country
     (>=95%), else surface the region as a hint with a blank country suggestion.
   * **otherwise** — a cached LLM triage (:func:`classify_escalation_candidate`) applies the
     **>=95%-or-homogeneous-category** adopt/skip rule (``wide_mix_skip`` / ``tight_cluster_escalate`` /
     ``uniform_propose``), given the field's ENA value distribution so the 95% test is grounded in the data.

A suggestion is offered ONLY when the resolution escalates — a ``wide_mix_skip`` row carries no pre-fill, so
Enter-to-accept never writes an un-vouched value. The curator's confirmed answer is a whole-field proposal
(``whole_project: True``) applied through the **existing** :func:`backfill.apply_whole_field` path.

Species-agnostic: the application supplies an ``evidence_fn`` that turns an accession into a
:class:`StudyEvidence` bundle (paper text + EBI title/description + sizing), so the engine never knows how
a given application resolves a paper reference.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

import pandas as pd

from . import backfill
from .fulltext import FullText
from .grader import DEFAULT_MAX_CHARS, _build_system_prompt, _build_user_prompt
from .llm import LLMClient
from .spec import AttributeSpec

CLASSIFY_SCHEMA_NAME = "escalation_candidate_classification"

#: How the grader resolves a declined field for escalation triage.
RESOLUTIONS = [
    "wide_mix_skip",          # genuinely wide, unrelated mix → leave to per-sample extraction, do not ask
    "tight_cluster_escalate",  # closely-related cluster that just misses one label → ask the human
    "uniform_propose",        # on reflection the evidence does support one whole-project value
]

#: Resolutions that put the item in front of the curator.
ESCALATE_RESOLUTIONS: frozenset[str] = frozenset({"tight_cluster_escalate", "uniform_propose"})

#: Per-field term patterns used to pull the evidence sentences a curator needs (a heuristic, not a parser).
_FIELD_TERMS: dict[str, str] = {
    "isolation_source": (
        r"blood|bacterae?mia|sepsis|cerebrospinal|\bcsf\b|urine|urinary|catheter|sputum|respiratory|"
        r"bronch|endotracheal|wound|abscess|peritone|stool|f[ae]ces|faecal|fecal|rect|carriage|"
        r"screen|specimen|isolat(?:ed|es) from|sampl|source|site of"
    ),
    "collection_date": (
        r"\b(?:19|20)\d{2}\b|collect|sampl|isolat(?:ed|es)\s+(?:were\s+)?(?:collected|obtained)|"
        r"between|during|period|over\s+the|study\s+period"
    ),
    "country": (
        r"countr|nationwide|hospital|clinic|province|region|collected\s+in|isolat(?:ed|es)\s+from|"
        r"sites?\s+in|across\b"
    ),
    "host": r"\bpatient|human|animal|\bhost\b|clinical|carriage|coloni[sz]|inpatient|outpatient",
}

#: Sentence splitter for the excerpt (greedy run up to terminal punctuation).
_SENTENCE_RE = re.compile(r"[^.!?]*[.!?]")

#: Generic FALLBACK triage criteria. The application supplies its own policy prose at
#: ``escalation.triage_guidance`` in its attributes.yaml (Klebsiella does — the ">=95%-or-homogeneous-category"
#: rule with its invasive-vs-carriage priors); the engine only assembles + renders it. collection_date is NOT
#: triaged here (resolved deterministically upstream); country region clustering is computed deterministically.
_TRIAGE_GUIDANCE = (
    "Decide whether one clean whole-study value can represent this field. ADOPT a single value when EITHER:\n"
    "  (a) ONE value covers about 95% or more of the study's samples — a clear dominant value. If you cannot "
    "count exactly, adopt when the evidence makes it LIKELY one value is >=95%.\n"
    "  (b) the values are BELOW 95% but are HOMOGENEOUS within one closely-related category — then adopt the "
    "DOMINANT single value WITHIN that category:\n"
    "    * isolation_source: all specimens are invasive infection sites (blood, CSF, BALF / deep respiratory, "
    "deep wound / abscess, other normally-sterile sites) -> adopt the dominant invasive specimen (usually "
    "blood). Do NOT adopt if invasive sites are mixed with carriage / screening (rectal, stool, perirectal, "
    "nasal or skin colonisation) — that is a genuine WIDE mix.\n"
    "    * country: all countries lie within ONE geographic region (e.g. all Central America, all East Africa, "
    "all W. Europe) -> adopt the dominant country. (Region clustering is also computed deterministically and "
    "given to you below when it applies.)\n"
    "    * host: all hosts fall in one group (all human clinical; all domesticated animals) -> adopt the "
    "dominant host.\n\n"
    "Resolutions:\n"
    "- uniform_propose — case (a): one value is ~95%+ of the study.\n"
    "- tight_cluster_escalate — case (b): homogeneous within a closely-related category, dominant value adopted.\n"
    "- wide_mix_skip — a genuinely WIDE, unrelated mix with no >=95% dominant AND no homogeneous category "
    "(e.g. blood + urine + respiratory + wound; invasive sites mixed with rectal/stool carriage; UK + Malawi + "
    "Argentina across continents; human + animal + environmental). Do not ask — per-sample extraction handles it.\n\n"
    "For uniform_propose or tight_cluster_escalate, set representative_value to that single dominant value. It "
    "MUST be a SINGLE, PARSEABLE, CANONICAL value of the field, never a region, a list, or a concatenation:\n"
    "    * country: ONE country name (e.g. 'Malawi', 'Guatemala') — NOT a region/continent and NOT a join. If "
    "the countries cluster to one region but no single country is dominant, prefer wide_mix_skip (the engine "
    "surfaces the region separately for the curator).\n"
    "    * isolation_source: one specimen term (e.g. 'blood'); host: one host (e.g. 'human').\n"
    "Set representative_value null for wide_mix_skip. Use the ENA base distribution provided (counts per value) "
    "to apply the 95% test; for values that appear only in the paper, use the paper's own proportions. Give a "
    "one-line cluster_theme naming the cluster and why it is homogeneous or wide, plus a verbatim "
    "evidence_quote. Judge ONLY from the evidence above; do not guess."
)

#: Generic FALLBACK: a single value at/above this share of a study's non-blank samples is "dominant" and
#: adoptable whole-study. The application sets its own value at ``escalation.dominant_share`` (Klebsiella: 0.95,
#: David's ">=95%" rule). Used for the deterministic country region-cluster dominant-country test.
DOMINANT_SHARE = 0.95


def triage_guidance(spec: AttributeSpec | None) -> str:
    """Return the application's escalation triage prose (yaml ``escalation.triage_guidance``) or the default."""
    if spec is not None:
        txt = (spec.raw.get("escalation", {}) or {}).get("triage_guidance", "")
        if (txt or "").strip():
            return txt.strip()
    return _TRIAGE_GUIDANCE


def dominant_share(spec: AttributeSpec | None) -> float:
    """Return the application's dominant-value share threshold (yaml ``escalation.dominant_share``) or default."""
    if spec is not None:
        v = (spec.raw.get("escalation", {}) or {}).get("dominant_share")
        if v is not None:
            return float(v)
    return DOMINANT_SHARE

#: The region LABELS emitted by ``pp.metadata_curation.categorise_region`` (passthrough leaves an unrecognised
#: country as its own name, so only these count as a real "one region" cluster).
KNOWN_REGIONS: frozenset[str] = frozenset({
    "N. America", "Central & S. America", "W. Europe", "E. Europe", "Africa",
    "M. East, Central Asia", "E. Asia", "Oceania",
})


@dataclass
class StudyEvidence:
    """The evidence one accession was graded on — re-supplied by the application for the classify call.

    Parameters
    ----------
    fulltext
        The :class:`FullText` resolved for the study's paper (re-fetched from disk cache; empty if none).
    ena_title, ena_description
        EBI study title / description (the second evidence source).
    sizing_row
        ENA assessment sizing row surfaced to the model as context (may be empty).
    """

    fulltext: FullText
    ena_title: str
    ena_description: str
    sizing_row: dict


@dataclass
class EscalationItem:
    """One tight near-miss to put to the curator, with the background needed to decide.

    Parameters
    ----------
    study_accession, field
        The project accession and the per-sample field (one of :data:`backfill.FIELDS`).
    gap_samples
        Genuinely-blank ENA cells for this ``(study, field)`` — the completeness a decision would close.
    resolution
        The triage call (a :data:`RESOLUTIONS` value). Candidacy is deterministic, so ``wide_mix_skip`` rows
        are ALSO queued — surfaced for the curator to confirm rather than auto-dropped (David, 2026-07-13).
    suggested_value
        The single representative value to pre-fill — non-empty ONLY when the resolution escalates.
    cluster_theme
        One line naming the cluster and why it is homogeneous or wide (the rationale).
    grader_quote
        The verbatim evidence the grader cited.
    paper_excerpt
        2-4 sentences from the paper mentioning the field's terms (the evidence to read).
    fulltext_status
        How the paper text was sourced (``europepmc_fulltext`` / ``abstract`` / ``none`` / …).
    """

    study_accession: str
    field: str
    gap_samples: int
    resolution: str
    suggested_value: str
    cluster_theme: str
    grader_quote: str
    paper_excerpt: str
    fulltext_status: str
    escalate_trigger: str = ""  # WHY this escalated: 'big_decision', a triage resolution, or both ('+')
    region_hint: str = ""  # for country: the single region the study's countries cluster to when no dominant one


def _classify_schema() -> dict:
    """Schema for the tight-vs-wide escalation triage of one declined field."""
    return {
        "type": "object",
        "properties": {
            "resolution": {"type": "string", "enum": RESOLUTIONS},
            "representative_value": {"type": ["string", "null"]},
            "cluster_theme": {"type": "string"},
            "evidence_quote": {"type": "string"},
        },
        "required": ["resolution", "representative_value", "cluster_theme", "evidence_quote"],
        "additionalProperties": False,
    }


def classify_escalation_candidate(
    spec: AttributeSpec,
    llm: LLMClient,
    *,
    accession: str,
    field: str,
    fulltext: FullText,
    ena_title: str,
    ena_description: str,
    sizing_row: dict | None,
    prior_proposed: str | None,
    prior_quote: str,
    distribution_text: str = "",
    region_note: str = "",
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Triage one whole-field decline with David's >=95%-or-homogeneous-category adopt/skip rule.

    Presented in the grader's own pitch (so it reasons in-rubric) with the same evidence it graded on, the
    field's ENA base value distribution (``distribution_text`` — counts per value, so the 95% test is
    applicable to base-borne data), an optional deterministic ``region_note`` for country, plus the criteria.
    Returns the validated classification dict (see :func:`_classify_schema`): ``resolution``,
    ``representative_value``, ``cluster_theme``, ``evidence_quote``.
    """
    system = _build_system_prompt(spec)
    evidence = _build_user_prompt(
        accession=accession,
        fulltext=fulltext,
        ena_title=ena_title,
        ena_description=ena_description,
        sizing_row=sizing_row,
        max_chars=max_chars,
    )
    context = ""
    if distribution_text:
        context += f"\n\nENA BASE DISTRIBUTION for `{field}` in this study:\n{distribution_text}"
    if region_note:
        context += f"\n\n{region_note}"
    follow_up = (
        "\n\n=== FOLLOW-UP: escalation triage (this supersedes the grading instruction above) ===\n"
        f"Earlier you declined a single whole-project value for `{field}` (proposed_value="
        f"{prior_proposed!r}, evidence quote {prior_quote!r})." + context + "\n\n" + triage_guidance(spec)
    )
    return llm.complete_structured(
        system=system,
        user=evidence + follow_up,
        json_schema=_classify_schema(),
        schema_name=CLASSIFY_SCHEMA_NAME,
        schema_description="Tight-cluster-vs-wide-mix triage of one whole-field backfill decline.",
        model=model,
    )


def field_gap(raw_ena: pd.DataFrame, fields: tuple[str, ...], *, group_col: str = "study_accession") -> dict:
    """Count genuinely-blank ENA cells per ``(study, field)`` (placeholder-stripped), vectorised.

    Parameters
    ----------
    raw_ena
        Raw per-sample ENA table (``group_col`` + the field columns).
    fields
        Fields to count.
    group_col
        Study key (default ``"study_accession"``).

    Returns
    -------
    dict
        ``{(study_accession, field): n_blank}``.
    """
    gap: dict[tuple[str, str], int] = {}
    for f in fields:
        if f not in raw_ena.columns:
            continue
        blank = backfill.strip_placeholders(raw_ena[f]).isna()
        counts = blank.groupby(raw_ena[group_col]).sum()
        for acc, n in counts.items():
            gap[(str(acc), f)] = int(n)
    return gap


def _paper_excerpt(text: str, field: str, *, max_sentences: int = 4, max_chars: int = 700) -> str:
    """Return up to ``max_sentences`` sentences from ``text`` mentioning ``field``'s terms (or "")."""
    pat = _FIELD_TERMS.get(field)
    if not text or not pat:
        return ""
    rx = re.compile(pat, re.IGNORECASE)
    hits: list[str] = []
    for m in _SENTENCE_RE.finditer(text):
        sentence = m.group(0).strip()
        if sentence and rx.search(sentence):
            hits.append(re.sub(r"\s+", " ", sentence))
            if len(hits) >= max_sentences:
                break
    return " … ".join(hits)[:max_chars]


def _declined(backfill_field: dict) -> bool:
    """True iff the grader did NOT fire a whole-field value for this field (the escalation candidates)."""
    if bool(backfill_field.get("applies_whole_project")):
        return False
    return not (backfill_field.get("proposed_value") or "").strip()


def _field_nulls(spec: AttributeSpec | None, field: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the ``(null_tokens, null_patterns)`` for a field from the spec's categorisation block (or ())."""
    if spec is None:
        return (), ()
    cat = spec.raw.get("attributes", {}).get("categorisation", {}).get("fields", {}).get(field, {}) or {}
    return tuple(cat.get("null_tokens", []) or []), tuple(cat.get("null_patterns", []) or [])


def _field_distribution(
    raw_ena: pd.DataFrame, acc: str, field: str, spec: AttributeSpec | None, *, max_values: int = 20
) -> tuple[str, pd.Series]:
    r"""Return ``(rendered_text, freqs)`` — the study's ENA base value distribution for ``field``.

    ``freqs`` is the distinct-informative-value count Series (descending); ``rendered_text`` is the compact
    ``count \\t value`` list for the triage prompt (empty when the study has no informative base value for the
    field, e.g. all-blank — the common escalation case, where the model falls back to the paper's proportions).
    """
    from .categorise.value_frequencies import render_for_prompt, value_frequencies

    empty = pd.Series(dtype="int64")
    if field not in raw_ena.columns:
        return "", empty
    sub = raw_ena[raw_ena["study_accession"] == acc]
    if not len(sub):
        return "", empty
    null_tokens, null_patterns = _field_nulls(spec, field)
    freqs = value_frequencies(sub[field], null_tokens=null_tokens, null_patterns=null_patterns)
    if freqs.empty:
        return "", empty
    total = int(freqs.sum())
    top_share = int(freqs.iloc[0]) / total if total else 0.0
    header = (f"(counts per value; {total} non-blank of {len(sub)} samples; top value {top_share:.0%})")
    return header + "\n" + render_for_prompt(freqs, max_values=max_values), freqs


def _country_region_map(countries: list[str]) -> dict[str, str]:
    """Map each country string to a ``categorise_region`` label (lazy, degrades to identity on import failure).

    Reuses the legacy ``pp.metadata_curation`` region buckets (parse_country -> categorise_region) so the
    escalation path clusters countries exactly as the canonical curation does. The module is heavy (matplotlib
    + HPC path constants at import); a failure to import/run degrades to identity (no clustering, no crash).
    """
    if not countries:
        return {}
    try:
        from bac_metadata.pp import metadata_curation as mc
        df = pd.DataFrame({"country": list(countries)})
        df = mc.parse_country(df, verbose=False)
        df = mc.categorise_region(df, verbose=False)
        return {str(c): str(r) for c, r in zip(df["country"], df["region"], strict=False)}
    except Exception:  # noqa: BLE001 — any import/parse failure degrades to no clustering
        return {c: c for c in countries}


def region_cluster_decision(
    counts: Mapping[str, int], region_of: Mapping[str, str], *, dominant_share: float = DOMINANT_SHARE
) -> dict | None:
    """Pure region-cluster decision: do a study's countries collapse to one region, and is one dominant?

    Parameters
    ----------
    counts
        ``{country: n_samples}`` for the study's distinct non-blank countries.
    region_of
        ``{country: region_label}`` (from :func:`_country_region_map`).
    dominant_share
        A country at/above this share of the counted samples is "dominant".

    Returns
    -------
    dict | None
        ``None`` when the countries do NOT cluster to one known region (or there is <2). Otherwise
        ``{"region", "dominant", "top_country", "top_share", "countries"}`` — ``dominant`` is the top country
        when its share ``>= dominant_share`` else ``""`` (region-only, surfaced for review).
    """
    countries = [c for c in counts if str(c).strip()]
    if len(countries) < 2:
        return None
    regions = {region_of.get(c, c) for c in countries}
    if len(regions) != 1:
        return None
    region = next(iter(regions))
    if region not in KNOWN_REGIONS:
        return None
    total = sum(int(counts[c]) for c in countries)
    top_country = max(countries, key=lambda c: int(counts[c]))
    top_share = int(counts[top_country]) / total if total else 0.0
    return {
        "region": region,
        "dominant": top_country if top_share >= dominant_share else "",
        "top_country": top_country,
        "top_share": top_share,
        "countries": countries,
    }


def _region_cluster(raw_ena: pd.DataFrame, acc: str, spec: AttributeSpec | None) -> dict | None:
    """Deterministic country region-cluster for one study from its ENA base countries (see above)."""
    _, freqs = _field_distribution(raw_ena, acc, "country", spec, max_values=None)
    if freqs.empty:
        return None
    counts = {str(v): int(c) for v, c in freqs.items()}
    region_of = _country_region_map(list(counts))
    return region_cluster_decision(counts, region_of, dominant_share=dominant_share(spec))


def detect_whole_field_escalations(
    grades: Iterable[dict],
    raw_ena: pd.DataFrame,
    spec: AttributeSpec,
    llm: LLMClient,
    evidence_fn: Callable[[str], StudyEvidence],
    *,
    fields: tuple[str, ...] = backfill.FIELDS,
    threshold: int = 50,
    frac: float = 0.75,
    post_gap: Mapping[tuple[str, str], int] | None = None,
    n_records: Mapping[str, int] | None = None,
    model: str | None = None,
    study_samples: dict[str, int] | None = None,
    cohort_total_samples: int | None = None,
    big_decision_frac: float = 0.01,
) -> list[EscalationItem]:
    """Detect whole-field near-misses worth a human decision, highest-gap first.

    Candidacy is **deterministic**: for every ``(study, field)`` the grader did NOT whole-project-fill
    (``applies_whole_project`` is false — whether it declined outright OR proposed a value it would not
    vouch for study-wide), an item is queued iff the field is still **materially incomplete after
    per-sample fills** — its post-per-sample residual exceeds ``threshold`` samples **and** its
    post-per-sample completeness is below ``frac`` (the same 0.75 the per-sample/backfill gate uses). This
    is a stable fact about the data, so the same run inputs always yield the same queue — unlike the
    previous gate, whose LLM triage veto and cohort-size-dependent big-decision boundary drifted between
    runs and silently dropped still-incomplete studies (with them, committed curator answers).

    The "proposed-but-not-whole-project" case (``applies_whole_project`` false, ``proposed_value`` set) was
    previously filled by NEITHER whole-field backfill (which needs ``applies_whole_project``) nor escalation
    (whose old gate, :func:`_declined`, required an *empty* value) — silently discarding the grader's value.
    It is now escalated with that value as the suggestion (the backup catch for grader under-confidence).

    :func:`classify_escalation_candidate` still runs, but only to **suggest** a ``representative_value`` /
    ``cluster_theme`` for the curator — it can no longer veto a candidate. A study's big-decision status
    (``>= big_decision_frac`` of the cohort) is recorded in ``escalate_trigger`` for audit, but no longer
    gates candidacy (a big study is simply one with a large residual, which the fraction gate already keeps).

    Parameters
    ----------
    grades, raw_ena, spec, llm, evidence_fn, fields, threshold, model
        As before (see module docstring). ``threshold`` is the min-residual-samples floor; ``frac`` the
        completeness gate.
    post_gap
        ``{(study, field): blank_samples_after_per_sample}`` — the residual per-sample left (what escalation
        would fill). Falls back to the raw ENA gap when ``None``.
    n_records
        ``{study_accession: n_samples}`` in the selection — the denominator for the completeness fraction.
    study_samples
        ``{study_accession: taxon_sample_count}`` over the WHOLE cohort — the big-decision size (audit only).
    cohort_total_samples
        Total taxon samples across the whole cohort; the denominator for the ``big_decision_frac`` test.
    big_decision_frac
        A study at/above this fraction of the cohort is tagged a big decision in the trigger (default 0.01).

    Returns
    -------
    list[EscalationItem]
        Escalations sorted by ``gap_samples`` (the residual) descending (highest-impact first).
    """
    raw_gap = field_gap(raw_ena, fields)
    resid = dict(post_gap) if post_gap is not None else dict(raw_gap)
    n_of = dict(n_records or {})
    study_samples = study_samples or {}
    items: list[EscalationItem] = []
    for g in grades:
        acc = g.get("study_accession")
        bf = g.get("backfill", {}) or {}
        is_big = bool(
            cohort_total_samples and study_samples.get(acc, 0) / cohort_total_samples >= big_decision_frac
        )
        for f in fields:
            b = bf.get(f, {}) or {}
            if b.get("applies_whole_project"):
                continue  # grader asserts a whole-project value → whole-field backfill fills it, not escalation
            gap_samples = int(resid.get((acc, f), raw_gap.get((acc, f), 0)))  # residual AFTER per-sample
            n = int(n_of.get(acc, 0))
            complete = 1.0 - gap_samples / n if n else 0.0
            # DETERMINISTIC candidacy: any field the grader did NOT whole-project-fill and that is still
            # materially incomplete after per-sample — a pure decline (no value) OR a "limbo" field where the
            # grader proposed a value but would not vouch for it study-wide. The latter was silently dropped
            # (filled by neither whole-field nor escalation), discarding the grader's value; surfacing it is
            # the backup catch (David, 2026-07-10). Gate = residual over the floor AND completeness below the
            # fraction — no LLM-triage/cohort-size dependence, so committed answers reapply and it reproduces.
            if gap_samples <= threshold or complete >= frac:
                continue

            proposed = (b.get("proposed_value") or "").strip()  # the grader's value, if it offered one
            ev = evidence_fn(acc)
            region_hint = ""

            if f == "collection_date":
                # DETERMINISTIC (no LLM): the span was resolved at grade time (value_validity.resolve_date_span);
                # only a pre-2010 mid-range span carries a midpoint suggestion, everything else surfaces blank.
                decision = str(b.get("date_decision", "") or "")
                span = b.get("date_span_months")
                if decision == "escalate_midpoint":
                    resolution, triage_escalates, suggested = "uniform_propose", True, proposed
                else:  # escalate_blank / blank_wide / no_dates (or an old grade) → surface for review, no fill
                    resolution, triage_escalates, suggested = "wide_mix_skip", False, ""
                cluster_theme = (
                    f"collection span {span} months "
                    f"({b.get('earliest_date') or '?'}–{b.get('latest_date') or '?'}); {decision or 'unresolved'}"
                )
                grader_quote = (b.get("evidence_quote", "") or "").strip()
            else:
                region = _region_cluster(raw_ena, acc, spec) if f == "country" else None
                if region is not None:
                    # DETERMINISTIC (no LLM): the study's countries collapse to ONE region (legacy region
                    # buckets). A dominant country (>=95%) is adopted; otherwise the region is surfaced as a
                    # hint (country suggestion left blank) for the curator to confirm (David, 2026-07-13).
                    resolution = "uniform_propose" if region["dominant"] else "tight_cluster_escalate"
                    triage_escalates = True
                    suggested = region["dominant"]
                    region_hint = "" if region["dominant"] else region["region"]
                    shown = ", ".join(region["countries"][:6]) + ("…" if len(region["countries"]) > 6 else "")
                    cluster_theme = f"all {region['region']} ({shown}); " + (
                        f"dominant {region['dominant']} ({region['top_share']:.0%})"
                        if region["dominant"]
                        else f"no single dominant country → suggest region {region['region']}"
                    )
                    grader_quote = (b.get("evidence_quote", "") or "").strip()
                else:
                    dist_text, _ = _field_distribution(raw_ena, acc, f, spec)
                    cls = classify_escalation_candidate(
                        spec, llm, accession=acc, field=f, fulltext=ev.fulltext, ena_title=ev.ena_title,
                        ena_description=ev.ena_description, sizing_row=ev.sizing_row,
                        prior_proposed=b.get("proposed_value"), prior_quote=b.get("evidence_quote", ""),
                        distribution_text=dist_text, model=model,
                        max_chars=spec.max_paper_chars if spec is not None else DEFAULT_MAX_CHARS,
                    )
                    resolution = cls.get("resolution", "")  # advisory — informs suggested/theme, never vetoes
                    triage_escalates = resolution in ESCALATE_RESOLUTIONS
                    # A suggestion (Enter-to-accept pre-fill) is offered ONLY when the triage escalates (David,
                    # 2026-07-13): a wide_mix_skip must carry NO value, else the grader's un-vouched "limbo" guess
                    # (PRJEB6891→rectal swab, PRJNA767944→sputum) shows as a pre-fill and Enter writes it wrongly.
                    suggested = (proposed or (cls.get("representative_value") or "").strip()) if triage_escalates else ""
                    cluster_theme = (cls.get("cluster_theme") or "").strip()
                    grader_quote = (cls.get("evidence_quote") or b.get("evidence_quote", "") or "").strip()

            trigger = "+".join(
                ([f"big_decision({study_samples.get(acc, 0)})"] if is_big else [])
                + ([resolution] if triage_escalates else [])
                + (["grader_proposed"] if proposed and not (is_big or triage_escalates) else [])
                + ([f"residual({gap_samples}/{n}={1 - complete:.0%}_blank)"]
                   if not (is_big or triage_escalates or proposed) else [])
            )

            items.append(
                EscalationItem(
                    study_accession=acc,
                    field=f,
                    gap_samples=gap_samples,
                    resolution=resolution,
                    suggested_value=suggested,
                    cluster_theme=cluster_theme,
                    grader_quote=grader_quote,
                    paper_excerpt=_paper_excerpt(ev.fulltext.text, f),
                    fulltext_status=g.get("fulltext_source", ev.fulltext.source),
                    escalate_trigger=trigger,
                    region_hint=region_hint,
                )
            )
    items.sort(key=lambda it: it.gap_samples, reverse=True)
    return items


def answers_to_proposals(answers: Iterable[dict]) -> dict[str, dict[str, dict]]:
    """Turn filled curator answers into the proposal shape :func:`backfill.apply_whole_field` consumes.

    Parameters
    ----------
    answers
        Rows with ``study_accession``, ``field``, and a curator ``answer`` (blank answers are dropped).

    Returns
    -------
    dict
        ``{study_accession: {field: {"value", "whole_project": True, "evidence": "curator escalation"}}}``.
    """
    proposals: dict[str, dict[str, dict]] = {}
    for a in answers:
        value = (a.get("answer") or "").strip()
        if not value:
            continue
        proposals.setdefault(str(a["study_accession"]), {})[str(a["field"])] = {
            "value": value,
            "whole_project": True,
            "evidence": "curator escalation",
        }
    return proposals
