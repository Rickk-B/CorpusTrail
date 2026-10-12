# Checkpoint 2 final project-management UX refinement

Development branch: `development/v0.1.0a3-read-only-local-ui`.
Version: `0.1.0a3.dev0`. Accepted removal baseline:
`6d6b07a04422496153531bbac142c8c5e5d17a7d`.
The baseline received user-reported native macOS functional acceptance. This
follow-up still requires native macOS visual acceptance; it is not Checkpoint 3.

## Changes and preserved boundaries

- The active project card has an explicit Active project label and Close Project
  action. The redundant page-level close button is removed. Close uses the existing
  protected endpoint, returns to Projects and refreshes available actions.
- Inactive cards do not offer Close Project. Closing makes no removal request and
  releases only this launcher's lease. Other processes can continue to block Trash.
- The confirmation is a compact panel with aligned project/location information,
  safely wrapping paths, a full-width labelled input and consistently spaced
  explanations/actions. Exact confirmation, cancellation and retention limits remain.
- Only packaged presentation assets, tests and documentation changed. Application,
  HTTP, scientific and native Trash/lease services, schema, migrations, configuration,
  dependencies and version are unchanged. No external service calls are introduced.

## Local Linux verification

- Project/UI/process focused suite: 71 tests, successful, one opt-in native Mac skip.
- Complete suite with optional ML: 417 tests, successful, one native Mac skip.
- Actual packaged JavaScript/actual loopback API harness: active-only close, updated
  actions, project preservation, confirmation identity/location, wrong-input gating,
  exact-input enablement and cancellation without native movement.
- Real independent-process test: closing one controller leaves another launcher
  alive and holding its lease; removal is refused until that launcher exits.
- Clean core wheel installation outside checkout: 71 focused tests, successful,
  one native Mac skip; CLI reports the unchanged development version.
- Wheel/sdist builds, Ruff, JavaScript syntax, bounded changed-file privacy checks
  and whitespace checks passed. No backend or dependency diff.

## Hosted and acceptance boundary

The existing Python 3.11–3.13 Linux full/core/ML/wheel/sdist acceptance and macOS/
Windows real-process lifecycle jobs remain required. Native Mac disposable Trash
tests are enabled only in the Mac job with the optional extra. The development
artifact is gated on all acceptance jobs and records its exact source/build SHA.
Actual hosted results and downloadable wheel checksum belong to the completion
report/Actions receipt, not an assumed result here. Native layout, screen-reader
and MacBook visual acceptance are not inferred from this DOM contract harness.

No main merge, tag, release, PyPI publication or later checkpoint is authorized.
