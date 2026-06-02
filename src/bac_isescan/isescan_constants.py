"""Shared ISEScan family column names."""

from __future__ import annotations

# Canonical IS family universe (explicit; alphabetically sorted for stable column order).
CANONICAL_IS_FAMILY_COLUMNS: tuple[str, ...] = tuple(
    sorted(
        [
            "IS1",
            "IS110",
            "IS1182",
            "IS1380",
            "IS1595",
            "IS1634",
            "IS200/IS605",
            "IS21",
            "IS256",
            "IS3",
            "IS30",
            "IS4",
            "IS481",
            "IS5",
            "IS6",
            "IS630",
            "IS66",
            "IS91",
            "ISAS1",
            "ISKRA4",
            "ISL3",
            "ISNCY",
            "new",
        ],
        key=str.lower,
    ),
)

META_COLUMNS: tuple[str, ...] = ("Sample", "Clonal group", "lra_final_list")


def cluster_csv_column(cluster_id: str) -> str:
    """Stable CSV column name for a cluster identifier."""
    safe = cluster_id.strip().replace("/", "_").replace(" ", "_")
    return f"cluster_{safe}"
