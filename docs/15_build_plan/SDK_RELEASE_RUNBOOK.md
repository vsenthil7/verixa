# SDK release runbook (CP-85)

End-to-end protocol for releasing `verixa@X.Y.Z` (PyPI) and `@verixa/ts@X.Y.Z` (npm) in lockstep via the CP-59 `release.yml` GitHub Actions workflow.

This runbook accompanies the CP-83 v0.2.0 release-commit (`e61e34f`) and the local-only annotated tag `v0.2.0`. It also documents the workflow_dispatch dry-run validation step that CP-85 makes part of the release process so the first PyPI/npm publish cannot fail on a typo or missing secret.

---

## Release roles + invariants

- **One human approver per release.** GitHub environments `release-pypi` and `release-npm` SHOULD have a required-reviewer rule on them so no SDK push goes out without sign-off.
- **Both SDKs always ship together.** Lockstep is enforced by the single `v*` tag triggering both publish jobs. Don't add a Python-only or TS-only tag pattern; if one ecosystem fails publish, fix forward with a `vX.Y.(Z+1)` patch, never a partial release.
- **Tags point at the version-bump commit, never a follow-up docs commit.** The v0.2.0 tag points at `e61e34f` (CP-83 release commit), not `867e590` (CP-84 root-CHANGELOG follow-up). Future releases follow the same pattern: bump versions in a single commit, tag *that* commit, push docs touch-ups after.
- **Dry-run before tag push, always.** Even after PyPI/npm publishers are configured, the first run on any new tag pattern goes through a `workflow_dispatch` dry-run first.

---

## One-time setup (must be complete before first publish)

### 1. PyPI trusted publisher (OIDC, no API token)

1. Sign in to PyPI account that will own `verixa` (https://pypi.org/manage/account/publishing/).
2. Click **Add a new pending publisher**.
3. Fill in:
   - PyPI Project Name: `verixa`
   - Owner: `vsenthil7`
   - Repository name: `verixa`
   - Workflow filename: `release.yml`
   - Environment name: `release-pypi`
4. Save. After the first publish the pending publisher becomes a permanent one.

No PyPI API token is stored anywhere. The workflow assumes the GitHub `id-token: write` permission and uses OIDC to mint a short-lived PyPI token at publish time.

### 2. npm provenance for the @verixa scope

1. Sign in to npm with an account that has publish rights on the `@verixa` scope.
2. Generate a granular access token at https://www.npmjs.com/settings/[user]/tokens with scope `publish:packages` limited to `@verixa/*` and a 90-day expiry.
3. In GitHub repo settings → Secrets and variables → Actions, add a repository secret named `NPM_TOKEN` with the token value.
4. Set up a GitHub environment named `release-npm` (Settings → Environments). Add the same `NPM_TOKEN` to the environment scope so it's reviewer-gated.
5. Verify the scope is provenance-eligible at https://docs.npmjs.com/generating-provenance-statements — the workflow uses `--provenance` which requires the package to be published from a public CI provider (GitHub Actions OIDC).

When npm rolls out trusted-publisher GA (tracked at https://github.com/npm/cli/issues), replace step 2-3 with the OIDC handshake and remove the `NPM_TOKEN` secret.

---

## Dry-run validation (every release, before tag push)

The `release.yml` workflow has TWO triggers:

```yaml
on:
  push:
    tags: ["v*"]              # tag-push trigger -- publishes for real
  workflow_dispatch:           # manual trigger -- dry-run only
    inputs:
      dry_run:
        description: "Skip publish steps (build + test only)"
        type: boolean
        default: true
```

The three publish jobs (`publish-pypi`, `publish-npm`, `github-release`) are gated on `if: github.event_name == 'push'`, which means **workflow_dispatch ALWAYS skips publish** regardless of the `dry_run` input value. The `dry_run` input is presently UI-descriptive only; it documents intent for the operator but the publish-skip is enforced by the event-name gate. This is by design — it prevents an operator from accidentally toggling `dry_run=false` in the Actions UI and publishing without going through the tag-push handshake.

### Dry-run protocol

1. Navigate to https://github.com/vsenthil7/verixa/actions/workflows/release.yml in a browser.
2. Click **Run workflow** dropdown (top right of the workflow runs list).
3. Leave the `dry_run` input at its default (`true`); leave the branch dropdown on `main`.
4. Click **Run workflow** (green button).
5. Wait for the run to appear in the runs list. Open it.
6. Expected job outcomes:
   - `verify (test + drift + lint)` → green (pytest+ruff+coverage+OpenAPI drift+TS typecheck+vitest)
   - `build verixa (Python)` → green (wheel + sdist produced; uploaded as artifact `python-dist`)
   - `build @verixa/ts (npm)` → green (npm tarball produced; uploaded as artifact `npm-dist`)
   - `publish to PyPI` → **skipped** (event_name != 'push')
   - `publish to npm` → **skipped** (event_name != 'push')
   - `github release` → **skipped** (event_name != 'push')
7. Download both artifacts. Inspect locally:
   - `unzip python-dist` → `verixa-X.Y.Z-py3-none-any.whl` + `verixa-X.Y.Z.tar.gz`
   - `unzip npm-dist` → `verixa-ts-X.Y.Z.tgz`
8. Run `pip install verixa-X.Y.Z-py3-none-any.whl` in a fresh venv and `python -c "import verixa; print(verixa.__version__)"`; expect the new version string.
9. Run `npm install verixa-ts-X.Y.Z.tgz` in a fresh dir and `node -e "console.log(require('@verixa/ts').VERIXA_TS_VERSION)"`; expect the new version string.

If any of steps 6-9 fail, **do NOT push the tag.** Fix forward on `main`, repeat the dry-run from step 1.

### Tag-push protocol (only after a green dry-run)

1. Make sure the local annotated tag points at the intended release commit (the version-bump commit, NOT a follow-up docs commit). For v0.2.0:
   ```
   git rev-list -n 1 v0.2.0
   # expect: e61e34f00d47a5d13811a2c6d4f2285efe6b2dc3 (CP-83)
   ```
2. Push the tag:
   ```
   git push origin v0.2.0
   ```
3. The `release.yml` workflow triggers automatically on the tag push.
4. Job sequence: `verify → build-python + build-npm (parallel) → publish-pypi + publish-npm (parallel) → github-release`.
5. Both publish jobs require manual approval if the `release-pypi` / `release-npm` environments have required reviewers configured (recommended).
6. After all jobs green:
   - https://pypi.org/project/verixa/X.Y.Z/ exists
   - https://www.npmjs.com/package/@verixa/ts/v/X.Y.Z exists with provenance attestation
   - https://github.com/vsenthil7/verixa/releases/tag/vX.Y.Z exists with both artifacts attached

### Rollback

PyPI and npm both forbid republishing the same version. If a release goes out broken:
1. Yank it (PyPI: project page → Manage → Releases → Yank; npm: `npm deprecate @verixa/ts@X.Y.Z "broken, use X.Y.(Z+1)"`).
2. Bump to `X.Y.(Z+1)` on `main`, dry-run, tag, push.
3. Never delete the tag on origin — leave it as a marker.

---

## v0.2.0 release status as of CP-85 (2026-05-12)

| Step | Status | Notes |
|---|---|---|
| Local tag at `e61e34f` | ✅ done | `git tag -l` shows `v0.2.0` |
| Workflow YAML lint | ✅ done | `python -c "import yaml; yaml.safe_load(...)"` → OK; all 6 jobs parse |
| PyPI trusted publisher | ⏳ pending | One-time account setup per "1. PyPI" above |
| npm provenance + NPM_TOKEN | ⏳ pending | One-time scope setup per "2. npm" above |
| Dry-run on main | ⏳ pending | Run AFTER above two steps (this validates the workflow against a real GitHub runner before tag push) |
| Tag push to origin | ⏳ pending | `git push origin v0.2.0` ONLY AFTER green dry-run |

The local tag is intentionally not pushed. Pushing prematurely would trigger the workflow, which would green through verify+build but the publish jobs would fail authentication (PyPI: trusted publisher not configured; npm: NPM_TOKEN secret missing) and leave a half-released v0.2.0 with no PyPI/npm artifacts but a populated GitHub Release. Easier to set up publishers first.

---

## Related ADRs and CPs

- ADR-0001 (persistence) — release pipeline does NOT touch persistence; first v1.0.0 will gate on Postgres + MinIO swap-in.
- CP-54 — OpenAPI drift gate (re-run as part of `verify`).
- CP-58 — Per-package `pyproject.toml` with hatchling backend (used by `python -m build`).
- CP-59 — This workflow file (`release.yml`).
- CP-83 — v0.2.0 version bumps + CHANGELOG entries.
- CP-84 — Root CHANGELOG entry + local v0.2.0 tag.
- CP-85 — This runbook + workflow YAML validation.

---

## Test references

The publish-readiness invariants enforced by 97 pytest tests in:
- `packages/verixa-python/tests/test_pyproject.py` — Python pyproject.toml ↔ `verixa.__version__` ↔ latest CHANGELOG header parity
- `packages/verixa-python/tests/test_sdk_publish_readiness.py` — Python package metadata, py.typed marker, README + LICENSE presence
- `packages/verixa-python/tests/test_verixa_ts_publish_readiness.py` — TS package.json + tsconfig + LICENSE + dist build artifacts

These run as part of the `verify` job in the workflow and will fail the release pipeline if any version drift sneaks back in.
