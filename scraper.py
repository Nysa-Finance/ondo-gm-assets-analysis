#!/usr/bin/env python3
"""
Ondo Assets Scraper
Reads ondo-assets-list.csv, scrapes Etherscan and BscScan for each token,
and outputs a CSV with: Holders, Onchain Market Cap, Total Transfers, Whale Concentration (Top 10).
"""

import csv
import re
import time
import random
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

CSV_INPUT = Path(__file__).parent / "assets" / "ondo-assets-list.csv"
CSV_OUTPUT = Path(__file__).parent / "output" / "ondo-assets-scraped.csv"

OUTPUT_HEADERS = [
    "Name", "Symbol",
    "ETH_URL",
    "ETH_Holders", "ETH_Market_Cap", "ETH_Total_Transfers", "ETH_Whale_Top10_Pct",
    "BSC_URL",
    "BSC_Holders", "BSC_Market_Cap", "BSC_Total_Transfers", "BSC_Whale_Top10_Pct",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def scrape_token(url: str, max_retries: int = 3) -> dict:
    """
    Scrape a single Etherscan or BscScan token page.
    Returns dict with holders, market_cap, transfers, whale_top10.
    """
    base = "https://etherscan.io" if "etherscan.io" in url else "https://bscscan.com"

    result = {
        "holders": "",
        "market_cap": "",
        "transfers": "",
        "whale_top10": "",
    }

    for attempt in range(max_retries):
        try:
            session = requests.Session()
            session.headers.update(HEADERS)

            r = session.get(url, timeout=30)
            r.raise_for_status()

            # Holders and Market Cap from meta description
            meta = BeautifulSoup(r.text, "html.parser").find("meta", {"name": "Description"})
            desc = meta.get("content", "") if meta else ""

            h_match = re.search(r"Holders:\s*([\d,]+)", desc)
            m_match = re.search(r"Onchain Market Cap:\s*([\$\d,\.]+)", desc)
            result["holders"] = h_match.group(1) if h_match else ""
            result["market_cap"] = m_match.group(1) if m_match else ""

            # Session ID used by sub-pages
            sid_match = re.search(r"var sid = '([a-f0-9]+)'", r.text)
            sid = sid_match.group(1) if sid_match else ""

            # Holder iframe params (address + total supply)
            hp_match = re.search(r"litTokenholdersContractUrlPara = '([^']+)'", r.text)
            holder_param = hp_match.group(1) if hp_match else ""

            contract_addr = url.split("/token/")[-1]

            time.sleep(random.uniform(0.8, 1.5))

            # Whale concentration from tokenholders iframe
            if holder_param and sid:
                holders_url = (
                    f"{base}/token/generic-tokenholders2"
                    f"?m=light&a={holder_param}&sid={sid}&p=1"
                )
                rh = session.get(holders_url, headers={"Referer": url}, timeout=30)
                sh = BeautifulSoup(rh.text, "html.parser")

                table = sh.find("table")
                if table:
                    top5, top10 = None, None
                    for row in table.find_all("tr"):
                        cells = [td.get_text(strip=True) for td in row.find_all("td")]
                        if len(cells) < 2:
                            continue
                        cohort = cells[0]
                        pct_raw = cells[-1].replace("%", "").replace("<", "").strip()
                        try:
                            pct_val = float(pct_raw)
                        except ValueError:
                            continue
                        if "Top 1-5" in cohort:
                            top5 = pct_val
                        elif "Top 6-10" in cohort:
                            top10 = pct_val
                    if top5 is not None and top10 is not None:
                        result["whale_top10"] = f"{round(top5 + top10, 2)}%"
                    elif top5 is not None:
                        result["whale_top10"] = f"{round(top5, 2)}%"

            time.sleep(random.uniform(0.8, 1.5))

            # Total transfers from tokentxns2 iframe (uses same session+cookies)
            if sid:
                txns_url = (
                    f"{base}/token/generic-tokentxns2"
                    f"?m=light&contractAddress={contract_addr}&a=&sid={sid}&p=1"
                )
                rt = session.get(txns_url, headers={"Referer": url}, timeout=30)
                t_match = re.search(
                    r"(More than\s*)?([\d,]+)\s*transactions?\s*found",
                    rt.text,
                    re.IGNORECASE,
                )
                if t_match:
                    prefix = (t_match.group(1) or "").strip()
                    count = t_match.group(2)
                    result["transfers"] = f"{prefix} {count}".strip() if prefix else count

            return result

        except Exception as exc:
            wait = 2 ** attempt
            print(f"    [attempt {attempt+1}/{max_retries}] Error: {exc} – retrying in {wait}s")
            time.sleep(wait)

    return result


def load_already_done() -> set:
    """Return set of asset names already written to output CSV."""
    done = set()
    if CSV_OUTPUT.exists():
        with open(CSV_OUTPUT, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add(row["Name"])
    return done


def read_assets() -> list[dict]:
    """Parse the semicolon-delimited input CSV."""
    assets = []
    with open(CSV_INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            name = row.get("Name", "").strip()
            symbol = row.get("Symbol", "").strip()
            eth_url = row.get("Etherscan Token", "").strip()
            bsc_url = row.get("BscScan Token", "").strip()
            if name:
                assets.append({
                    "name": name,
                    "symbol": symbol,
                    "eth_url": eth_url,
                    "bsc_url": bsc_url,
                })
    return assets


def main():
    CSV_OUTPUT.parent.mkdir(exist_ok=True)

    assets = read_assets()
    total = len(assets)
    print(f"Loaded {total} assets from CSV.")

    already_done = load_already_done()
    if already_done:
        print(f"Resuming – {len(already_done)} assets already scraped.")

    # Open output in append mode (write header only if file is new)
    file_exists = CSV_OUTPUT.exists() and CSV_OUTPUT.stat().st_size > 0
    out_file = open(CSV_OUTPUT, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(out_file, fieldnames=OUTPUT_HEADERS)
    if not file_exists:
        writer.writeheader()

    scraped = 0
    skipped = 0
    for i, asset in enumerate(assets, 1):
        name = asset["name"]

        if name in already_done:
            skipped += 1
            continue

        print(f"[{i}/{total}] {name} ({asset['symbol']})")

        eth_data = {}
        if asset["eth_url"]:
            print(f"  ETH: {asset['eth_url']}")
            eth_data = scrape_token(asset["eth_url"])
        else:
            print("  ETH: no URL")

        bsc_data = {}
        if asset["bsc_url"]:
            print(f"  BSC: {asset['bsc_url']}")
            bsc_data = scrape_token(asset["bsc_url"])
        else:
            print("  BSC: no URL")

        row = {
            "Name": name,
            "Symbol": asset["symbol"],
            "ETH_URL": asset["eth_url"],
            "ETH_Holders": eth_data.get("holders", ""),
            "ETH_Market_Cap": eth_data.get("market_cap", ""),
            "ETH_Total_Transfers": eth_data.get("transfers", ""),
            "ETH_Whale_Top10_Pct": eth_data.get("whale_top10", ""),
            "BSC_URL": asset["bsc_url"],
            "BSC_Holders": bsc_data.get("holders", ""),
            "BSC_Market_Cap": bsc_data.get("market_cap", ""),
            "BSC_Total_Transfers": bsc_data.get("transfers", ""),
            "BSC_Whale_Top10_Pct": bsc_data.get("whale_top10", ""),
        }

        writer.writerow(row)
        out_file.flush()
        scraped += 1

        eth_summary = f"H={eth_data.get('holders','-')} MC={eth_data.get('market_cap','-')} T={eth_data.get('transfers','-')} W={eth_data.get('whale_top10','-')}"
        bsc_summary = f"H={bsc_data.get('holders','-')} MC={bsc_data.get('market_cap','-')} T={bsc_data.get('transfers','-')} W={bsc_data.get('whale_top10','-')}"
        print(f"  ETH → {eth_summary}")
        print(f"  BSC → {bsc_summary}")

        # Polite delay between assets
        time.sleep(random.uniform(1.0, 2.5))

    out_file.close()
    print(f"\nDone. Scraped {scraped} new assets, skipped {skipped} already done.")
    print(f"Output: {CSV_OUTPUT}")


if __name__ == "__main__":
    main()
