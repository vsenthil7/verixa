# ADR-0005 — Mermaid for sequence / architecture diagrams (vs draw.io / PlantUML)

- **Status:** Accepted
- **Date:** 2026-05-11
- **Phase:** 0 (hackathon prototype) — durable through Phase 1+
- **Decision owner:** v_sen
- **Affects:** All sequence diagrams, flowcharts, and most architecture diagrams in `docs/`

## Context

Verixa's docs/ pack contains 20+ documents that include diagrams: sequence diagrams for use cases (UC-01 through UC-10), system flowcharts in the architecture spec, state diagrams for protocol phases, ER-style diagrams in the data model spec, and decision trees in the risk router doc.

Diagram-authoring tools differ along several axes:

| Tool | Text-source? | Renders in GitHub? | Renders in Hugging Face Space markdown? | Visual quality | Workflow friction |
|---|---|---|---|---|---|
| **draw.io / diagrams.net** | No (XML) | No (need PNG export) | No (need PNG export) | High | High (export step every edit) |
| **PlantUML** | Yes | No (needs server or proxy) | No | Medium-high | Medium |
| **Mermaid** | Yes | **Yes natively** since 2022 | **Yes** (markdown passthrough) | Medium | Very low |
| **D2** | Yes | No (needs server) | No | High | Medium |
| **Excalidraw** | No (JSON) | No (needs export) | No | High (sketchy aesthetic) | Medium |
| **ASCII art** | Yes | Yes | Yes | Low | Low |

For Verixa specifically, the constraints are:

- Diagrams must **render in the README on GitHub** so a hackathon judge or a reader of the repo sees them inline
- Diagrams must **render in the Hugging Face Space landing page** (which is markdown with YAML frontmatter)
- Diagrams must be **version-controlled as text** so `git diff` shows changes meaningfully — binary PNGs in PRs are a known anti-pattern
- Authoring friction must be **near-zero** so we actually keep diagrams up to date as the architecture evolves

## Decision

**Use Mermaid for every diagram in `docs/` and `README.md`** unless a diagram is fundamentally not expressible in Mermaid syntax (in which case file an exception and use an SVG checked into `docs/<folder>/assets/`).

Concrete usage:

- Sequence diagrams → `mermaid sequenceDiagram` (`docs/05_use_cases_and_user_stories/USE_CASES.md` UC-01 through UC-10 use this)
- High-level system flow → `mermaid flowchart LR` (USE_CASES.md "High-level system flow")
- State diagrams → `mermaid stateDiagram-v2` (planned for triad protocol)
- ER diagrams → `mermaid erDiagram` (planned for data model)
- Class diagrams → `mermaid classDiagram` (planned for Protocol-typed interfaces in architecture spec)

Mermaid blocks live inline in the markdown file using the standard fenced-code-block form:

````
```mermaid
sequenceDiagram
    actor Agent
    Agent->>Gateway: POST /govern
    ...
```
````

## Consequences

### Positive

- **Zero-friction edits.** Update the markdown, push, GitHub renders it. No export step, no separate diagram repo, no image hosting.
- **Native render on every surface Verixa cares about**: GitHub README + GitHub markdown anywhere in the repo + Hugging Face Space landing page + most modern markdown viewers (VSCode preview, Typora, Obsidian, GitLab).
- **Diff-friendly.** A diagram change shows up as a meaningful text diff in the PR. Reviewers can see exactly which arrow moved or which actor was renamed.
- **No external dependencies for readers.** A judge cloning the repo and running `grep -r "mermaid" docs/` finds every diagram source instantly.
- **Mermaid 10.x supports `par`-blocks** (parallel execution segments in sequence diagrams) which Verixa needs for the commit-then-reveal triad protocol diagram in UC-02.

### Negative

- **Visual quality is mid-tier.** Mermaid's auto-layout is not as polished as a hand-drawn draw.io diagram. For Phase 0 (hackathon judging timeline), this is fine — diagram correctness matters more than diagram beauty. Phase 1 may invest in custom SVG for top-3 marketing diagrams.
- **Limited customisation.** Custom colours, fonts, and shapes are constrained by Mermaid's theme system. Accepted.
- **One-page-PDF export is awkward.** Mermaid renders to inline SVG in browsers; getting it into a print-quality PDF requires extra tooling. Not a current need — judges read on screen.
- **GitHub-rendered Mermaid has a per-block size limit** (lines and cells). Very large diagrams may need to be split into multiple blocks or moved to SVG. None of Verixa's current diagrams hit this limit.

### Mitigations

- For any diagram that genuinely doesn't fit Mermaid (e.g. floor-plan style infrastructure diagrams in the Phase-1 deployment topology doc), file an SVG into `docs/<folder>/assets/<slug>.svg` and reference it via standard markdown image syntax. Source the SVG from draw.io with the editable XML embedded so future edits don't lose context.
- Re-evaluate this decision at the start of Phase 1 if customer-facing marketing material (data sheets, white papers) needs higher-fidelity diagrams. The decision for *engineering docs* is durable; the decision for *marketing* may be different.

## Alternatives considered

1. **draw.io / diagrams.net with PNG exports** — rejected. Every diagram edit requires an export step; PNG diffs are unreadable; image storage clutters the repo. Mermaid's rendered output is good enough for engineering docs.
2. **PlantUML** — rejected. Doesn't render natively on GitHub; needs either a server-side proxy (e.g. `plantuml.com`) which adds a runtime network dependency for readers, or a CI step to generate SVGs which adds workflow friction.
3. **ASCII art** — used selectively for very small diagrams (e.g. one-line directory trees) but rejected as the default. Doesn't scale past ~5 boxes and arrows.
4. **D2** — interesting newer tool; rejected because GitHub doesn't render it natively and the ecosystem is small.
5. **Excalidraw embedded as SVG** — considered for hand-drawn-aesthetic diagrams. Filed as Phase 1 candidate for the marketing-facing one-pager.

## Verification

- All sequence diagrams in `docs/05_use_cases_and_user_stories/USE_CASES.md` render on GitHub — visually confirmed at https://github.com/v-sen/verixa/blob/main/docs/05_use_cases_and_user_stories/USE_CASES.md
- The Hugging Face Space landing page at https://huggingface.co/spaces/vsenthil7/verixa-control-plane renders the same Mermaid blocks (when included)
- `git log --stat docs/05_use_cases_and_user_stories/USE_CASES.md` shows clean text diffs across CP-25 → CP-25.1 → CP-26 → CP-27

## Related

- Phase 1 candidate ADR: marketing-facing diagram pipeline (data sheets, customer one-pagers)
- Companion: no specific BR / UC — this is a doc-tooling decision, indirectly serves every BR via the diagrams in their use-case docs
