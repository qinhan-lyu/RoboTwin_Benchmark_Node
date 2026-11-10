# robotwin-benchmark 0.2.2 candidate

Not accepted for publication until the real-model and PAOS lifecycle tests pass.

Gateway: http://127.0.0.1:19132. Tools: `robotwin.benchmark.describe`, `robotwin.benchmark.run`,
`robotwin.policy`.

| Profile | Paradigm | Policy | Weight | Nodes |
| --- | --- | --- | --- | --- |
| `vla-g05-1006` | VLA | G05 (lerobot 0.7, System1) | `g05-robotwin20-1006` | gateway 1.1.0, robotwin_benchmark 1.2.2, lerobot_infer 1.1.1 |

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
missing files (HTTPS, resumable, no token). `robotwin_benchmark` ships its Python environment
inside the Node archive (since 1.2.2, archive ~3.9 GB), so nothing is downloaded on first start;
the hook runs `robotwin_benchmark --prepare` to verify that environment against its lock before
PAOS starts the `startup_timeout_s` (900 s) clock.
See HOST_RUNTIME.md for the RoboTwin sources and assets.

0.2.2: robotwin_benchmark 1.2.2 bundles its prebuilt environment (torch 2.5.1+cu124, SAPIEN, cuRobo, open3d). A clean machine no longer downloads ~6 GB of packages on first start. Node code is unchanged from 1.2.1.

0.2.1: robotwin_benchmark 1.2.1 checks every policy action against the environment action space (14D for qpos on aloha-agilex, 16D for ee) before `env.step`. A mismatch fails the whole run with `action_dim_mismatch` instead of scoring each episode as 0. `describe` now reports `action_dim`.
