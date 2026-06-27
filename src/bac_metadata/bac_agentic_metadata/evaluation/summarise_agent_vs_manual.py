r"""Agent vs manual-curation accounting: agreement, then adjudicated accuracy of each (Klebsiella).

The frozen sheet is **manual curation, not ground truth**, so an agent-vs-sheet "accuracy" is really
**agreement**. This script reframes the measured results accordingly. Per item (paper-finding, and the
two primary grading attributes ``amr_study`` / ``study_setting``) it reports:

* **agreement** — how often the agent and the manual curation already agree;
* on the **disagreements** the opposing **Opus adjudicator** ruled (with a verbatim quote): how often
  the **agent** was right (a manual-curation error) vs the **manual curation** was right (an agent
  error), plus ties (both defensible) and undetermined;
* the derived **adjudicated accuracy of the agent** and **of the manual curation**, and the **Δ**
  improvement the agent delivers over manual curation.

Agreements are assumed jointly correct (only disagreements are adjudicated) — so both accuracies are
upper bounds on any undetected joint error. Reads the existing validation + adjudication artifacts; runs
no model. Writes ``data/<prefix>_agent_vs_manual.{md,tsv}``.

Examples
--------
uv run python .../summarise_agent_vs_manual.py                               # default Sonnet run
uv run python .../summarise_agent_vs_manual.py --grades data/study_grades_opus.tsv \\
    --find-validation data/find_opus_validation_report.tsv \\
    --find-adjudication data/find_opus_adjudication_report.tsv \\
    --grading-adjudication data/grading_opus_adjudication_report.tsv --prefix opus
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import pandas as pd

SELF_DIR = Path(__file__).resolve().parent  # this evaluation/ dir (for the sibling path-load)
APP_DIR = SELF_DIR.parents[1] / "applications" / "klebsiella"  # gold-bearing app tree (see evaluation/__init__.py)
DATA_DIR = APP_DIR / "data"


def _load_validator():
    """Import the sibling ``validate_study_grading`` module by path (reuse its frozen-GT loaders)."""
    spec = importlib.util.spec_from_file_location("_vsg", SELF_DIR / "validate_study_grading.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's κ between the two raters' labels — observed agreement corrected for chance.

    ``κ = (p_o − p_e) / (1 − p_e)`` where ``p_o`` is observed agreement and ``p_e`` the agreement
    expected from the two label distributions by chance. Nominal (unweighted). Returns NaN if it is
    undefined (no pairs, or perfect chance agreement when one label dominates entirely).
    """
    from collections import Counter

    n = len(pairs)
    if n == 0:
        return float("nan")
    p_o = sum(1 for a, b in pairs if a == b) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    p_e = sum((ca[c] / n) * (cb[c] / n) for c in set(ca) | set(cb))
    return (p_o - p_e) / (1 - p_e) if p_e != 1 else float("nan")


def _account(agree: int, agent_right: int, manual_right: int, tie: int, undet: int,
             kappa: float | None = None) -> dict:
    """Assemble one accounting row + derived agreement / κ / agent-accuracy / manual-accuracy / Δ."""
    n = agree + agent_right + manual_right + tie + undet
    den = n - undet  # undetermined disagreements excluded from the accuracy denominator
    agent_acc = (agree + agent_right + tie) / den if den else float("nan")
    manual_acc = (agree + manual_right + tie) / den if den else float("nan")
    return {
        "N": n, "agreement_n": agree, "agreement": round(agree / n, 4) if n else float("nan"),
        "agent_right": agent_right, "manual_right": manual_right, "tie": tie, "undetermined": undet,
        "cohen_kappa": (round(kappa, 4) if kappa is not None and kappa == kappa else None),
        "agent_accuracy": round(agent_acc, 4), "manual_accuracy": round(manual_acc, 4),
        "improvement": round(agent_acc - manual_acc, 4),
    }


def _read_tsv(path: Path, columns: list[str]) -> pd.DataFrame:
    """Read a TSV; return an empty frame with ``columns`` if it is missing or empty.

    A fold with zero disagreements writes a header-less adjudication file (grading), or none at all
    (finding only writes its adjudication report when there are mismatches) — e.g. the test fold.
    """
    try:
        return pd.read_csv(path, sep="\t", dtype=str)
    except (pd.errors.EmptyDataError, FileNotFoundError) as exc:
        print(f"WARNING: adjudication file {Path(path).name} is missing/empty ({type(exc).__name__}); "
              "treating as 0 rows — verify the upstream validator wrote it (paths may be stale).",
              file=sys.stderr)
        return pd.DataFrame(columns=columns)


def _finding(find_validation: Path, find_adjudication: Path) -> dict:
    """Finding accounting: agreement = exact+title matches; verdicts from the find-adjudication."""
    fv = _read_tsv(find_validation, ["category"])
    fa = _read_tsv(find_adjudication, ["adj_verdict"])
    agree = int(fv["category"].isin(["exact_match", "title_match"]).sum())
    v = fa["adj_verdict"].value_counts().to_dict() if "adj_verdict" in fa.columns else {}
    return {"item": "paper-finding",
            **_account(agree, v.get("found_correct", 0), v.get("curated_correct", 0), v.get("both_describe", 0), 0)}


def _grading(attr: str, agent_map: dict[str, str], manual_map: dict[str, str],
             gc_set: set, adj_verdict: dict) -> dict:
    """One grading attribute: agreement vs the original sheet, disagreements classed by verdict."""
    agree = agent_right = manual_right = tie = undet = 0
    pairs: list[tuple[str, str]] = []  # (agent_label, manual_label) for Cohen's κ
    for acc, man in manual_map.items():
        man = (man or "").strip().lower()
        agent = agent_map.get(acc, "")
        if not man or not agent:
            continue
        pairs.append((agent, man))
        if agent == man:
            agree += 1
            continue
        key = (acc, attr)
        if key in gc_set:  # David-verified manual-curation error (agent right)
            agent_right += 1
        else:
            verd = adj_verdict.get(key)
            if verd == "model_correct":
                agent_right += 1
            elif verd == "sheet_correct":
                manual_right += 1
            elif verd == "both_defensible":
                tie += 1
            else:
                undet += 1
    return {"item": attr, **_account(agree, agent_right, manual_right, tie, undet, _cohen_kappa(pairs))}


def main() -> None:
    """Compute the agent-vs-manual accounting across finding + grading and write the report."""
    p = argparse.ArgumentParser(description="Agent vs manual-curation accounting (Klebsiella).")
    p.add_argument("--grades", default=str(DATA_DIR / "study_lv_attributes" / "grading" / "study_grades.tsv"))
    p.add_argument("--find-validation", default=str(DATA_DIR / "find_papers" / "find_validation_report.tsv"))
    p.add_argument("--find-adjudication", default=str(DATA_DIR / "find_papers" / "find_adjudication_report.tsv"))
    p.add_argument("--grading-adjudication", default=str(DATA_DIR / "study_lv_attributes" / "grading" / "grading_adjudication_report.tsv"))
    p.add_argument("--prefix", default="sonnet", help="Run tag for the output basename (e.g. sonnet, opus).")
    args = p.parse_args()

    vsg = _load_validator()
    gt = vsg._gt_by_accession().set_index("study_accession")
    ss_frozen = vsg._study_setting_frozen() or {}

    g = pd.read_csv(args.grades, sep="\t", dtype=str).fillna("")
    amr_agent = {r["study_accession"]: r.get("amr_study__value", "").strip().lower() for _, r in g.iterrows()}
    ss_agent = {r["study_accession"]: r.get("study_setting__value", "").strip().lower() for _, r in g.iterrows()}

    gc = pd.read_csv(vsg.GT_CORRECTIONS, sep="\t", dtype=str).fillna("") if vsg.GT_CORRECTIONS.exists() else \
        pd.DataFrame(columns=["study_accession", "attribute"])
    gc_set = {(r["study_accession"], r["attribute"]) for _, r in gc.iterrows()}
    ga = _read_tsv(args.grading_adjudication, ["study_accession", "attribute", "verdict"])
    adj_verdict = {(r["study_accession"], r["attribute"]): r["verdict"] for _, r in ga.iterrows()}

    rows = [
        _finding(Path(args.find_validation), Path(args.find_adjudication)),
        _grading("amr_study", amr_agent, {a: gt.loc[a, "gt_amr_study"] for a in gt.index}, gc_set, adj_verdict),
        _grading("study_setting", ss_agent, ss_frozen, gc_set, adj_verdict),
    ]
    res = pd.DataFrame(rows)
    tot = res[["agreement_n", "agent_right", "manual_right", "tie", "undetermined"]].sum()
    total_row = {"item": "TOTAL", **_account(int(tot["agreement_n"]), int(tot["agent_right"]),
                                             int(tot["manual_right"]), int(tot["tie"]), int(tot["undetermined"]))}
    res = pd.concat([res, pd.DataFrame([total_row])], ignore_index=True)

    def _kappa(v: object) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) and v == v else "—"

    md = ["# Agent vs manual curation — agreement, then adjudicated accuracy of each (train+val)\n",
          "The frozen sheet is *manual curation*, not ground truth, so agent-vs-sheet is **agreement**, "
          "not accuracy. **agreement** is observed agreement *n (ratio)*; **Cohen κ** is that agreement "
          "corrected for chance (categorical raters only — finding/TOTAL N/A). On the disagreements the "
          "Opus adjudicator ruled, we count who was right and derive each side's **adjudicated accuracy**. "
          "Agreements are assumed jointly correct.\n",
          "| item | N judged | agreement | agent right | manual right | tie | undet | Cohen κ | agent acc | manual acc | Δ (agent−manual) |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for _, r in res.iterrows():
        md.append(f"| {r['item']} | {int(r['N'])} | {int(r['agreement_n'])} ({r['agreement']:.2f}) | "
                  f"{int(r['agent_right'])} | {int(r['manual_right'])} | {int(r['tie'])} | "
                  f"{int(r['undetermined'])} | {_kappa(r['cohen_kappa'])} | {r['agent_accuracy']:.2f} | "
                  f"{r['manual_accuracy']:.2f} | {r['improvement']:+.2f} |")
    md.append("\n- **agreement** = observed agreement (p₀); **Cohen κ** = chance-corrected agreement "
              "(can read low when one label dominates — the prevalence effect — even at high p₀).")
    md.append("- **agent right** = adjudicated manual-curation errors the agent corrects; "
              "**manual right** = agent errors. When they disagree the agent is right far more often.")

    (DATA_DIR / "scorecard" / f"agent_vs_manual_{args.prefix}.md").write_text("\n".join(md) + "\n")
    res.to_csv(DATA_DIR / "scorecard" / f"agent_vs_manual_{args.prefix}.tsv", sep="\t", index=False)
    print(f"Wrote agent_vs_manual_{args.prefix}.{{md,tsv}}", file=sys.stderr)
    print(res.to_string(index=False), file=sys.stderr)


if __name__ == "__main__":
    main()
