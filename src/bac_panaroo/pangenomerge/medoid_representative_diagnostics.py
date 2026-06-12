"""Diagnose paralogue-split clusters in a pangenomerge merged pangenome.

For a merged pangenomerge run (``pangenome_metadata.sqlite`` +
``postprocess/gene_presence_absence.csv``):

1. Identify clusters at the suspicious mid-prevalence band (default ``[0.48,
   0.52]``) where genuine population-balanced clusters should be rare.
2. For each such *spike* cluster, find its best union-partner among the spike
   set (the cluster ``j`` that maximises ``|present_i \\cup present_j|``).
3. Bridge the GPA ``Gene`` column to the SQLite ``nodes`` table via the
   ``isolate_names`` table + Jaccard set match on each cluster's
   genome-presence pattern — pangenomerge re-numbers clusters during
   postprocess, so name-based matching does not work.
4. Pull each cluster's representative AA sequence from
   ``nodes_sequences.protein`` and pairwise-align the two reps with
   Biopython's identity-only ``PairwiseAligner``.
5. Emit a TSV with one row per spike cluster + summary stats stratified by
   best-partner-union strength.

The output answers two questions for the merge author at once:
- "How many clusters at ~50% are anti-correlated paralogue-split pairs?"
  (count of clusters whose best-partner union is high)
- "Are the part-graphs picking sensible representatives?"
  (pct_identity / len_ratio of the rep pairs)

Run as a module from the BacHGT repo root, with the bac_panaroo uv env:

    uv run python -m bac_panaroo.pangenomerge.medoid_representative_diagnostics \\
        --merge-dir /path/to/SL147_frameshift \\
        --out spike_pair_similarity.tsv
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from Bio.Align import PairwiseAligner


META_COLS = {"Gene", "Non-unique Gene name", "Annotation"}


def _read_gpa_presence(gpa_csv: Path) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    """Return (full df, NxM boolean presence matrix, list of sample column names)."""
    df = pd.read_csv(gpa_csv, low_memory=False)
    sample_cols = [c for c in df.columns if c not in META_COLS]
    present = (df[sample_cols].notna() & (df[sample_cols] != "")).values
    return df, present, sample_cols


def _spike_indices(present: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Return GPA row indices for clusters with prevalence in [lo, hi]."""
    n = present.shape[1]
    freq = present.sum(axis=1) / n
    return np.where((freq >= lo) & (freq <= hi))[0]


def _best_partners(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """For each spike row i find j maximising union; return arrays of (j, union_frac, intersect, sum_i)."""
    Xi = X.astype(np.int32)
    sums = Xi.sum(axis=1)
    inter = Xi @ Xi.T
    union = sums[:, None] + sums[None, :] - inter
    np.fill_diagonal(union, -1)
    np.fill_diagonal(inter, X.shape[1] + 1)
    best_j = union.argmax(axis=1)
    n = X.shape[1]
    best_u = union[np.arange(len(X)), best_j] / n
    best_i = inter[np.arange(len(X)), best_j]
    return best_j, best_u, best_i, sums


def _load_isolate_map(conn: sqlite3.Connection) -> dict[tuple[int, int], str]:
    """Return {(graph_id, member_index): sample_name} from the isolate_names table."""
    iso_map: dict[tuple[int, int], str] = {}
    for graph_id, member_idx, sname, _pp in conn.execute(
        "SELECT graph_id, member_index, sample_name, poppunk_cluster FROM isolate_names"
    ):
        iso_map[(int(graph_id), int(member_idx))] = sname
    return iso_map


def _load_all_nodes(
    conn: sqlite3.Connection,
    iso_map: dict[tuple[int, int], str],
) -> list[tuple[str, str, int, set[str], str | None]]:
    """Return list of (node_id, name, size, sample_set, protein) for every node in nodes table."""
    nodes: list[tuple[str, str, int, set[str], str | None]] = []
    for nid, nm, sz, gids, prot in conn.execute(
        "SELECT n.node_id, n.name, n.size, n.genomeIDs, s.protein "
        "FROM nodes n LEFT JOIN node_sequences s ON n.node_id = s.node_id"
    ):
        samples: set[str] = set()
        if gids:
            for tok in gids.split(";"):
                if not tok:
                    continue
                try:
                    idx_s, g_s = tok.rsplit("_g", 1)
                    sn = iso_map.get((int(g_s), int(idx_s)))
                except ValueError:
                    sn = None
                if sn is not None:
                    samples.add(sn)
        nodes.append((nid, nm, sz, samples, prot))
    return nodes


def _build_inverted_index(
    nodes: list[tuple[str, str, int, set[str], str | None]],
) -> dict[str, list[int]]:
    """Inverted index sample_name -> [node_idx]; used for fast Jaccard search."""
    idx: dict[str, list[int]] = {}
    for ni, (_nid, _nm, _sz, sset, _p) in enumerate(nodes):
        for sn in sset:
            idx.setdefault(sn, []).append(ni)
    return idx


def _best_node_match(
    target_set: set[str],
    nodes: list[tuple[str, str, int, set[str], str | None]],
    sid_to_nodes: dict[str, list[int]],
) -> tuple[int | None, float]:
    """Return (node_idx, jaccard) for the SQLite node best matching target_set."""
    if not target_set:
        return None, 0.0
    counts: dict[int, int] = {}
    for sn in target_set:
        for ni in sid_to_nodes.get(sn, ()):
            counts[ni] = counts.get(ni, 0) + 1
    best_ni: int | None = None
    best_jac = 0.0
    tlen = len(target_set)
    for ni, inter_n in counts.items():
        nset_len = len(nodes[ni][3])
        union_n = tlen + nset_len - inter_n
        if union_n == 0:
            continue
        jac = inter_n / union_n
        if jac > best_jac:
            best_jac = jac
            best_ni = ni
    return best_ni, best_jac


def _pct_identity(a: str, b: str, aligner: PairwiseAligner) -> tuple[float, int]:
    """Return (% identity, raw match score). Identity = matches / max(len_a, len_b)."""
    score = aligner.score(a, b)
    return 100.0 * score / max(len(a), len(b)), int(score)


def _stratify_summary(df: pd.DataFrame, label: str) -> str:
    """Render a one-line + bins summary string for log output."""
    if df.empty:
        return f"\n[{label}] no rows."
    out = [f"\n[{label}] n={len(df)}"]
    if "pct_identity" in df.columns:
        pid = df["pct_identity"].dropna()
        if len(pid):
            out.append(
                f"  pct_identity:  median={pid.median():.1f}  q25={pid.quantile(.25):.1f}  q75={pid.quantile(.75):.1f}  min={pid.min():.1f}  max={pid.max():.1f}"
            )
            for lo, hi in [(0, 30), (30, 50), (50, 70), (70, 80), (80, 90), (90, 95), (95, 99), (99, 100.1)]:
                n = ((pid >= lo) & (pid < hi)).sum()
                bar = "#" * int(50 * n / max(1, len(pid)))
                out.append(f"    {lo:>3}-{hi:>5.0f}  n={n:>4}  {bar}")
    if "len_ratio" in df.columns:
        lr = df["len_ratio"].dropna()
        if len(lr):
            out.append(
                f"  len_ratio:     median={lr.median():.3f}  q25={lr.quantile(.25):.3f}  q75={lr.quantile(.75):.3f}  min={lr.min():.3f}  max={lr.max():.3f}"
            )
    return "\n".join(out)


def run(merge_dir: Path, out_tsv: Path, lo: float, hi: float) -> None:
    """Run the full pipeline for a single merge dir."""
    t0 = time.time()

    gpa = merge_dir / "postprocess" / "gene_presence_absence.csv"
    sql = merge_dir / "pangenome_metadata.sqlite"
    if not gpa.exists():
        sys.exit(f"missing GPA at {gpa}")
    if not sql.exists():
        sys.exit(f"missing sqlite at {sql}")

    print(f"[{time.time()-t0:6.1f}s] reading GPA {gpa}")
    df, present, sample_cols = _read_gpa_presence(gpa)
    print(f"           n_genomes={len(sample_cols)}  n_clusters={len(df)}")

    spike_idx = _spike_indices(present, lo, hi)
    print(f"[{time.time()-t0:6.1f}s] spike clusters in [{lo}, {hi}]: {len(spike_idx)}")

    print(f"[{time.time()-t0:6.1f}s] mutual-exclusivity best-partner search")
    X = present[spike_idx]
    best_j, best_u, best_i, sums = _best_partners(X)

    print(f"[{time.time()-t0:6.1f}s] opening sqlite {sql}")
    conn = sqlite3.connect(str(sql))
    iso_map = _load_isolate_map(conn)
    print(f"           isolate_names rows: {len(iso_map)}")
    nodes = _load_all_nodes(conn, iso_map)
    conn.close()
    print(f"           nodes loaded: {len(nodes)}")
    sid_to_nodes = _build_inverted_index(nodes)
    print(f"           inverted-index keys: {len(sid_to_nodes)}")

    sample_arr = np.array(sample_cols)
    spike_sets = [set(sample_arr[X[i].astype(bool)].tolist()) for i in range(len(X))]

    print(f"[{time.time()-t0:6.1f}s] mapping {len(spike_idx)} spike clusters to SQLite nodes")
    spike_to_node: list[tuple[int | None, float]] = [
        _best_node_match(spike_sets[i], nodes, sid_to_nodes) for i in range(len(X))
    ]
    matched = sum(1 for v in spike_to_node if v[0] is not None)
    print(f"           matched: {matched}/{len(spike_to_node)}")

    aligner = PairwiseAligner(
        mode="global", match_score=1, mismatch_score=0, open_gap_score=0, extend_gap_score=0
    )

    print(f"[{time.time()-t0:6.1f}s] aligning {len(spike_idx)} cluster-partner pairs")
    gpa_gene = df["Gene"].astype(str).values[spike_idx]
    gpa_annot = df["Annotation"].astype(str).values[spike_idx]

    rows: list[dict] = []
    for i in range(len(X)):
        j = int(best_j[i])
        niA, jacA = spike_to_node[i]
        niB, jacB = spike_to_node[j]

        # Strict-pair flags
        inter_ratio = best_i[i] / max(1, sums[i])
        is_strict = (best_u[i] >= 0.98) and (inter_ratio <= 0.02)

        row: dict = {
            "cluster_A_gpa": gpa_gene[i],
            "best_partner_gpa": gpa_gene[j],
            "best_partner_union_frac": round(float(best_u[i]), 4),
            "best_partner_inter_ratio": round(float(inter_ratio), 4),
            "cluster_A_size": int(sums[i]),
            "is_strict_pair": int(is_strict),
            "annotation_A": gpa_annot[i][:120],
            "annotation_B": gpa_annot[j][:120],
        }
        if niA is None or niB is None:
            row["note"] = "no sqlite node match"
            rows.append(row)
            continue
        nidA, nmA, szA, _, protA = nodes[niA]
        nidB, nmB, szB, _, protB = nodes[niB]
        row.update(
            {
                "cluster_A_sql": nmA,
                "size_A_sql": int(szA),
                "len_A": len(protA) if protA else 0,
                "jac_A": round(jacA, 3),
                "cluster_B_sql": nmB,
                "size_B_sql": int(szB),
                "len_B": len(protB) if protB else 0,
                "jac_B": round(jacB, 3),
            }
        )
        if not protA or not protB:
            row["note"] = "missing protein"
            rows.append(row)
            continue
        try:
            pid, score = _pct_identity(protA, protB, aligner)
        except Exception as e:
            row["note"] = f"align err: {e}"
            rows.append(row)
            continue
        row.update(
            {
                "match_score": score,
                "pct_identity": round(pid, 2),
                "len_ratio": round(min(len(protA), len(protB)) / max(len(protA), len(protB)), 3),
            }
        )
        rows.append(row)

    out = pd.DataFrame(rows)
    out.to_csv(out_tsv, sep="\t", index=False)
    print(f"[{time.time()-t0:6.1f}s] wrote {out_tsv}  ({len(out)} rows)")

    aligned = out.dropna(subset=["pct_identity"]) if "pct_identity" in out.columns else out.iloc[0:0]
    print(f"\n=== ALL spike clusters (n={len(out)}) ===")
    print(_stratify_summary(aligned, "all-spike"))

    if "best_partner_union_frac" in out.columns:
        for lo_u, hi_u, name in [
            (0.98, 1.001, "union >= 0.98 (strict pair)"),
            (0.90, 0.98, "union 0.90-0.98 (looser pair)"),
            (0.0, 0.90, "union < 0.90 (no clean partner)"),
        ]:
            sub = aligned[(aligned["best_partner_union_frac"] >= lo_u) & (aligned["best_partner_union_frac"] < hi_u)]
            print(_stratify_summary(sub, name))

    if "is_strict_pair" in out.columns:
        strict = aligned[aligned["is_strict_pair"] == 1]
        print(_stratify_summary(strict, "strict (union>=0.98 AND inter<=0.02)"))


def main() -> None:
    """CLI entry point."""
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--merge-dir",
        type=Path,
        required=True,
        help="Pangenomerge merge output dir (must contain pangenome_metadata.sqlite + postprocess/gene_presence_absence.csv).",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output TSV path. Defaults to <merge-dir>/spike_pair_similarity.tsv.",
    )
    ap.add_argument("--prevalence-low", type=float, default=0.48, help="Spike-band low (default 0.48).")
    ap.add_argument("--prevalence-high", type=float, default=0.52, help="Spike-band high (default 0.52).")
    args = ap.parse_args()

    merge_dir = args.merge_dir.resolve()
    out_tsv = args.out if args.out is not None else (merge_dir / "spike_pair_similarity.tsv")
    run(merge_dir, out_tsv, args.prevalence_low, args.prevalence_high)


if __name__ == "__main__":
    main()
