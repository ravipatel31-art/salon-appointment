---
description: Fan out pending salon build phases to specialists in parallel, then reconcile.
agent: salon-lead
---

Read `AGENTS.md`, `docs/CONTRACT.md`, and `docs/PHASES.md`.

User filter: `$ARGUMENTS` (empty = all eligible phases).

Tasks:

1. List rows in `PHASES.md` that are `pending` (or matching the filter) and whose dependencies are satisfied (W1: 0a,0b → W2: 1,2,3,5 → W3: 4,6 → W4: 7; 5 may start with mocks in parallel with 1–3).
2. If any selected phase has no owner ready, leave it `pending` and explain.
3. **Single message, parallel fan-out:** spawn every owner once — salon-backend (0a,1,2,4), salon-flutter (0b,5), salon-integration (3,6,7) — with phase ids, file paths above, ownership rules, and required final report `DONE` / `BLOCKED` / `CONTRACT_CHANGE`.
4. On results: apply `CONTRACT_CHANGE` to contract first; update only reconciled rows + wave log; verify enough to flip `done`; re-dispatch any `BLOCKED` with the blocker addressed if you can.
5. Finish with a wave summary table: agent, phases, state, notes.

Do not implement specialist code yourself. Do not commit.
