r"""Standalone figure report for the curated M. abscessus metadata master.

Reproduces the Klebsiella figure set (grouped light/steel-blue pre/post-curation bars + a plotly
choropleth) for M. abscessus, plus CF-vs-non-CF views. Self-contained in the application folder for now
(may be promoted into the engine later). No LLM: the "pre-curation" side is the raw ENA base table
categorised via a value->category join on the existing reassignment audits + the deterministic
country/date parsers from ``pp.metadata_curation``; the "post-curation" side is the reconciled final
master.

Figures (each written as PDF + PNG into ``visualisations/``; the map also as HTML):
  1. host_category_pre_and_post_curation
  2. isolation_source_category_pre_and_post_curation
  3. region_distribution_pre_and_post_curation
  3b. cf_status_pre_and_post_curation        (Not-filled -> filled; filled split CF / non-CF)
  4. collection_date_5yr_bins_cf_vs_noncf   (5-year bins, paired CF vs non-CF)
  5. country_distribution_cf_vs_noncf        (top-N countries)
  6. region_distribution_cf_vs_noncf
  7. country_map_cf_vs_noncf                 (two-panel CF | non-CF choropleth)

Run::

    uv run python src/bac_metadata/bac_agentic_metadata/applications/m_abs/report_metadata.py
"""

from __future__ import annotations

import argparse
import contextlib
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from bac_metadata.pp.metadata_curation import (
    categorise_region,
    parse_collection_date,
    parse_country,
)

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
FINAL = DATA / "curated" / "metadata_curated_master_final.tsv"
BASE = DATA / "inputs" / "base_table.csv"
CAT_DIR = DATA / "study_lv_attributes" / "categorisation"
OUT_DIR = HERE / "visualisations"

PRE, POST = "lightblue", "steelblue"      # pre/post-curation palette (matches Klebsiella)
CF_C, NONCF_C = "#c44e52", "#4c72b0"      # CF (red) vs non-CF (blue)
NOT_FILLED = {"", "NA"}                    # blank cell OR uninformative "NA" -> not usable


# --------------------------------------------------------------------------- IO + frames
def _read(path: Path) -> pd.DataFrame:
    sep = "\t" if str(path).endswith(".tsv") else ","
    return pd.read_csv(path, sep=sep, dtype=str, low_memory=False, keep_default_na=False)


def _audit_map(field: str) -> dict[str, str]:
    """Value -> category from the ``apply`` reassignment audit (informative values only)."""
    a = pd.read_csv(CAT_DIR / f"{field}_reassignment_audit.tsv", sep="\t", keep_default_na=False, dtype=str)
    return dict(zip(a["value"], a["category"], strict=False))


def _build_pre_frame(base: pd.DataFrame) -> pd.DataFrame:
    """Categorise the raw ENA base table exactly as curation would, but with NO fills (pre-curation)."""
    df = base.copy()
    df["host_category"] = df["host"].map(_audit_map("host"))
    df["isolation_source_category"] = df["isolation_source"].map(_audit_map("isolation_source"))
    with open(os.devnull, "w") as devnull, contextlib.redirect_stdout(devnull):
        df = parse_country(df, verbose=False)
        df = categorise_region(df, verbose=False)
        df = parse_collection_date(df, verbose=False)
    return df


def _cat_counts(series: pd.Series) -> tuple[pd.Series, int]:
    """Return (real-category counts desc, not-filled count) — blank/``NA`` fold into not-filled."""
    s = series.fillna("").astype(str)
    not_filled = int(s.isin(NOT_FILLED).sum())
    real = s[~s.isin(NOT_FILLED)].value_counts()
    return real, not_filled


# --------------------------------------------------------------------------- plot helpers
def _bars(ax, cats, series_a, series_b, label_a, label_b, colour_a, colour_b, width=0.45):
    """Grouped two-series bars with ``{:,}`` value labels + horizontal grid (the Klebsiella style)."""
    x = np.arange(len(cats))
    b1 = ax.bar(x - width / 2, series_a, width, label=label_a, color=colour_a)
    b2 = ax.bar(x + width / 2, series_b, width, label=label_b, color=colour_b)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, rotation=45, ha="right", fontsize=11)
    ax.grid(axis="y", alpha=0.3)
    for bars in (b1, b2):
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2.0, h, f"{int(h):,}",
                        ha="center", va="bottom", fontsize=9)
    return b1, b2


def _save_mpl(fig, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / f"{stem}.png", dpi=300, bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{stem}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"  wrote {stem}.pdf / .png")


def _save_plotly(fig, stem: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.write_html(OUT_DIR / f"{stem}.html")
    fig.write_image(OUT_DIR / f"{stem}.png", width=1600, height=650, scale=2)
    fig.write_image(OUT_DIR / f"{stem}.pdf", width=1600, height=650)
    print(f"  wrote {stem}.pdf / .png / .html")


# --------------------------------------------------------------------------- figures 1-3 (pre/post)
def fig_host(pre: pd.DataFrame, post: pd.DataFrame) -> None:
    """3-panel host: Human | non-human | Not-filled, pre vs post-curation."""
    pre_r, pre_nf = _cat_counts(pre["host_category"])
    post_r, post_nf = _cat_counts(post["host_category"])
    non_human = [c for c in post_r.index if c != "human"]  # order by post count

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(14, 8), gridspec_kw={"width_ratios": [1, 4, 1]})
    fig.suptitle("Hosts, pre- and post-curation", fontsize=16, fontweight="bold")
    _bars(ax1, ["human"], [pre_r.get("human", 0)], [post_r.get("human", 0)],
          "Pre-curation", "Post-curation", PRE, POST, width=0.35)
    ax1.set_ylabel("Number of samples", fontsize=12)
    ax1.set_title("Human", fontsize=14, fontweight="bold")
    _bars(ax2, non_human, [pre_r.get(c, 0) for c in non_human], [post_r.get(c, 0) for c in non_human],
          "Pre-curation", "Post-curation", PRE, POST)
    ax2.set_title("Non-human hosts", fontsize=14, fontweight="bold")
    ax2.legend(fontsize=11)
    _bars(ax3, ["Not-filled"], [pre_nf], [post_nf], "Pre-curation", "Post-curation", PRE, POST, width=0.35)
    ax3.set_title("Not-filled", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_mpl(fig, "host_category_pre_and_post_curation")


def _fig_prepost_2panel(pre_col, post_col, title, main_title, stem, truncate=False):
    """2-panel pre/post (main categories wide + Not-filled narrow), ordered by post count."""
    pre_r, pre_nf = _cat_counts(pre_col)
    post_r, post_nf = _cat_counts(post_col)
    cats = list(post_r.index)  # by post count desc
    for c in pre_r.index:      # append any category only present pre-curation
        if c not in cats:
            cats.append(c)
    labels = [" ".join(str(c).split()[:3]) for c in cats] if truncate else cats

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 8), gridspec_kw={"width_ratios": [11, 1]})
    fig.suptitle(title, fontsize=16, fontweight="bold")
    b1, _ = _bars(ax1, labels, [pre_r.get(c, 0) for c in cats], [post_r.get(c, 0) for c in cats],
                  "Pre-curation", "Post-curation", PRE, POST)
    ax1.set_ylabel("Number of samples", fontsize=12)
    ax1.set_title(main_title, fontsize=14, fontweight="bold")
    ax1.legend(fontsize=11)
    _bars(ax2, ["Not-filled"], [pre_nf], [post_nf], "Pre-curation", "Post-curation", PRE, POST, width=0.35)
    ax2.set_title("Not-filled", fontsize=14, fontweight="bold")
    fig.tight_layout()
    _save_mpl(fig, stem)


def fig_isolation(pre, post):
    """2-panel isolation_source_category pre/post."""
    _fig_prepost_2panel(pre["isolation_source_category"], post["isolation_source_category"],
                        "Isolation source, pre- and post-curation", "Isolation sources",
                        "isolation_source_category_pre_and_post_curation", truncate=True)


def fig_region(pre, post):
    """2-panel region pre/post."""
    _fig_prepost_2panel(pre["region"], post["region"],
                        "Region, pre- and post-curation", "Region distribution",
                        "region_distribution_pre_and_post_curation")


# --------------------------------------------------------------------------- figures 4-6 (CF split)
def _cf_frame(post: pd.DataFrame) -> pd.DataFrame:
    """Rows with a definite binary cf_status (blank excluded)."""
    return post[post["cf_status"].isin(["CF", "non-CF"])].copy()


def fig_date_bins(post: pd.DataFrame) -> None:
    """Collection date in 5-year bins, paired CF vs non-CF columns."""
    d = _cf_frame(post)
    yr = pd.to_numeric(d["collection_year"], errors="coerce")
    d = d.assign(_yr=yr).dropna(subset=["_yr"])
    edges = [-np.inf, 1999, 2004, 2009, 2014, 2019, 2024, np.inf]
    labels = ["<2000", "2000–04", "2005–09", "2010–14", "2015–19", "2020–24", "2025+"]
    d["_bin"] = pd.cut(d["_yr"], bins=edges, labels=labels)
    cf = d[d["cf_status"] == "CF"]["_bin"].value_counts().reindex(labels, fill_value=0)
    nc = d[d["cf_status"] == "non-CF"]["_bin"].value_counts().reindex(labels, fill_value=0)

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("Collection date (5-year bins), CF vs non-CF", fontsize=15, fontweight="bold")
    _bars(ax, labels, cf.values, nc.values, "CF", "non-CF", CF_C, NONCF_C)
    ax.set_ylabel("Number of samples", fontsize=12)
    ax.set_xlabel("Collection period", fontsize=12)
    ax.legend(fontsize=11)
    fig.tight_layout()
    _save_mpl(fig, "collection_date_5yr_bins_cf_vs_noncf")


def fig_country_cf(post: pd.DataFrame, top_n: int = 20) -> None:
    """Top-N countries by total samples, CF vs non-CF."""
    d = _cf_frame(post)
    d = d[d["country_parsed"].fillna("") != ""]
    top = d["country_parsed"].value_counts().head(top_n).index.tolist()
    cf = d[d["cf_status"] == "CF"]["country_parsed"].value_counts().reindex(top, fill_value=0)
    nc = d[d["cf_status"] == "non-CF"]["country_parsed"].value_counts().reindex(top, fill_value=0)

    fig, ax = plt.subplots(figsize=(16, 8))
    fig.suptitle(f"Top {top_n} countries, CF vs non-CF", fontsize=15, fontweight="bold")
    _bars(ax, top, cf.values, nc.values, "CF", "non-CF", CF_C, NONCF_C)
    ax.set_ylabel("Number of samples", fontsize=12)
    ax.legend(fontsize=11)
    fig.tight_layout()
    _save_mpl(fig, "country_distribution_cf_vs_noncf")


def fig_region_cf(post: pd.DataFrame) -> None:
    """Regions, CF vs non-CF."""
    d = _cf_frame(post)
    d = d[d["region"].fillna("") != ""]
    regions = d["region"].value_counts().index.tolist()
    cf = d[d["cf_status"] == "CF"]["region"].value_counts().reindex(regions, fill_value=0)
    nc = d[d["cf_status"] == "non-CF"]["region"].value_counts().reindex(regions, fill_value=0)

    fig, ax = plt.subplots(figsize=(12, 7))
    fig.suptitle("Region, CF vs non-CF", fontsize=15, fontweight="bold")
    _bars(ax, regions, cf.values, nc.values, "CF", "non-CF", CF_C, NONCF_C)
    ax.set_ylabel("Number of samples", fontsize=12)
    ax.legend(fontsize=11)
    fig.tight_layout()
    _save_mpl(fig, "region_distribution_cf_vs_noncf")


# cf_status normalisation to the binary form (raw base carries case/junk variants; matches reconcile).
CF_NORMALISE = {"Non-CF": "non-CF", "?": "", "Environmental": ""}


def fig_cf_status(pre: pd.DataFrame, post: pd.DataFrame) -> None:
    """cf_status completeness, pre vs post-curation: Not-filled shrinks; filled splits into CF / non-CF."""
    def _c(series):
        s = series.fillna("").astype(str).replace(CF_NORMALISE)
        return {"CF": int((s == "CF").sum()), "non-CF": int((s == "non-CF").sum()),
                "Not-filled": int((s == "").sum())}

    pre_c, post_c = _c(pre["cf_status"]), _c(post["cf_status"])
    cats = ["CF", "non-CF", "Not-filled"]
    fig, ax = plt.subplots(figsize=(9, 7))
    fig.suptitle("cf_status, pre- and post-curation", fontsize=15, fontweight="bold")
    _bars(ax, cats, [pre_c[c] for c in cats], [post_c[c] for c in cats],
          "Pre-curation", "Post-curation", PRE, POST)
    ax.set_ylabel("Number of samples", fontsize=12)
    ax.legend(fontsize=11)
    fig.tight_layout()
    _save_mpl(fig, "cf_status_pre_and_post_curation")


# --------------------------------------------------------------------------- figure 7 (two-panel map)
def _iso3(names) -> dict[str, str]:
    """Country name -> ISO-3 via pycountry fuzzy + the plot_country_map alias fallbacks."""
    import pycountry
    aliases = {"USA": "USA", "United States of America": "USA", "United Kingdom": "GBR",
               "United Arab Emirates": "ARE", "South Korea": "KOR", "Vietnam": "VNM",
               "Czech Republic": "CZE", "Czechia": "CZE"}
    out = {}
    for n in names:
        try:
            out[n] = pycountry.countries.search_fuzzy(n)[0].alpha_3
        except (LookupError, IndexError):
            if n in aliases:
                out[n] = aliases[n]
    return out


def fig_map_cf(post: pd.DataFrame) -> None:
    """Two-panel choropleth (CF | non-CF) of per-country sample counts (green Robinson map)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d = _cf_frame(post)
    d = d[d["country_parsed"].fillna("") != ""]
    iso = _iso3(d["country_parsed"].unique())
    zmax = int(d.groupby(["cf_status", "country_parsed"]).size().max())

    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "choropleth"}, {"type": "choropleth"}]],
                        subplot_titles=("CF", "non-CF"), horizontal_spacing=0.02)
    for i, status in enumerate(["CF", "non-CF"], start=1):
        cc = d[d["cf_status"] == status]["country_parsed"].value_counts()
        locs = [iso[c] for c in cc.index if c in iso]
        vals = [int(cc[c]) for c in cc.index if c in iso]
        txt = [c for c in cc.index if c in iso]
        fig.add_trace(go.Choropleth(
            locations=locs, locationmode="ISO-3", z=vals, text=txt,
            zmin=0, zmax=zmax, colorscale="Greens",
            marker={"line": {"width": 0}},
            colorbar={"title": "samples"} if i == 2 else None, showscale=(i == 2),
            hovertemplate="<b>%{text}</b><br>samples: %{z:,}<extra></extra>",
            geo=f"geo{i if i > 1 else ''}",
        ), row=1, col=i)
    geo = {"showframe": False, "showcoastlines": False, "projection_type": "robinson",
           "lataxis": {"range": [-55, 70]}, "landcolor": "lightgray"}
    fig.update_layout(title_text="Sample distribution by country — CF vs non-CF",
                      geo=geo, geo2=geo, height=650, width=1600)
    _save_plotly(fig, "country_map_cf_vs_noncf")


def main() -> None:
    """Build every figure from the final master + raw base table."""
    global OUT_DIR
    ap = argparse.ArgumentParser(description="M. abscessus metadata figure report.")
    ap.add_argument("--final", default=str(FINAL), help="Reconciled final master TSV.")
    ap.add_argument("--base", default=str(BASE), help="Raw ENA base table (pre-curation).")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory for figures.")
    ap.add_argument("--top-n", type=int, default=20, help="Countries shown in the CF/non-CF country plot.")
    args = ap.parse_args()

    OUT_DIR = Path(args.out_dir)
    post = _read(Path(args.final))
    base = _read(Path(args.base))
    # Same cohort + one row per sample on both sides: the base export has multiple run-rows per sample
    # (7,217 rows / 6,455 samples), so dedup to one row per sample_accession and restrict to the final
    # cohort — otherwise the pre/post comparison double-counts and uses a wider denominator.
    base = (base[base["sample_accession"].isin(set(post["sample_accession"]))]
            .drop_duplicates(subset="sample_accession").copy())
    pre = _build_pre_frame(base)
    print(f"[report] post={len(post)} rows, pre(base, cohort-matched)={len(pre)} rows -> {OUT_DIR}")

    fig_host(pre, post)
    fig_isolation(pre, post)
    fig_region(pre, post)
    fig_cf_status(pre, post)
    fig_date_bins(post)
    fig_country_cf(post, top_n=args.top_n)
    fig_region_cf(post)
    fig_map_cf(post)
    print("[report] done.")


if __name__ == "__main__":
    main()
