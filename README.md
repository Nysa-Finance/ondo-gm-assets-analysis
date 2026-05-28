# Ondo RWA Collateral Selection — BSC Analysis

This repository contains the data pipeline and analysis used to evaluate Ondo tokenized assets across Ethereum (ETH) and BNB Chain (BSC), with the goal of selecting a collateral basket for a permissionless RWA lending protocol.

---

## Analysis Overview

The work is structured in three phases: data extraction, data processing, and data evaluation.

### Phase 1 — Data Extraction

The starting point is `assets/ondo-assets-list.csv`, a semicolon-delimited file containing 263 Ondo tokenized assets (equities and ETFs). Each row includes two key columns: the Etherscan token URL and the BscScan token URL, used as entry points for scraping.

The scraper (`scraper.py`) hits three HTTP endpoints per asset per chain using a `requests.Session`, with no browser automation required:

| Endpoint | Data Extracted |
|---|---|
| `/token/<address>` (main page) | Holders count, Market Cap (from `<meta name="Description">` tag), session `sid` from inline JS |
| `/token/generic-tokenholders2?a=<addr>&sid=<sid>` | Whale concentration — Top 1–5% and Top 6–10% holder cohorts |
| `/token/generic-tokentxns2?contractAddress=<addr>&sid=<sid>` | Total transfers count (requires the `sid` from the main page — the key trick avoiding browser automation) |

Output is written to `output/ondo-assets-scraped.csv`, one row per asset, with separate columns for ETH and BSC: `Name`, `Symbol`, `ETH_Holders`, `ETH_Market_Cap`, `ETH_Total_Transfers`, `ETH_Whale_Top10_Pct`, and their BSC equivalents.

### Phase 2 — Data Processing

The analysis script (`analysis.py`) reads the scraped CSV and runs a chain-comparative distribution analysis across three metrics: number of holders, market cap, and whale concentration.

Data cleaning steps include stripping `$`, `,`, `More than`, and `%` from raw strings, clamping whale concentration values slightly above 100% (a rounding artefact in the source data), and excluding assets with a $0 market cap as these carry no on-chain liquidity signal.

For each metric and chain, the following approach is applied:

- **Holders and Market Cap** — log₁₀-transformed, then a Normal distribution is fitted to the transformed data (i.e., a log-normal fit in original space). Density histograms use log-spaced bins.
- **Whale Concentration** — kept on a linear scale, with a Normal distribution fitted directly and linear bins.

Outputs are written to `output/gaussian_distributions.csv` (fitted μ and σ parameters per metric per chain, plus histogram bin data) and `output/chain_distributions.png` (a 3-panel figure with overlapping ETH/BSC histograms and fitted curves).

![ETH vs BSC Distribution Analysis](https://raw.githubusercontent.com/Nysa-Finance/ONDOGM-assets-analysis/main/output/chain_distributions.png)

### Phase 3 — Data Evaluation

#### Chain Evaluation

Using the fitted distribution parameters, a cross-chain comparison was conducted across all three metrics. The key statistics are reported below.

**Fitted Distribution Parameters**

| Metric | Chain | μ | σ | Interpretation |
|---|---|---|---|---|
| Holders | ETH | 1.565 (≈ 37 holders) | 0.612 (×/÷ 4.1 per σ) | One sigma spans a 4x range |
| Holders | BSC | 1.885 (≈ 77 holders) | 0.574 (×/÷ 3.7 per σ) | Wider base, tighter spread |
| Market Cap | ETH | 5.524 (≈ $334K) | 1.402 (×/÷ 25 per σ) | Highly heterogeneous |
| Market Cap | BSC | 5.273 (≈ $187K) | 1.234 (×/÷ 17 per σ) | More homogeneous |
| Whale Top 10% | ETH | 98.18% | ±5.06 pp | Near-total concentration, stable |
| Whale Top 10% | BSC | 92.23% | ±8.63 pp | Lower and more variable |

**Chain Comparison Summary**

| Dimension | ETH | BSC | Advantage |
|---|---|---|---|
| Median holder base | 37 | 77 | BSC |
| Holder dispersion (σ) | ×4.1/σ | ×3.7/σ | BSC |
| Median market cap | $334K | $187K | ETH |
| Market cap predictability | ×25/σ | ×17/σ | BSC |
| Whale concentration | 98.2% | 92.2% | BSC |
| Whale variability | ±5.1 pp | ±8.6 pp | BSC* |

*Higher variability on BSC is a structural advantage for collateral selection: it means there exist assets with meaningfully lower whale concentration, whereas on ETH virtually all assets are hypercentralized regardless of other characteristics.

**Conclusion:** BSC dominates on every dimension relevant to a permissionless lending protocol — broader holder distribution, more predictable collateral sizing, and a whale concentration landscape that allows selective inclusion of genuinely distributed assets.

#### Asset Evaluation

Asset selection was approached by category rather than purely quantitatively, reflecting the different risk profiles of equities versus fixed income instruments.

A composite **Quality Score** was computed per asset by normalizing all available metrics and combining them as follows:

```
Quality Score = norm(Market Cap) + norm(Holders) + norm(Transfers) − norm(Whale Top 10%)
```

Whale concentration is subtracted because it is an inverse quality signal: higher concentration means fewer independent holders controlling the collateral, which increases liquidation risk.

Out of 265 assets in the dataset, only 10 returned a positive Quality Score on BSC. This is not a limitation — it is a strict natural filter that directly identifies the assets with the best combination of on-chain liquidity, holder distribution, and low concentration risk.

**Final Collateral Basket**

The selected assets span two categories — equities and a fixed income ETF — with differentiated LTV profiles reflecting their underlying risk:

| Asset | Category | BSC Market Cap | Quality Score |
|---|---|---|---|
| Circle Internet Group (Ondo Tokenized) | Equity | $137,833,700 | 0.906 |
| NVIDIA (Ondo Tokenized) | Equity | $36,692,970 | 0.778 |
| iShares Silver Trust (Ondo Tokenized) | Commodity ETF | $6,434,988 | 0.525 |
| Tesla (Ondo Tokenized) | Equity | $20,509,720 | 0.276 |
| Invesco QQQ (Ondo Tokenized) | Equity ETF | $24,373,217 | 0.025 |
| Alphabet Class A (Ondo Tokenized) | Equity | $31,225,490 | 0.002 |
| iShares 20+ Year Treasury Bond ETF (Ondo Tokenized) | Bond ETF | $289,536 | — |

The iShares 20+ Year Treasury Bond ETF is included as a fixed income anchor despite its low on-chain metrics. Its inclusion is justified by the nature of the underlying instrument — long-duration US Treasuries — rather than its current BSC liquidity profile. It is treated as a special collateral type with a conservative LTV cap and a separate TVL ceiling.

---

## Repository Structure

```
.
├── assets/
│   └── ondo-assets-list.csv          # Source asset list (263 Ondo tokenized assets)
├── output/
│   ├── ondo-assets-scraped.csv       # Raw scraped data (ETH + BSC per asset)
│   ├── gaussian_distributions.csv    # Fitted distribution parameters and bin data
│   ├── chain_distributions.png       # ETH vs BSC distribution comparison chart
│   └── bsc_quality_score.csv         # Per-asset Quality Score and normalized metrics
├── scraper.py                        # HTTP scraper (no browser automation)
└── analysis.py                       # Distribution fitting and comparative analysis
```

---

## Dependencies

```bash
pip install requests pandas numpy scipy matplotlib
```
