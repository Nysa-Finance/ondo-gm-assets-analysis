#!/usr/bin/env python3
"""
BSC Rankings by Metric
Produces one CSV per metric, all assets ranked descending by that metric.
Output files:
  output/bsc_marketcap_rank.csv
  output/bsc_holders_rank.csv
  output/bsc_transfers_rank.csv
  output/bsc_whale_rank.csv
"""

import re
import numpy as np
import pandas as pd
from pathlib import Path

IN_CSV  = Path(__file__).parent / "output" / "ondo-assets-scraped.csv"
OUT_DIR = Path(__file__).parent / "output"

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

def write_rank(df, value_col, display_col, out_path):
    ranked = (
        df[["Name", value_col]]
        .sort_values(value_col, ascending=False)
        .reset_index(drop=True)
    )
    ranked.index += 1
    ranked.index.name = "Rank"
    ranked = ranked.rename(columns={value_col: display_col})
    ranked.to_csv(out_path)
    print(f"  {out_path.name}  ({len(ranked)} assets)")
    print(f"    #1  {ranked.iloc[0]['Name']}  →  {ranked.iloc[0][display_col]}")
    print(f"    #{len(ranked)}  {ranked.iloc[-1]['Name']}  →  {ranked.iloc[-1][display_col]}")


df = pd.read_csv(IN_CSV)

df["_mcap"]      = df["BSC_Market_Cap"].apply(parse_money)
df["_holders"]   = df["BSC_Holders"].apply(parse_num)
df["_transfers"] = df["BSC_Total_Transfers"].apply(parse_num)
df["_whale"]     = df["BSC_Whale_Top10_Pct"].apply(parse_pct)

metrics = [
    ("_mcap",      "BSC_Market_Cap",      OUT_DIR / "bsc_marketcap_rank.csv"),
    ("_holders",   "BSC_Holders",         OUT_DIR / "bsc_holders_rank.csv"),
    ("_transfers", "BSC_Total_Transfers",  OUT_DIR / "bsc_transfers_rank.csv"),
    ("_whale",     "BSC_Whale_Top10_Pct",  OUT_DIR / "bsc_whale_rank.csv"),
]

print("Writing BSC ranking CSVs …\n")
for value_col, display_col, out_path in metrics:
    write_rank(df, value_col, display_col, out_path)
    print()

print("Done.")
