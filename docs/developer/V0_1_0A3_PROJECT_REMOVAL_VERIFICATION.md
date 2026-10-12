# Checkpoint 2 safe project removal — local verification

Development branch `development/v0.1.0a3-read-only-local-ui`, version `0.1.0a3.dev0`.
Accepted base `7b1af848196efce5335523e2e8195a2ab59a3347` remains preserved.
This is not a release, main merge or authorization for Checkpoint 3.

## Implemented boundary

- Shared/exclusive OS lifecycle leases outside project directories, covering local
  launchers, review server, complete CLI operations and the packaged tutorial.
- One-time exact-folder confirmation and controller-owned targets; exclusive
  revalidation before native movement. No arbitrary paths or permanent-delete fallback.
- Optional macOS Cocoa/core 12.2.2 bindings, lazy import, returned-destination and
  project/database/tree verification; failed/uncertain outcomes do not become success.
- Active/busy refusal, explicit close, cancelled/expired/replayed token refusal,
  changed-root/identity/configuration/database/inventory checks, external-file preservation.
- Project chooser refresh and invalidation of handles/tokens/receipts after success.
- No scientific service, migration/schema, authority/review/evidence/identity/model/
  prioritization/Knowledge/ASReview behavior changed. No permanent registry/job framework.

See [architecture](PROJECT_REMOVAL.md) and [Mac installation/acceptance](../user/PROJECT_REMOVAL.md).
The earlier uncommitted temporary checkout was missing; its recorded guard architecture
was reconstructed on the unchanged accepted branch and tested again. Byte-identical
recovery of that uncommitted checkout is not claimed.

## Local Linux / Python 3.12 results

| Check | Result |
|---|---|
| Focused project-management/process/security/native-mock tests | 30 run, successful; 1 native macOS opt-in skip |
| Complete standalone suite with optional ML | 414 run, successful; 1 native macOS skip |
| Clean wheel core | 414 run, successful; 47 skips (46 optional ML + native Mac) |
| Clean wheel optional ML | 414 run, successful; 1 native Mac skip |
| Clean sdist-built wheel core | 414 run, successful; 47 skips |
| Clean sdist-built wheel optional ML | 414 run, successful; 1 native Mac skip |
| Offline core/ML tutorials, installed CLI/scientific examples, uninstall/reinstall/reopen | Passed; no scientific network use |
| Ruff correctness, both packaged JavaScript syntax, whitespace | Passed |
| Changed-file bounded privacy scan | No findings |
| Optional Cocoa/core binary wheels for Apple Silicon CPython 3.11/3.12/3.13 | All six universal2 wheels downloaded/verified available, not installed on Linux |

Independent subprocess tests exercise two launchers, launcher/review/CLI combinations,
shared coexistence, exclusive entry denial, killed-process recovery, initialization
and interrupted **controlled temporary renames**. Those renames are not native Trash.
Local removal outcomes use controlled fake backends; no real researcher project,
historical scientific artifact or real OS Trash was a Linux test target.
Existing five-paper fingerprints, method-blind/review/authority, 20,000-record bounded
pagination and science/provenance regressions are included in the complete suite.

## Native hosted acceptance boundary

The unchanged Linux 3.11–3.13 matrix remains mandatory. Additional macOS 15 and
Windows lifecycle jobs cover all three Python versions. macOS first checks core
without Cocoa, then installs only the optional extra and enables a real disposable
native move/returned-destination verification/restore test. Windows checks real
locks and normal no-Cocoa operation; native Windows removal stays unavailable.
The development artifact is gated on both job groups. The completion report records
actual hosted results, exact source/build SHA, run/artifact name and wheel checksum.
No hosted success or native Mac functionality is inferred from the local mocks.

## Limitations

Same-user/same-machine cooperating versions only; older/external/custom unwrapped
clients and multi-host/filesystem attackers are not covered. Cloud/nonlocal/unknown
storage and unverifiable destination identity fail closed. Tree metadata signature
is not a cryptographic audit of every article byte. OS/user controls Trash retention.
Uncertain results require manual source/Trash inspection, never automatic retry.
Confirmations/uncertainty are process memory, not a durable recovery journal.
Kernel anchor files deliberately persist outside projects after release/uninstall;
never clear them while clients run. Windows/Linux native removal is not implemented.
User-performed native Mac **graphical** acceptance remains necessary, using only a
uniquely named disposable project. No public release or later checkpoint is started.
