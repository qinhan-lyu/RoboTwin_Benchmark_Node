"""Apply RoboTwin's upstream site-packages patches inside this Node's private venv.

Same edits as RoboTwin scripts/_install.sh (commit 96c1feab):
  * sapien/wrapper/urdf_loader.py: open URDF/SRDF with encoding="utf-8"
  * mplib/planner.py: screw planning no longer aborts on `collide`
Idempotent. Each file is rewritten through a temp file + os.replace, so the uv
cache (venv files may be hard links into it) is never modified in place.
Fails if a target is neither in the original nor the patched form.
"""
from __future__ import annotations

import os
import re
import sys
import sysconfig
import tempfile
from pathlib import Path

SITE = Path(sysconfig.get_paths()["purelib"])
PATCHES = [
    ("sapien/wrapper/urdf_loader.py",
     re.compile(r'("r")(\))( as)'), r'\1, encoding="utf-8") as',
     'open(urdf_file, "r", encoding="utf-8")'),
    ("mplib/planner.py",
     re.compile(r"(if np\.linalg\.norm\(delta_twist\) < 1e-4 )(or collide )(or not within_joint_limit:)"),
     r"\1\3",
     "if np.linalg.norm(delta_twist) < 1e-4 or not within_joint_limit:"),
]


def main() -> int:
    for rel, pattern, repl, marker in PATCHES:
        path = SITE / rel
        text = path.read_text(encoding="utf-8")
        new, count = pattern.subn(repl, text)
        if count == 0:
            if marker not in text:
                print(f"patch_site: {rel} matches neither original nor patched form", file=sys.stderr)
                return 1
            continue
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(new)
        os.chmod(tmp, path.stat().st_mode & 0o777)
        os.replace(tmp, path)
        for cached in path.parent.glob(f"__pycache__/{path.stem}.*.pyc"):
            cached.unlink()
        print(f"patch_site: patched {rel} ({count} edits)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
