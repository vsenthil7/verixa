# `docs/22_session_status/` — session continuity for Verixa

This folder is the single source of truth for **session-resume context** and **CP-grain progress + planning**. It exists because the Verixa build runs across many discrete sessions on Windows host (different conversation contexts, different working hours, occasional network drops) and a CP grain that's much finer than `BUILD_PLAN.md`'s capability grain. Three files; each has one job.

## Files

| File | Purpose | Update cadence |
|---|---|---|
| `SESSION_EXPORT_2026-05-12.md` | End-of-session state snapshot: HEAD commit, working-tree state, live metrics, established design patterns, anti-patterns, session-discipline rules. | Rewritten at the end of every long session; one file per session-end date. |
| `CP_PROGRESS_LEDGER.md` | Chronological append-only ledger of every CP shipped from CP-01 to current HEAD. One row per CP with commit hash, status, category, one-line subject. | Append-only. One row added per commit. |
| `PHASE_ROADMAP_FUTURE.md` | Forward-looking CP-grain planning ledger from next-up CP through Phase 6. Aligns with `docs/15_build_plan/BUILD_PLAN.md`'s capability/phase grain. | Rewritten when a phase gate moves; rows MOVE to `CP_PROGRESS_LEDGER.md` when CPs land. |

## How they interact

```
PHASE_ROADMAP_FUTURE.md            CP_PROGRESS_LEDGER.md           SESSION_EXPORT_2026-05-{date}.md
       (plans)                          (shipped)                        (snapshot)
          |                                ^                                  ^
          |    CP commits + pushes ────────|                                  |
          |                                                                    |
          +─────────── at session end, snapshot of state ─────────────────────+
```

When a planned CP lands, **move its row** from `PHASE_ROADMAP_FUTURE.md` to `CP_PROGRESS_LEDGER.md`. Don't dual-track — keep the planning file free of committed work and the ledger file free of speculation.

## How to use this folder at session resume

1. Open `SESSION_EXPORT_2026-05-12.md` (or latest dated session export).
2. Run its **session-resume verification block** to confirm the working tree matches the snapshot.
3. Open `CP_PROGRESS_LEDGER.md` and scan the most recent table rows; verify `git log -1` matches the bottom row's commit hash.
4. Open `PHASE_ROADMAP_FUTURE.md`; find the next 🔜 next CP; verify it's still blocker-free (gates listed in the row).
5. Start the next CP per the established workflow (announce session-start, task-start, etc.).

## Companion documents (referenced from these files)

- `docs/15_build_plan/BUILD_PLAN.md` — phase-grain capability roadmap (Phase 0 → Phase 6); this is the canonical product-level plan.
- `docs/15_build_plan/SDK_RELEASE_RUNBOOK.md` — operational protocol for the CP-59 release pipeline; one-time setup steps + dry-run + tag-push.
- `docs/17_traceability_matrix/TRACEABILITY_MATRIX.md` — BR ↔ UC ↔ Test ↔ Code cross-references.
- `docs/16_testing_and_qa/NEGATIVE_TEST_PLAN.md` — adversarial-coverage tracker.
- `docs/07_system_architecture/adr/` — Architecture Decision Records (ADR-0001 → ADR-0010 as of CP-31).

## Folder slot

`22_` was chosen because `docs/` runs 00–20 today (per `CP-26` canonical renumbering); `21_` is reserved for a release-management doc that may slot in between. Inside this folder no further numbering is used because the three files are sufficiently self-describing; if a phase-gated breakdown is ever needed, slot it as `PHASE_{N}_CP_BREAKDOWN.md` per the convention in `PHASE_ROADMAP_FUTURE.md` "How to use this roadmap".
