# Strata-HotRod — isolated test on this PC

A test-only copy of [Strata-HotRod](https://github.com/sangharshadhyeta/Strata-HotRod), built for this
machine's Pascal cards and kept **completely separate** from the pinned Strata v0.2.13.1 install in
`~/dev/strata` (port 8090, image `strata:v0.2.13.1-pascal`). Nothing here writes to the Strata repo,
its container, or its model/pack files.

**Result: HotRod is not measurably faster than the pinned v0.2.13.1 on this machine.** The safe
configuration is performance-neutral; all-rank stand-ins buy ~3% long-prompt prefill at ~10-14%
slower decode and change the output by design. Numbers, method and the engine-log evidence:
[`RESULTS.md`](RESULTS.md); the operating notes and pitfalls: [`AGENT.md`](AGENT.md).

| | Strata (pinned) | Strata-HotRod (this folder) |
|---|---|---|
| Port | 127.0.0.1:8090 | **127.0.0.1:8091** |
| Image | `strata:v0.2.13.1-pascal` | `strata:hotrod-0.1.45-pascal` |
| Engine | 0.1.59.1 (upstream v0.2.13.1) | 0.1.45 + fork changes |
| Control A | — | `strata:upstream-0.1.45-pascal` on 8092 |
| Control B | the pinned image itself, run read-only | `strata-baseline-2131` on 8093 |
| Data | `~/dev/strata/Strata-data` | `./data` (config, logs, state) |
| Model/pack/MTP | owned | mounted **read-only** from the same files |

## Layout

```
Dockerfile              the fork, built with CUDA 12.9 for sm_60;61 (Pascal)
docker-entrypoint.sh    starts serve/server.py; never runs setup.py or downloads
docker-compose.yaml     the 8091 service
AGENT.md                operating notes, hard rules, pitfalls, open questions
RESULTS.md              measured tables, verdict, evidence
data/config/            the run config (paths: /data/{models,packs,mtp})
bench.py                the four cases from ~/dev/strata/build-revision.md
prefill.py              long-prompt prefill (~6.7K tokens, unique prefix)
quality.py              math / code / JSON / long-context smoke checks
control/                plain upstream v0.1.45, same build recipe, port 8092
baseline2131/           the existing v0.2.13.1 image, run read-only, port 8093
bench-*.json            raw benchmark results
quality-*.json          raw quality answers
Strata-HotRod/          the fork checkout (git-ignored; pinned in AGENT.md)
upstream-0.1.45/        the fork's base (git-ignored; pinned in AGENT.md)
```

## Images

Both test images are built **locally** (not published):

| Image | What | Built from |
|---|---|---|
| `strata:hotrod-0.1.45-pascal` | the fork + HotRod changes | fork `9d3b6c30` |
| `strata:upstream-0.1.45-pascal` | control: the fork's base | upstream tag `v0.1.45` |
| `strata:v0.2.13.1-pascal` | pre-existing, the user's install | upstream `v0.2.13.1` |

The two source checkouts are not committed. Re-clone them at the pinned commits (see `AGENT.md`),
then `docker compose build` and `docker compose -f control/docker-compose.yaml build`.


## Use

```sh
docker compose build
docker compose up -d                 # 8091; ~30 s to ready with a warm page cache
curl -s http://127.0.0.1:8091/health
docker compose logs -f
docker compose down
```

The model, pack and MTP layer are bind-mounted read-only:

```
~/dev/strata/Strata-data/Strata-data/{models,packs,mtp} -> /data/{models,packs,mtp} (ro)
```

The existing pack was built by v0.1.45's `tools/iq_pack.py`, so the fork (0.1.45 line) reads it
without re-packing. The engine's own learned files go under `/data` (this folder), never into the
shared shares.

## Measurements

`python3 bench.py` runs PREFILL short (~280 prompt tokens, fresh prefix), DECODE 128, PREFILL long
(~640, fresh prefix), DECODE 256, temperature 0, non-streaming, one warmup and six runs; it reports
the median of runs 2+ (the first decode after a load is 20-40% slower).

`python3 quality.py` asks a multi-step maths question (checked), writes a Python function (executed
against tests), demands strict JSON (parsed), and asks for a fact buried in ~8K tokens of filler
(quoted exactly).

Results are recorded in `RESULTS.md`.
