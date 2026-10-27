# Verify every published value

This folder holds the code that calculates Compute Screener's GPU rental index (`method.py`, `recompute.py`,
`catalog.py`) and a verifier (`verify.py`). The verifier recomputes published values from the public files on
computescreener.com and checks that they match. It needs Python 3.9 or later and nothing else (standard library only).

```sh
python verify.py --date 2026-10-25 --gpu H100     # one GPU's final value on one day
python verify.py --date 2026-10-25                # every GPU and AI company that day
python verify.py --all                            # every day with a manifest
python verify.py --all --data ./data              # from a local copy of computescreener.com/data
python verify.py --date 2026-10-28 --readings     # rebuild a day's records from its price readings (any day)
```

Exit status: 0 if every value checked matches, 1 if a value or file does not match, 2 if a file could not be read.

A scheduled job in this repository runs `python verify/verify.py --all` every day. Each run adds one row to
[results.csv](results.csv), and the full output of the latest run is in [last-run.txt](last-run.txt).

## Manifests

Once a day is final, the index writes a manifest for it:

- **GPU index days** (US Central days, final after midnight Chicago time):
  [data/manifests/gpu/&lt;day&gt;.json](https://computescreener.com/data/manifests/gpu/2026-10-25.json)
- **Token index days** (UTC days): [data/manifests/tokens/&lt;day&gt;.json](https://computescreener.com/data/manifests/tokens/2026-10-25.json)
- **List of all manifests:** [data/manifests/index.json](https://computescreener.com/data/manifests/index.json)

A GPU day's manifest names every file the day was computed from, each with its SHA-256:

- from 2026-10-28, the day's price readings: every reading at every collection, with its time;
- the day's records: each offer's readings summed (how many with and without capacity, and their prices);
- the stored state of the 28 earlier days the calculation looks back on;
- the trace: what was used or left out, and why;
- the day's own stored state, which the next days build on.

It also gives the SHA-256 of the standardization factors in force, the final values, and the SHA-256 of each
calculation file that produced them. The manifest's `id` is the SHA-256 of all of this.

A manifest is written once and never changed. It is kept only if its day already reproduces from the files it
names. If a published value ever needed correcting, the correction would roll forward; it would not rewrite a
final day. See the [methodology](https://computescreener.com/methodology).

## What the verifier checks

For each GPU index day:

1. It downloads every file the manifest names and checks each SHA-256.
2. From 2026-10-28, it sums the day's price readings again into each offer's counts and sums, which must equal the
   day's records: the records are checked against what was read, not taken on trust.
3. It recomputes each GPU's value with `method.py` from:
   - the day's records,
   - the factors in force,
   - the stored state of the earlier days.
4. It compares each recomputed value with the published final value, to the published 4 decimals.
5. It checks that the day's own recomputed state equals the stored one. Verifying every day in turn therefore
   checks the whole chain back to the readings.

The readings (`data/readings/<day>.json.gz`) list, per offer, each reading's collection (`t`: the first as an index
into `runs`, then the gaps) and its value (`v`: `[count, price per GPU-hour as posted, 1 with capacity / 0 without]`,
consecutive equal readings counted once). `expand()` in `verify.py` turns them into one row per reading. The code
that reads the providers' prices is not published; the readings show what it read and when.

For each token index day, it recomputes each company's value from the day's trace and compares it with the
published value. The trace lists each model's tokens and posted prices, and the value is the token-weighted mean
of the company's models, blended 3 input : 1 output.

If this folder's copy of a calculation file differs from the one that wrote a manifest, the verifier prints a
note. When a methodology version changes the code, this folder is updated with it.

## Licence

The code in this folder is licensed under the terms in [LICENSE](LICENSE): you may read, copy and run it to check
or reproduce Compute Screener's published values, and publish what you find. The data is
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), with credit to "Compute Screener (computescreener.com)".
