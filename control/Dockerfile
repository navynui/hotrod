# syntax=docker/dockerfile:1
#
# CONTROL IMAGE: plain upstream Strata v0.1.45 (the fork's own base), built the
# same way as ~/dev/hotrod/Dockerfile. It isolates the fork's changes from the
# engine version: same 0.1.45, same CUDA 12.9, same sm_60;61, same model/pack.
#
#   docker compose -f control/docker-compose.yaml build
#   docker compose -f control/docker-compose.yaml up -d      -> 127.0.0.1:8092

ARG CUDA_IMAGE=nvidia/cuda:12.9.1-devel-ubuntu24.04
FROM ${CUDA_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 LANG=C.UTF-8 \
    STRATA_EXPERIMENTAL_SM60=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git libatomic1 libgomp1 \
        python3 python3-pip python3-venv unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/strata
COPY upstream-0.1.45/ ./

ARG CUDA_ARCHITECTURES=60;61
ARG BUILD_VISION=0

RUN python3 -m venv .venv \
    && .venv/bin/pip install --no-cache-dir --upgrade pip \
    && .venv/bin/pip install --no-cache-dir -r requirements.txt \
    && chmod +x setup.sh docker-entrypoint.sh

RUN .venv/bin/python - <<'PYEOF'
import json, os, pathlib, shutil
import setup

llama = setup.get_llama_cpp()
nvcc, _ = setup.find_nvcc()
arch = os.environ.get("CUDA_ARCHITECTURES", "60;61").strip().strip('"').replace(",", ";")

setup.cmake_build(setup.ROOT, setup.ROOT / "build", "strata",
    ["-DSTRATA_ENABLE_CUDA=ON", "-DSTRATA_BUILD_TESTS=OFF", "-DSTRATA_EXPERIMENTAL_SM60=ON",
     f"-DCMAKE_CUDA_ARCHITECTURES={arch}", f"-DCMAKE_CUDA_COMPILER={nvcc}",
     f"-DSTRATA_GGML_DIR={llama}"], None, "build-strata.bat")

eng = setup.ROOT / "engine-cuda12"
eng.mkdir(exist_ok=True)
shutil.copy2(setup.ROOT / "build" / setup.EXE, eng / setup.EXE)
if (setup.ROOT / "build" / setup.KQ_LIB).exists():
    shutil.copy2(setup.ROOT / "build" / setup.KQ_LIB, eng / setup.KQ_LIB)
bindir = pathlib.Path(nvcc).parent
meta = {"source": "docker build", "version": setup.source_version(),
        "archs": [int(a.split("-")[0]) for a in arch.split(";") if a.split("-")[0].isdigit()],
        "vision": "none", "toolkit": 12,
        "cuda_dirs": [str(d) for d in (bindir, bindir / "x64", bindir.parent / "lib64") if d.is_dir()],
        "src": setup.source_hash(setup.ENGINE_SOURCES),
        "vision_src": None}
(eng / "BUILD.json").write_text(json.dumps(meta, indent=1))
PYEOF

RUN rm -rf build

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=1800s --retries=3 \
  CMD curl -fs "http://127.0.0.1:${PORT:-8080}/health" || exit 1

COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
