# Project-use leases and recoverable removal

Approved Checkpoint 2 management extension. Scientific services/schema/authority
contracts stay unchanged; only entry-point lifecycle wrappers and application/UI
services are added. No job framework, database cleanup or persistent registry.

## Guard

`application/project_use.py`: nonblocking `flock` (macOS/Linux) or `LockFileEx`
(Windows). External location anchors protect creation/removal/replacement;
device/inode anchors coordinate path spellings and remain valid across same-volume
moves. OS account/shell folder APIs, not HOME/TEMP/XDG overrides, choose placement.
Private modes/ownership on POSIX, link/reparse/descriptor identity checks fail closed.
Shared nesting is reference-counted; no upgrades/waits/nested exclusives. Partial
acquisitions unwind; explicit close/context/finally paths and crash termination
release kernel leases. Fork resets state; descriptors do not cross exec.

Never unlink a live anchor: that splits coordination. Anchor files contain no
project data, names, credentials or PID registry; file existence is not an active
lock. Their documented application-owned location remains after pip uninstall.
Active app projects and full read/settings/configuration requests hold shared use;
switching validates/acquires new use before releasing old use. Direct local/review
servers hold it through server_close. CLI and packaged tutorial commands hold use
through full operations, including initialization and transaction/network gaps.
Custom Python callers must wrap complete operations in `project_use(project.root)`.
Same-user/same-machine cooperating clients only: not older versions, external
programs, other OS users, hostile filesystem mutation or multi-host storage.

## Removal contract

`application/trash.py`: eligibility → five-minute one-time confirmation → exclusive
use → identity/schema/configuration/snapshot revalidation → immediate target check
→ native move → destination verification. Controller mutex prevents selection/
close/configuration races. All validation DB connections close before the move.
Snapshots cover root/project directory identity, project ID, config head, bootstrap/
database hashes and database state, plus a deterministic tree identity/metadata
signature. Symlink contents are inventoried without following external targets;
article bytes are not duplicated/read into provenance. Special filesystem entries
are refused. Tree metadata is not a full cryptographic article-content audit.

Only registered valid direct children of allowed roots, inactive and exclusively
lockable, are eligible. Root/parent/arbitrary-path/link/reparse/source-repository/
software-containing targets fail closed. No UI paths are accepted as mutation targets.

Protected POSTs use `corpustrail-project-trash/v1` (also include `schema`):

- `/api/v1/projects/trash/prepare`: `{handle}`
- `/api/v1/projects/trash/cancel`: `{confirmation}`
- `/api/v1/projects/trash/execute`: `{confirmation, folder}`

Existing exact Host/Origin/session/CSRF checks, 64 KiB bounds and strict key/JSON
allowlists apply. GET cannot execute commands. `/api/v1/projects/close` uses existing
project-form/v1 and closes only the launcher's context. It kills no other operation.
Exact confirmation text is required; attempts consume nonces before filesystem
work. Capacity is 256 pending tokens; expiry/cancel/restart invalidates them.

Lazy `MacOSTrash.move` imports only the optional, pinned Cocoa/core bindings.
Foundation checks local/non-ubiquitous storage using
`isUbiquitousItemAtURL:` for the Boolean iCloud-targeted item check (the nullable
NSURL resource property is not inferred to mean false). This is not detection of
every third-party synchronization service. It moves the folder with
`trashItemAtURL:resultingItemURL:error:`. Status, returned file destination and redacted
numeric diagnostic are retained; raw NSError/stack/private-path text is not exposed.
Success requires original path absent, returned same directory identity, valid
standalone project, unchanged bootstrap/database hashes and matching tree signature.
Renamed Trash folders work. Unknown/cross-volume identity changes do not become
success. OS/user controls retention. Failure requires verifying source identity/
database/inventory unchanged with no observed destination; otherwise result is uncertain.
Uncertain handles are blocked for further removal in this launcher. Interruptions/
restarts require manual source/Trash inspection, never automatic retries.
Success invalidates registered handles, remaining tokens and cached receipts for
that project, then refreshes actual permitted locations. No permanent deletion,
partial scientific cleanup, external-reference traversal or automatic restoration.

Windows/Linux native removal is deliberately disabled. Future adapters must meet
the same verification contract. All other functionality remains independent of Cocoa.

## Acceptance boundary

Independent subprocess tests cover launchers, review, CLI/tutorial, overlapping
shared use, exclusive blocking, death/recovery and interrupted controlled renames.
Mock native outcomes are separate from an explicit macOS opt-in test using the
real API on one disposable project, checking returned destination and restoring
only that exact folder without overwrite for fixture cleanup.
macOS 15 and Windows lifecycle CI covers Python 3.11–3.13; macOS installs the extra
and enables the native test. Existing Linux core/ML/wheel/sdist matrix remains;
artifact build needs both job groups. No real scientific providers/models are used.
Native GUI acceptance remains a separate disposable-project owner test.

The prior uncommitted temporary checkout was no longer present in this session.
The guard architecture was reconstructed from the recorded work on the unchanged
accepted branch and independently tested again; byte-identical recovery is not claimed.
