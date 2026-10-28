"""Daily CSV copy of Compute Screener's published price indices (https://computescreener.com).

Downloads the public JSON files the website reads and writes them to data/*.csv. The data is CC BY 4.0:
credit "Compute Screener (computescreener.com)".
"""
import csv
import json
import os
import urllib.request

SITE = "https://computescreener.com"
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def get(name):
    req = urllib.request.Request(SITE + "/data/" + name, headers={"User-Agent": "compute-screener-dataset"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def write(name, header, rows):
    with open(os.path.join(OUT, name), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    print("%s: %d rows" % (name, len(rows)))


def yn(x):
    return "true" if x else "false"


# Token Price Index 2.0 (from 2026-10-28): a model's price at the index's mix of 87% cache reads, 12% input and 1% output;
# a model with no cache price is priced at its input price (https://computescreener.com/methodology#tokens)
MIX = {"cache_read": 0.87, "input": 0.12, "output": 0.01}
SHOWN_GPUS = ("H100", "H200", "A100", "B200", "B300", "RTX PRO 6000")


def at_mix(inp, out, cache):
    if inp is None or out is None:
        return None
    return round(MIX["cache_read"] * (cache if cache is not None else inp) + MIX["input"] * inp + MIX["output"] * out, 6)


def blended(inp, out):
    """The 3 input : 1 output list price (version 1's blend), kept for comparison."""
    return None if inp is None or out is None else round((3 * inp + out) / 4, 6)


def page_url(models, mid):
    """The model's page on the website, e.g. https://computescreener.com/models/kimi-k3."""
    m = models.get(mid)
    return SITE + "/models/" + m["page"] if m and m.get("page") else ""


def main():
    index, series = get("index.json"), get("series.json")
    tokens, token_series = get("tokens.json"), get("token_series.json")
    mdoc = get("models.json")
    models = mdoc.get("models", {})   # models in today's token index, with their daily history
    # the cache read and mix columns are filled from Token Price Index 2.0's files only (version 1 had no cache prices)
    v2 = tokens.get("version") == "2.0" and mdoc.get("version") == "2.0"
    # the GPUs the website shows (owner, 2026-10-28: only these six), when published
    gpus = [g for g, e in index["gpus"].items() if e.get("value") is not None and g in SHOWN_GPUS]

    write("gpu_index_daily.csv", ["date", "gpu", "usd_per_gpu_hour", "final", "weekly_history", "restated"],
          [[p["d"], g, p["v"], yn(p.get("final")), yn(p.get("w")), yn(p.get("restated"))]
           for g in gpus for p in series.get(g, []) if p.get("v") is not None])
    write("gpu_providers_latest.csv", ["gpu", "provider", "average_usd_per_gpu_hour", "prices", "status", "read_at"],
          [[g, p["name"], p["avg"], p.get("records"), p.get("status"), p.get("read")]
           for g in gpus for p in index["gpus"][g].get("providers", [])])
    labs = [l for l, e in tokens["labs"].items() if e.get("value") is not None]
    write("token_index_daily.csv", ["date", "company", "usd_per_1m_tokens", "final", "rebuilt_history"],
          [[p["d"], l, p["v"], yn(p.get("final")), yn(p.get("h"))]
           for l in labs for p in token_series.get(l, []) if p.get("v") is not None])
    # usd_per_1m_blended stays the 3 input : 1 output list price; the cache read price and the price at the index's
    # mix are added at the end, so the existing columns keep their places and meanings
    write("token_models_latest.csv", ["date", "company", "model", "model_id", "usd_per_1m_input", "usd_per_1m_output",
                                      "usd_per_1m_blended", "share_of_company_tokens", "url", "usd_per_1m_cache_read",
                                      "usd_per_1m_at_mix"],
          [[tokens["labs"][l].get("date"), l, m["name"], m.get("id"), m["input"], m["output"],
            m.get("list_price", blended(m["input"], m["output"])), m["share"], page_url(models, m.get("id")),
            m.get("cache_read") if v2 else None, m.get("price") if v2 else None]
           for l in labs for m in tokens["labs"][l].get("models", [])])
    write("token_models_daily.csv", ["date", "company", "model", "model_id", "usd_per_1m_input", "usd_per_1m_output",
                                     "usd_per_1m_blended", "share_of_company_tokens", "usd_per_1m_cache_read",
                                     "usd_per_1m_at_mix"],
          [[r[0], m["company"], m["name"], mid, r[1], r[2], blended(r[1], r[2]), r[3],
            (r[4] if len(r) > 4 else None) if v2 else None,
            at_mix(r[1], r[2], r[4] if len(r) > 4 else None) if v2 else None]
           for mid, m in sorted(models.items(), key=lambda x: (x[1]["company"], x[1]["name"]))
           for r in m.get("s", []) if r[1] is not None and r[2] is not None])
    with open(os.path.join(OUT, "updated.txt"), "w") as f:
        f.write("GPU prices: %s\nToken prices: %s\n" % (index.get("updated"), tokens.get("updated")))


if __name__ == "__main__":
    main()
