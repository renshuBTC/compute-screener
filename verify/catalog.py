"""What the GPU Rental Index covers: the GPU families, each family's form factors (the benchmark contract's first),
the providers (index constituents) and which of them are marketplaces.

Shared by the collectors (providers.py), the calculation (method.py) and the public verifier (verify.py), so the
published calculation code needs nothing from the collectors. Standard library only.
"""

# the first seven families (indexed from the start), then the families added later (owner, 2026-10-27: "Put as many
# gpu from the every gpu in the list in the table, following the same format and same methodology")
CORE_GPUS = ["H100", "H200", "A100", "B200", "B300", "MI300X", "RTX PRO 6000"]
ADDED_GPUS = ["L40S", "RTX A6000", "RTX 6000 Ada", "L40", "RTX 5090", "RTX 4090", "RTX A4000"]
GPUS = CORE_GPUS + ADDED_GPUS

# the first index day of each added family: its offers before then are recorded but not used. An added family without
# a start is collected but not indexed yet: on the day the collectors were extended (2026-10-27) only the L40S and the
# RTX A6000 had the five providers an index needs (methodology: aggregation); each other starts once a whole day of
# collection prices it at five providers or more, and is given its start then. 2026-10-28 (the method run on the day's
# records as if indexed): RTX 6000 Ada 5 (Lium, Massed Compute, RunPod, Vast.ai, Verda), L40 5 (CoreWeave, Hyperstack,
# Massed Compute, RunPod, Vast.ai), RTX 4090 5 (Akash, Excess Supply, Lium, RunPod, Vast.ai): indexed from 2026-10-30;
# RTX 5090 4, RTX A4000 3: collected until a day prices them at five
FAMILY_START = {"L40S": "2026-10-28", "RTX A6000": "2026-10-28",
                "RTX 6000 Ada": "2026-10-30", "L40": "2026-10-30", "RTX 4090": "2026-10-30"}
# From 2026-10-31 a family is started without a code change (owner: "no longer hide and ask for my permissions before
# you expand the lists, once theres new GPUs roll it out right away"): scripts/auto_start.py writes its start to
# data/families.json, published at /data/families.json, which the pipeline, the site, the app, the connector and the
# public verifier read. A start set here never changes; the file only adds families of ADDED_GPUS that have none.
FAMILIES_FILE = "families.json"


def merge_started(started):
    """Add the starts of families started since (data/families.json "start"): only families of ADDED_GPUS without a
    start here, each an ISO day; returns the families added."""
    added = []
    for g, d in sorted((started or {}).items()):
        if g in ADDED_GPUS and g not in FAMILY_START and isinstance(d, str) and len(d) == 10 and d[4] == "-":
            FAMILY_START[g] = d
            added.append(g)
    return added


def _load_started():
    import json
    import os
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", FAMILIES_FILE)
    try:
        with open(p) as f:
            merge_started((json.load(f) or {}).get("start"))
    except (OSError, ValueError, AttributeError):
        pass   # no file (the public verifier's copy reads it from the published data instead)


_load_started()

# Benchmark contract form factor per family (the first entry) and the other variants that can be standardized to it.
VARIANTS = {
    "H100": ["SXM", "PCIe", "NVL"],
    "H200": ["SXM", "NVL"],
    "A100": ["SXM", "PCIe", "SXM-40GB", "PCIe-40GB"],
    "B200": ["SXM"],
    "B300": ["SXM"],
    "MI300X": ["OAM"],
    # 600W = the 600 W card (Server or Workstation Edition: same GB202 chip, 96GB);
    # Max-Q = the 300 W Workstation card. Listings that do not say which edition
    # keep variant=None and are dropped by the completeness check.
    "RTX PRO 6000": ["600W", "Max-Q"],
    # the added families: each is one product, a PCIe card with one memory size (CARD_GB); a listing of another memory
    # size (an RTX 4090 modified to 48 GB) is another product, left out as an unsupported variant
    "L40S": ["PCIe"], "RTX 6000 Ada": ["PCIe"], "RTX A6000": ["PCIe"], "L40": ["PCIe"],
    "RTX 5090": ["PCIe"], "RTX 4090": ["PCIe"], "RTX A4000": ["PCIe"],
}
CARD_GB = {"L40S": 48, "RTX 6000 Ada": 48, "RTX A6000": 48, "L40": 48, "RTX 5090": 32, "RTX 4090": 24, "RTX A4000": 16}


def card_variant(gpu, vram):
    """An added family's form factor for a listing with this memory per GPU (GB as the source states it, None when it
    does not): "PCIe" for the family's card (with ECC on, a card reports up to a tenth less memory), else the memory
    as an unsupported variant ("48GB")."""
    gb = CARD_GB[gpu]
    if not vram or 0.9 * gb <= vram <= gb + 1:
        return "PCIe"
    return "%dGB" % round(vram)


def gpus_on(day):
    """The families indexed on a day (ISO date; None: every family indexed or to be indexed on a set day): the first
    seven, and each added family from its FAMILY_START."""
    return [g for g in GPUS if g in CORE_GPUS or (g in FAMILY_START and (not day or day >= FAMILY_START[g]))]


def not_indexed(gpu, day):
    """Why an added family's offers are not used on a day (None when they are)."""
    if gpu in CORE_GPUS or gpu not in GPUS:
        return None
    if gpu not in FAMILY_START:
        return "%s is not indexed yet (collected until it has five providers)" % gpu
    if day and day < FAMILY_START[gpu]:
        return "%s is indexed from %s" % (gpu, FAMILY_START[gpu])
    return None


# providers (index constituents)
PROVIDER_NAMES = {
    "vast": "Vast.ai", "runpod": "RunPod", "akash": "Akash", "verda": "Verda (DataCrunch)",
    "scaleway": "Scaleway", "ovhcloud": "OVHcloud", "lambda": "Lambda", "nebius": "Nebius",
    "coreweave": "CoreWeave", "hyperstack": "Hyperstack", "jarvislabs": "Jarvis Labs",
    "hotaisle": "Hot Aisle",
    # added in methodology 4.1 (2026-10-24)
    "lium": "Lium", "vultr": "Vultr", "together": "Together AI",
    "massedcompute": "Massed Compute", "latitude": "Latitude.sh", "digitalocean": "DigitalOcean", "civo": "Civo",
    "crusoe": "Crusoe via Shadeform", "imwt": "IMWT via Shadeform",
    "boostrun": "BoostRun via Shadeform", "voltagepark": "Voltage Park via Shadeform",
    "denvr": "Denvr via Shadeform", "excesssupply": "Excess Supply via Shadeform",
    "horizon": "Horizon via Shadeform", "phyntec": "Phyntec via Shadeform",
}

# marketplaces: per-listing asks from many hosts (a book needs enough listings and hosts to count)
MARKETPLACES = {"vast", "lium"}
