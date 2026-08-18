#!/usr/bin/env python3
"""Map Vanguard's holdings export to Yahoo Finance tickers."""
import pandas as pd, re, sys

SRC = "/Users/freddiehewer/Desktop/Holdings details - Vanguard FTSE All-World UCITS ETF (USD) Accumulating - 18_08_2026.xlsx"

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
 "INFO.NS":"INFY.NS","BAF.NS":"BAJFINANCE.NS","MM.NS":"M&M.NS",
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
    out.to_csv("/tmp/mapped.csv", index=False)
    print("\ntop 12 mapped:")
    print(out.head(12)[["ticker", "region", "wt", "name"]].to_string(index=False))


if __name__ == "__main__":
    main()
