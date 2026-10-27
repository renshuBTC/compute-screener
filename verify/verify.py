#!/usr/bin/env python3
"""Recompute Compute Screener's published index values from its public files and check them.

    python verify.py --date 2026-10-25 --gpu H100     one GPU's final value on one day
    python verify.py --date 2026-10-25                every GPU and company that day
    python verify.py --all                            every day with a manifest
    python verify.py --all --data ./data              from a local copy instead of https://computescreener.com/data

For a GPU index day the verifier reads the day's manifest (data/manifests/gpu/<day>.json), downloads every file it
names and checks each SHA-256, then runs the published calculation (method.py) on the day's records with the factors
in force and the stored state of the previous days, and compares:
  - each GPU's value with the published final value (to the published 4 decimals);
  - the day's own state (what the next days build on) with the stored one, so verifying every day in turn checks the
    whole chain from the records.
For a token index day it recomputes each company's value from the day's trace: the token-weighted mean of its models'
posted prices, blended 3 input : 1 output.

Exit status: 0 every value checked matches; 1 a value or file does not match; 2 a file could not be read.
Needs Python 3.9+ and nothing else (standard library). The calculation code (method.py, recompute.py, catalog.py) is
the code the index runs; see https://computescreener.com/methodology.
"""
import argparse
import gzip
import hashlib
import json
import os
import sys
import urllib.request
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import method as M  # noqa: E402
import recompute as R  # noqa: E402

SITE_DATA = "https://computescreener.com/data"
UA = "computescreener-verify/1.0 (+https://computescreener.com/methodology)"


NOTES = []   # information printed after the checks (not counted as checks)


class Missing(Exception):
    pass


def same_code(m):
    """Note when this copy's calculation code differs from the code that wrote manifest m (the recomputation is the
    test; a difference only explains a mismatch)."""
    for f, h in ((m.get("code") or {}).get("files") or {}).items():
        try:
            with open(os.path.join(HERE, f), "rb") as fh:
                mine = sha256(fh.read())
        except OSError:
            mine = None
        if mine != h:
            note = "this copy of %s differs from the one that wrote the %s manifests from %s" % (f, m.get("kind"), m.get("day"))
            if not any(n.startswith(note.split(" from ")[0]) for n in NOTES):
                NOTES.append(note)


class Source:
    """The published files, from the site or a local copy (a folder laid out like /data)."""

    def __init__(self, base):
        self.base = base.rstrip("/")
        self.cache = {}

    def raw(self, rel):
        """The bytes of a published file, by its path from the repository root ("data/records/<day>.json.gz")."""
        if rel in self.cache:
            return self.cache[rel]
        if not rel.startswith("data/"):
            raise Missing(rel)
        sub = rel[len("data/"):]
        try:
            if self.base.startswith(("http://", "https://")):
                req = urllib.request.Request("%s/%s?source=static" % (self.base, sub), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r:
                    b = r.read()
            else:
                with open(os.path.join(self.base, sub), "rb") as f:
                    b = f.read()
        except Exception as e:
            raise Missing("%s (%s)" % (rel, e))
        self.cache[rel] = b
        return b

    def json(self, rel):
        b = self.raw(rel)
        return json.loads(gzip.decompress(b) if rel.endswith(".gz") else b)


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(b):
    return hashlib.sha256(b).hexdigest()


def roundtrip(obj):
    """As stored: through JSON, so tuples become lists and only JSON values remain."""
    return json.loads(json.dumps(obj))


def check_manifest(src, m, problems):
    want = sha256(canon({k: v for k, v in m.items() if k not in ("id", "created")}))
    if m.get("id") != want:
        problems.append("manifest id %s does not match its contents (%s)" % (m.get("id"), want))
    for group in ("inputs", "state", "trace"):
        for rel, h in (m.get(group) or {}).items():
            got = sha256(src.raw(rel))
            if got != h:
                problems.append("%s: SHA-256 %s, manifest %s" % (rel, got, h))


def verify_gpu_day(src, ds, only=None):
    """[(line, ok)] for one GPU index day."""
    m = src.json("data/manifests/gpu/%s.json" % ds)
    problems = []
    check_manifest(src, m, problems)
    same_code(m)
    d = date.fromisoformat(ds)
    model = R.model_for(src.json("data/model.json"), d)
    if sha256(canon(model)) != m["model"]["sha256"]:
        problems.append("factors calibrated on %s differ from the manifest's" % model["calibrated_on"])
    own = src.json(next(iter(m["state"])))
    stats = {"days": {}, "first_seen": own.get("first_seen") or {}, "shadow_from": own.get("shadow_from") or M.V4_START}
    for rel in m["inputs"]:
        if rel.startswith("data/state/"):
            s = src.json(rel)
            stats["days"][s["day"]] = s["state"]
    store = src.json("data/records/%s.json.gz" % ds)
    res = M.compute_day(R.day_records(store, ds), model, R.build_ctx(stats, d))
    lines = []
    for g, a in res["agg"].items():
        if only and g.lower() != only.lower():
            continue
        mine = round(a["value"], 4) if a["value"] is not None else None
        pub = m["values"].get(g)
        if mine is None and pub is None:
            continue
        ok = mine == pub
        ch = a.get("chain") or {}
        how = "%d providers, %d priced that day" % (len(a["providers"]), sum(1 for v in a["providers"].values() if not v["carried"]))
        if ch.get("from"):
            how += "; %s x %.6f from %s" % (ch["level"] and round(ch["level"], 4), ch["ratio"], ch["from"])
        lines.append(("%s %s  published %s, recomputed %s  (%s)" % (ds, g, pub, mine, how), ok))
    mine, stored, note = roundtrip(res["stats"]), dict(own["state"]), ""
    if ds < M.V41_START and not stored.get("offers"):
        # each day's offers are stored from methodology 4.1 (2026-10-24); an earlier day's state has none, and the
        # next day chained on its averages as stored
        mine.pop("offers", None)
        stored.pop("offers", None)
        note = " (offers are stored from methodology 4.1)"
    if canon(mine) != canon(stored):
        problems.append("the day's state recomputed differs from the stored state")
    lines += [("%s  %s" % (ds, p), False) for p in problems]
    if not only and not problems:
        lines.append(("%s  every input file matches its SHA-256; the day's state reproduces%s" % (ds, note), True))
    return lines


def verify_token_day(src, ds, only=None):
    m = src.json("data/manifests/tokens/%s.json" % ds)
    problems = []
    check_manifest(src, m, problems)
    same_code(m)
    trace = src.json(next(iter(m["inputs"])))
    minc = trace.get("min_coverage", 0.8)
    lines = []
    for lab, r in sorted((trace.get("labs") or {}).items()):
        if only and lab.lower() != only.lower():
            continue
        ms = r.get("models") or []
        bad = [x["slug"] for x in ms if abs(x["price"] - (3 * x["input"] + x["output"]) / 4) > 1e-9]
        w = sum(x["tokens"] for x in ms)
        v = sum(x["tokens"] * x["price"] for x in ms) / w if w else None
        if v is not None and r.get("coverage", 0) < minc:
            v = None
        mine = round(v, 4) if v is not None else None
        pub = m["values"].get(lab)
        if mine is None and pub is None:
            continue
        ok = mine == pub and not bad
        lines.append(("%s %s  published %s, recomputed %s  (%d models)%s" % (
            ds, lab, pub, mine, len(ms), "; blend wrong for " + ", ".join(bad) if bad else ""), ok))
    lines += [("%s  %s" % (ds, p), False) for p in problems]
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--data", default=SITE_DATA, help="the published data: a URL or a local folder (default %(default)s)")
    ap.add_argument("--date", help="an index day (YYYY-MM-DD)")
    ap.add_argument("--all", action="store_true", help="every day with a manifest")
    ap.add_argument("--gpu", help="one GPU (e.g. H100)")
    ap.add_argument("--company", help="one company (e.g. Anthropic)")
    a = ap.parse_args(argv)
    if not a.date and not a.all:
        ap.error("give --date or --all")
    src = Source(a.data)
    try:
        index = src.json("data/manifests/index.json")
        gdays = sorted(index.get("gpu") or {})
        tdays = sorted(index.get("tokens") or {})
        if a.date:
            gdays, tdays = [x for x in gdays if x == a.date], [x for x in tdays if x == a.date]
            if not gdays and not tdays:
                print("%s has no manifest yet: a GPU day gets one once it is final (after midnight US Central), "
                      "a token day once the next day is published" % a.date)
                return 2
        lines = []
        if not a.company:
            for ds in gdays:
                lines += verify_gpu_day(src, ds, a.gpu)
        if not a.gpu:
            for ds in tdays:
                lines += verify_token_day(src, ds, a.company)
    except Missing as e:
        print("could not read %s" % e)
        return 2
    for text, ok in lines:
        print(("ok    " if ok else "FAIL  ") + text)
    bad = sum(1 for _, ok in lines if not ok)
    for n in NOTES:
        print("note  " + n)
    print("\n%d checked, %d %s" % (len(lines), bad, "do not match" if bad else "mismatches: every value reproduces"))
    return 1 if bad or not lines else 0


if __name__ == "__main__":
    sys.exit(main())
