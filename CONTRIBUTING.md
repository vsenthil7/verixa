# Contributing to Verixa

Thanks for your interest in contributing. Verixa is currently a Phase 0
hackathon prototype targeting the AMD Developer Cloud / lablab.ai
**AI Agents & Agentic Workflows** track, so contribution scope is narrow
right now. This document explains how to engage usefully.

---

## Phase 0 scope (now)

Until the hackathon submission lands, the project is in single-author
mode. External contributions are welcome as:

- **Bug reports** — open a GitHub issue with reproduction steps
- **Security findings** — see [`SECURITY.md`](SECURITY.md)
- **Documentation fixes** — small PRs (typos, broken links, factual errors) welcome
- **Discussion** — open a GitHub Discussion if you want to chat about
  architecture, regulatory mapping, or roadmap

We are NOT accepting feature PRs in Phase 0 because the codebase is
moving fast, has 100% line+branch coverage targets, and every commit
goes through a strict discipline (see [`docs/15_build_plan/BUILD_PLAN.md`](docs/15_build_plan/BUILD_PLAN.md)).

---

## Phase 1+ (after the hackathon)

Once Phase 1 starts, this section expands to cover:

- Branch model (feature branches off `main` with PRs)
- Required reviews (≥ 1 maintainer approval before merge)
- CI gates (all green: `python-tests`, `typescript`, `playwright`)
- Coverage requirements (100% line + branch on changed code)
- Negative-test requirement (every new BR row in
  [`docs/17_traceability_matrix/`](docs/17_traceability_matrix/) must have
  a documented negative-test category)

---

## Development environment

The repository is a monorepo with two language stacks:

- **Python 3.12** managed via Poetry
- **Node 20+** managed via pnpm + Turborepo

Setup:

```bash
git clone https://github.com/v-sen/verixa.git
cd verixa

# Python side
poetry install
poetry run pytest -m 'not integration'

# Node side
pnpm install
pnpm test
```

For full instructions including Docker Compose dev stack (Phase 1+),
see [`docs/15_build_plan/BUILD_PLAN.md`](docs/15_build_plan/BUILD_PLAN.md).

---

## Commit message conventions

We use a **strict label-prefixed format** because the git log is treated
as an audit artefact:

```
[LABEL] CP-N -- short subject

Detailed body explaining the change, broken into clear sentences with
specific anchor file paths, test names, and rationale. Long is fine.
```

Labels:

- `[FEAT]` — net-new functionality
- `[FIX]` — bug fix
- `[CHORE]` — non-functional change (deps, config)
- `[DOCS]` — documentation only
- `[SESSION]` — session bookends (rare)
- `[REFACTOR]` — structural changes without behaviour change

CP-N is the checkpoint number from the build plan.

---

## Code style

- **Python:** Ruff + Black. Line length 88. Type annotations required for all
  new public functions.
- **TypeScript:** ESLint + Prettier. Strict mode on. No `any` without comment.
- **Tests:** must be added in the same commit as the code change.

---

## Code of Conduct

Participation in this project is governed by the
[Contributor Covenant](CODE_OF_CONDUCT.md). Be respectful, assume good
faith, and engage constructively.

---

## Licence

By contributing, you agree that your contributions will be licensed under
the project's MIT licence (see [`LICENSE`](LICENSE)).
