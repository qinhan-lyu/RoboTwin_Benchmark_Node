# RoboTwin host data

The Nodes bring their own Python environments. The host provides only the RoboTwin checkout with its
simulator assets, configured as `robotwin.root` in `~/.PhyAgentOS/benchmarks.yaml`.

## Pinned sources and simulator assets

- RoboTwin: https://github.com/RoboTwin-Platform/RoboTwin, commit
  `96c1feab536306b50c26af200044fcdf126e8904`.
- Simulator assets: https://huggingface.co/datasets/TianxingChen/RoboTwin2.0,
  revision `981c92aa34d8f94d4cff47e0d5bc2f7d4e0af042`.

| Archive | SHA-256 |
| --- | --- |
| embodiments.zip | 6b87d7d55e106d8ff25917e0538eb1e177fc549280e8a742a8cec3cb9f953fc6 |
| objects.zip | 6aa56b3cf1e1064f7c809308144da36b00815f8b137fef2d7e4de856f8becf27 |

Extract both into the RoboTwin `assets/` directory and apply the upstream embodiment path
configuration. The profile uses `demo_clean` with random backgrounds disabled; other scene
configurations may also need `background_texture.zip`.

The start hook checks that the root has `envs/`, `env_cfg/task_config/`, `assets/embodiments`,
`assets/objects` and `description/task_instruction`.

## Weight g05-robotwin20-1006

https://huggingface.co/lerobot/g05_robotwin20 at revision
`b3b9695ce1f6dd08b4fb96486597fd2eb5c63ab0`. The 16 files and their sha256 are in
`locks/g05_robotwin20_1006.lock.json` (11.6 GB in total). The start hook downloads them when no
local copy is configured. The lerobot 0.7 G05 policy reads this lerobot-format checkpoint directly;
it is not the XPolicyLab `OpenGalaxea/G05` checkpoint.

## GPU

Select the GPU with `CUDA_VISIBLE_DEVICES` in the shell that runs `paos skill start`, as for any
other Skill. The G05 policy needs about 12 GB.
