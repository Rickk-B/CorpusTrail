# Guided project setup — experimental Checkpoint 2 contract

UI → versioned local HTTP → `application.projects.ProjectController` → existing
`Project.create/open/configure` and typed `ProjectConfig`. No CLI subprocess,
scientific SQL in transport/controller, replacement configuration system, schema
change or dependency is introduced. Python/HTTP interfaces remain experimental.

## Routes and explicit writes

Pages: `/home`, `/projects`, `/projects/new`, `/settings`, plus existing dashboard/catalogue.
`/` shows static packaged Home without an active project; direct project launches
retain the dashboard. Home uses no JavaScript or API requests. Project navigation
visibility follows launcher state only, never scientific state or an inferred role.
Packaged `projects.html`/`projects.js` are separate from the accepted browsing UI.
Creation retains six steps; settings shows all sections with explicit save/discard.
The same POST/configuration contract and controller are used without modification.
Definition-change acknowledgment is a UI confirmation, not a new authority rule.

| Route | Contract |
|---|---|
| GET `/api/v1/projects?offset=0&limit=25` | Paginated enrolled/direct-child projects, approved root, installed capability descriptors; no filesystem writes |
| GET `/api/v1/project-settings?handle=…` | Saved human-facing form, revision/version, explicit scope presence/hash, last 20 configuration authors/timestamps; no secret values |
| POST `/api/v1/projects/open` | Enrolled opaque handle only; in-memory active selection, no scientific writes/upgrades |
| POST `/api/v1/projects/create` | Explicit folder/form/request receipt + optional authority confirmation; existing Project.create |
| POST `/api/v1/project-settings/save` | Explicit project handle/revision/form/request receipt + authority/session confirmation; existing Project.configure |

All command envelopes and DTOs carry `schema: corpustrail-project-form/v1`.
Unknown fields/versions and duplicate JSON keys fail closed. Paper/read APIs keep
their existing DTOs; no universal rich review object or blinded route is added.

`fields` explicitly allowlists name, description, scope, providers, resolvers,
search concepts, configuration-author/reviewer pseudonym and authorized reviewers.
Provider records carry id/adapter/credential **environment-variable name**, never
key/header values. The UI does not inspect/connect to providers. Capabilities
instantiate only currently installed built-in adapters, without request execution.

The reviewer pseudonym is recorded in existing configuration `created_by`
provenance. Authority is an independent explicit `ReviewPolicy.authorized_reviewers`
choice. No default-reviewer semantic field, implied administrator role or new
authority mechanism is invented. Existing reviewer authorization policy remains
the scientific enforcement point. Local configuration editing follows existing
project-owner CLI/API semantics, not a new multi-user access-control system.

## Concurrency, definition and preservation

Complete replacement configurations are built with dataclass `replace` from the
current saved config, preserving unedited fields and incrementing exactly once.
The existing service checks the expected event ID under its transaction lock.
The immutable bootstrap/history is not rewritten. No-op forms add no event.
Scope/description/policy changes after an authoritative review are still blocked.

Definition provenance is existing configuration event identity plus SHA-256 of
the actual scope/description/policy representation. No definition table is added.
Absence of legacy scope remains explicit; no review question/name is used as a
surrogate definition. Historical review packets keep their frozen original text.

Every config change continues to invalidate updates to frozen review sessions.
The application explains this and requires explicit acknowledgment rather than
relaxing guards. Scientific tables, evidence/artifact files, identity, membership,
ranking, Knowledge/model and ASReview state are not edited by settings saves.

## Security and storage

The shared loopback transport retains strict Host/Origin/Sec-Fetch-Site checks,
nonce-bound API access, CSP, no CORS and safe text rendering. Mutation endpoints
add mandatory exact same-origin Origin, session nonce, matching CSRF header,
JSON content type, single Content-Length and 64-KiB body limit; chunked bodies,
unknown fields/nonfinite values/duplicate keys are rejected. Unexpected errors
return redacted messages, never request values, credentials or OS paths.

The launcher explicitly chooses a projects root (default `~/CorpusTrailProjects`)
or enrolls an existing project path. HTTP receives only portable child-folder
names and registered opaque handles. All existing path components, bootstrap and
database are checked for symlinks. No arbitrary file-reading/writing/deletion
API is exposed. Same-user malicious filesystem races are outside this local-app
confinement guarantee; this is not an OS sandbox.

Creating a target uses Project.create's exclusive reservation. Existing directories
are never reused/overwritten, and partial initialization is preserved for manual
inspection. A process-local lock and 256 successful receipt entries prevent
duplicate execution/retries with changed payloads. Receipts/handles disappear on
shutdown. Durable restart guarantees are the existing exclusive reservation and
configuration CAS, not a new request ledger or automatic recovery job.

One application server has one active project. Writes specify their enrolled
project handle and saved revision; they never infer a target from a title or path.
No persistent global registry/settings/cache/logs or browser storage is introduced.
Project-owned scientific/configuration data is preserved by package uninstall.

The compatibility `make_server(project)` remains read-only. `serve` and CLI `app`
enable the guided controller, and `app` can now launch without a project path.
The separate `corpustrail review serve` implementation and allowlist are unchanged.

## Scope boundary

No discovery/evidence/model calls, automatic migration, deletion, guided-review
authority redesign, population/reference/classifier/import infrastructure or
desktop packaging. Local transport, form validation and read-only browsing are
not scientific decision engines. Later checkpoints require separate approval.
