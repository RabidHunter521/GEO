---
name: seenby-phase
description: How to execute a SeenBy roadmap phase (multi-task feature) end-to-end with the discipline that produced Phase 1's clean run — plan file, per-task implement/review gates, commits per task, memory checkpoints. Trigger on "start phase", "continue phase", "resume the roadmap", "implement the plan", or any multi-task feature spanning >3 files. This process is what guarantees consistent quality regardless of which model is driving.
---

# SeenBy Phase Execution

This is the process that shipped Phase 1 (Share-of-Source) with every task passing independent review. Follow it exactly — the process compensates for model variance; skipping gates reintroduces it.

## 0. Resume protocol (ALWAYS first)

1. Read `MEMORY.md` index → open the roadmap memory (`seenby-geo-endtoend-roadmap.md`). It records which phase/task is active, commit SHAs, and the exact resume point.
2. `git log --oneline -10` + `git status` — confirm the branch matches the memory's record. If they disagree, trust git and update the memory.
3. Read the phase's plan file (path recorded in memory). Never re-derive a plan that already exists.

## 1. Plan before code

- A phase needs a written plan file (via superpowers:writing-plans) with numbered tasks, each independently implementable and verifiable, each with explicit success criteria and files-to-touch.
- Ground every plan claim against the real codebase first (grep the actual hook points, check the real migration head, read the real model). Plans written from memory of the codebase contain stale assumptions.
- Get the plan committed before Task 1.

## 2. Per-task loop (the quality gate)

For EACH task, in order:

1. **Brief**: restate the task's success criteria and files-to-touch from the plan. If reality has drifted from the plan, update the plan file first.
2. **Skills**: invoke `seenby-workflow` for sequencing; `seenby-prompts` if prompts are touched; `seenby-migrations` if schema is touched.
3. **Test-first**: failing test → implementation → green (superpowers:test-driven-development).
4. **Verify**: run `seenby-verify` gates relevant to the diff.
5. **Commit**: one commit per task, conventional message (`feat(scope): ...`), so review and rollback are per-task.
6. **Independent review**: a fresh pass (subagent if budget allows, otherwise re-read the full diff yourself with `git show` AFTER a context break) checking the diff against the plan's success criteria. Findings are fixed or explicitly waived with a reason — never silently ignored.
7. **Ledger**: record task done + commit SHA + any deviations in the progress notes.

## 3. Checkpoint protocol (end of every session or on "pause")

Update the project memory with: tasks done (n/total), commit SHAs, spec deviations, and the EXACT resume point ("resume at Task 4: <one-line description>"). A checkpoint that says "made progress" is useless; a checkpoint that names the next action is the product.

## 4. Phase completion

- All plan tasks committed + reviewed.
- Full `seenby-verify` (all gates, not just per-diff ones).
- Update memory: phase complete, note what is verified vs assumed (e.g. "migration ran locally, NOT yet on Supabase").
- Merge via superpowers:finishing-a-development-branch. Prod deploy only via `seenby-release`.

## Anti-patterns that have cost us before

- Starting to code before reading the memory/plan → duplicate or conflicting work.
- Batching 3 tasks into one commit → review can't isolate a regression.
- "Tests pass" without pasting output → they didn't run.
- Claiming done while prod migration is unverified → say "verified locally, Supabase pending" every time.
