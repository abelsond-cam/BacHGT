"""Human-in-the-loop escalation tier for whole-field backfill — ask the curator on a *tight* near-miss.

When the grader declines a single whole-project (whole-field) value, the field's values fall into two very
different shapes, and only one is worth a human's time:

* a **tight, closely-related cluster** that just misses one clean rubric label — all-invasive specimens
  (blood + CSF), countries in one close region, a short *older* date span — where a human could reasonably
  accept one representative value;
* a **genuinely wide mix** — isolates from 37 countries; UK + Malawi + Argentina; blood + urine +
  respiratory + wound; urine + sputum + blood + rectal — which has no single label and belongs to
  per-sample extraction (per-sample), not a whole-field value.

This tier escalates only the first. The order David set is: **per-sample runs first** — if per-sample data
is available the question is already answered — and the grader **auto-rejects the wide mixes**; only the
tight near-misses reach a human. Each is packaged as an :class:`EscalationItem` (the grader's quote, a
paper excerpt, the candidate value, the gap it closes) so the curator decides once; those decisions later
become rubric clauses.

Detection, per ``(study, field)`` the grader declined whole-field:

1. **Gate by gap** (cheap, deterministic): blank ENA cells for that field, placeholder-stripped. Skip at
   or below the threshold.
2. **Gate by per-sample**: skip if per-sample extraction already resolved the field (sample-level data
   answers it).
3. **Classify** (cached LLM, the grader's own pitch): :func:`classify_escalation_candidate` decides
   ``wide_mix_skip`` / ``tight_cluster_escalate`` / ``uniform_propose`` and, for the latter two, the
   single ``representative_value`` a human would most likely accept (blood; the region; the midpoint
   year). Only the escalating resolutions reach the queue.

The curator's confirmed answer is a whole-field proposal (``whole_project: True``) that applies through the
**existing** :func:`backfill.apply_whole_field` path — never a new fill mechanism.

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

#: The triage criteria — David's "tight cluster vs wide mix" rule, field by field. Encodes the research
#: priors (invasiveness as the primary phenotype axis). collection_date uses a STRICT 2-year window with no
#: exceptions and is NEVER escalated (David, 2026-07-02): the cohorts already have a good spread of true
#: dates, so accepting an imprecise wide-range midpoint would only corrupt fine-grained lineage dating.
_TRIAGE_GUIDANCE = (
    "We only ask a human to confirm a value when the field, though it does not fit one clean rubric "
    "label, is a TIGHT, CLOSELY-RELATED cluster a human could reasonably collapse to one representative "
    "value. When it is a genuinely WIDE, unrelated mix, do NOT ask — per-sample extraction handles it.\n\n"
    "Resolutions:\n"
    "- tight_cluster_escalate — closely related, worth a human's confirmation. By field:\n"
    "    * isolation_source: all specimens share the INVASIVENESS theme — e.g. all invasive (blood and "
    "CSF; blood and deep-tissue/abscess). WIDE (skip) if it mixes invasive sites with carriage/screening "
    "(rectal, stool) OR spans many unrelated sites (e.g. blood + urine + respiratory + wound).\n"
    "    * country: all countries lie in ONE close region (e.g. all Nordic, all East Africa). WIDE (skip) "
    "across continents (e.g. UK + Malawi + Argentina) or dozens of countries (e.g. '37 countries').\n"
    "    * collection_date: NEVER escalate — dates use a STRICT 2-year window with no exceptions. A span of "
    "2 years (24 months) or less is already auto-filled with its midpoint by whole-field backfill (nothing "
    "to ask); ANY span wider than 2 years is WIDE — use wide_mix_skip and leave the date blank. Never accept "
    "an imprecise midpoint for a wide range: the cohort already has a good spread of true collection dates, "
    "and a coarse range-midpoint would corrupt fine-grained lineage dating. There is no 'older/valuable "
    "span' exception.\n"
    "    * host: closely-related hosts (e.g. all human clinical) are tight; mixing human + animal + "
    "environmental is WIDE.\n"
    "- wide_mix_skip — a genuinely wide, unrelated mix; do not escalate.\n"
    "- uniform_propose — on reflection the evidence DOES support one whole-project value you should have "
    "proposed.\n\n"
    "For tight_cluster_escalate or uniform_propose, set representative_value to the single value a human "
    "would most likely accept — it is the representative of the tight set. It MUST be a SINGLE, PARSEABLE, "
    "CANONICAL value of that field, never a region, a list, or a concatenation:\n"
    "    * country: ONE country name as it would appear in metadata (e.g. 'Malawi', 'Guatemala') — NOT a "
    "region/continent ('Central America', 'East Africa') and NOT a join ('Uganda; Malawi'). If the cluster "
    "spans a few neighbouring countries, give the single DOMINANT country; if there is no dominant one, "
    "prefer wide_mix_skip.\n"
    "    * isolation_source: one specimen term (e.g. 'blood'); host: one host (e.g. 'human'). collection_date "
    "is never escalated, so it never has a representative_value.\n"
    "Set representative_value null for wide_mix_skip. Give a one-line cluster_theme naming the cluster and "
    "why it is tight or wide, plus a verbatim evidence_quote. Judge ONLY from the evidence above; do not guess."
)


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
        The grader's triage call (a :data:`RESOLUTIONS` value; always an escalating one for queued items).
    suggested_value
        The single representative value the grader judged a human would likely accept (the pre-fill).
    cluster_theme
        One line naming the cluster and why it is tight (the grader's rationale).
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
    model: str | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict:
    """Triage one whole-field decline as a tight near-miss (escalate) vs a wide mix (skip).

    Presented in the grader's own pitch (so it reasons in-rubric) with the same evidence it graded on,
    plus David's tight-vs-wide criteria. Returns the validated classification dict (see
    :func:`_classify_schema`): ``resolution``, ``representative_value``, ``cluster_theme``,
    ``evidence_quote``.
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
    follow_up = (
        "\n\n=== FOLLOW-UP: escalation triage (this supersedes the grading instruction above) ===\n"
        f"Earlier you declined a single whole-project value for `{field}` (proposed_value="
        f"{prior_proposed!r}, evidence quote {prior_quote!r}).\n\n" + _TRIAGE_GUIDANCE
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
            cls = classify_escalation_candidate(
                spec,
                llm,
                accession=acc,
                field=f,
                fulltext=ev.fulltext,
                ena_title=ev.ena_title,
                ena_description=ev.ena_description,
                sizing_row=ev.sizing_row,
                prior_proposed=b.get("proposed_value"),
                prior_quote=b.get("evidence_quote", ""),
                model=model,
            )
            resolution = cls.get("resolution", "")  # advisory — informs suggested_value/theme, never vetoes
            triage_escalates = resolution in ESCALATE_RESOLUTIONS
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
                    # prefer the grader's own proposed value as the suggestion; fall back to the triage's
                    suggested_value=proposed or (cls.get("representative_value") or "").strip(),
                    cluster_theme=(cls.get("cluster_theme") or "").strip(),
                    grader_quote=(cls.get("evidence_quote") or b.get("evidence_quote", "") or "").strip(),
                    paper_excerpt=_paper_excerpt(ev.fulltext.text, f),
                    fulltext_status=g.get("fulltext_source", ev.fulltext.source),
                    escalate_trigger=trigger,
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
