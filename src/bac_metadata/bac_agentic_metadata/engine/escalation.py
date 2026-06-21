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
from collections.abc import Callable, Iterable
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
#: priors (invasiveness as the primary phenotype axis; old dates are high-value for lineage dating).
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
    "    * collection_date: a span of about five years or less is tight; an OLDER span (pre-2010, and "
    "especially pre-2000) stays tight even up to ~6–7 years, because old samples are high-value for "
    "lineage dating. WIDE (skip) for spans of a decade or more, or recent wide spans.\n"
    "    * host: closely-related hosts (e.g. all human clinical) are tight; mixing human + animal + "
    "environmental is WIDE.\n"
    "- wide_mix_skip — a genuinely wide, unrelated mix; do not escalate.\n"
    "- uniform_propose — on reflection the evidence DOES support one whole-project value you should have "
    "proposed.\n\n"
    "For tight_cluster_escalate or uniform_propose, set representative_value to the single value a human "
    "would most likely accept (e.g. the dominant invasive specimen such as 'blood'; the region; the "
    "midpoint year of the span). Set representative_value null for wide_mix_skip. Give a one-line "
    "cluster_theme naming the cluster and why it is tight or wide, plus a verbatim evidence_quote. Judge "
    "ONLY from the evidence above; do not guess."
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
    per_sample_covered: set[tuple[str, str]] | None = None,
    model: str | None = None,
) -> list[EscalationItem]:
    """Detect tight whole-field near-misses worth a human decision, highest-gap first.

    For every ``(study, field)`` the grader declined (see :func:`_declined`): gate by gap (skip if
    ``gap_samples <= threshold``), gate by per-sample coverage (skip if already resolved per-sample), then
    triage with :func:`classify_escalation_candidate`; keep only the escalating resolutions
    (:data:`ESCALATE_RESOLUTIONS`). The LLM is only called on declines that clear both deterministic
    gates, so cost scales with the few material, unresolved declines.

    Parameters
    ----------
    grades
        The grader's JSONL records (each a dict with ``study_accession`` + ``backfill`` map).
    raw_ena
        Raw per-sample ENA table, for the gap gate.
    spec
        The application :class:`AttributeSpec` (the rubric the grader pitches from).
    llm
        The LLM client (the classify call is cached on disk).
    evidence_fn
        Application callback ``accession -> StudyEvidence`` (re-supplies the graded evidence).
    fields
        Per-sample fields to consider (default :data:`backfill.FIELDS`).
    threshold
        Minimum blank-cell gap to bother a human (default 50).
    per_sample_covered
        ``(study, field)`` pairs per-sample extraction already resolved — skipped (per-sample runs first).
    model
        Per-call model override for the classify step (default: the grader's workhorse).

    Returns
    -------
    list[EscalationItem]
        Escalations sorted by ``gap_samples`` descending (highest-impact first).
    """
    gap = field_gap(raw_ena, fields)
    covered = per_sample_covered or set()
    items: list[EscalationItem] = []
    for g in grades:
        acc = g.get("study_accession")
        bf = g.get("backfill", {}) or {}
        for f in fields:
            b = bf.get(f, {}) or {}
            if not _declined(b):
                continue
            gap_samples = gap.get((acc, f), 0)
            if gap_samples <= threshold or (acc, f) in covered:
                continue

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
            resolution = cls.get("resolution", "")
            if resolution not in ESCALATE_RESOLUTIONS:
                continue

            items.append(
                EscalationItem(
                    study_accession=acc,
                    field=f,
                    gap_samples=gap_samples,
                    resolution=resolution,
                    suggested_value=(cls.get("representative_value") or "").strip(),
                    cluster_theme=(cls.get("cluster_theme") or "").strip(),
                    grader_quote=(cls.get("evidence_quote") or b.get("evidence_quote", "") or "").strip(),
                    paper_excerpt=_paper_excerpt(ev.fulltext.text, f),
                    fulltext_status=g.get("fulltext_source", ev.fulltext.source),
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
