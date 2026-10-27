"""The steps between the published files and method.compute_day, shared by the index build (build_index.py) and the
public verifier (verify.py), so both compute a day the same way:

- day_records: a day's offers from its records file (data/records/<day>.json.gz), each with its price for the day;
- model_for: the standardization factors in force on a day (data/model.json);
- build_ctx: the look-back state compute_day needs, from the stored state of the previous days (data/stats.json
  "days", or one data/state/<day>.json.gz per day once a day is final).

Pure functions on the files' contents; standard library only.
"""
from datetime import date, timedelta

import method as M
from catalog import GPUS, VARIANTS


def day_records(store, day):
    """The day's offers from a records file's contents ({"records": {key: offer}}), with "unit_usd", the offer's
    price for the day: the average at the collections where it had capacity, or, for an offer with none, its average
    posted price (it counts only if its provider had capacity elsewhere: method.capacity_rule)."""
    if not store:
        return []
    out = []
    for r in store["records"].values():
        r = dict(r, day=day)
        if r.get("obs"):
            r["unit_usd"] = r["unit_sum"] / r["obs"]
        elif r.get("posted_n"):
            r["unit_usd"] = r["posted_sum"] / r["posted_n"]
        else:
            r["unit_usd"] = r.get("unit_last") if r.get("unavail_obs") else None
        out.append(r)
    return out


def model_for(models, d):
    """The calibration in force on day d: the latest calibrated on or before it (else the first)."""
    hist = models.get("history") or []
    eligible = [m for m in hist if m["calibrated_on"] <= d.isoformat()]
    m = (eligible or hist)[-1]
    # a family added after the last calibration: its benchmark variant is 1.0 by
    # definition; its other variants wait for the next calibration
    for g in GPUS:
        m["variant"].setdefault(g, {VARIANTS[g][0]: 1.0})
    return m


def build_ctx(stats, d):
    """compute_day's look-back state for day d from stats = {"days": {day: state}, "first_seen", "shadow_from"}."""
    days = stats.get("days", {})
    hc, pvh = {}, {}
    for ds, s in days.items():
        dd = date.fromisoformat(ds)
        if d - timedelta(days=M.OUTLIER_WINDOW_DAYS) <= dd < d:
            for k, v in (s.get("variant_median") or {}).items():
                if v:
                    hc.setdefault(k, []).append(v)
        if d - timedelta(days=M.VALIDATION_WINDOW_DAYS) <= dd < d:
            for k, v in (s.get("pv") or {}).items():
                pvh.setdefault(k, []).append((ds, v["mean"], v["n"], v["held"]))
    prior = [b.isoformat() for b in M.prev_days(d, M.PERSIST_DAYS - 1)]
    prior_held = {}
    if all(p in days for p in prior):
        keys = set.intersection(*[set((days[p].get("pv") or {}).keys()) for p in prior]) if prior else set()
        for k in keys:
            entries = [days[p]["pv"][k] for p in prior]
            # a move counts toward persistence on every day it was held, released or corroborated, so a release
            # sticks; a source-wide hold never does (that source's error is not released by persisting)
            if all((e["held"] or e.get("status") in ("released", "corroborated")) and not e.get("source_hold")
                   for e in entries):
                prior_held[k] = [e["mean"] for e in entries]
    # each provider's latest observed average in the imputation window, with the
    # other providers' averages that day (for the change since then)
    lookback = {}
    for b in M.prev_days(d, M.IMPUTE_DAYS):
        s = days.get(b.isoformat())
        for g, provs in ((s or {}).get("provider_avg") or {}).items():
            for p, avg in provs.items():
                if p not in lookback.setdefault(g, {}):
                    lookback[g][p] = (b.isoformat(), avg, {q: a for q, a in provs.items() if q != p})
    # the chained index: the last published day within CHAIN_GAP_DAYS, its level and every provider's average
    chain = {}
    for b in M.prev_days(d, M.CHAIN_GAP_DAYS):
        s = days.get(b.isoformat()) or {}
        for g, lvl in (s.get("level") or {}).items():
            if g not in chain and lvl:
                chain[g] = {"day": b.isoformat(), "level": lvl, "avgs": (s.get("chain_avgs") or {}).get(g) or {},
                            "offers": (s.get("offers") or {}).get(g) or {}}
    # the stored offers and observed averages of the IMPUTE_DAYS days before d, every day listed ({} where nothing is
    # stored), for method.restate (from RESTATE_FROM every earlier day is compared in d's own factors)
    offers_by_day, avgs_by_day = {}, {}
    for b in M.prev_days(d, M.IMPUTE_DAYS):
        s = days.get(b.isoformat()) or {}
        offers_by_day[b.isoformat()] = s.get("offers") or {}
        avgs_by_day[b.isoformat()] = s.get("provider_avg") or {}
    return {"history_centers": hc, "pv_history": pvh, "prior_held": prior_held, "lookback": lookback,
            "chain": chain, "first_seen": stats.get("first_seen") or {}, "day": d.isoformat(),
            "shadow_from": stats.get("shadow_from") or M.V4_START,
            "offers_by_day": offers_by_day, "avgs_by_day": avgs_by_day}


def look_back_days(d):
    """The days whose stored state build_ctx reads for day d (the longest window: the outlier screen's)."""
    return [d - timedelta(days=k) for k in range(1, M.OUTLIER_WINDOW_DAYS + 1)]
