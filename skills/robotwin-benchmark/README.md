# robotwin-benchmark 0.2.0 candidate

Not accepted for publication until the real-model and PAOS lifecycle tests pass.

Gateway: http://127.0.0.1:19132. Tools: `robotwin.benchmark.describe`, `robotwin.benchmark.run`,
`robotwin.policy`.

| Profile | Paradigm | Policy | Weight | Nodes |
| --- | --- | --- | --- | --- |
| `vla-g05-1006` | VLA | G05 (lerobot 0.7, System1) | `g05-robotwin20-1006` | gateway 1.1.0, robotwin_benchmark 1.2.0, lerobot_infer 1.1.1 |

Profile names are `<paradigm>-<policy>-<weight date MMDD>`. `weights.yaml` lists each profile's
weight; `locks/` pins the exact files (size and sha256).

## User configuration

Everything goes in one file, `~/.PhyAgentOS/benchmarks.yaml`. No environment variables.

```yaml
robotwin:
  root: /path/to/RoboTwin             # required once: RoboTwin 2.0 checkout with assets
  # weights_dir: /big/disk/weights    # optional, default ~/.PhyAgentOS/weights/robotwin-benchmark
  # hf_endpoint: https://hf-mirror.com
  # weights:                          # optional: reuse a local copy instead of downloading
  #   g05-robotwin20-1006: /models/lerobot_g05_robotwin20
```

Then `paos skill start robotwin-benchmark --profile vla-g05-1006`.

The start hook (`start.sh` -> `scripts/prepare.py`) links the RoboTwin root to
`~/.PhyAgentOS/data/robotwin`, then verifies the profile weight against its lock and downloads
missing files (HTTPS, resumable, no token). Each Node launcher builds its own uv environment from
its lock on first start. For `robotwin_benchmark` (~6 GB of packages) the hook does this
itself with `robotwin_benchmark --prepare`, because PAOS starts the `startup_timeout_s` (900 s)
clock only after the hook, and a cold download on a clean machine takes longer than that.
Later starts reuse `~/.PhyAgentOS/cache/nodes/robotwin_benchmark/<lock digest>` and skip it.
See HOST_RUNTIME.md for the RoboTwin sources and assets.
