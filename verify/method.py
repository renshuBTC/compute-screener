"""Compute Screener GPU Rental Index — methodology (v4.2).

Four steps per index day (every calendar day, US Central), one index per GPU family:

1. Preprocessing   unit_price = total_rental_price / (num_gpus x duration_hours),
                   converted to USD at the ECB reference rate.
2. Filtering       completeness checks; where a source shows capacity, a provider
                   counts for a GPU only if one of its offers had capacity at some
                   collection that day; outlier screening against dynamic historical
                   price bands; provider-variant validation: a move of more than 35%
                   is held unless the median move of at least three other sources
                   matches it, and released when it persists (structural), except a
                   move across most of one relay source's clouds, which is held;
                   marketplace books with too few usable asks or hosts.
3. Standardization basis adjustment of every record to the benchmark contract
                   (on-demand, benchmark form factor, 8-GPU node, US, neutral CPU)
                   with factors recalibrated weekly from matched comparisons.
4. Aggregation     provider-level averages; a provider missing on the day is
                   imputed from its last average and the other providers'
                   change since then. The index moves by the equal-weighted
                   geometric mean of the price changes, since the last published
                   day, of the providers priced on both days (at least 5), each
                   change measured with both days standardized on today's factors,
                   so a provider joining or leaving, or a recalibration, does not
                   move it (a chained index). The cross-section average of all
                   providers (winsorized mean) is published beside it.

A family added after the start (catalog.FAMILY_START) is indexed from its first day: its offers before then are
recorded but not used (an added family with no start yet is collected only), the providers first priced in its first
14 days count at once (later ones after the shadow period), its index starts on the first day at least five providers
are priced (the cross-section), and the node-size, region and CPU factors stay those calibrated on the first seven
families (CALIBRATION_GPUS), so adding a family changes nothing for the families already indexed.

Pure functions only; I/O lives in build_index.py. Standard library only.
"""
import math
import statistics
from datetime import date, timedelta

from catalog import CORE_GPUS, FAMILY_START, GPUS, MARKETPLACES, VARIANTS, gpus_on, not_indexed

VERSION = "4.2"
BENCH_NODE = "8"
MIN_PROVIDERS = 5          # providers needed to publish a value (observed or imputed); each weighs <= 20%
MIN_OBSERVED = 3           # of which observed on the day
IMPUTE_DAYS = 7            # days a missing provider's average may be imputed
WINSOR_SHARE = 0.10        # share of providers clipped at each end (at least one)
OUTLIER_BAND = 2.0         # within-provider: ask kept if within [median/2, median*2]
MIN_BAND_RECORDS = 3       # asks needed before a provider median is used as a band
BAND_X = 2.5               # cross-provider: record kept if within [center/2.5, center*2.5]
MIN_BAND_PROVIDERS = 3     # providers needed to set a cross-provider band center
OUTLIER_WINDOW_DAYS = 28
# MARKETPLACES (providers.py): per-listing asks from many hosts; matched pairs need >= MIN_SIDE asks per side
MIN_BOOK_LISTINGS = 3      # a marketplace counts for a GPU on a day with at least this many usable asks ...
MIN_BOOK_HOSTS = 2         # ... from at least this many hosts
BOOK_FLOOR_FROM = "2026-10-24"   # the marketplace minimum applies from 4.1
MIN_SIDE = 3
VALIDATION_WINDOW_DAYS = 14
VALIDATION_TOL = 0.35      # provider-variant mean vs its reference (every move of 25-35% in the 13-month restated
                           # history was a lasting repricing, so a tighter screen only delays real moves)
MIN_CORROBORATING = 3      # other sources whose median move can confirm a large move (a median of two is their mean)
PERSIST_DAYS = 3           # a held move that persists this many days is accepted as structural
PERSIST_SPREAD = 0.10
CALIBRATION_WINDOW_DAYS = 28
RECALIBRATE_EVERY_DAYS = 7
MIN_PAIR_PROVIDERS = 2     # providers needed to calibrate a node/variant factor
MIN_PAIR_GROUPS = 5        # matched groups needed to calibrate a region/CPU factor
ANOMALY_MOVE = 0.05        # day-over-day index move flagged for review
CHAIN_GAP_DAYS = 7         # the index chains from the last published day within this many days
SHADOW_DAYS = 14           # a provider first collected after the panel start counts after 14 days
V4_START = "2026-10-24"    # first index day calculated with 4.0; providers collected before it count at once
V41_START = "2026-10-24"   # 4.1 applied (owner): its added providers count at once, from their second day of prices
ADDED_41 = frozenset({"lium", "vultr", "together", "massedcompute", "latitude", "digitalocean", "civo", "crusoe",
                      "imwt", "boostrun", "voltagepark", "denvr", "excesssupply", "horizon", "phyntec"})
# From this index day (audit, 2026-10-27) the within-provider 2x screen applies to marketplace asks only, as the
# methodology states; before, it was applied to every provider with three or more asks for a form factor (see
# data/errata.json). The first days after compare the clouds it affected like for like (old_screen_keys).
MARKETPLACE_SCREEN_FROM = "2026-10-27"
# From this index day (audit, 2026-10-27) every earlier day is compared in the day's own factors (restate), and each
# observed provider's offers without a factor are stored with its day, so a recalibration never moves the index.
RESTATE_FROM = "2026-10-27"
# the families whose matched comparisons calibrate the pooled factors (node size, region, CPU): the first seven, so
# adding a family never changes the factors of the families already indexed (4.2, 2026-10-28); every family is
# standardized with them
CALIBRATION_GPUS = frozenset(CORE_GPUS)

BENCHMARK = {
    "H100": "H100 SXM 80GB", "H200": "H200 SXM 141GB", "A100": "A100 SXM 80GB",
    "B200": "B200 SXM on HGX", "B300": "B300 SXM on HGX", "MI300X": "MI300X OAM 192GB",
    "RTX PRO 6000": "RTX PRO 6000 Blackwell 96GB, 600 W, Server or Workstation Edition",
    # added on 2026-10-28 (FAMILY_START): each one PCIe card
    "L40S": "L40S 48GB PCIe", "RTX 6000 Ada": "RTX 6000 Ada Generation 48GB PCIe", "RTX A6000": "RTX A6000 48GB PCIe",
    "L40": "L40 48GB PCIe", "RTX 5090": "GeForce RTX 5090 32GB", "RTX 4090": "GeForce RTX 4090 24GB",
    "RTX A4000": "RTX A4000 16GB PCIe",
}
BENCH_TERMS = "on-demand, 8-GPU node, US hardware, CPU-neutral"

EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT",
      "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "GB", "NO", "CH", "IS"}
APAC = {"JP", "KR", "TW", "HK", "SG", "AU", "NZ", "IN", "MY", "TH", "VN", "ID", "PH", "CN"}


def region_of(cc):
    if not cc:
        return None
    if cc == "US":
        return "US"
    if cc in EU:
        return "EU"
    if cc in APAC:
        return "APAC"
    return "OTHER"


def node_bucket(n):
    if not n:
        return None
    return "1" if n == 1 else "2" if n <= 3 else "4" if n <= 7 else "8"


def prev_days(d, k):
    """The k index days before d, most recent first (every calendar day is an index day)."""
    return [d - timedelta(days=i) for i in range(1, k + 1)]


def med(xs):
    return statistics.median(xs) if xs else None


def mean(xs):
    return sum(xs) / len(xs) if xs else None


# ------------------------------------------------------------------ step 1
def preprocess(raw, fx):
    """Attach unit_usd = price_hr / num_gpus (duration = 1 hour) in USD."""
    out = []
    for r in raw:
        rate = fx.get(r.get("currency") or "USD")
        n = r.get("num_gpus")
        p = r.get("price_hr")
        r = dict(r)
        r["unit_usd"] = (p / n) * rate if (rate and n and p and p > 0) else None
        out.append(r)
    return out


# ------------------------------------------------------------------ step 2
def completeness(records):
    kept, dropped = [], []
    for r in records:
        why = None
        if r.get("gpu") not in GPUS:
            why = "unknown GPU"
        elif not_indexed(r["gpu"], r.get("day")):
            why = not_indexed(r["gpu"], r.get("day"))
        elif r.get("variant") not in VARIANTS.get(r["gpu"], []):
            why = "form factor not published" if r.get("variant") is None else "unsupported variant"
        elif r.get("rental_type") != "on-demand":
            why = "not on-demand"
        elif not r.get("unit_usd") or not math.isfinite(r["unit_usd"]) or r["unit_usd"] <= 0:
            why = "missing or invalid price"
        (dropped if why else kept).append((r, why) if why else r)
    return kept, [dict(r, reason=w) for r, w in dropped]


def capacity_rule(records):
    """Where a source shows capacity, a provider counts for a GPU on a day only if at least one of its offers had
    capacity at some collection; its posted prices then all count. Deciding per provider, not per offer, keeps an
    offer selling out from reading as a change in the provider's price."""
    present = {(r["provider"], r["gpu"]) for r in records if r.get("obs", 1)}
    kept, dropped = [], []
    for r in records:
        if (r["provider"], r["gpu"]) in present:
            kept.append(r)
        else:
            dropped.append(dict(r, reason="no capacity at any collection that day"))
    return kept, dropped


def book_floor(records, day=None):
    """A marketplace (per-listing asks from many hosts) counts for a GPU on a day only with at least
    MIN_BOOK_LISTINGS usable asks (after the other filters and standardization) from at least MIN_BOOK_HOSTS
    hosts; a thinner book is one host's offer, whose identity can change from day to day, not a market price.
    Applies from BOOK_FLOOR_FROM."""
    if day and day < BOOK_FLOOR_FROM:
        return records, []
    books = {}
    for r in records:
        if r["provider"] in MARKETPLACES:
            books.setdefault((r["provider"], r["gpu"]), []).append(r)
    thin = {}
    for k, rs in books.items():
        hosts = {r.get("host") for r in rs if r.get("host")}
        if len(rs) < MIN_BOOK_LISTINGS or len(hosts) < MIN_BOOK_HOSTS:
            thin[k] = "marketplace book too thin (%d listings, %d hosts; need %d and %d)" % (
                len(rs), len(hosts), MIN_BOOK_LISTINGS, MIN_BOOK_HOSTS)
    kept, dropped = [], []
    for r in records:
        why = thin.get((r["provider"], r["gpu"]))
        (dropped.append(dict(r, reason=why)) if why else kept.append(r))
    return kept, dropped


def _provider_means(records, keyf):
    by = {}
    for r in records:
        by.setdefault(keyf(r), {}).setdefault(r["provider"], []).append(r["unit_usd"])
    return {k: {p: mean(v) for p, v in d.items()} for k, d in by.items()}


def _own_band(records, everyone):
    """{(provider, "GPU|variant"): median ask} for the within-provider screen: marketplaces only (everyone=False),
    or every provider with MIN_BAND_RECORDS asks (everyone=True: the screen as it ran before MARKETPLACE_SCREEN_FROM)."""
    pv = {}
    for r in records:
        if everyone or r["provider"] in MARKETPLACES:
            pv.setdefault((r["provider"], "%s|%s" % (r["gpu"], r["variant"])), []).append(r["unit_usd"])
    return {k: med(v) for k, v in pv.items() if len(v) >= MIN_BAND_RECORDS}


def old_screen_keys(records):
    """The offers the within-provider screen dropped before MARKETPLACE_SCREEN_FROM and keeps from then on (a cloud's
    asks more than OUTLIER_BAND x from its own median): a day compared with a day before then leaves them out of the
    comparison, so the rule's change is not read as a price change."""
    band = _own_band(records, everyone=True)
    out = set()
    for r in records:
        m = band.get((r["provider"], "%s|%s" % (r["gpu"], r["variant"])))
        if r["provider"] not in MARKETPLACES and m and not (m / OUTLIER_BAND <= r["unit_usd"] <= m * OUTLIER_BAND):
            out.add(r["key"])
    return out


def outlier_screen(records, history_centers, day=None):
    """Two layers, both aimed at reporting errors rather than real dispersion.

    1. Within a marketplace provider (>= MIN_BAND_RECORDS asks for a variant),
       drop asks more than OUTLIER_BAND x away from that provider's median
       (before MARKETPLACE_SCREEN_FROM, within every provider).
    2. Across providers, drop records outside [center/BAND_X, center*BAND_X],
       where center is the median of prior days' cross-provider medians for the
       variant (dynamic historical band) or, with no history, today's median of
       provider means. A center needs >= MIN_BAND_PROVIDERS providers.

    history_centers: {"H100|SXM": [daily cross-provider medians, ...]}.
    """
    vkey = lambda r: "%s|%s" % (r["gpu"], r["variant"])
    out = []
    pv_med = _own_band(records, everyone=not day or day < MARKETPLACE_SCREEN_FROM)
    stage1 = []
    for r in records:
        m = pv_med.get((r["provider"], vkey(r)))
        if m and not (m / OUTLIER_BAND <= r["unit_usd"] <= m * OUTLIER_BAND):
            out.append(dict(r, reason="more than %gx from this provider's median ask (%.4f)" % (OUTLIER_BAND, m)))
        else:
            stage1.append(r)
    today = _provider_means(stage1, vkey)
    centers = {}
    for k, pm in today.items():
        hist = history_centers.get(k) or []
        if hist:
            centers[k] = med(hist)
        elif len(pm) >= MIN_BAND_PROVIDERS:
            centers[k] = med(list(pm.values()))
    kept = []
    for r in stage1:
        c = centers.get(vkey(r))
        if c and not (c / BAND_X <= r["unit_usd"] <= c * BAND_X):
            out.append(dict(r, reason="outside dynamic price band (center %.4f, x%g)" % (c, BAND_X)))
        else:
            kept.append(r)
    variant_medians = {k: med(list(pm.values())) for k, pm in _provider_means(kept, vkey).items()
                       if len(pm) >= MIN_BAND_PROVIDERS}
    return kept, out, variant_medians, centers


def validate(records, pv_history, prior_held):
    """Provider-variant reference ranges and the jump screen.

    A provider-variant whose mean today is more than VALIDATION_TOL from its reference (the median of its unheld
    means in the window) is held, unless the market moved with it: with at least MIN_CORROBORATING sources other
    than its own priced for the GPU, the move divided by their median move (each source counted once, as the
    median of its providers' moves) is within VALIDATION_TOL (Hidiroglou and Berthelot's centring on the median
    change). Sources, not clouds, are counted because the clouds relayed by one catalog share its errors. A held
    move that persists PERSIST_DAYS days is released, except a move shared by most of one source's groups for the
    GPU that the market does not show: that is the source's error, held with no release (its providers drop out
    after IMPUTE_DAYS and return, without moving the index, once their old reference has left the window).

    pv_history: {"vast|H100|SXM": [(day, mean, n, held), ...]} for prior days.
    prior_held: {"vast|H100|SXM": [means on the previous PERSIST_DAYS-1 days]} (only if each of those days was
                 held, released or corroborated, and none was a source-wide hold).
    """
    key = lambda r: "%s|%s|%s" % (r["provider"], r["gpu"], r["variant"])
    groups = {}
    for r in records:
        groups.setdefault(key(r), []).append(r)
    kept, held, pv_today, alerts = [], [], {}, []
    moves = {}   # group -> (mean today, reference, relative = mean / reference, source)
    for k, rs in groups.items():
        m = mean([r["unit_usd"] for r in rs])
        hist = pv_history.get(k) or []
        ref = med([h[1] for h in hist if not h[3]])
        moves[k] = (m, ref, m / ref if ref else None, rs[0].get("source") or rs[0]["provider"])
    status, why = {}, {}
    for k in groups:
        m, ref, x, src = moves[k]
        status[k], why[k] = "ok", None
        if x and abs(x - 1) > VALIDATION_TOL:
            gpu = k.split("|")[1]
            by_src = {}
            for o, (_, _, ox, osrc) in moves.items():
                if ox and osrc != src and o.split("|")[1] == gpu:
                    by_src.setdefault(osrc, []).append(ox)
            market = med([med(v) for v in by_src.values()]) if len(by_src) >= MIN_CORROBORATING else None
            persisted = prior_held.get(k)
            if market and abs(x / market - 1) <= VALIDATION_TOL:
                status[k], why[k] = "corroborated", "move of %+.0f%% in line with the median move of %d other sources (%+.0f%%)" % (
                    (x - 1) * 100, len(by_src), (market - 1) * 100)
            elif persisted and len(persisted) >= PERSIST_DAYS - 1 and all(
                    abs(p / m - 1) <= PERSIST_SPREAD for p in persisted):
                status[k], why[k] = "released", "move persisted %d days; accepted as structural" % PERSIST_DAYS
            else:
                status[k], why[k] = "held", "mean %.4f vs reference %.4f (> %d%%), not matched by other sources" % (
                    m, ref, VALIDATION_TOL * 100)
    # a large move by most of the clouds one source relays for a GPU, not shown by the market, is that source's
    # error (a single provider repricing all its variants is not: it needs at least 2 providers)
    by_sg = {}
    for k, (_, _, x, src) in moves.items():
        if x:
            by_sg.setdefault((src, k.split("|")[1]), []).append(k)
    source_hold = set()
    for (src, gpu), ks in by_sg.items():
        provs = {k.split("|")[0] for k in ks}
        for up in (True, False):
            side = [k for k in ks if status[k] in ("held", "released") and (moves[k][2] > 1) == up]
            side_provs = {k.split("|")[0] for k in side}
            if len(side_provs) >= 2 and 2 * len(side_provs) >= len(provs):
                for k in side:
                    source_hold.add(k)
                    status[k], why[k] = "held", "move of %+.0f%% shared by %d of the %d clouds %s relays for %s, not shown by other sources" % (
                        (moves[k][2] - 1) * 100, len(side_provs), len(provs), src, gpu)
    for k, rs in groups.items():
        m = moves[k][0]
        ref_n = med([h[2] for h in pv_history.get(k) or []])
        if ref_n and len(rs) < 0.2 * ref_n:
            alerts.append("%s: %d records vs usual %d" % (k, len(rs), ref_n))
        if k in source_hold:
            alerts.append("%s: %s" % (k, why[k]))
        pv_today[k] = {"mean": round(m, 6), "n": len(rs), "held": status[k] == "held", "status": status[k]}
        if k in source_hold:
            pv_today[k]["source_hold"] = True
        if status[k] == "held":
            held.extend(dict(r, reason=why[k]) for r in rs)
        else:
            kept.extend(dict(r, note=why[k]) if why[k] else r for r in rs)
    return kept, held, pv_today, alerts


# ------------------------------------------------------------------ step 3
def _ratio_by_provider(pairs):
    """pairs: [(provider, ratio)] -> median across providers of per-provider medians."""
    byp = {}
    for p, x in pairs:
        if x and math.isfinite(x) and x > 0:
            byp.setdefault(p, []).append(x)
    per = [med(v) for v in byp.values()]
    return (med(per), len(per)) if per else (None, 0)


def calibrate(records, calibrated_on, window):
    """Estimate basis-adjustment factors from matched comparisons.

    Sequential: node size, then form factor (on node-adjusted prices), then
    region and CPU platform (on node+variant adjusted prices). Calibrated on the
    CALIBRATION_GPUS families' records only; every family is standardized with
    these factors (an added family's single form factor is its benchmark, 1.0).
    """
    recs = [dict(r) for r in records if r.get("gpu") in CALIBRATION_GPUS]
    for r in recs:
        r["_b"] = node_bucket(r.get("node"))
        r["_reg"] = region_of(r.get("country"))
    model = {"calibrated_on": calibrated_on, "window": window, "node": {BENCH_NODE: 1.0},
             "variant": {g: {VARIANTS[g][0]: 1.0} for g in GPUS}, "region": {"US": 1.0},
             "cpu": {}, "support": {"node": {}, "variant": {}, "region": {}, "cpu": {}}}

    def grouped(rows, keyf, levelf):
        """{group key: {level: [records]}}; a marketplace level with fewer than
        MIN_SIDE asks is dropped so single listings cannot set a factor."""
        g = {}
        for r in rows:
            lv = levelf(r)
            if lv is None:
                continue
            g.setdefault(keyf(r), {}).setdefault(lv, []).append(r)
        for k, lv in g.items():
            for name in [n for n, rs in lv.items() if rs[0]["provider"] in MARKETPLACES and len(rs) < MIN_SIDE]:
                del lv[name]
        return g

    # node size
    groups = grouped(recs, lambda r: (r["day"], r["provider"], r.get("tier"), r["gpu"], r["variant"],
                                      r["_reg"], r.get("cpu")), lambda r: r["_b"])
    for b in ("1", "2", "4"):
        pairs = [(k[1], mean([x["unit_usd"] for x in lv[b]]) / mean([x["unit_usd"] for x in lv[BENCH_NODE]]))
                 for k, lv in groups.items() if b in lv and BENCH_NODE in lv]
        m, n = _ratio_by_provider(pairs)
        ok = m is not None and n >= MIN_PAIR_PROVIDERS
        model["node"][b] = round(min(1.4, max(0.7, m)), 4) if ok else 1.0
        model["support"]["node"][b] = n
    nf = lambda r: model["node"].get(r["_b"], 1.0) if r["_b"] else 1.0
    for r in recs:
        r["_u1"] = r["unit_usd"] / nf(r)

    # form factor, per family
    groups = grouped(recs, lambda r: (r["day"], r["provider"], r.get("tier"), r["gpu"], r["_reg"], r.get("cpu")),
                     lambda r: r["variant"])
    for g in GPUS:
        bench = VARIANTS[g][0]
        for v in VARIANTS[g][1:]:
            pairs = [(k[1], mean([x["_u1"] for x in lv[v]]) / mean([x["_u1"] for x in lv[bench]]))
                     for k, lv in groups.items() if k[3] == g and v in lv and bench in lv]
            m, n = _ratio_by_provider(pairs)
            model["support"]["variant"]["%s|%s" % (g, v)] = n
            if m is not None and n >= MIN_PAIR_PROVIDERS:
                model["variant"][g][v] = round(min(1.5, max(0.3, m)), 4)
    vf = lambda r: model["variant"].get(r["gpu"], {}).get(r["variant"])
    recs = [r for r in recs if vf(r)]
    for r in recs:
        r["_u2"] = r["_u1"] / vf(r)

    # region (pooled across families), relative to US
    groups = grouped(recs, lambda r: (r["day"], r["provider"], r.get("tier"), r["gpu"], r["variant"], r["_b"],
                                      r.get("cpu")), lambda r: r["_reg"])
    for reg in ("EU", "APAC", "OTHER"):
        ratios = [med([x["_u2"] for x in lv[reg]]) / med([x["_u2"] for x in lv["US"]])
                  for lv in groups.values() if reg in lv and "US" in lv]
        model["support"]["region"][reg] = len(ratios)
        model["region"][reg] = round(min(1.4, max(0.7, med(ratios))), 4) if len(ratios) >= MIN_PAIR_GROUPS else 1.0
    rf = lambda r: model["region"].get(r["_reg"], 1.0) if r["_reg"] else 1.0
    for r in recs:
        r["_u3"] = r["_u2"] / rf(r)

    # CPU platform, effect-coded so the platforms average to 1
    groups = grouped(recs, lambda r: (r["day"], r["provider"], r.get("tier"), r["gpu"], r["variant"], r["_b"],
                                      r["_reg"]), lambda r: r.get("cpu"))
    ratios = [med([x["_u3"] for x in lv["AMD"]]) / med([x["_u3"] for x in lv["Intel"]])
              for lv in groups.values() if "AMD" in lv and "Intel" in lv]
    model["support"]["cpu"]["AMD/Intel"] = len(ratios)
    if len(ratios) >= MIN_PAIR_GROUPS:
        m = min(1.4, max(0.7, med(ratios)))
        model["cpu"] = {"AMD": round(math.sqrt(m), 4), "Intel": round(1 / math.sqrt(m), 4)}
    else:
        model["cpu"] = {"AMD": 1.0, "Intel": 1.0}
    return model


def factor(r, model):
    """The record's basis-adjustment factor under the model, or None when its form factor has no calibrated factor."""
    vf = model["variant"].get(r["gpu"], {}).get(r["variant"])
    if not vf:
        return None
    b = node_bucket(r.get("node"))
    f = vf * (model["node"].get(b, 1.0) if b else 1.0)
    reg = region_of(r.get("country"))
    f *= model["region"].get(reg, 1.0) if reg else 1.0
    f *= model["cpu"].get(r.get("cpu"), 1.0) if r.get("cpu") else 1.0
    return f


def standardize(records, model):
    kept, dropped = [], []
    for r in records:
        f = factor(r, model)
        if not f:
            dropped.append(dict(r, reason="no calibrated basis adjustment for %s %s" % (r["gpu"], r["variant"])))
            continue
        kept.append(dict(r, factor=f, adj_usd=r["unit_usd"] / f))
    return kept, dropped


OFFER_FIELDS = ("key", "unit_usd", "gpu", "variant", "node", "country", "cpu")


def offers_state(std_records, old_keys=()):
    """Each observed provider's offers on the day, as stored for the next day's chain: {gpu: {provider: [rows]}}
    with rows in OFFER_FIELDS order (raw USD per GPU-hour and what standardization needs), and a final 1 on an offer
    the within-provider screen dropped before MARKETPLACE_SCREEN_FROM (old_keys), so a comparison with a day before
    then can leave it out."""
    out = {}
    for r in std_records:
        row = [r.get(f) if f != "unit_usd" else round(r["unit_usd"], 6) for f in OFFER_FIELDS]
        if r.get("key") in old_keys:
            row.append(1)
        out.setdefault(r["gpu"], {}).setdefault(r["provider"], []).append(row)
    return out


def restandardize(offers, model, old_rule=False):
    """A day's stored offers for one GPU standardized with another day's model:
    {provider: {"keys": {offer key: raw USD}, "avg": mean standardized price}}; old_rule leaves out the offers the
    within-provider screen dropped before MARKETPLACE_SCREEN_FROM (for a comparison with a day before then)."""
    out = {}
    n = len(OFFER_FIELDS)
    for p, rows in (offers or {}).items():
        keys, adj = {}, []
        for row in rows:
            if old_rule and len(row) > n and row[n]:
                continue
            r = dict(zip(OFFER_FIELDS, row))
            f = factor(r, model)
            if f and r["unit_usd"]:
                keys[r["key"]] = r["unit_usd"]
                adj.append(r["unit_usd"] / f)
        if adj:
            out[p] = {"keys": keys, "avg": mean(adj)}
    return out


def restate(lookback, chain, offers_by_day, avgs_by_day, model):
    """The look-back state in the day's own factors (from RESTATE_FROM): a change of the factors, as at the weekly
    recalibration, must not read as a price change, so every earlier day is compared in today's factors.

    offers_by_day, avgs_by_day: {day: {gpu: stored offers}} and {day: {gpu: {provider: observed average}}} for each of
    the IMPUTE_DAYS days before the day computed ({} for a day with nothing stored; a day beyond them is not used,
    so every run computes a day from the same days whatever else it has stored).

    Returns (lookback, bases):
      lookback  as given, with an imputed provider's last average and the other providers' averages that day
                restandardized from that day's offers in today's factors (as given where they are not stored);
      bases     {gpu: {provider: its chain-day average in today's factors}} for each provider imputed on the chain day,
                imputed again the same way (none where the inputs are not stored: its stored average then applies).
    A provider observed on the chain day is compared with its offers then (provider_change)."""
    cache = {}

    def rest(day, g, old_rule=False):
        if (day, g, old_rule) not in cache:
            offs = (offers_by_day.get(day) or {}).get(g)
            cache[(day, g, old_rule)] = restandardize(offs, model, old_rule) if offs else {}
        return cache[(day, g, old_rule)]

    out = {}
    for g, provs in (lookback or {}).items():
        out[g] = {}
        for p, (d, last, others) in provs.items():
            rd = rest(d, g)
            out[g][p] = (d, rd[p]["avg"], {q: rd[q]["avg"] for q in others if q in rd}) if p in rd else (d, last, others)
    bases = {}
    for g, c in (chain or {}).items():
        rc = rest(c["day"], g)
        for p in c.get("avgs") or {}:
            if p in rc or not rc:
                continue
            # imputed on the chain day: from its last observed day before then, as that day's own calculation did
            for b in prev_days(date.fromisoformat(c["day"]), IMPUTE_DAYS):
                s = b.isoformat()
                if s not in avgs_by_day:
                    break
                seen = avgs_by_day[s].get(g) or {}
                if p in seen:
                    rs = rest(s, g)
                    # the chain day as the screen of day s saw it, when that screen was the old one
                    rcs = rest(c["day"], g, c["day"] >= MARKETPLACE_SCREEN_FROM > s)
                    if p in rs:
                        ratio = gmean([rcs[q]["avg"] / rs[q]["avg"] for q in seen
                                       if q != p and q in rcs and q in rs and rs[q]["avg"]]) or 1.0
                        bases.setdefault(g, {})[p] = rs[p]["avg"] * ratio
                    break
    return out, bases


# ------------------------------------------------------------------ step 4
def gmean(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else None


def winsor_bounds(values):
    """(lo, hi): the k-th lowest and k-th highest value, k = max(1, floor(n x WINSOR_SHARE))."""
    xs = sorted(values)
    k = max(1, int(len(xs) * WINSOR_SHARE))
    return xs[k], xs[-k - 1]


def wmean(values):
    """Winsorized equal-weighted mean: values beyond the k-th lowest / highest are clipped to them."""
    lo, hi = winsor_bounds(values)
    return sum(min(max(v, lo), hi) for v in values) / len(values)


def quartiles(values):
    xs = sorted(values)
    if len(xs) < 2:
        return None
    q = statistics.quantiles(xs, n=4, method="inclusive")
    return [q[0], q[1], q[2]]


def eligible(first, day, shadow_from, provider=None, gpu=None):
    """A provider counts in the chained index once collected for SHADOW_DAYS, unless it was in the panel
    before shadow_from (the start of the panel) or was added by 4.1 (counted at once by the owner's decision;
    a chained index still needs two days of its prices to measure a change). For a family added later
    (FAMILY_START), the panel is the providers first priced in its first SHADOW_DAYS days (its index starts on the
    first day five of them are priced), which count at once; a provider first priced later serves the shadow period.
    The 4.1 exception is for the first seven families only."""
    if not first:
        return False
    if not day:
        return True
    start = FAMILY_START.get(gpu)
    if start:
        launch = (date.fromisoformat(first) - date.fromisoformat(start)).days < SHADOW_DAYS
        return launch or (date.fromisoformat(day) - date.fromisoformat(first)).days >= SHADOW_DAYS
    if provider in ADDED_41 and day >= V41_START:
        return True
    return first < shadow_from or (date.fromisoformat(day) - date.fromisoformat(first)).days >= SHADOW_DAYS


def provider_change(p, v, prev_avg, prev_offers, base=None, restated=False, cur=None):
    """A matched provider's price change since the last published day: its average today over its average then,
    both standardized with today's factors, so a recalibration of the factors is not read as a price change.
    Before RESTATE_FROM, imputed providers, and providers imputed on that day, move by their averages as carried.
    From then (restated), every provider is compared in today's factors: with its offers on that day (prev_offers),
    else with its average imputed again from that day's offers (base), else with its average as stored.
    cur: its average today for this comparison when that differs from v["avg"] (old_screen_keys)."""
    now = v["avg"] if cur is None else cur
    po = prev_offers.get(p)
    if restated:
        return now / (po["avg"] if po else (base or prev_avg))
    if v["carried"] or not po:
        return v["avg"] / prev_avg
    return v["avg"] / po["avg"]


def aggregate(std_records, lookback, chain=None, first_seen=None, day=None, shadow_from=V4_START, prev_offers=None,
              bases=None, old_avgs=None):
    """lookback: {gpu: {provider: (day, avg, {other provider: avg})}} with each
    provider's most recent observed average in the previous IMPUTE_DAYS days and
    the averages of the other providers observed that day.
    chain: {gpu: {"day", "level", "avgs": {provider: avg}}}: the last published day within CHAIN_GAP_DAYS.
    first_seen: {gpu: {provider: first day observed}}.
    prev_offers: {gpu: restandardize(offers on the chain day, today's model)}.
    bases: {gpu: {provider: chain-day average in today's factors}} for providers imputed then (restate).
    old_avgs: {gpu: {provider: average today without old_screen_keys}}, used when comparing with a day before
    MARKETPLACE_SCREEN_FROM.

    A provider missing today is imputed (class-mean imputation): its last average
    times the geometric-mean change, since that day, of the providers observed on
    both days.
    Cross-section: the equal-weighted mean of the provider averages after
    winsorizing (values beyond the k-th lowest / highest are clipped to them).
    Index (chained): the last published level times the geometric mean of the changes of the providers
    priced on both days (matched), so entries and exits do not move it; with no published day within
    CHAIN_GAP_DAYS the index starts at the cross-section."""
    out = {}
    for g in gpus_on(day):
        rs = [r for r in std_records if r["gpu"] == g]
        byp = {}
        for r in rs:
            byp.setdefault(r["provider"], []).append(r["adj_usd"])
        provs = {p: {"avg": mean(v), "records": len(v), "carried": False} for p, v in byp.items()}
        seen = {p: v["avg"] for p, v in provs.items()}   # observed today: only these measure the change since then
        old = (old_avgs or {}).get(g) or {}
        now_vs = lambda q, then: old[q] if q in old and then < MARKETPLACE_SCREEN_FROM else seen[q]
        for p, (d, last, others) in (lookback.get(g) or {}).items():
            if p in provs:
                continue
            # "the geometric-mean change, since that day, of the providers observed on both days": a provider imputed
            # a moment earlier in this loop is not observed and does not count (it did before 2026-10-27, so with
            # two providers carried from the same day the result depended on their order)
            ratio = gmean([now_vs(q, d) / a for q, a in others.items() if q in seen and a]) or 1.0
            provs[p] = {"avg": last * ratio, "records": 0, "carried": True, "from": d, "last": last, "ratio": ratio}
        observed = [p for p, v in provs.items() if not v["carried"]]
        res = {"value": None, "cross": None, "providers": provs, "records": len(rs), "clip": None, "chain": None,
               "quartiles": quartiles([v["avg"] for v in provs.values()]), "reason": None}
        if len(provs) >= MIN_PROVIDERS and len(observed) >= MIN_OBSERVED:
            lo, hi = winsor_bounds([v["avg"] for v in provs.values()])
            w = 1.0 / len(provs)
            for v in provs.values():
                v["weight"] = w
                v["used"] = min(max(v["avg"], lo), hi)
            res["cross"] = sum(v["weight"] * v["used"] for v in provs.values())
            res["clip"] = [lo, hi]
        prev = (chain or {}).get(g)
        if prev and prev.get("level"):
            fs = (first_seen or {}).get(g) or {}
            matched = sorted(p for p in provs if p in prev["avgs"] and eligible(fs.get(p), day, shadow_from, p, g))
            m_obs = [p for p in matched if not provs[p]["carried"]]
            for p, v in provs.items():
                v["matched"] = p in matched
            if len(matched) >= MIN_PROVIDERS and len(m_obs) >= MIN_OBSERVED:
                # equal-weighted geometric mean of the matched providers' changes: each provider's change counts
                # 1/n, whatever its price level or rank (a winsorized mean of levels would count the providers at
                # the clipping points twice)
                po = (prev_offers or {}).get(g) or {}
                base = (bases or {}).get(g) or {}
                restated = bool(day and day >= RESTATE_FROM)
                changes = {p: provider_change(p, provs[p], prev["avgs"][p], po, base.get(p), restated,
                                              old[p] if p in old and prev["day"] < MARKETPLACE_SCREEN_FROM else None)
                           for p in matched}
                for p, c in changes.items():
                    provs[p]["change"] = c
                ratio = gmean(list(changes.values()))
                res["value"] = prev["level"] * ratio
                res["chain"] = {"from": prev["day"], "level": prev["level"], "ratio": ratio, "matched": matched}
            else:
                res["reason"] = "insufficient providers priced on both %s and today (%d, %d observed; need %d and %d)" % (
                    prev["day"], len(matched), len(m_obs), MIN_PROVIDERS, MIN_OBSERVED)
        elif res["cross"] is not None:
            res["value"] = res["cross"]   # the chain starts (or restarts after a gap) at the cross-section
            res["chain"] = {"from": None, "level": None, "ratio": None, "matched": []}
        else:
            res["reason"] = "insufficient providers (%d, %d observed; need %d and %d)" % (
                len(provs), len(observed), MIN_PROVIDERS, MIN_OBSERVED)
        out[g] = res
    return out


def imputed_because(cats):
    """A carried provider's label from its own records' exclusion reasons (categories) today."""
    if "held" in cats:
        return "imputed: price move held until confirmed"
    if "thin" in cats:
        return "imputed: marketplace book too thin"
    if cats == {"no capacity"}:
        return "imputed: no capacity at any collection"
    if "outlier" in cats:
        return "imputed: prices left out by the outlier checks"
    if "unadjustable" in cats:
        return "imputed: no standardization factor for its form factor"
    if cats:
        return "imputed: prices incomplete"
    return "imputed: no price collected"


def compute_day(day_records, model, ctx):
    """Run steps 2-4 for one index date.

    ctx carries prior-day state from stats: history_centers, pv_history,
    prior_held, lookback, chain (with each GPU's offers on the chain day), first_seen, day and shadow_from.
    Returns results plus the stats to store for the day.
    """
    day = ctx.get("day")
    kept, incomplete = completeness(day_records)
    kept, soldout = capacity_rule(kept)
    incomplete += soldout
    old_keys = old_screen_keys(kept) if day and day >= MARKETPLACE_SCREEN_FROM else set()
    kept, outliers, variant_medians, centers = outlier_screen(kept, ctx["history_centers"], day)
    kept, held, pv_today, alerts = validate(kept, ctx["pv_history"], ctx["prior_held"])
    std, unadjustable = standardize(kept, model)
    std, thin = book_floor(std, day)   # counted on the asks the index can use, after every other filter
    chain = ctx.get("chain") or {}
    prev_offers = {g: restandardize(c.get("offers"), model) for g, c in chain.items()}
    lookback, bases = ctx["lookback"], None
    if day and day >= RESTATE_FROM:
        lookback, bases = restate(ctx["lookback"], chain, ctx.get("offers_by_day") or {}, ctx.get("avgs_by_day") or {},
                                  model)
    # each cloud with offers the old within-provider screen dropped: its average without them, for comparisons with
    # the days before MARKETPLACE_SCREEN_FROM (their stored averages and offers were made without them)
    old_by = {}
    hit = {(r["provider"], r["gpu"]) for r in std if r["key"] in old_keys}
    for r in std:
        if (r["provider"], r["gpu"]) in hit and r["key"] not in old_keys:
            old_by.setdefault(r["gpu"], {}).setdefault(r["provider"], []).append(r["adj_usd"])
    old_avgs = {g: {p: mean(v) for p, v in d.items()} for g, d in old_by.items()}
    agg = aggregate(std, lookback, chain, ctx.get("first_seen"), day, ctx.get("shadow_from", V4_START), prev_offers,
                    bases, old_avgs)
    # why each provider without a price today is imputed, from its own records' exclusion reasons
    why = {}
    for cat, rows in (("incomplete", incomplete), ("thin", thin), ("outlier", outliers), ("held", held),
                      ("unadjustable", unadjustable)):
        for r in rows:
            c = "no capacity" if cat == "incomplete" and r.get("reason", "").startswith("no capacity") else cat
            why.setdefault((r["provider"], r["gpu"]), set()).add(c)
    for g, a in agg.items():
        for p, v in a["providers"].items():
            v["status"] = "observed" if not v["carried"] else imputed_because(why.get((p, g), set()))
    provider_avg = {g: {p: v["avg"] for p, v in a["providers"].items() if not v["carried"]}
                    for g, a in agg.items()}
    # the offers stored with the day: each observed provider's, and from RESTATE_FROM also those of its offers that
    # have no factor today, so a form factor that gains one at a recalibration is counted on both days compared
    stored = std
    if day and day >= RESTATE_FROM:
        observed = {(r["provider"], r["gpu"]) for r in std}
        stored = std + [r for r in unadjustable if (r["provider"], r["gpu"]) in observed]
    return {
        "agg": agg, "std": std,
        "excluded": {"incomplete": incomplete, "thin": thin, "outliers": outliers, "held": held,
                     "unadjustable": unadjustable},
        "alerts": alerts, "centers": centers,
        "stats": {"variant_median": variant_medians, "pv": pv_today, "provider_avg": provider_avg,
                  # the chained index's state: each GPU's level, every provider's average (imputed included) and
                  # the observed providers' offers, so the next day compares each offer with itself
                  "level": {g: a["value"] for g, a in agg.items()},
                  "chain_avgs": {g: {p: v["avg"] for p, v in a["providers"].items()} for g, a in agg.items()},
                  "offers": offers_state(stored, old_keys)},
    }
