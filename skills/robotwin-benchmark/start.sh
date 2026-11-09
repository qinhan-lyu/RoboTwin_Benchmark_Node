#!/usr/bin/env bash
# PAOS start hook: make the host data and the profile weights available at the fixed
# paths the profile files use. Each Node launcher builds its own environment.
set -euo pipefail
bundle_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python="${PAOS_HOOK_PYTHON:-python3}"
exec "$python" -I -B "$bundle_root/scripts/prepare.py" \
  --skill-root "$bundle_root" --profile "${PAOS_SKILL_PROFILE:?PAOS_SKILL_PROFILE is set by PAOS}"
