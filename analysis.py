#!/usr/bin/env python3
"""
Ondo Assets Chain Analysis
Comparative ETH vs BSC distribution analysis for:
  - Number of Holders
  - Whale Concentration (Top-10)
  - Onchain Market Cap

Outputs:
  output/gaussian_distributions.csv  – bin frequencies + Gaussian PDF values + fitted params
  output/chain_distributions.png     – matplotlib figure with overlapping histograms + Gaussian curves
"""

import re
import csv
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from scipy import stats

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT    = Path(__file__).parent
IN_CSV  = ROOT / "output" / "ondo-assets-scraped.csv"
OUT_CSV = ROOT / "output" / "gaussian_distributions.csv"
OUT_PNG = ROOT / "output" / "chain_distributions.png"
OUT_PNG.parent.mkdir(exist_ok=True)

# ── Colour palette ─────────────────────────────────────────────────────────────
C_ETH    = "#2563EB"
C_BSC    = "#F59E0B"
ALPHA    = 0.55
CURVE_LW = 2.2

# ═══════════════════════════════════════════════════════════════════════════════
# Formatting helpers
# ═══════════════════════════════════════════════════════════════════════════════
def fmt_num(n):
    """Human-readable number: 1.5M, 300K, 42."""
    if n >= 1e6:  return f"{n/1e6:.1f}M"
    if n >= 1e3:  return f"{n/1e3:.0f}K"
    return f"{n:.0f}"


def fmt_log_mu(mu, log_scale):
    """Format Gaussian mean for legend: if log-scale, convert 10^mu back to readable number."""
    if log_scale:
        return fmt_num(10 ** mu)
    return f"{mu:.1f}"

# ── Parsers ────────────────────────────────────────────────────────────────────
def _num(s):
    s = str(s).replace("More than", "").replace(",", "").strip()
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else np.nan


def _money(s):
    s = str(s).replace("More than", "").replace(",", "").replace("$", "").strip()
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else np.nan


def _pct(s):
    s = str(s).replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan

# ═══════════════════════════════════════════════════════════════════════════════
# Gaussian fitting helpers
# ═══════════════════════════════════════════════════════════════════════════════
def fit_log_gaussian(data, x_range):
    """
    Fit Normal to log10(data), return (mu_log, sigma_log, pdf_in_original_scale).
    Uses Jacobian: pdf_orig = pdf_log / (x * ln10)
    """
    log_data = np.log10(data[data > 0])
    mu, sigma = stats.norm.fit(log_data)
    pdf_log  = stats.norm.pdf(np.log10(x_range), mu, sigma)
    pdf_orig = pdf_log / (x_range * np.log(10))
    return mu, sigma, pdf_orig


def fit_linear_gaussian(data, x_range):
    """Fit Normal directly to data. Return (mu, sigma, pdf at x_range)."""
    mu, sigma = stats.norm.fit(data)
    return mu, sigma, stats.norm.pdf(x_range, mu, sigma)

# ── Bin builders ───────────────────────────────────────────────────────────────
def log_bins(*datasets, n=14):
    combined = np.concatenate([d[d > 0] for d in datasets])
    lo = np.floor(np.log10(combined.min()))
    hi = np.ceil(np.log10(combined.max()))
    return np.logspace(lo, hi, n + 1)


def linear_bins(*datasets, n=14):
    combined = np.concatenate(datasets)
    lo = np.floor(combined.min() / 5) * 5
    hi = min(100.0, np.ceil(combined.max() / 5) * 5)
    return np.linspace(lo, hi, n + 1)

# ═══════════════════════════════════════════════════════════════════════════════
# Core analysis bundle builder
# ═══════════════════════════════════════════════════════════════════════════════
def analyse_metric(label, eth_data, bsc_data, bins, log_scale: bool):
    eth_counts, _ = np.histogram(eth_data, bins=bins)
    bsc_counts, _ = np.histogram(bsc_data, bins=bins)

    bw = np.diff(bins)
    eth_density = eth_counts / (eth_data.size * bw)
    bsc_density = bsc_counts / (bsc_data.size * bw)

    if log_scale:
        curve_x = np.logspace(np.log10(bins[0]), np.log10(bins[-1]), 500)
        eth_mu, eth_sigma, eth_curve = fit_log_gaussian(eth_data, curve_x)
        bsc_mu, bsc_sigma, bsc_curve = fit_log_gaussian(bsc_data, curve_x)
    else:
        curve_x = np.linspace(bins[0], bins[-1], 500)
        eth_mu, eth_sigma, eth_curve = fit_linear_gaussian(eth_data, curve_x)
        bsc_mu, bsc_sigma, bsc_curve = fit_linear_gaussian(bsc_data, curve_x)

    return dict(
        label=label, bins=bins, log_scale=log_scale,
        eth_data=eth_data, bsc_data=bsc_data,
        eth_counts=eth_counts, bsc_counts=bsc_counts,
        eth_density=eth_density, bsc_density=bsc_density,
        curve_x=curve_x,
        eth_curve=eth_curve, bsc_curve=bsc_curve,
        eth_mu=eth_mu, eth_sigma=eth_sigma,
        bsc_mu=bsc_mu, bsc_sigma=bsc_sigma,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# Load & clean data
# ═══════════════════════════════════════════════════════════════════════════════
print("Reading scraped data …")
df = pd.read_csv(IN_CSV)
for c in ("ETH_Holders", "BSC_Holders"):
    df[c] = df[c].apply(_num)
for c in ("ETH_Market_Cap", "BSC_Market_Cap"):
    df[c] = df[c].apply(_money)
for c in ("ETH_Whale_Top10_Pct", "BSC_Whale_Top10_Pct"):
    df[c] = df[c].apply(_pct).clip(upper=100.0)

eth_holders = df["ETH_Holders"].dropna().values
bsc_holders = df["BSC_Holders"].dropna().values
eth_mcap    = df.loc[df["ETH_Market_Cap"] > 0, "ETH_Market_Cap"].dropna().values
bsc_mcap    = df.loc[df["BSC_Market_Cap"] > 0, "BSC_Market_Cap"].dropna().values
eth_whale   = df["ETH_Whale_Top10_Pct"].dropna().values
bsc_whale   = df["BSC_Whale_Top10_Pct"].dropna().values

print(f"  ETH holders: {len(eth_holders)}  |  BSC holders: {len(bsc_holders)}")
print(f"  ETH mcap:    {len(eth_mcap)}  |  BSC mcap:    {len(bsc_mcap)}")
print(f"  ETH whale:   {len(eth_whale)}  |  BSC whale:   {len(bsc_whale)}")

# ═══════════════════════════════════════════════════════════════════════════════
# Build metric bundles
# ═══════════════════════════════════════════════════════════════════════════════
metrics = [
    analyse_metric(
        "Number of Holders",
        eth_holders, bsc_holders,
        log_bins(eth_holders, bsc_holders, n=14),
        log_scale=True,
    ),
    analyse_metric(
        "Onchain Market Cap (USD)",
        eth_mcap, bsc_mcap,
        log_bins(eth_mcap, bsc_mcap, n=14),
        log_scale=True,
    ),
    analyse_metric(
        "Whale Concentration – Top 10 Holders",
        eth_whale, bsc_whale,
        linear_bins(eth_whale, bsc_whale, n=14),
        log_scale=False,
    ),
]

# ═══════════════════════════════════════════════════════════════════════════════
# Save CSV
# ═══════════════════════════════════════════════════════════════════════════════
print("Writing gaussian_distributions.csv …")

fieldnames = [
    "section", "metric", "chain", "transform",
    "gaussian_mean", "gaussian_std", "n_assets",
    "bin_start", "bin_end", "bin_label",
    "frequency", "density", "gaussian_pdf",
]

def blank_row():
    return {k: "" for k in fieldnames}

rows = []

# — PARAMS section header —
hdr = blank_row()
hdr.update(section="PARAMS", metric="Metric", chain="Chain",
           transform="Transform", gaussian_mean="Gaussian_Mean",
           gaussian_std="Gaussian_Std", n_assets="N_Assets")
rows.append(hdr)

for m in metrics:
    transform = "log10" if m["log_scale"] else "linear"
    for chain, mu, sigma, data in [
        ("ETH", m["eth_mu"], m["eth_sigma"], m["eth_data"]),
        ("BSC", m["bsc_mu"], m["bsc_sigma"], m["bsc_data"]),
    ]:
        r = blank_row()
        r.update(section="PARAMS", metric=m["label"], chain=chain,
                 transform=transform,
                 gaussian_mean=round(mu, 6),
                 gaussian_std=round(sigma, 6),
                 n_assets=len(data))
        rows.append(r)

# separator
rows.append(blank_row())

# — BINS section header —
hdr2 = blank_row()
hdr2.update(section="BINS", metric="Metric", chain="Chain",
            bin_start="Bin_Start", bin_end="Bin_End", bin_label="Bin_Label",
            frequency="Frequency", density="Density", gaussian_pdf="Gaussian_PDF")
rows.append(hdr2)

for m in metrics:
    bins = m["bins"]
    mids = (bins[:-1] + bins[1:]) / 2

    for i, (lo, hi, mid) in enumerate(zip(bins[:-1], bins[1:], mids)):
        label = (f"{fmt_num(lo)}–{fmt_num(hi)}" if m["log_scale"]
                 else f"{lo:.1f}–{hi:.1f}%")

        for chain, counts, density in [
            ("ETH", m["eth_counts"], m["eth_density"]),
            ("BSC", m["bsc_counts"], m["bsc_density"]),
        ]:
            curve_x = m["curve_x"]
            curve_y = m["eth_curve"] if chain == "ETH" else m["bsc_curve"]
            g_pdf   = float(np.interp(mid, curve_x, curve_y))
            r = blank_row()
            r.update(
                section="BINS", metric=m["label"], chain=chain,
                transform="log10" if m["log_scale"] else "linear",
                bin_start=round(float(lo), 4),
                bin_end=round(float(hi), 4),
                bin_label=label,
                frequency=int(counts[i]),
                density=round(float(density[i]), 8),
                gaussian_pdf=round(g_pdf, 8),
            )
            rows.append(r)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

print(f"  → {OUT_CSV}")

# ═══════════════════════════════════════════════════════════════════════════════
# Plot
# ═══════════════════════════════════════════════════════════════════════════════
print("Rendering chart …")

fig, axes = plt.subplots(1, 3, figsize=(21, 7))
fig.patch.set_facecolor("#F8FAFC")

subplot_cfg = [
    (metrics[0], axes[0], "Number of Holders",      "holders"),
    (metrics[1], axes[1], "Onchain Market Cap",      "usd"),
    (metrics[2], axes[2], "Whale Concentration (%)", "pct"),
]

for m, ax, xlabel, fmt_type in subplot_cfg:
    ax.set_facecolor("#F8FAFC")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    bins      = m["bins"]
    bw        = np.diff(bins)
    log_scale = m["log_scale"]

    # ── Histogram bars ──────────────────────────────────────────────────────
    ax.bar(bins[:-1], m["eth_density"], width=bw, align="edge",
           color=C_ETH, alpha=ALPHA, label="ETH", zorder=2)
    ax.bar(bins[:-1], m["bsc_density"], width=bw, align="edge",
           color=C_BSC, alpha=ALPHA, label="BSC", zorder=2)

    # ── Gaussian curves ─────────────────────────────────────────────────────
    cx = m["curve_x"]
    eth_lbl = (f"ETH fit  μ={fmt_log_mu(m['eth_mu'], log_scale)}"
               f"  σ={m['eth_sigma']:.2f}")
    bsc_lbl = (f"BSC fit  μ={fmt_log_mu(m['bsc_mu'], log_scale)}"
               f"  σ={m['bsc_sigma']:.2f}")
    ax.plot(cx, m["eth_curve"], color=C_ETH, lw=CURVE_LW, zorder=3, label=eth_lbl)
    ax.plot(cx, m["bsc_curve"], color=C_BSC, lw=CURVE_LW, zorder=3,
            linestyle="--", label=bsc_lbl)

    # ── X-axis scale & formatting ───────────────────────────────────────────
    if log_scale:
        ax.set_xscale("log")
        if fmt_type == "usd":
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"${fmt_num(x)}"))
        else:
            ax.xaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: fmt_num(x)))
        ax.set_xlim(bins[0] * 0.8, bins[-1] * 1.25)
    else:
        ax.xaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
        ax.set_xlim(bins[0] - 1, bins[-1] + 1)

    ax.set_xlabel(xlabel, fontsize=11, labelpad=8)
    ax.set_ylabel("Density", fontsize=10)
    ax.set_title(m["label"], fontsize=13, fontweight="bold", pad=12)
    ax.legend(fontsize=8.5, framealpha=0.9, loc="upper right")
    ax.tick_params(axis="x", rotation=28, labelsize=9)
    ax.tick_params(axis="y", labelsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)

    # ── Asset count annotation ───────────────────────────────────────────────
    ax.annotate(
        f"n ETH={len(m['eth_data'])}  |  n BSC={len(m['bsc_data'])}",
        xy=(0.99, 0.97), xycoords="axes fraction",
        ha="right", va="top", fontsize=8.5, color="#6B7280",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", alpha=0.75),
    )

fig.suptitle(
    "Ondo Tokenized Assets – ETH vs BSC Chain Distribution Analysis",
    fontsize=15, fontweight="bold", y=1.02,
)
plt.tight_layout()
fig.savefig(OUT_PNG, dpi=160, bbox_inches="tight", facecolor=fig.get_facecolor())
print(f"  → {OUT_PNG}")
print("\nDone.")
