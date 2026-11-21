# Strata-HotRod on this PC — measured results

Date: 2026-11-21. Same machine for every row: Tesla P100-16GB (sm_60) only, i7-9700K, 31.2 GiB RAM,
WD Blue SN5000 NVMe. Model: **Qwen3.8-Flash-Next Coder IQ1_M**, the existing pack/MTP layer, mounted
read-only. Every engine was built with CUDA 12.9 for `60;61` and `-DSTRATA_EXPERIMENTAL_SM60=ON`.

## Why a control was needed

HotRod's headline numbers (50-70 tok/s) are for an **RTX 3060 12 GB running IQ3_S (78 GB)**, where a
large share of experts is streamed from the SSD. This box runs **IQ1_M (~25 GB of experts)**, which is
already resident in RAM + VRAM, so the SSD is idle. A first quick run of HotRod looked 20-30% faster
than the recorded v0.2.13.1 numbers, but that compared **different prompts and different warm-up
states**. Two same-day controls were added:

| Control | What it is | Port |
|---|---|---|
| `strata:upstream-0.1.45-pascal` | plain upstream 0.1.45, HotRod's own base, identical build | 8092 |
| `strata:v0.2.13.1-pascal` (existing image) | the pinned install's engine 0.1.59.1, started directly, read-only | 8093 |

The pinned `strata` container was **not started or modified**. Its image was run as a throwaway
service with its own `/data` and read-only model shares.

## Method

`bench.py`, the cases from `~/dev/strata/build-revision.md`:

- PREFILL short (~283 prompt tokens, `max_tokens 1`), DECODE 128, PREFILL long (~655), DECODE 256.
- temperature 0, non-streaming; 2 warm-up requests per case, then 6 measured; median of runs 2+.
- Prefill prompts get a **unique prefix per run** (`cache_n 0`), so the prompt is really read.
- Decode keeps a stable prompt (the prefix is cached, as in the recorded baseline).
- Speeds are the engine's own `timings`; draft acceptance is reported in the raw JSON files.

Run-to-run spread is ±5-10%: expert placement changes rounding, so the generated text (and the MTP
draft acceptance, and therefore tok/s) differs slightly between runs. Read the table as "within noise"
unless a difference is consistent across the four cases.

## Decode / short prefill

| Arm | prefill ~283 | decode 128 | prefill ~655 | decode 256 |
|---|---:|---:|---:|---:|
| upstream v0.1.45 (control) | 143.3 | 46.2 | 211.4 | 41.9 |
| **v0.2.13.1 (current install)** | **134.7** | **39.5** | **202.0** | **44.4** |
| HotRod, default (no stand-ins) | 134.9 | 42.3 | 199.0 | 42.7 |
| HotRod, stand-ins ranks 6-9 @ 1 logit (+ default 5% mask) | 144.9 | 40.3 | 209.2 | 44.8 |
| HotRod, stand-ins all ranks, unlimited | 157.1 | 40.9 | 231.5 | 38.2 |

tok/s. `raw: bench-*.json`.

## Long-prompt prefill

Unique prefixes, `max_tokens 1`, 3 runs each:

| Arm | ~3.6K prompt | ~6.7K prompt |
|---|---:|---:|
| **v0.2.13.1 (current)** | **326.5** | **349.3** |
| HotRod default | 323.7 | 347.4 |
| HotRod stand-ins 6-9 | 325.4 | — |
| HotRod all-rank stand-ins | 346.5 | 361.0 |

tok/s. The all-rank arm's short-prompt prefill gain (+15% at 655 tokens) shrinks to **+3.3% at 6.7K**;
the safe arm is flat.

## What the engine actually did

| | expert cache | VRAM | experts in RAM | decode hit rate | KV in RAM |
|---|---:|---:|---:|---:|---:|
| v0.2.13.1 | 3955 slots | 7.54 GiB | 19.28 GiB | 70% -> 90% | full KV in VRAM |
| upstream 0.1.45 | 4106 slots | 7.82 GiB | 19.00 GiB | 72% -> 92% | full KV in VRAM |
| HotRod default | **4696 slots** | **8.94 GiB** | **20.95 GiB** | **79% -> 98.5%** | **1.55 GiB, KV streaming** |

HotRod does what it says: it streams K/V from pinned RAM, frees ~1.4 GiB of VRAM for experts (+870
slots), and its swap scheduler drives the decode hit rate to ~98%. File reads stay at **0 blobs** in
steady state, exactly as in the current install. **The extra hit rate does not buy speed here** — the
remaining ~2% of RAM-computed experts are not the bottleneck; the P100's quantized GEMVs are.

`standin` counters: with ranks 6-9 the mask moved **0 picks** in every measured request, and decode
did not improve. With all ranks, prompt processing speeds up (fewer expert reads), decode gets slower
(fewer draft tokens accepted per step: 15-18 drafts vs 25-38, i.e. the text changed).

## Quality smoke checks

`quality.py`: multi-step maths (checked), a Python function (executed against tests), strict JSON
(parsed), a fact at the start of ~3.6K tokens (quoted back).

| Arm | Result |
|---|---|
| v0.2.13.1 (current) | 4/4 |
| HotRod default | 4/4 |
| HotRod stand-ins 6-9 (+mask) | 4/4 |
| HotRod all ranks | 4/4 |

Four checks cannot show a small quality delta, and the stand-in arms passed them. They also do not
show the failure modes HotRod's own docs report at high budgets (broken words in long prose), because
this workload never needed a stand-in: with 98% of the routed experts already resident, the mechanism
rarely fires.

## Verdict

**On this hardware HotRod is not faster than the pinned v0.2.13.1.** The safe configuration is
performance-neutral (decode 42.3/42.7 vs 39.5/44.4; prefill flat); the only arm with a repeatable gain
is all-rank stand-ins, which buys ~3% long-prompt prefill and costs ~10-14% decode, while changing the
model's output by design. The 50-70 tok/s claim does not transfer to a P100 running a fully resident
IQ1_M.

Other reasons not to switch:

- HotRod is the **0.1.45 line**; the current install is engine 0.1.59.1 (v0.2.13.1), which carries
  Pascal-specific work added after 0.1.45 (`STRATA_Q8_SM60`, `STRATA_MTP_Q8_SM60`, `STRATA_PATTN_SM60`,
  `STRATA_SM60_PERF`, ...). None of those exist in the fork.
- It uses **more RAM** (20.95 GiB pinned + 1.55 GiB KV vs 19.53 GiB) on a 31.2 GiB host; the container
  sat at 23.9 GiB with ~2.4 GiB in zram during the test.
- Adopting it means maintaining a fork of an old release; porting its ~100-file delta onto 0.2.x is a
  real merge.

## Reproduce / clean up

```sh
cd ~/dev/hotrod
docker compose up -d                      # HotRod on 8091
docker compose -f control/docker-compose.yaml up -d          # upstream 0.1.45 on 8092
docker compose -f baseline2131/docker-compose.yaml up -d     # v0.2.13.1 image on 8093

python3 bench.py --base http://127.0.0.1:8091 --out bench.json
python3 quality.py --base http://127.0.0.1:8091 --out quality.json
python3 prefill.py --base http://127.0.0.1:8091 --runs 3

# A/B the stand-ins (recreate after changing):
HOTROD_MARGIN=1 docker compose up -d --force-recreate strata-hotrod
HOTROD_STANDIN_ALL=1 docker compose up -d --force-recreate strata-hotrod

# free the P100 again
docker compose stop strata-hotrod
docker compose -f control/docker-compose.yaml stop
docker compose -f baseline2131/docker-compose.yaml stop
```

Only one of these can hold the P100 at a time. The pinned `strata` install on 8090 is untouched.
