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


def main():
    index, series = get("index.json"), get("series.json")
    tokens, token_series = get("tokens.json"), get("token_series.json")
    gpus = [g for g, e in index["gpus"].items() if e.get("value") is not None]   # published GPUs only

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
    write("token_models_latest.csv", ["date", "company", "model", "usd_per_1m_input", "usd_per_1m_output",
                                      "usd_per_1m_blended", "share_of_company_tokens"],
          [[tokens["labs"][l].get("date"), l, m["name"], m["input"], m["output"], m["price"], m["share"]]
           for l in labs for m in tokens["labs"][l].get("models", [])])
    with open(os.path.join(OUT, "updated.txt"), "w") as f:
        f.write("GPU prices: %s\nToken prices: %s\n" % (index.get("updated"), tokens.get("updated")))


if __name__ == "__main__":
    main()
