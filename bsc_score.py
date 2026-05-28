#!/usr/bin/env python3
"""
BSC Asset Quality Scorer

Min-max normalises each BSC metric, then computes:
  quality_score = norm(mcap) + norm(transfers) + norm(holders) - norm(whale_top10)

Score range: -1  (worst – tiny/inactive + fully whale-dominated)
         to  +3  (best  – large cap, liquid, distributed)

Output: output/bsc_quality_score.csv
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path

IN_CSV  = Path(__file__).parent / "output" / "ondo-assets-scraped.csv"
OUT_CSV = Path(__file__).parent / "output" / "bsc_quality_score.csv"


# ── Parsers ────────────────────────────────────────────────────────────────────
def parse_money(s):
    s = str(s).replace("More than", "").replace(",", "").replace("$", "").strip()
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else np.nan

def parse_num(s):
    s = str(s).replace("More than", "").replace(",", "").strip()
    m = re.search(r"[\d.]+", s)
    return float(m.group()) if m else np.nan

def parse_pct(s):
    s = str(s).replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return np.nan

def minmax(series):
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series(0.0, index=series.index)
    return (series - lo) / (hi - lo)


# ── Load & parse ───────────────────────────────────────────────────────────────
df = pd.read_csv(IN_CSV)

df["mcap"]      = df["BSC_Market_Cap"].apply(parse_money).fillna(0)
df["holders"]   = df["BSC_Holders"].apply(parse_num).fillna(0)
df["transfers"] = df["BSC_Total_Transfers"].apply(parse_num).fillna(0)
df["whale"]     = df["BSC_Whale_Top10_Pct"].apply(parse_pct).fillna(df["BSC_Whale_Top10_Pct"].apply(parse_pct).mean())

# ── Normalise (0–1) ────────────────────────────────────────────────────────────
df["norm_mcap"]      = minmax(df["mcap"])
df["norm_holders"]   = minmax(df["holders"])
df["norm_transfers"] = minmax(df["transfers"])
df["norm_whale"]     = minmax(df["whale"])

# ── Score ──────────────────────────────────────────────────────────────────────
df["quality_score"] = (
    df["norm_mcap"]
    + df["norm_transfers"]
    + df["norm_holders"]
    - df["norm_whale"]
)

# ── Rank & export ──────────────────────────────────────────────────────────────
out = (
    df[[
        "Name", "Symbol",
        "quality_score",
        "norm_mcap", "norm_holders", "norm_transfers", "norm_whale",
        "mcap", "holders", "transfers", "whale",
    ]]
    .sort_values("quality_score", ascending=False)
    .reset_index(drop=True)
)
out.index += 1
out.index.name = "Rank"

out = out.rename(columns={
    "quality_score":   "Quality_Score",
    "norm_mcap":       "Norm_MarketCap",
    "norm_holders":    "Norm_Holders",
    "norm_transfers":  "Norm_Transfers",
    "norm_whale":      "Norm_Whale_Top10",
    "mcap":            "BSC_MarketCap_USD",
    "holders":         "BSC_Holders",
    "transfers":       "BSC_Transfers",
    "whale":           "BSC_Whale_Top10_Pct",
})

# Round for readability
for col in ["Quality_Score", "Norm_MarketCap", "Norm_Holders", "Norm_Transfers", "Norm_Whale_Top10"]:
    out[col] = out[col].round(6)

out.to_csv(OUT_CSV)
print(f"Saved → {OUT_CSV}\n")

# ── Print top 10 & bottom 5 ────────────────────────────────────────────────────
pd.set_option("display.max_colwidth", 45)
pd.set_option("display.float_format", "{:.4f}".format)
print("── TOP 10 ──────────────────────────────────────────────────────")
print(out[["Name", "Quality_Score", "Norm_MarketCap", "Norm_Holders",
           "Norm_Transfers", "Norm_Whale_Top10"]].head(10).to_string())
print()
print("── BOTTOM 5 ────────────────────────────────────────────────────")
print(out[["Name", "Quality_Score", "Norm_MarketCap", "Norm_Holders",
           "Norm_Transfers", "Norm_Whale_Top10"]].tail(5).to_string())
