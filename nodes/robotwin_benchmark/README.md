# robotwin_benchmark Node runtime

This directory defines the Node's own environment. Per the one-env-per-Node rule, the Node
does not use a host Python or a shared venv.

| File | Purpose |
| --- | --- |
| `pyproject.toml` | Direct dependencies plus constraints frozen from a known-good RoboTwin host env (py3.12, torch 2.5.1+cu124, sapien 3.0.0b1, mplib 0.2.1). |
| `uv.lock` | Exact resolution. The launcher runs `uv sync --frozen` against it. |
| `.python-version` | `3.12` (uv-managed CPython). |
| `patch_site.py` | Re-applies the two site-packages patches from RoboTwin's `scripts/_install.sh`: sapien `urdf_loader.py` utf-8 open, and the mplib `planner.py` collision check. Idempotent. It writes through a temp file, so files hard-linked into the uv cache are not modified. |
| `wheels/` | `nvidia_curobo-0.7.8-cp312-cp312-linux_x86_64.whl` (not in git, see below). |

`scripts/build_node_bundles.py` assembles this directory, `nodes/common/launcher.sh` and
`verify.py`, the uv binary and the Node source into
`dist/nodes/robotwin_benchmark-<ver>-linux-x86_64.tar.gz`. With `--bundle-env` (all releases
since 1.2.2) it also builds the environment from `uv.lock` into `runtime/env/{python,venv}`
(about 7.8 GB unpacked, 3.9 GB in the archive). The env is patched, verified and made
relocatable (relative symlinks, no `home` in `pyvenv.cfg`) at packaging time.

## First start

```
robotwin_benchmark --prepare   # verify the env (bundled) or build + patch + verify it, then exit
```

Bundled Node: the launcher uses `runtime/env` in place and downloads nothing.
Unbundled Node (dev builds without `--bundle-env`): the env is built in
`~/.PhyAgentOS/cache/nodes/robotwin_benchmark/<digest>/venv`. Here `<digest>` is derived from
`uv.lock` + `patch_site.py`. That first start downloads about 5 GB.

## curobo wheel

curobo has no PyPI wheel. Build it once against the locked torch (2.5.1+cu124, CUDA 12.4):

```
git clone https://github.com/NVlabs/curobo && cd curobo && git checkout v0.7.8   # d64c4b0
export SETUPTOOLS_SCM_PRETEND_VERSION=0.7.8   # tag-less checkout otherwise yields 0.0.post1.dev1
export CUDA_HOME=/usr/local/cuda-12.4 PATH=/usr/local/cuda-12.4/bin:$PATH
export TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0+PTX" MAX_JOBS=16
<py3.12 env with torch==2.5.1+cu124>/bin/python -m pip wheel . --no-build-isolation --no-deps -w <out>
```

Expected sha256 for the wheel built this way:
`f24238f30b1cacba173a6a2d5fa39d098e769a76e82f48387ed53d13fb43a88e`. `uv.lock` pins this hash,
and `build_node_bundles.py` refuses a wheel that does not match it. If you rebuild and get a
different hash, put the new wheel in `wheels/` and re-run `uv lock`.

Arch list covers Turing through Hopper. Blackwell (sm_120) gets the PTX fallback.

## Updating dependencies

1. Edit `pyproject.toml`.
2. Run `UV_DEFAULT_INDEX=<mirror> uv lock --project nodes/robotwin_benchmark`.
3. If the patched upstream files changed, update `patch_site.py`. Its digest is part of the env key, so existing envs are rebuilt.
