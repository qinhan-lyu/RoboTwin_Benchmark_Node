#!/usr/bin/env bash
# Self-contained Forge Node launcher (one Node = one environment).
#
# Layout (next to this file):  runtime/{uv,pyproject.toml,uv.lock,.python-version,node.env,verify.py,
#                                       patch_site.py,wheels/}
#                              runtime/env/{python,venv}   prebuilt environment (bundled builds)
#                              app/            Node source
# Bundled build: runtime/env was built from runtime/uv.lock at packaging time (patches applied,
# symlinks relative, so it runs from wherever PAOS unpacked the Node). Nothing is downloaded.
# Unbundled build: `uv sync --frozen` against runtime/uv.lock into a private venv keyed by the
# lock digest, then apply the upstream site-packages patches.
# Either way the installed set is verified against uv.lock before the Node starts. Nothing comes
# from the host Python. `<node> --prepare` only prepares/verifies the environment.
set -euo pipefail

here="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
runtime="$here/runtime"
app="$here/app"
# shellcheck source=/dev/null
source "$runtime/node.env"            # NODE_NAME, NODE_ENTRY, NODE_REQUIRE_CUDA, NODE_CORE_IMPORTS

# Isolate from whatever the caller's shell had active.
unset VIRTUAL_ENV CONDA_PREFIX PYTHONHOME PYTHONPATH PYTHONSTARTUP ROBOTWIN_ENV_SITE ROBOTWIN_PYTHON
export PYTHONNOUSERSITE=1
export NODE_CORE_IMPORTS

log() { printf '[%s] %s\n' "$NODE_NAME" "$*" >&2; }

if [[ -x "$runtime/env/venv/bin/python" ]]; then
  env_root="$runtime/env"
  ensure_env() {
    "$env_root/venv/bin/python" -I "$runtime/verify.py" "$runtime/uv.lock" "$NODE_REQUIRE_CUDA" >&2
  }
else
  paos_home="${HOME:?HOME must be set}/.PhyAgentOS"
  lock_digest="$(cat "$runtime/uv.lock" "$runtime/patch_site.py" 2>/dev/null | sha256sum | cut -c1-16)"
  env_root="$paos_home/cache/nodes/$NODE_NAME/$lock_digest"
  mkdir -p "$env_root"
  export UV_PROJECT_ENVIRONMENT="$env_root/venv"
  export UV_PYTHON_INSTALL_DIR="$env_root/python"
  export UV_PYTHON_PREFERENCE=only-managed
  export UV_NO_CONFIG=1
  # Download cache only (not an environment); keep it on the same disk as the venv.
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$paos_home/cache/uv}"
  ensure_env() {
    exec 9>"$env_root/.lock"
    flock 9
    if [[ ! -f "$env_root/.verified" ]]; then
      log "preparing private environment $env_root (first start downloads packages)"
    fi
    "$runtime/uv" sync --project "$runtime" --frozen --no-dev --no-install-project \
        --python-preference only-managed --quiet >&2
    if [[ -f "$runtime/patch_site.py" ]]; then
      "$env_root/venv/bin/python" -I "$runtime/patch_site.py" >&2
    fi
    "$env_root/venv/bin/python" -I "$runtime/verify.py" "$runtime/uv.lock" "$NODE_REQUIRE_CUDA" >&2
    touch "$env_root/.verified"
    flock -u 9
  }
fi

ensure_env
[[ "${1:-}" == "--prepare" ]] && { log "environment ready ($env_root)"; exit 0; }

export PYTHONPATH="$app"
exec "$env_root/venv/bin/python" -s "$app/$NODE_ENTRY" "$@"
