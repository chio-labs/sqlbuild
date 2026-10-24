# DuckShop 10K

A deterministic generator for a ten-thousand-model SQLBuild project in Snowflake SQL. It describes
Mallard & Co., the fictional duck-themed home goods business of the
[DuckShop](../duckshop/README.md) project, after a decade of growth: 40 storefronts in 10 regions,
marketplace partners, carriers, warehouses, retail stores, suppliers, payment gateways, ad
networks, messaging, affiliates, support tools, ledgers, wholesale desks, returns portals and a
product catalogue. Every name and value is invented.

Only the generator, its tests and `checksum.txt` are committed. The generated project is written
to a directory you choose.

## Usage

```bash
python benchmarks/duckshop-10k/generate.py --out /path/to/duckshop-10k   # write the project
python benchmarks/duckshop-10k/generate.py --verify /path/to/duckshop-10k  # check a written copy
python benchmarks/duckshop-10k/generate.py --check            # check an in-memory build
cd /path/to/duckshop-10k && sqb compile                        # no warehouse connection needed
```

`--profile smoke` writes a small project of about 1,100 models with the same templates, for fast
iteration. `checksum.txt` records the full profile only.

## Determinism and versioning

The generator uses no randomness, clocks or environment: the same generator version always writes
byte-identical files. `checksum.txt` holds the generator version, the file count and the SHA-256 of
`MANIFEST.sha256`, a sorted list of the SHA-256 of every generated file.

When a change alters any generated file, bump `GENERATOR_VERSION` in `duckshop10k/__init__.py` and
run `python benchmarks/duckshop-10k/generate.py --update-checksum`.

## Shape

| | Count |
|---|---|
| Models | 10,282 |
| Staging, intermediate, marts and snapshots | 6,149 (59.8%), 1,961 (19.1%), 2,162 (21.0%), 10 |
| Sources | 2,466 table sources and one expression source |
| Unit tests and scenarios | 288 and 2 |
| Dependency depth | 11 at most; 168 models at depth 7 or more |

Most models read one to four upstreams; a few dozen wide marts, unions and scorecards read ten or
more. Staging deduplicates change logs with a change-log macro, types three platform layouts
(legacy columns with local times, typed columns with offset times, and JSON documents with epoch
times) and flattens arrays into child models. The intermediate layer converts every instance to a
shared shape (UTC times, major-unit amounts, mapped statuses), enriches headers with child totals,
unions instances by region and company, converts currencies with `ASOF JOIN`, sessionises
clickstream events in microbatches and builds customer identity, value and segment models and a
budget variance chain. Marts give every instance, team and region its reports, and publish facts and
dimensions with enforced contracts.

The models that use `HASH`, `TIMESTAMP_LTZ` or `CURRENT_TIMESTAMP()` are tagged `known_divergence`,
because their results depend on the engine or the session.

## Checks

- `benchmarks/duckshop-10k/tests/` checks the shape, the determinism of two builds, the recorded
  checksum and the generated custom Rule's tests, offline.
- `tests/e2e/.../compile/test_duckshop_10k_compile.py` generates the project, verifies it against
  `checksum.txt` and compiles it cold with the checkout's build, requiring zero errors and zero
  warnings.

CI runs both in the 10,000-model cell of the dense compile job, under its 4 GiB memory limit, after
the dense guards have finished, so the DuckShop compile never shares the limit with them.
