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

--bundle-env (release builds since 1.2.2) also builds the environment into
``runtime/env/{python,venv}`` from runtime/uv.lock at packaging time, so a clean machine
downloads nothing on first start. The env is made relocatable (relative symlinks, no
``home`` in pyvenv.cfg), patched, verified (needs a visible CUDA GPU) and checked against
the PAOS archive rules (no hard links, no absolute or escaping symlinks, no case
collisions, every file < 2 GiB).

    python3 scripts/build_node_bundles.py --curobo-wheel <whl> --bundle-env --out dist/nodes
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
VERSION = "1.2.2"
MAX_FILE = 2 * 1024 * 1024 * 1024
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


def tree(top: Path) -> list[Path]:
    """Every path under ``top`` (inclusive), not descending into symlinked directories."""
    out = [top]
    for d, dirs, files in os.walk(top):
        out.extend(Path(d) / name for name in dirs + files)
    return sorted(out)


def bundle_env(runtime: Path, uv_cache: Path | None) -> None:
    """Build runtime/env from runtime/uv.lock and make it relocatable."""
    env_dir = runtime / "env"
    env = {k: v for k, v in os.environ.items()
           if k not in ("VIRTUAL_ENV", "CONDA_PREFIX", "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP")}
    env.update(UV_PROJECT_ENVIRONMENT=str(env_dir / "venv"), UV_PYTHON_INSTALL_DIR=str(env_dir / "python"),
               UV_PYTHON_PREFERENCE="only-managed", UV_NO_CONFIG="1", UV_LINK_MODE="copy",
               PYTHONNOUSERSITE="1", NODE_CORE_IMPORTS=CORE_IMPORTS)
    if uv_cache:
        env["UV_CACHE_DIR"] = str(uv_cache)
    subprocess.run([str(runtime / "uv"), "sync", "--project", str(runtime), "--frozen", "--no-dev",
                    "--no-install-project", "--python-preference", "only-managed", "--quiet"],
                   env=env, check=True)
    python = env_dir / "venv" / "bin" / "python"
    subprocess.run([str(python), "-I", "-B", str(runtime / "patch_site.py")], env=env, check=True)
    subprocess.run([str(python), "-I", "-B", str(runtime / "verify.py"), str(runtime / "uv.lock"), "1"],
                   env=env, check=True)
    # uv bookkeeping and the curses terminfo database (case-colliding names, unused here).
    for junk in [env_dir / "python" / ".lock", env_dir / "python" / ".temp",
                 *(env_dir / "python").glob("*/share/terminfo")]:
        if junk.is_dir() and not junk.is_symlink():
            shutil.rmtree(junk)
        elif junk.exists() or junk.is_symlink():
            junk.unlink()
    roots = {str(env_dir), str(env_dir.resolve())}
    for link in tree(env_dir):
        if not link.is_symlink():
            continue
        target = os.readlink(link)
        if not os.path.isabs(target):
            continue
        root = next((r for r in roots if target == r or target.startswith(r + "/")), None)
        if root is None:
            raise SystemExit(f"symlink leaves the env: {link} -> {target}")
        rel = os.path.relpath(Path(env_dir) / os.path.relpath(target, root), link.parent)
        link.unlink()
        link.symlink_to(rel)
    cfg = env_dir / "venv" / "pyvenv.cfg"
    cfg.write_text("".join(line for line in cfg.read_text().splitlines(keepends=True)
                           if not line.startswith("home =")))
    # The relocated env must still start (prefix from the venv, stdlib via the relative link).
    probe = subprocess.run([str(python), "-I", "-B", "-c", "import sys; print(sys.prefix, sys.base_prefix)"],
                           env=env, check=True, capture_output=True, text=True).stdout.split()
    if Path(probe[0]).resolve() != (env_dir / "venv").resolve() or \
            not Path(probe[1]).resolve().is_relative_to((env_dir / "python").resolve()):
        raise SystemExit(f"relocated env resolves wrong prefixes: {probe}")


def check_archive_rules(top: Path) -> int:
    """PAOS directory_tar_gz rules: no hard links, relative contained symlinks, no case collisions."""
    seen: dict[str, str] = {}
    paths = tree(top)
    if len(paths) > 100_000:
        raise SystemExit(f"{len(paths)} archive members > 100000")
    for path in paths:
        rel = path.relative_to(top.parent).as_posix()
        key = unicodedata.normalize("NFC", rel).casefold()
        if key in seen:
            raise SystemExit(f"case collision: {seen[key]} / {rel}")
        seen[key] = rel
        st = path.lstat()
        if path.is_symlink():
            target = os.readlink(path)
            resolved = os.path.normpath(os.path.join(os.path.dirname(rel), target))
            if os.path.isabs(target) or resolved == ".." or resolved.startswith("../"):
                raise SystemExit(f"symlink not relative/contained: {rel} -> {target}")
        elif path.is_file():
            if st.st_nlink > 1:
                raise SystemExit(f"hard-linked file: {rel}")
            if st.st_size >= MAX_FILE:
                raise SystemExit(f"file >= 2 GiB: {rel}")
    return len(paths)


def pack(top: Path, archive: Path) -> str:
    def norm(info: tarfile.TarInfo) -> tarfile.TarInfo:
        info.uid = info.gid = 0
        info.uname = info.gname = ""
        info.mtime = 0
        info.mode = 0o755 if (info.isdir() or info.mode & 0o111) else 0o644
        return info

    archive.parent.mkdir(parents=True, exist_ok=True)
    pigz = shutil.which("pigz")
    with open(archive, "wb") as raw:
        # pigz output does not depend on the thread count; -n drops name and mtime.
        proc = subprocess.Popen([pigz, "-n", "-6"], stdin=subprocess.PIPE, stdout=raw) if pigz else None
        sink = proc.stdin if proc else gzip.GzipFile(fileobj=raw, mode="wb", mtime=0)
        with sink, tarfile.open(fileobj=sink, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            for path in tree(top):
                tar.add(path, arcname=path.relative_to(top.parent).as_posix(), recursive=False, filter=norm)
        if proc and proc.wait() != 0:
            raise SystemExit("pigz failed")
    return sha256(archive)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--curobo-wheel", type=Path, required=True)
    parser.add_argument("--uv", type=Path, default=Path(shutil.which("uv") or "uv"))
    parser.add_argument("--out", type=Path, default=REPO / "dist" / "nodes")
    parser.add_argument("--stage-only", type=Path, help="write the unpacked Node here instead of packing")
    parser.add_argument("--bundle-env", action="store_true",
                        help="build the environment into runtime/env (no download on first start)")
    parser.add_argument("--uv-cache", type=Path, help="uv download cache for --bundle-env")
    parser.add_argument("--tmp", type=Path, help="staging parent (the bundled env needs ~8 GB)")
    args = parser.parse_args()

    def stage(root: Path) -> Path:
        top = stage_node(args.curobo_wheel.resolve(), args.uv.resolve(), root)
        if args.bundle_env:
            bundle_env(top / "runtime", args.uv_cache)
        print(f"staged {top}: {check_archive_rules(top)} members", flush=True)
        return top

    if args.stage_only:
        if args.stage_only.exists():
            raise SystemExit(f"{args.stage_only} exists")
        print(stage(args.stage_only))
        return 0
    with tempfile.TemporaryDirectory(prefix="robotwin-nodes-", dir=args.tmp) as tmp:
        top = stage(Path(tmp))
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
