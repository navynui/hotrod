# syntax=docker/dockerfile:1
#
# Strata-HotRod on this PC - Tesla P100 (sm_60) + GTX 1060 (sm_61).
#
# This is a patched copy of the fork's own Dockerfile, with exactly two changes:
#   1. CUDA 12.9 base image. CUDA 13 dropped Pascal (sm_60), so the fork's
#      nvidia/cuda:13.0.0 base cannot build for this machine.
#   2. -DSTRATA_EXPERIMENTAL_SM60=ON, and the engine is installed in
#      engine-cuda12/ (the folder setup.py uses for the experimental CUDA 12
#      engine). The engine is the only thing this image runs; the server is
#      started directly from serve/server.py (see docker-compose.yaml), so the
#      installer's download/pack paths never run.
#
# Build context is this folder (~/dev/hotrod): the fork's source is copied from
# Strata-HotRod/ (see .dockerignore). The upstream 0.1.45 checkout is reference
# only and is not part of the image.
#
#   docker compose build
#   docker compose up -d
#
# Upstream fork: https://github.com/sangharshadhyeta/Strata-HotRod (MIT).
# Pinned here at main, 9d3b6c30 (2026-11-20). Base: upstream Strata 0.1.45.

ARG CUDA_IMAGE=nvidia/cuda:12.9.1-devel-ubuntu24.04
FROM ${CUDA_IMAGE}

# STRATA_EXECV is the fork's entrypoint setting; the server is PID 1 here.
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 LANG=C.UTF-8 \
    STRATA_EXPERIMENTAL_SM60=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential ca-certificates curl git libatomic1 libgomp1 \
        python3 python3-pip python3-venv unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/strata
COPY Strata-HotRod/ ./

# 60;61 only: the P100 and the 1060. Wider = slower build and larger image.
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
vision = "gpu" if os.environ.get("BUILD_VISION", "0") == "1" else "none"

# Pascal: CUDA 12 + STRATA_EXPERIMENTAL_SM60. The arch list is deliberately
# narrow (the two cards on this PC).
setup.cmake_build(setup.ROOT, setup.ROOT / "build", "strata",
    ["-DSTRATA_ENABLE_CUDA=ON", "-DSTRATA_Q6K_EXPERTS=ON", "-DSTRATA_MMQ_KQUANTS=ON",
     "-DSTRATA_BUILD_TESTS=OFF", "-DSTRATA_EXPERIMENTAL_SM60=ON",
     f"-DCMAKE_CUDA_ARCHITECTURES={arch}", f"-DCMAKE_CUDA_COMPILER={nvcc}",
     f"-DSTRATA_GGML_DIR={llama}"], None, "build-strata.bat")
if vision != "none":
    setup.cmake_build(setup.ROOT / "tools" / "vision", setup.ROOT / "build-vision", "strata-vision",
        [f"-DLLAMA_DIR={llama}", "-DSTRATA_VISION_CUDA=ON", "-DSTRATA_PORTABLE=OFF",
         f"-DCMAKE_CUDA_ARCHITECTURES={arch}", f"-DCMAKE_CUDA_COMPILER={nvcc}"], None, "build-vision.bat")

# engine-cuda12/ is the folder the 0.1.45 setup uses for a CUDA 12 engine.
eng = setup.ROOT / "engine-cuda12"
eng.mkdir(exist_ok=True)
shutil.copy2(setup.ROOT / "build" / setup.EXE, eng / setup.EXE)
if (setup.ROOT / "build" / setup.KQ_LIB).exists():
    shutil.copy2(setup.ROOT / "build" / setup.KQ_LIB, eng / setup.KQ_LIB)
if vision != "none":
    shutil.copy2(setup.ROOT / "build-vision" / "bin" / setup.VEXE, eng / setup.VEXE)
bindir = pathlib.Path(nvcc).parent
meta = {"source": "docker build", "version": setup.source_version(),
        "archs": [int(a.split("-")[0]) for a in arch.split(";") if a.split("-")[0].isdigit()],
        "vision": vision, "toolkit": 12,
        "cuda_dirs": [str(d) for d in (bindir, bindir / "x64", bindir.parent / "lib64") if d.is_dir()],
        "src": setup.source_hash(setup.ENGINE_SOURCES),
        "vision_src": setup.source_hash(setup.VISION_SOURCES) if vision != "none" else None}
(eng / "BUILD.json").write_text(json.dumps(meta, indent=1))
PYEOF

# the cmake trees are build-time only
RUN rm -rf build build-vision

VOLUME ["/data"]
EXPOSE 8080

# /health is answered before the API key gate. The first start page-locks
# ~19.5 GiB of experts and loads the model; allow it time.
HEALTHCHECK --interval=30s --timeout=5s --start-period=1800s --retries=3 \
  CMD curl -fs "http://127.0.0.1:${PORT:-8080}/health" || exit 1

# The installer's entrypoint starts setup.py, which would try to install or
# download a model. This image already has the engine and the model is mounted
# read-only, so the server is started directly instead (no setup pass).
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
