---
name: robotwin-benchmark
description: Run RoboTwin 2.0 evaluation. Profile vla-g05-1006 runs the G05 VLA (lerobot 0.7, weight g05-robotwin20-1006) inside the Skill.
---

# RoboTwin evaluation

Profile `vla-g05-1006` starts everything it needs: the Gateway, the RoboTwin benchmark Node and the
lerobot 0.7 G05 policy Node. The policy loads the model before its endpoint registers, so a ready
runtime already holds the model in GPU memory. There is no external model server.

1. Start the profile and require runtime status `ready`. The first start builds each Node's
   environment and verifies the weights (several minutes); later starts are fast.
2. Start `robotwin.policy` as a Session with no arguments. It holds the resident policy service.
3. Query `robotwin.benchmark.describe`. Use its actual suite, task table and limits. Do not infer
   task IDs from names or invent dataset coverage.
4. Start `robotwin.benchmark.run` as a Session. Default smoke: task_ids=[0], init_state_ids=[0],
   num_runs=1, seed=0. Ask for the evaluation scope when the user did not give one.
5. Poll the run Session, consume terminal events, then fetch its result. Report completed_episodes,
   total_episodes, success_rate, failure_summary and result_file. Check the benchmark-owned result
   JSON for protocol-specific metrics and seed records.
6. To stop a batch, stop the run Session and wait for its terminal result; the current episode
   finishes first.
7. Another batch may start after the previous one is terminal, with the same `robotwin.policy`
   Session. When finished, stop `robotwin.policy`, then stop the Skill and check that the Gateway
   and Node processes are gone.

If start fails in the start hook, report its message: it names the missing setting in
`~/.PhyAgentOS/benchmarks.yaml` (RoboTwin root) or the weight file that failed verification.

Treat missing weights, assets, runtime errors and partial/stopped batches as such. Unit tests or a
stub policy do not establish model accuracy. A debug subset score must never be described as a full
official benchmark score.
