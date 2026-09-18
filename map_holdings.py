#!/usr/bin/env python3
"""Map Vanguard's holdings export to Yahoo Finance tickers."""
import os
import pandas as pd, re, sys

import sys as _sys
# Vanguard's export, given on the command line:  python map_holdings.py <file.xlsx>
if len(_sys.argv) < 2 or not _sys.argv[1].lower().endswith((".xlsx", ".xls")):
    _sys.exit("usage: python map_holdings.py <Vanguard holdings export.xlsx>")
SRC = _sys.argv[1]

# Vanguard region code -> Yahoo exchange suffix
SUFFIX = {
    "US": "", "GB": ".L", "JP": ".T", "HK": ".HK", "IN": ".NS", "KR": ".KS",
    "TW": ".TW", "AU": ".AX", "CA": ".TO", "DE": ".DE", "FR": ".PA", "SE": ".ST",
    "CH": ".SW", "IT": ".MI", "NL": ".AS", "ES": ".MC", "DK": ".CO", "NO": ".OL",
    "FI": ".HE", "BE": ".BR", "AT": ".VI", "PT": ".LS", "IE": ".IR", "GR": ".AT",
    "PL": ".WA", "HU": ".BD", "CZ": ".PR", "RO": ".RO", "IS": ".IC",
    "BR": ".SA", "MX": ".MX", "CL": ".SN", "CO": ".CL", "AR": ".BA",
    "ZA": ".JO", "IL": ".TA", "TR": ".IS", "SA": ".SR", "QA": ".QA",
    "SG": ".SI", "TH": ".BK", "ID": ".JK", "MY": ".KL", "PH": ".PS",
    "NZ": ".NZ", "EG": ".CA", "CN": ".SS",
    # No usable Yahoo feed
    "RU": None, "KW": None, "AE": None,
}


# Vanguard uses Bloomberg-style tickers; these differ from Yahoo's. Each one
# below was verified to return the right company before being added.
OVERRIDES = {
 "NOVOB.CO":"NOVO-B.CO","VOLVB.ST":"VOLV-B.ST","INVEB.ST":"INVE-B.ST",
 "INVEA.ST":"INVE-A.ST","ATCOB.ST":"ATCO-B.ST","ATCOA.ST":"ATCO-A.ST",
 "ASSAB.ST":"ASSA-B.ST","SWEDA.ST":"SWED-A.ST","SEBA.ST":"SEB-A.ST",
 "NDA.HE":"NDA-FI.HE","DBS.SI":"D05.SI","OCBC.SI":"O39.SI","UOB.SI":"U11.SI",
 "HDFCB.NS":"HDFCBANK.NS","ICICIBC.NS":"ICICIBANK.NS","BHARTI.NS":"BHARTIARTL.NS",
 "INFO.NS":"INFY.NS","BAF.NS":"BAJFINANCE.NS","MM.NS":"M&M.NS","AXSB.NS":"AXISBANK.NS",
 "RJHI.SR":"1120.SR","ARAMCO.SR":"2222.SR","SNB.SR":"1180.SR",
 "285.T":"285A.T","AIRB.PA":"AI.PA",
}


def yahoo_ticker(raw, region):
    t = str(raw).strip().upper()
    if not t or t == "NAN":
        return None
    # Vanguard writes UK lines as "BP/" and share classes as "TECK/B".
    t = t.rstrip("/")
    t = t.replace("/", "-")
    suf = SUFFIX.get(region, "MISSING")
    if suf == "MISSING" or suf is None:
        return None

    if region == "US":
        return t.replace(".", "-").replace("/", "-")   # BRK/B -> BRK-B
    if region == "HK":
        d = re.sub(r"\D", "", t)
        return d.zfill(4) + ".HK" if d else None
    if region == "JP":
        d = re.sub(r"\D", "", t)
        return d + ".T" if d else None
    if region in ("KR",):
        d = re.sub(r"\D", "", t)
        return d.zfill(6) + ".KS" if d else None
    if region == "CN":
        d = re.sub(r"\D", "", t)
        if not d:
            return None
        d = d.zfill(6)
        return d + (".SS" if d[0] == "6" else ".SZ")
    if region == "TW":
        return re.sub(r"\s", "", t) + ".TW"
    return t.replace(" ", "-") + suf


def main():
    df = pd.read_excel(SRC, header=6).dropna(subset=["Ticker"])
    df["wt"] = df["% of market value"].astype(str).str.rstrip("%").astype(float)
    df = df.sort_values("wt", ascending=False).reset_index(drop=True)

    rows, skipped = [], {}
    for _, r in df.iterrows():
        region = str(r["Region"]).strip()
        tk = yahoo_ticker(r["Ticker"], region)
        tk = OVERRIDES.get(tk, tk)
        if tk:
            rows.append({"ticker": tk, "region": region, "wt": r["wt"],
                         "name": str(r["Holding name"])})
        else:
            skipped[region] = skipped.get(region, 0) + 1

    out = pd.DataFrame(rows).drop_duplicates(subset="ticker", keep="first")
    print(f"holdings in file : {len(df)}")
    print(f"mapped to tickers: {len(out)}")
    print(f"unmapped         : {sum(skipped.values())}  {skipped}")
    print(f"weight mapped    : {out['wt'].sum():.1f}% of fund")
    # Trim to the holdings that could plausibly reach the top 150 within a year.
    # Below that a holding needs 5x-35x growth, so fetching it nightly buys
    # nothing but build time.
    CUTOFF_MULTIPLE = 4
    out = out.sort_values("wt", ascending=False).reset_index(drop=True)
    cut = float(out.iloc[149]["wt"]) if len(out) > 150 else 0.0
    thresh = cut / CUTOFF_MULTIPLE
    keep = out[out["wt"] >= thresh] if thresh > 0 else out

    head = pd.read_excel(SRC, header=None, nrows=6)
    as_of = next((str(v).replace("As at", "").strip() for v in head.values.ravel()
                  if str(v).lower().startswith("as at")), "unknown date")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdings.csv")
    with open(out_path, "w") as fh:
        fh.write(f"# VWRP holdings from Vanguard's export, data as at {as_of}.\n")
        fh.write(f"# Trimmed to the {len(keep)} holdings that could plausibly reach the "
                 f"top 150 within a year:\n")
        fh.write(f"# the 150th carries {cut:.4f}%, everything here is above {thresh:.4f}% "
                 f"(a {CUTOFF_MULTIPLE}x move). {keep['wt'].sum():.1f}% of the fund.\n")
        fh.write("#\n# vanguard_weight is the fund's REAL published weight, not an estimate.\n")
        fh.write("ticker,region,vanguard_weight,name\n")
        for _, r in keep.iterrows():
            nm = str(r["name"]).replace(",", " ").replace('"', "")[:48]
            fh.write(f"{r['ticker']},{r['region']},{r['wt']:.6f},{nm}\n")
    print(f"holdings.csv     : {len(keep)} kept ({keep['wt'].sum():.1f}% of fund), as at {as_of}")


if __name__ == "__main__":
    main()
