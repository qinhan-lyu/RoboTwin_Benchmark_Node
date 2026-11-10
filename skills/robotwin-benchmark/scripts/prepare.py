"""Start hook for robotwin-benchmark: RoboTwin data root and profile weights.

All user settings live in one optional file shared by every benchmark Skill,
~/.PhyAgentOS/benchmarks.yaml. Only the robotwin section is read here:

    robotwin:
      root: /data/RoboTwin                  # RoboTwin 2.0 checkout with assets (needed once)
      weights_dir: /big/disk/paos-weights   # optional, default ~/.PhyAgentOS/weights/robotwin-benchmark
      hf_endpoint: https://hf-mirror.com    # optional, default: base_url in the weight lock
      weights:                              # optional: reuse an existing local copy of a weight
        g05-robotwin20-1006: /models/lerobot_g05_robotwin20

The profile files only use the fixed paths below. This hook links them to the
configured places, verifies the weights against their lock and downloads what
is missing. It then runs `<node> --prepare` on the uv-based Nodes: the Node
ships its prebuilt environment (robotwin_benchmark >= 1.2.2), so this only
verifies it against the lock before PAOS starts the startup_timeout_s clock.
Standard library + PyYAML, Python 3.8+.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PAOS_HOME = Path.home() / ".PhyAgentOS"
CONFIG = PAOS_HOME / "benchmarks.yaml"
SECTION = "robotwin"
DATA_LINK = PAOS_HOME / "data" / "robotwin"
WEIGHTS_LINK = PAOS_HOME / "weights" / "robotwin-benchmark"
STAMPS = PAOS_HOME / "cache" / "weights-verified"
# uv-based Nodes; `--prepare` verifies the bundled environment (builds it for unbundled Nodes).
PREPARE_NODES = ("robotwin_benchmark",)
CONFIG_KEYS = {"root", "weights_dir", "hf_endpoint", "weights"}
ROOT_REQUIRED = (
    "envs",
    "env_cfg/task_config/_embodiment_config.yml",
    "env_cfg/task_config/_camera_config.yml",
    "assets/embodiments",
    "assets/objects",
    "description/task_instruction",
)


class Fail(Exception):
    pass


def log(message):
    print("[robotwin-benchmark] " + message, file=sys.stderr, flush=True)


def load_yaml(path):
    try:
        import yaml
    except ImportError:
        raise Fail("PyYAML is missing from the PAOS Python (" + sys.executable + ")")
    with open(path, encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def user_config():
    if not CONFIG.is_file():
        return {}
    data = load_yaml(CONFIG) or {}
    if not isinstance(data, dict):
        raise Fail(str(CONFIG) + " must be a mapping")
    section = data.get(SECTION) or {}
    if not isinstance(section, dict):
        raise Fail(str(CONFIG) + ": " + SECTION + " must be a mapping")
    unknown = sorted(set(section) - CONFIG_KEYS)
    if unknown:
        raise Fail(str(CONFIG) + ": unknown keys under " + SECTION + ": " + ", ".join(unknown)
                   + " (allowed: " + ", ".join(sorted(CONFIG_KEYS)) + ")")
    return section


def expand(value):
    return Path(os.path.expandvars(os.path.expanduser(str(value)))).absolute()


def link(fixed, target, key):
    """Point the fixed path at target. Only symlinks are ever replaced."""
    if fixed.is_symlink():
        if Path(os.readlink(str(fixed))) == target:
            return
        fixed.unlink()
    elif fixed.exists():
        raise Fail(str(fixed) + " is a real directory, so " + SECTION + "." + key + " in "
                   + str(CONFIG) + " cannot be linked there. Move it away or drop the setting.")
    fixed.parent.mkdir(parents=True, exist_ok=True)
    fixed.symlink_to(target)


def prepare_root(cfg):
    if cfg.get("root"):
        target = expand(cfg["root"])
        if not target.is_dir():
            raise Fail(SECTION + ".root in " + str(CONFIG) + " does not exist: " + str(target))
        link(DATA_LINK, target, "root")
    elif not DATA_LINK.exists():
        raise Fail("RoboTwin data root is not configured. Add to " + str(CONFIG) + ":\n\n"
                   "  " + SECTION + ":\n    root: /path/to/RoboTwin\n\n"
                   "(a RoboTwin 2.0 checkout with assets/embodiments, assets/objects, envs, ...)")
    missing = [rel for rel in ROOT_REQUIRED if not (DATA_LINK / rel).exists()]
    if missing:
        raise Fail("RoboTwin root " + str(DATA_LINK.resolve()) + " is incomplete, missing: "
                   + ", ".join(missing))
    log("RoboTwin root: " + str(DATA_LINK.resolve()))


def find_weight(skill_root, profile):
    entries = load_yaml(skill_root / "weights.yaml") or []
    matches = [entry for entry in entries if entry.get("profile") == profile]
    if not matches:
        log("profile " + profile + " declares no weights")
        return None
    if len(matches) > 1:
        raise Fail("weights.yaml has more than one entry for profile " + profile)
    return matches[0]


def sha256(path):
    digest = hashlib.sha256()
    with open(str(path), "rb") as stream:
        for block in iter(lambda: stream.read(1 << 22), b""):
            digest.update(block)
    return digest.hexdigest()


def check_https(url):
    if urllib.parse.urlsplit(url).scheme != "https":
        raise Fail("weight downloads must use https: " + url)


def download(url, target, size):
    """Fetch url into target with Range resume. No token is sent; URLs are not logged."""
    partial = target.with_name(target.name + ".partial")
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, 6):
        have = partial.stat().st_size if partial.exists() else 0
        if have > size:
            partial.unlink()
            have = 0
        if have == size:
            break
        request = urllib.request.Request(url, headers={"User-Agent": "paos-robotwin-benchmark"})
        if have:
            request.add_header("Range", "bytes=" + str(have) + "-")
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                if have and response.status != 206:
                    have = 0
                mode = "ab" if have else "wb"
                with open(str(partial), mode) as stream:
                    last = time.monotonic()
                    while True:
                        block = response.read(1 << 22)
                        if not block:
                            break
                        stream.write(block)
                        have += len(block)
                        if time.monotonic() - last > 30:
                            log("  %s: %.1f / %.1f GB" % (target.name, have / 1e9, size / 1e9))
                            last = time.monotonic()
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "code", None) or type(error).__name__
            log("  %s: attempt %d failed (%s), retrying" % (target.name, attempt, reason))
            time.sleep(min(30, 2 ** attempt))
    if not partial.exists() or partial.stat().st_size != size:
        raise Fail("download of " + target.name + " did not complete")
    return partial


def prepare_weights(cfg, skill_root, entry):
    weight_id = entry["weight_id"]
    lock = json.loads((skill_root / entry["lock"]).read_text(encoding="utf-8"))
    if lock.get("resource_id") != weight_id:
        raise Fail("lock " + entry["lock"] + " does not belong to " + weight_id)
    if cfg.get("weights_dir"):
        weights_dir = expand(cfg["weights_dir"])
        weights_dir.mkdir(parents=True, exist_ok=True)
        link(WEIGHTS_LINK, weights_dir, "weights_dir")
    WEIGHTS_LINK.mkdir(parents=True, exist_ok=True)
    local = (cfg.get("weights") or {}).get(weight_id)
    target = WEIGHTS_LINK / entry["path"]
    if local:
        local = expand(local)
        if not local.is_dir():
            raise Fail(SECTION + ".weights." + weight_id + " in " + str(CONFIG)
                       + " does not exist: " + str(local))
        link(target, local, "weights." + weight_id)

    files = lock["files"]
    stamp = STAMPS / (weight_id + ".json")
    expected = {item["path"]: [item["size_bytes"], item["sha256"]] for item in files}
    try:
        stamped = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        stamped = {}

    def current():
        state = {}
        for item in files:
            path = target / item["path"]
            if path.is_file():
                info = path.stat()
                state[item["path"]] = [info.st_size, info.st_mtime_ns]
        return state

    state = current()
    if stamped.get("files") == expected and stamped.get("state") == state and len(state) == len(files):
        log("weights " + weight_id + ": verified, " + str(target.resolve()))
        return

    base = (cfg.get("hf_endpoint") or lock.get("base_url") or "https://huggingface.co").rstrip("/")
    check_https(base)
    for item in files:
        path = target / item["path"]
        if path.is_file() and path.stat().st_size == item["size_bytes"]:
            if sha256(path) == item["sha256"]:
                continue
            raise Fail("weights " + weight_id + ": " + item["path"] + " in " + str(target.resolve())
                       + " does not match its lock (sha256). Remove it to download again.")
        if local:
            raise Fail("weights " + weight_id + ": " + item["path"] + " is missing or has the wrong "
                       "size in the local copy " + str(local))
        log("weights " + weight_id + ": downloading " + item["path"]
            + " (%.2f GB) from %s" % (item["size_bytes"] / 1e9, urllib.parse.urlsplit(base).netloc))
        url = "/".join([base, lock["repo_id"], "resolve", lock["revision"],
                        urllib.parse.quote(item["path"])])
        partial = download(url, path, item["size_bytes"])
        if sha256(partial) != item["sha256"]:
            partial.unlink()
            raise Fail("weights " + weight_id + ": " + item["path"] + " failed sha256 after download")
        os.replace(str(partial), str(path))

    STAMPS.mkdir(parents=True, exist_ok=True)
    tmp = stamp.with_suffix(".tmp")
    tmp.write_text(json.dumps({"files": expected, "state": current()}), encoding="utf-8")
    os.replace(str(tmp), str(stamp))
    log("weights " + weight_id + ": verified, " + str(target.resolve()))


def prepare_nodes(skill_name, profile):
    """Verify Node environments now; PAOS links the profile bin dir before this hook."""
    bin_dir = PAOS_HOME / "forge_runtime" / "environments" / skill_name / profile / "current" / "bin"
    for node in PREPARE_NODES:
        launcher = bin_dir / node
        if not launcher.exists():
            log("skip %s environment prepare: %s not found" % (node, launcher))
            continue
        log("checking %s environment (bundled in the Node, no download)" % node)
        started = time.time()
        if subprocess.call([str(launcher), "--prepare"]) != 0:
            raise Fail("%s --prepare failed" % node)
        log("%s environment ready (%.0fs)" % (node, time.time() - started))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill-root", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    args = parser.parse_args()
    try:
        cfg = user_config()
        prepare_root(cfg)
        entry = find_weight(args.skill_root.resolve(), args.profile)
        if entry is not None:
            prepare_weights(cfg, args.skill_root.resolve(), entry)
        prepare_nodes(os.environ.get("PAOS_SKILL_NAME", "robotwin-benchmark"), args.profile)
    except Fail as error:
        log("ERROR: " + str(error))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
