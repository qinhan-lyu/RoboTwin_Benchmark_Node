# PAOS Ubuntu 20.04 integration, 2026-09-17

Published candidate scope: `robotwin_benchmark` 1.1.4, `robotwin_policy` 1.1.1, and `robotwin-benchmark` 0.1.0. Resource registration is handled separately by the owner.

## Validation

RoboTwin source tests: **123 passed**. Real SAPIEN/cuRobo simulation plus a hold-action protocol server completed two 400-step Sessions (800 observation/action requests), with matching scene seed/instruction, separate result ledgers and clean stop.

**Real G05 model acceptance is pending.** The exact gated g05-robotwin20 checkpoint has not been obtained. A separate matching G05 model-server environment, its weights and auxiliary assets, and an official-versus-Forge evaluation are still required. The Skill owns its websocket client only; it does not manage the external server. The hold-action test must not be reported as G05 accuracy.

Both frozen Nodes were built on Ubuntu 20.04 x86_64 with Python 3.12. Their scanned ELF dependencies require at most GLIBC 2.28 (target OS: 2.31). The Skill passed repeat installation, inspection, ready/Query, Session, result retrieval and stop checks in an isolated PAOS test environment. Production Registry installation remains a post-registration step.

## Runtime and sources

This repository holds the `robotwin_benchmark` Node only. The `robotwin-benchmark` Skill
(profiles, Node locks, start hook) and the G05 policy code were moved out on 2026-11-11 and
are versioned and packaged separately. The Node owns its runtime under
`nodes/robotwin_benchmark/`, see [its README](../nodes/robotwin_benchmark/README.md).
Model and simulator assets are external.

The student's original repository history is retained. The Python project's package version
and the independently versioned binary artifact are separate identifiers.

## Rebuild commands

Current Node releases (1.2.2 and later) bundle the prebuilt env. On Ubuntu 20.04 x86_64 with
uv, Python >= 3.9 for the build script, and a visible CUDA GPU for env verification:

```bash
python3 scripts/build_node_bundles.py --curobo-wheel <nvidia_curobo-0.7.8 whl> \
    --bundle-env --out dist/nodes
```

The 2026-09-17 candidate (`robotwin_benchmark` 1.1.4) was built with
`scripts/build_release.py --kind benchmark --version 1.1.4`. A fresh Node build needs new
digest verification and relevant runtime acceptance; binary reproducibility is not assumed.

Hashes, sizes, build source hashes and dependency receipts are in [the publication manifest](../releases/paos-ubuntu20-20260917.json). No model weights or simulator datasets are redistributed here.
