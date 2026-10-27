"""What the GPU Rental Index covers: the GPU families, each family's form factors (the benchmark contract's first),
the providers (index constituents) and which of them are marketplaces.

Shared by the collectors (providers.py), the calculation (method.py) and the public verifier (verify.py), so the
published calculation code needs nothing from the collectors. Standard library only.
"""

GPUS = ["H100", "H200", "A100", "B200", "B300", "MI300X", "RTX PRO 6000"]

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
}

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
