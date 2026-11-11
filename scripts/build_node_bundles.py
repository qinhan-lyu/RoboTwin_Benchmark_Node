#!/usr/bin/env python3
"""Build the self-contained robotwin_benchmark Node archive.

The Node is a ``directory_tar_gz`` with its OWN environment definition:

    robotwin_benchmark/robotwin_benchmark   launcher (nodes/common/launcher.sh)
    robotwin_benchmark/runtime/             uv, pyproject.toml, uv.lock, .python-version,
                                            verify.py, patch_site.py, node.env, wheels/
    robotwin_benchmark/app/                 Node source

On start the launcher runs ``uv sync --frozen`` against ``runtime/uv.lock`` into a
private venv, applies the RoboTwin upstream site-packages patches (patch_site.py),
verifies the env, then execs the Node. No host Python, no shared env.

The RoboTwin upstream checkout (assets, task code) is NOT vendored; it comes from the
``robotwin_root`` field of the benchmark config.

nvidia-curobo has no PyPI wheel. Build it once (see nodes/robotwin_benchmark/README.md)
and pass it with --curobo-wheel; its sha256 must match runtime/uv.lock.

    python3 scripts/build_node_bundles.py --curobo-wheel <whl> --out dist/nodes
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = "1.2.1"
NODE = "robotwin_benchmark"
ENTRY = "main.py"
CORE_IMPORTS = ("numpy torch sapien mplib toppra open3d scipy transforms3d trimesh cv2 "
                "curobo warp dora forge_msgs forge_tool pyarrow yaml")
APP_FILES = ["main.py", "config.py", "result.py"]
APP_PACKAGES = ["_core", "adapters", "bench_tool"]
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "tests", ".pytest_cache")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def locked_wheel_hash(lock: Path, filename: str) -> str:
    m = re.search(r'filename = "' + re.escape(filename) + r'", hash = "sha256:([0-9a-f]{64})"',
                  lock.read_text())
    if not m:
        raise SystemExit(f"{filename} not found in {lock}")
    return m.group(1)


def stage_node(curobo: Path, uv: Path, root: Path) -> Path:
    top = root / NODE
    runtime, app = top / "runtime", top / "app"
    node_dir = REPO / "nodes" / NODE
    runtime.mkdir(parents=True)
    for name in ("pyproject.toml", "uv.lock", ".python-version", "patch_site.py"):
        shutil.copy2(node_dir / name, runtime / name)
    want = locked_wheel_hash(node_dir / "uv.lock", curobo.name)
    have = sha256(curobo)
    if have != want:
        raise SystemExit(f"{curobo} sha256 {have} != uv.lock {want}")
    (runtime / "wheels").mkdir()
    shutil.copy2(curobo, runtime / "wheels" / curobo.name)
    shutil.copy2(REPO / "nodes" / "common" / "verify.py", runtime / "verify.py")
    shutil.copy2(uv, runtime / "uv")
    (runtime / "node.env").write_text(
        f'NODE_NAME={NODE}\nNODE_ENTRY={ENTRY}\nNODE_REQUIRE_CUDA=1\nNODE_CORE_IMPORTS="{CORE_IMPORTS}"\n')
    app.mkdir()
    for name in APP_FILES:
        shutil.copy2(REPO / name, app / name)
    for name in APP_PACKAGES:
        shutil.copytree(REPO / name, app / name, ignore=IGNORE)
    launcher = top / NODE
    shutil.copy2(REPO / "nodes" / "common" / "launcher.sh", launcher)
    for path in (launcher, runtime / "uv"):
        path.chmod(0o755)
    return top


def pack(top: Path, archive: Path) -> str:
    def norm(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        info.mode = 0o755 if (info.isdir() or info.mode & 0o111) else 0o644
        return info

    archive.parent.mkdir(parents=True, exist_ok=True)
    with open(archive, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted([top, *top.rglob("*")]):
            tar.add(path, arcname=path.relative_to(top.parent).as_posix(), recursive=False, filter=norm)
    return sha256(archive)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curobo-wheel", type=Path, required=True)
    parser.add_argument("--uv", type=Path, default=Path(shutil.which("uv") or "uv"))
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "nodes")
    parser.add_argument("--stage-only", type=Path, help="write the unpacked Node here instead of packing")
    args = parser.parse_args()
    if args.stage_only:
        if args.stage_only.exists():
            raise SystemExit(f"{args.stage_only} exists")
        top = stage_node(args.curobo_wheel.resolve(), args.uv.resolve(), args.stage_only)
        print(top)
        return 0
    with tempfile.TemporaryDirectory(prefix="robotwin-nodes-") as tmp:
        top = stage_node(args.curobo_wheel.resolve(), args.uv.resolve(), Path(tmp))
        artifact_id = f"{NODE}-{VERSION}-linux-x86_64"
        archive = args.out / f"{artifact_id}.tar.gz"
        digest = pack(top, archive)
    manifest = {NODE: {"artifact_id": artifact_id, "version": VERSION, "artifact_type": "directory_tar_gz",
                       "entrypoint": NODE, "sha256": digest, "file": archive.name,
                       "size": archive.stat().st_size}}
    (args.out / "nodes-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"{archive}  {digest}  {archive.stat().st_size / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
