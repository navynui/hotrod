# AGENT.md — Strata-HotRod evaluation workspace

What this folder is for, what was built, and the things that were learned the hard way. Written for
the next agent (or the same one after a context reset). Every number here was measured on **this PC**;
`RESULTS.md` holds the tables and the raw JSON files sit beside it.

## The question this answered

Is `https://github.com/sangharshadhyeta/Strata-HotRod` (fork of upstream Strata, engine 0.1.45) faster
than the pinned **Strata v0.2.13.1** (engine 0.1.59.1) that this machine already runs on port 8090?

**Answer: no, not measurably.** The safe configuration is performance-neutral; the only repeatable gain
(all-rank stand-ins) buys ~3% long-prompt prefill, costs ~10-14% decode, and changes the model's output
by design. See `RESULTS.md` for the numbers and the engine-log evidence.

## Hard rules (do not break these)

1. **Never start, stop, rebuild or write to the pinned `strata` install** in `~/dev/strata`
   (container `strata`, port 8090, image `strata:v0.2.13.1-pascal`). It is the user's working setup.
   Reading its files is fine. Its container is normally Exited; leave it that way.
2. **The model/pack/MTP shares are mounted read-only** here. Never move, re-pack or re-download them.
   `experts.bin` mtime must stay 2026-10-17.
3. **Only one service can hold the P100.** The test services (8091/8092/8093) and the real install all
   want GPU 0. Stop the others before starting one; check `nvidia-smi` first. The GTX 1060 (GPU 1) is
   not used.
4. **Do not expose 8091/8092/8093 beyond loopback.** The test services publish on `127.0.0.1` only;
   8091/8092 have no API key, 8093 uses the throwaway key `bench-key`.
5. **Do not commit the upstream checkouts or runtime state.** `Strata-HotRod/` and `upstream-0.1.45/`
   are public clones (pinned below), and `data/logs`, `data/state` are recreated at start.
6. **Do not touch the user's git repo** `~/dev/strata` (it is clean at `837f7b1`; keep it that way).

## Machine

| Item | Value |
|---|---|
| GPU 0 | Tesla P100-PCIE-16GB, sm_60 (16 GB) |
| GPU 1 | GTX 1060 6GB, sm_61 — deliberately unused |
| CPU / RAM | i7-9700K (8C/8T) / 31.2 GiB |
| Driver | 580.x |
| Disk | WD Blue SN5000 NVMe, 152 GB free at test time |
| P100 link | PCIe 3.0 **x8** (6.5 GB/s reported by the engine) |

**Pascal needs CUDA 12.** CUDA 13 dropped sm_60/sm_70. Every engine build here uses
`nvidia/cuda:12.9.1-devel-ubuntu24.04`, `CUDA_ARCHITECTURES=60;61`, and `-DSTRATA_EXPERIMENTAL_SM60=ON`
(CMake hard-refuses archs < 75 without it).

## Images built here (local only, not in a registry)

| Image | What | Engine | Built from |
|---|---|---|---|
| `strata:hotrod-0.1.45-pascal` | the fork + HotRod changes | 0.1.45 | `Strata-HotRod` @ `9d3b6c30` (2026-11-20) |
| `strata:upstream-0.1.45-pascal` | control: the fork's own base | 0.1.45 | `upstream-0.1.45` @ `477ac13c` (tag `v0.1.45`) |
| `strata:v0.2.13.1-pascal` | **pre-existing**, the user's install | 0.1.59.1 | upstream `v0.2.13.1` (`628f7495`) |

Both test images install the engine in `/opt/strata/engine-cuda12/` with a `BUILD.json`
(`archs: [60,61]`, `toolkit: 12`) and contain no model. `docker images` shows them; there is no
registry to pull from, so `docker compose build` is the way back if they are deleted.

The source checkouts are **not** in this git repo. To recreate:

```sh
git clone https://github.com/sangharshadhyeta/Strata-HotRod.git Strata-HotRod
git -C Strata-HotRod checkout 9d3b6c3051b61a2143bdb8a132a4f60b9f5a16d3
git clone --branch v0.1.45 --depth 1 https://github.com/Niko1221/Strata.git upstream-0.1.45
git -C upstream-0.1.45 rev-parse HEAD      # 477ac13cbe8e582c20484871ce459d20d82df09d
```

`.dockerignore` excludes `.git` of both, runtime data and logs from the build context.

## Layout

```
Dockerfile               patched copy of the fork's Dockerfile (CUDA 12.9, SM60, arch 60;61)
docker-entrypoint.sh     starts serve/server.py; never runs setup.py; unsets empty A/B env vars
docker-compose.yaml      HotRod service, 127.0.0.1:8091
data/config/…json        the run config (identical flags to the 0.2.13.1 install)
data/logs/engine.log     engine log: tiering, cache slots, hit rate, swaps (runtime, not committed)
bench.py                 the four cases from ~/dev/strata/build-revision.md
prefill.py               ~6.7K-token prefill with a unique prefix (no prompt cache)
quality.py               maths / code / JSON / 3.6K-token recall checks
control/                 upstream 0.1.45 control, 127.0.0.1:8092 (own Dockerfile + compose)
baseline2131/            the existing v0.2.13.1 image, read-only 3rd control, 127.0.0.1:8093
RESULTS.md               measured tables, verdict, evidence
AGENT.md                 this file
```

## Build

```sh
cd ~/dev/hotrod
docker compose build                                    # hotrod image
docker compose -f control/docker-compose.yaml build     # upstream control
```

The engine compiles during `docker build` (llama.cpp is downloaded into `third_party/` at build time,
then the CMake/Ninja build runs with `.venv/bin/cmake`). Expect a few minutes on this 8-core host.
The build is **not** reproducible from the repo alone without network: `setup.get_llama_cpp()` fetches
llama.cpp at the commit pinned in the fork's `setup.py`.

The Dockerfile deliberately differs from the fork's own in two ways (documented at the top of the
file): CUDA 12.9 base instead of CUDA 13 (Pascal), and a direct server entrypoint instead of
`setup.py`. Everything else mirrors the user's Strata wrapper.

## Run / stop

```sh
docker compose up -d                                      # HotRod on 8091
docker compose -f control/docker-compose.yaml up -d       # upstream 0.1.45 on 8092
docker compose -f baseline2131/docker-compose.yaml up -d  # v0.2.13.1 image on 8093
curl -s http://127.0.0.1:8091/health
docker compose logs -f
docker compose stop strata-hotrod                         # free the P100
```

Startup with a warm page cache is ~30-40 s: it page-locks ~21 GiB of experts and fills ~4700 VRAM
slots. `restart: "no"` on purpose — a crashed test must not loop.

A/B the stand-ins (recreate after changing; the entrypoint removes empty values so they really are
unset):

```sh
HOTROD_MARGIN=1       docker compose up -d --force-recreate strata-hotrod   # ranks 6-9 @ 1 logit
HOTROD_STANDIN_ALL=1  docker compose up -d --force-recreate strata-hotrod   # every rank, unlimited
HOTROD_RECHECK=1      …                                                     # flip re-check (+quality, ~25% slower)
```

`docker compose config` is a quick sanity check; the bind mounts are nested under `/data` on purpose
(`/data` is writable, `/data/{models,packs,mtp}` are the read-only shares).

## Run config (the same flags as the pinned install)

`data/config/strata-coder-iq1_m.json`:

```
--pack /data/packs/coder-iq1_m
--native /data/models/coder-IQ1_M/…-00001-of-00002.gguf
--ple-gguf /data/models/coder-IQ1_M/…-00002-of-00002.gguf
--expert-profile /opt/strata/data/expert-profile-coder.bin
--expert-cache auto --prefill auto --spec 4 --spec-min-p 0.5
--mtp /data/mtp/rt --max-context 131072 --kv int8 --resident-experts
```

The model is the user's **Qwen3.8-Flash-Next Coder IQ1_M** (25 GB of experts), not the fork's tested
IQ3_S (78 GB). The pack was built on 2026-10-17 by 0.1.45's `tools/iq_pack.py`, so this 0.1.45-line
engine reads it without re-packing. The expert profile is byte-identical to the install's
(`sha256 a5146611…`), so it is not a variable.

## Measurement method (and why it took three runs)

- `bench.py`: PREFILL ~283 (max_tokens 1), DECODE 128, PREFILL ~655, DECODE 256; temperature 0,
  non-streaming; **2 warm-up requests per case**, then 6 measured; median of runs 2+.
- Prefill prompts get a **unique prefix each run** (`cache_n 0`). Without it the server's prompt cache
  serves the prefix and `prompt_per_second` measures only a handful of new tokens — the first run of
  this harness was invalid for that reason.
- Decode keeps a stable prompt (prefix cached) as in `~/dev/strata/build-revision.md`.
- Decode needs warm-up: the swap cache learns across requests. Cold medians understated an engine by
  ~20% (upstream 0.1.45 measured 38.4 cold vs 46.2 steady).
- Run-to-run spread is **±5-10%**: expert placement changes rounding, so the text differs, and the MTP
  draft acceptance (and tok/s) moves with it. Differences inside that band are not a result.
- The recorded numbers in `~/dev/strata/build-revision.md` used different prompts (and therefore
  different draft acceptance); they are **not** directly comparable with these runs. Compare only
  same-day, same-harness arms.

## Results (medians; full tables in RESULTS.md)

| Arm | prefill ~283 | decode 128 | prefill ~655 | decode 256 | prefill ~6.7K |
|---|---:|---:|---:|---:|---:|
| upstream v0.1.45 | 143.3 | 46.2 | 211.4 | 41.9 | — |
| **v0.2.13.1 (current)** | **134.7** | **39.5** | **202.0** | **44.4** | **349.3** |
| HotRod default | 134.9 | 42.3 | 199.0 | 42.7 | 347.4 |
| HotRod stand-ins 6-9 | 144.9 | 40.3 | 209.2 | 44.8 | — |
| HotRod all-rank | 157.1 | 40.9 | 231.5 | 38.2 | 361.0 |

Quality smoke checks (`quality.py`) passed 4/4 on every arm, including the baseline. That is weak
evidence (four checks cannot see a small delta) and it does not exercise HotRod's documented failure
mode at high budgets, because the stand-ins rarely fired here.

## What the engine actually does on this box

| | expert cache | VRAM | experts in RAM | decode hit rate | KV |
|---|---:|---:|---:|---:|---|
| v0.2.13.1 | 3955 slots | 7.54 GiB | 19.28 GiB | 70→90% | full K/V in VRAM |
| upstream 0.1.45 | 4106 slots | 7.82 GiB | 19.00 GiB | 72→92% | full K/V in VRAM |
| HotRod default | **4696 slots** | **8.94 GiB** | **20.95 GiB** | **79→98.5%** | 1.55 GiB RAM, KV streaming |

HotRod's tiering works as advertised (KV streaming frees ~1.4 GiB of VRAM, ~+870 slots, ~98% hit
rate, **0 file reads** in steady state). The speed does not follow: the remaining ~2% RAM-computed
experts are not the bottleneck; the P100's quantized GEMVs are. With ranks 6-9 the stand-in mask moved
**0 picks** in every measured request.

## Pitfalls hit while building this (save the next agent the time)

1. **The fork's Dockerfile is CUDA 13.0** and its default archs are `75;80;86;89;120`. Pascal needs
   the patched copy in this folder; do not "fix" it back to upstream's.
2. **The fork's entrypoint runs `setup.py`**, which would try to install/download a model. This image
   starts `serve/server.py` directly with a config instead. Do not run `docker-entrypoint.sh` from the
   fork tree.
3. **0.1.45 expects `/data/{models,packs,mtp}`**, while the install keeps them in
   `/data/Strata-data/…`. Bridged with nested read-only bind mounts; no files moved.
4. **The engine log path must exist** before the server starts (`/data/logs`); a missing directory
   crashes the 0.2.13.1 server with `FileNotFoundError` at engine start. The entrypoint makes it.
5. **Empty is not unset.** Compose sets `STRATA_ROUTE_RESIDENT=""` even when the knob is unused, and
   an empty `STRATA_ROUTE_RESIDENT` overrides `STRATA_STANDIN`'s margin with 0. The entrypoint unsets
   empty A/B variables for this reason.
6. **Stand-ins are off by default** in this engine (`margin = 0`). `STRATA_ROUTE_RESIDENT=1` turns on
   ranks 6-9 at 1 logit; `STRATA_STANDIN=1` turns on every rank at any distance.
7. **`STRATA_MASK` defaults to `learn` (5%) whenever `STRATA_ROUTE_RESIDENT` is set** — not clearly
   documented, and it is a quality-changing feature. It moved 0 picks here; set `STRATA_MASK=0` if an
   arm must isolate the stand-ins.
8. **The 0.1.45 line has none of the 0.2.x Pascal switches** (`STRATA_Q8_SM60`, `STRATA_MTP_Q8_SM60`,
   `STRATA_PATTN_SM60`, `STRATA_SM60_PERF`, …). Do not copy the strata compose env into this one and
   expect it to do anything.
9. **Running the existing v0.2.13.1 image directly** (the 8093 baseline) needs:
   `/opt/strata/terminal/python/bin/python3`, `serve/server.py`, `--config`, `--api-key`,
   `LD_LIBRARY_PATH=/opt/strata/components/engine/0.1.59.1-…-cuda12`, and cwd
   `/opt/strata/terminal`. It prints a false "built for sm_0, sm_1, sm_6" warning from its arch-string
   parse; the component's `BUILD.json` says `60;61` and it runs fine.
10. **Memory is tight.** The HotRod container sits at **23.9 GiB** with 20.95 GiB pinned + 1.55 GiB KV;
    ~2.4 GiB went to zram during the test. Do not run a second model or a big build at the same time,
    and expect pressure at longer contexts.
11. **`--resident-experts` is supported by 0.1.45** (it is in the config), but HotRod's own docs assume
    its three-tier streaming; on this box everything is RAM/VRAM-resident and the file tier stays idle.
12. `strata:v0.2.13.1-pascal` is ~2.3 GB; the two test images add ~5-6 GB. If disk is needed,
    `docker image rm` them and rebuild from this repo.

## Open questions if work continues

- 32K+ prompt prefill and long-context decode (the fork claims 262K; this test used 131072 and at most
  ~6.7K-token prompts).
- The stand-in arms with `STRATA_FRAGILE_RECHECK=1` (quality guard) — untested here; docs say ~25% cost.
- A quality test with enough samples to see a delta (the four smoke checks do not).
- Using the idle GTX 1060 as a second compute/expert device — untested; the 0.2.13.1 install
  deliberately keeps it out of the split.
- Whether the 0.1.45 control's apparent decode edge (46.2/41.9 vs 39.5/44.4) is real or noise; it is
  one arm and inside the spread.

## Handy commands

```sh
nvidia-smi --query-gpu=index,name,memory.used --format=csv
docker ps -a --format 'table {{.Names}}\t{{.Status}}' | grep strata
docker exec strata-hotrod grep -E 'expert cache|hit rate|resident RAM' /data/logs/engine.log | tail
docker exec strata-hotrod sh -c 'env | grep STRATA'          # which A/B knobs are live
docker inspect strata-hotrod --format '{{range .Mounts}}{{.Source}} -> {{.Destination}} rw={{.RW}}{{println}}{{end}}'
```

## Upstream references

- Fork: `https://github.com/sangharshadhyeta/Strata-HotRod` (MIT), pinned `9d3b6c30`.
- Base: upstream `Niko1221/Strata` tag `v0.1.45`, commit `477ac13c`.
- The fork's own claims and caveats: `Strata-HotRod/docs/HOTROD-DETAILS.md`, `docs/OLDER_GPUS.md`;
  it states it was tested on one machine (RTX 3060 12 GB, 30 GB RAM, IQ3_S) and no other.
