"""Load an application's ``attributes.yaml`` into a typed :class:`AttributeSpec`.

The YAML is the single source of truth for the curation rubric (David edits it directly).
ENA assessment only needs the deterministic parts: the taxon of interest and the per-sample
completeness fields + their normalisers. The full parsed mapping is retained on
:attr:`AttributeSpec.raw` for later stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

#: Generic FALLBACK values for the application pipeline gates (used only when the app's ``attributes.yaml``
#: omits the ``gates`` key). The application sets its own under a top-level ``gates:`` section, so the yaml is
#: the single constants file; the engine keeps these merely so an app that declares none still runs.
_DEFAULT_COMPLETENESS_THRESHOLD = 0.75  # ENA non-null fraction at/above which a field is "already complete"
_DEFAULT_ESCALATION_RESIDUAL_FLOOR = 50  # min blank samples remaining after per-sample to bother escalating
_DEFAULT_ESCALATION_BIG_DECISION_FRAC = 0.01  # a study at/above this fraction of the cohort is a "big decision"
_DEFAULT_MAX_PAPER_CHARS = 120_000  # single-tier fallback paper-text ceiling when no ladder is configured


@dataclass(frozen=True)
class TaxonOfInterest:
    """Genus/species the application studies, matched against the ENA ``scientific name``.

    Parameters
    ----------
    rank
        Taxonomic rank, e.g. ``"genus"`` or ``"species"``.
    name
        Human-readable taxon name, e.g. ``"Klebsiella"``.
    scientific_name_match
        Substrings matched (case-insensitively) against an ENA ``scientific_name`` to decide
        whether a record belongs to the taxon of interest.
    """

    rank: str
    name: str
    scientific_name_match: tuple[str, ...]


@dataclass(frozen=True)
class AttributeSpec:
    """Typed view of an application ``attributes.yaml`` for the deterministic stage.

    Parameters
    ----------
    application
        Application slug (``"klebsiella"`` / ``"m_abs"``).
    species
        Free-text species description from the spec.
    taxon_of_interest
        The :class:`TaxonOfInterest` used for sizing and completeness.
    completeness_fields
        Per-sample fields whose completeness ENA assessment measures, e.g.
        ``["country", "collection_date", "isolation_source", "host"]``.
    deterministic_normaliser
        Mapping ``field -> [parse_fn, categorise_fn, ...]`` naming the reusable
        ``pp.metadata_curation`` callables. Empty for applications that declare none.
    raw
        The full parsed YAML document (for attributes ENA assessment does not consume).
    """

    application: str
    species: str
    taxon_of_interest: TaxonOfInterest
    completeness_fields: tuple[str, ...]
    deterministic_normaliser: dict[str, tuple[str, ...]]
    sample_identifier_columns: tuple[str, ...]
    categorisation: dict[str, dict]
    raw: dict

    def _gate(self, key: str, default: float) -> float:
        """Read a numeric gate from the yaml ``gates`` section, falling back to the engine default."""
        v = (self.raw.get("gates", {}) or {}).get(key)
        return default if v is None else v

    @property
    def completeness_threshold(self) -> float:
        """ENA non-null fraction at/above which a field is "already complete" (``gates.completeness_threshold``)."""
        return float(self._gate("completeness_threshold", _DEFAULT_COMPLETENESS_THRESHOLD))

    @property
    def escalation_residual_floor(self) -> int:
        """Min blank samples remaining after per-sample before a field escalates (``gates.escalation_residual_floor``)."""
        return int(self._gate("escalation_residual_floor", _DEFAULT_ESCALATION_RESIDUAL_FLOOR))

    @property
    def escalation_big_decision_frac(self) -> float:
        """Cohort fraction at/above which a study is an escalation "big decision" (``gates.escalation_big_decision_frac``)."""
        return float(self._gate("escalation_big_decision_frac", _DEFAULT_ESCALATION_BIG_DECISION_FRAC))

    @property
    def grade_context_tiers(self) -> tuple[int, ...]:
        """Ascending paper-text budgets the grader climbs (``gates.grade_context_tiers``), smallest first.

        The grader reads only the first tier (e.g. 10k chars ~= the abstract); it climbs to the next tier ONLY
        when it self-reports that the truncated remainder might hold an answer it could not determine. Most
        studies resolve at the cheapest tier, so the ladder collapses per-call token cost dramatically (David,
        2026-07-14). Falls back to a single tier at ``gates.max_paper_chars`` (or the engine default) when no
        ladder is configured — i.e. the original single-pass behaviour.
        """
        v = (self.raw.get("gates", {}) or {}).get("grade_context_tiers")
        if v:
            return tuple(sorted({int(x) for x in v}))
        return (int(self._gate("max_paper_chars", _DEFAULT_MAX_PAPER_CHARS)),)

    @property
    def max_paper_chars(self) -> int:
        """The ceiling paper-text budget (top of :attr:`grade_context_tiers`); the escalation triage single pass."""
        return self.grade_context_tiers[-1]

    @property
    def auto_skip_wide_mix(self) -> bool:
        """Auto-resolve ``wide_mix_skip`` escalations as skips instead of surfacing them (``escalation.auto_skip_wide_mix``)."""
        return bool((self.raw.get("escalation", {}) or {}).get("auto_skip_wide_mix", False))

    @classmethod
    def from_yaml(cls, path: str | Path) -> AttributeSpec:
        """Parse an ``attributes.yaml`` file into an :class:`AttributeSpec`.

        Parameters
        ----------
        path
            Path to the application's ``attributes.yaml``.

        Returns
        -------
        AttributeSpec
            The parsed spec.
        """
        doc = yaml.safe_load(Path(path).read_text())

        toi = doc["taxon_of_interest"]
        taxon = TaxonOfInterest(
            rank=toi["rank"],
            name=toi["name"],
            scientific_name_match=tuple(toi.get("scientific_name_match", [toi["name"]])),
        )

        completeness = doc.get("attributes", {}).get("per_sample_completeness", {})
        fields = tuple(completeness.get("fields", []))
        normaliser = {
            field: tuple(funcs)
            for field, funcs in (completeness.get("deterministic_normaliser") or {}).items()
        }
        # Per-sample identifier columns the extractor may anchor supplementary tables on (empty -> the
        # extractor's default Klebsiella id set). Reviewing the input for ALL per-sample identifiers is the
        # first onboarding step for a new species (see PROGRESS_REPORT + the yaml note).
        id_columns = tuple(completeness.get("sample_identifier_columns", []))

        # Agentic-categorisation config (per-field null_tokens / categories / cross_column). Empty for
        # applications that declare no `attributes.categorisation` block. Stored as plain nested dicts;
        # consumers (preclean, induce/apply, reconcile) read the sub-keys they need.
        categorisation = {
            field: dict(cfg or {})
            for field, cfg in ((doc.get("attributes", {}).get("categorisation", {}) or {}).get("fields", {}) or {}).items()
        }

        return cls(
            application=doc["application"],
            species=doc.get("species", ""),
            taxon_of_interest=taxon,
            completeness_fields=fields,
            deterministic_normaliser=normaliser,
            sample_identifier_columns=id_columns,
            categorisation=categorisation,
            raw=doc,
        )
