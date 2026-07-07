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
