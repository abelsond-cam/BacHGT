r"""Escalation-conservation gate — the end-to-end check that no curator decision is silently lost.

The curator-escalation answer travels a five-link chain, and every past silent-drop bug hid at a *different*
link. The run-health report accounts for links 1–2 (detect → decisions queue → answered/skip), but stops
there; it cannot see links 3–5. This script is the missing hard gate over those links — it asserts, per tag
and across the accumulated master, that a decision the curator made survives all the way to the final cell:

    1 detect     → decisions_needed_<tag>.tsv            (run-health covers)
    2 answer      → answer / answer_note in that queue    (run-health covers)
    3 apply       → escalation_applied_<tag>.tsv          INV1  (this gate)
    4 accumulate  → curated_escalations.tsv (master)      INV2  (this gate — vs git HEAD)
    5 fill        → filled_metadata_<tag>.tsv (final)     INV3  (this gate)

Invariants (each loud-fails; the script exits non-zero on any failure):

* **INV1 apply** — every *answered* decision (a non-blank ``answer``) in ``decisions_needed_<tag>.tsv`` has at
  least one matching non-blank fill in ``escalation_applied_<tag>.tsv`` (``method=curator_escalation``). A
  curator *skip* (a reject/skip note, no value) legitimately produces no fill and is not required to.
* **INV2 master-preserve** — ``curated_escalations.tsv`` on disk ⊇ its committed (``git show HEAD:``) self:
  every prior ``(study, field)`` is still present and the row count never decreases. THIS is the check that
  would have caught the accumulate-rebuild bug (6a83242) before it dropped eight committed answers.
* **INV3 fill** — every non-blank fill in ``escalation_applied_<tag>.tsv`` lands as a non-blank cell in the
  final ``filled_metadata_<tag>.tsv``. A higher-precedence per-sample value may *change* the cell, but it must
  never leave it blank — a blank final cell under an escalation fill is a silent loss.
* **INV4 counts** — reports the funnel (answered decisions → applied fills → cells non-blank in final) per tag
  and flags any shrinkage, so the numbers are on the record even when the assertions pass.

On success the gate **amends the run-health report** — it writes a stamped, idempotent
``ESCALATION-CONSERVATION`` block into ``scorecard/run_health_<tag>_report.md`` recording the verified funnel,
so the report itself carries the confirmation that links 3–5 held (run-health only says the gate *should* run).

Read-only except for that stamped block. Mirrors ``evaluation/regression_edge_cases.py`` assertion style. Run
after a driver pass (or an ``escalate --apply`` + accumulate):

    uv run python -m bac_metadata.bac_agentic_metadata.evaluation.verify_escalation_conservation \
        --data-dir .../applications/klebsiella/data --tags train,test,tail100,tail50_99,tail25_49,tail10_24
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd

from bac_metadata.bac_agentic_metadata.engine import backfill as bf

#: A resolved decision with no value is a *skip* (a deliberate "no single whole-field value"), not a fill —
#: mirrors accumulate._RESOLVED_NOTE_MARKERS. An engine-generated ``auto-skip`` is regenerable, never a fill.
_SKIP_NOTE_MARKERS = ("reject", "skip", "undeterm", "leave uncoded", "no value")
_CONSERVATION_MARKER = "<!-- ESCALATION-CONSERVATION -->"


def _read_tsv(path: Path) -> pd.DataFrame:
    """Read a TSV as strings (blanks preserved), or an empty frame if absent/empty."""
    try:
        return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return pd.DataFrame()


def _nonblank(series: pd.Series) -> pd.Series:
    """Engine-canonical non-blank mask (placeholder nulls count as blank), matching the fill/guard logic."""
    return bf.strip_placeholders(series).notna()


def _answered_pairs(decisions: pd.DataFrame) -> set[tuple[str, str]]:
    """The (study, field) decisions the curator answered with a real value (must produce a fill)."""
    if not len(decisions) or "answer" not in decisions.columns:
        return set()
    ans = decisions[_nonblank(decisions["answer"])]
    return set(zip(ans["study_accession"], ans["field"], strict=False))


def _git_head_tsv(repo_root: Path, path: Path) -> pd.DataFrame | None:
    """Read a TSV as it stands at git HEAD (None if the path is untracked / no committed version)."""
    try:
        rel = path.resolve().relative_to(repo_root)
    except ValueError:
        return None
    try:
        blob = subprocess.run(["git", "-C", str(repo_root), "show", f"HEAD:{rel}"],
                              capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        return None
    from io import StringIO

    if not blob.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(blob), sep="\t", dtype=str, keep_default_na=False)


def _repo_root(start: Path) -> Path:
    """Nearest ancestor holding a .git dir (for the git HEAD comparison); falls back to start.

    Resolves ``start`` first so a relative input doesn't collapse to ``.`` (which would then fail the
    absolute ``relative_to`` in :func:`_git_head_tsv` and wrongly SKIP the master-preserve check).
    """
    start = start.resolve()
    for p in [start, *start.parents]:
        if (p / ".git").exists():
            return p
    return start


def check_inv1_apply(esc_dir: Path, tag: str, fails: list[str]) -> dict:
    """INV1 — every answered decision has ≥1 non-blank curator_escalation fill in escalation_applied."""
    decisions = _read_tsv(esc_dir / f"decisions_needed_{tag}.tsv")
    applied = _read_tsv(esc_dir / f"escalation_applied_{tag}.tsv")
    answered = _answered_pairs(decisions)
    if len(applied) and {"applied_value", "study_accession", "field"} <= set(applied.columns):
        filled_rows = applied[_nonblank(applied["applied_value"])]
        applied_pairs = set(zip(filled_rows["study_accession"], filled_rows["field"], strict=False))
    else:
        applied_pairs = set()
    missing = sorted(answered - applied_pairs)
    ok = not missing
    ev = f"{len(answered)} answered → {len(answered & applied_pairs)} applied"
    if missing:
        ev += f"; UNAPPLIED: {', '.join(f'{s}/{f}' for s, f in missing[:6])}"
        fails.append(f"[{tag}] INV1 apply: {len(missing)} answered decision(s) never applied")
    print(f"  {'PASS' if ok else 'FAIL'}  [{tag}] INV1 apply — {ev}")
    return {"answered": len(answered), "applied_pairs": len(applied_pairs), "n_fills": int(_nonblank(
        applied["applied_value"]).sum()) if len(applied) and "applied_value" in applied.columns else 0}


def check_inv3_fill(esc_dir: Path, enriched_dir: Path, tag: str, fails: list[str]) -> dict:
    """INV3 — every non-blank escalation fill lands non-blank in the final filled_metadata table."""
    applied = _read_tsv(esc_dir / f"escalation_applied_{tag}.tsv")
    filled = _read_tsv(enriched_dir / f"filled_metadata_{tag}.tsv")
    if not len(applied) or "applied_value" not in applied.columns:
        print(f"  PASS  [{tag}] INV3 fill — no escalation fills to trace")
        return {"traced": 0, "in_final": 0}
    fills = applied[_nonblank(applied["applied_value"])]
    if not len(filled) or "sample_accession" not in filled.columns:
        fails.append(f"[{tag}] INV3 fill: {len(fills)} escalation fill(s) but no filled_metadata_{tag}.tsv")
        print(f"  FAIL  [{tag}] INV3 fill — filled_metadata_{tag}.tsv missing/empty ({len(fills)} fills orphaned)")
        return {"traced": len(fills), "in_final": 0}
    fm = filled.set_index("sample_accession")
    lost: list[str] = []
    in_final = 0
    for _, r in fills.iterrows():
        sample, field = r["sample_accession"], r["field"]
        if sample not in fm.index or field not in fm.columns:
            lost.append(f"{sample}/{field}(absent)")
            continue
        cell = fm.at[sample, field]
        cell = cell.iloc[0] if isinstance(cell, pd.Series) else cell  # duplicate sample rows → take first
        if bf.strip_placeholders(pd.Series([cell])).isna().iloc[0]:
            lost.append(f"{sample}/{field}(blank)")
        else:
            in_final += 1
    ok = not lost
    ev = f"{len(fills)} escalation fills → {in_final} non-blank in final"
    if lost:
        ev += f"; LOST: {', '.join(lost[:6])}"
        fails.append(f"[{tag}] INV3 fill: {len(lost)} escalation fill(s) blank/absent in final")
    print(f"  {'PASS' if ok else 'FAIL'}  [{tag}] INV3 fill — {ev}")
    return {"traced": len(fills), "in_final": in_final}


def check_inv2_master(master_path: Path, fails: list[str]) -> dict:
    """INV2 — the curated_escalations master on disk ⊇ its git-HEAD self (never shrinks, never drops a key)."""
    disk = _read_tsv(master_path)
    disk_pairs = set(zip(disk["study_accession"], disk["field"], strict=False)) if len(disk) else set()
    head = _git_head_tsv(_repo_root(master_path), master_path)
    if head is None:
        print("  SKIP  INV2 master-preserve — no committed HEAD version to compare (untracked/first commit)")
        return {"disk_rows": len(disk), "head_rows": None, "dropped": 0}
    head_pairs = set(zip(head["study_accession"], head["field"], strict=False)) if len(head) else set()
    dropped = sorted(head_pairs - disk_pairs)
    shrank = len(disk) < len(head)
    ok = not dropped and not shrank
    ev = f"disk {len(disk)} rows vs HEAD {len(head)} rows"
    if dropped:
        ev += f"; DROPPED: {', '.join(f'{s}/{f}' for s, f in dropped[:6])}"
        fails.append(f"INV2 master-preserve: {len(dropped)} committed decision(s) missing from disk master")
    if shrank and not dropped:
        ev += "; row count SHRANK (rows lost with no key drop — inspect)"
        fails.append("INV2 master-preserve: master row count shrank vs HEAD")
    print(f"  {'PASS' if ok else 'FAIL'}  INV2 master-preserve — {ev}")
    return {"disk_rows": len(disk), "head_rows": len(head), "dropped": len(dropped)}


def _amend_run_health(score_dir: Path, tag: str, inv1: dict, inv3: dict, inv2: dict) -> None:
    """Write an idempotent, stamped conservation block into run_health_<tag>_report.md (verified confirmation)."""
    md_path = score_dir / f"run_health_{tag}_report.md"
    if not md_path.exists():
        print(f"  [amend] run_health_{tag}_report.md absent — skipped (run run-health first)", file=sys.stderr)
        return
    head = f"disk {inv2['disk_rows']} ⊇ HEAD {inv2['head_rows']} rows" if inv2["head_rows"] is not None \
        else f"disk {inv2['disk_rows']} rows (no HEAD baseline)"
    block = (
        f"{_CONSERVATION_MARKER}\n"
        f"## ✅ Escalation conservation VERIFIED — links 3–5 confirmed\n\n"
        "`verify_escalation_conservation.py` traced every curator decision through apply → master → final and "
        "found none lost:\n\n"
        f"- **INV1 apply** — {inv1['answered']} answered decision(s) → {inv1['applied_pairs']} applied "
        f"(study×field), {inv1['n_fills']} per-sample fills. 0 unapplied.\n"
        f"- **INV2 master-preserve** — curated_escalations {head}; 0 committed decisions dropped.\n"
        f"- **INV3 fill** — {inv3['traced']} escalation fill(s) → {inv3['in_final']} non-blank in "
        f"filled_metadata_{tag}. 0 lost to a blank final cell.\n"
    )
    text = md_path.read_text()
    idx = text.find(_CONSERVATION_MARKER)
    text = (text[:idx].rstrip() + "\n\n" + block) if idx != -1 else (text.rstrip() + "\n\n---\n\n" + block)
    md_path.write_text(text if text.endswith("\n") else text + "\n")
    print(f"  [amend] stamped conservation block into run_health_{tag}_report.md", file=sys.stderr)


def main() -> None:
    """Run every conservation invariant per tag (+ the master vs HEAD), amend run-health, exit non-zero on fail."""
    ap = argparse.ArgumentParser(description="Escalation-conservation gate — no curator decision silently lost.")
    ap.add_argument("--data-dir", required=True, help="Application data tree root.")
    ap.add_argument("--tags", required=True, help="Comma-separated run tags (e.g. train,test,tail100).")
    ap.add_argument("--no-amend", action="store_true", help="Do not write the verified block into run-health.")
    args = ap.parse_args()

    data = Path(args.data_dir)
    esc_dir = data / "study_lv_attributes" / "escalation"
    enriched_dir = data / "sample_lv_attributes" / "enriched"
    score_dir = data / "scorecard"
    master_path = data / "curated" / "curated_escalations.tsv"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    fails: list[str] = []
    print("Escalation-conservation gate — answer → apply → master → final\n")

    # INV2 once (the cross-tag master vs its committed self).
    inv2 = check_inv2_master(master_path, fails)

    per_tag: dict[str, tuple[dict, dict]] = {}
    inv2_ok = not any("INV2" in f for f in fails)
    for tag in tags:
        before = len(fails)
        inv1 = check_inv1_apply(esc_dir, tag, fails)
        inv3 = check_inv3_fill(esc_dir, enriched_dir, tag, fails)
        per_tag[tag] = (inv1, inv3)
        # Only stamp the "VERIFIED" block when THIS tag's links (and the master) held — never claim
        # conservation over a run where an answer was actually lost (INV1/INV3 for the tag, INV2 for master).
        tag_ok = (len(fails) == before) and inv2_ok
        if not args.no_amend:
            if tag_ok:
                _amend_run_health(score_dir, tag, inv1, inv3, inv2)
            else:
                print(f"  [amend] {tag}: invariants FAILED — run-health NOT stamped (fix the loss, rerun)",
                      file=sys.stderr)

    # INV4 funnel roll-up.
    print("\nINV4 conservation funnel (answered → applied study×field → escalation fills → in final):")
    for tag, (inv1, inv3) in per_tag.items():
        print(f"  {tag:<12} answered {inv1['answered']:>3} → applied {inv1['applied_pairs']:>3} "
              f"→ fills {inv3['traced']:>5} → in final {inv3['in_final']:>5}")

    print(f"\n{'ALL CONSERVATION INVARIANTS HOLD' if not fails else f'{len(fails)} FAILURE(S):'}")
    for f in fails:
        print(f"  ⛔ {f}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
