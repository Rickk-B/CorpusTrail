# Repository publication and execution review — 2026-10-16

This is a bounded technical audit, not penetration testing, a legal opinion,
certification, checkpoint acceptance or permission to publish.

## Verified starting state

GitHub metadata reports `Rickk-B/CorpusTrail` **PUBLIC**, MIT licensed, development
HEAD `21d78b6bbe513ea255db768ca9ea9ec47d7c0de4`. Visibility was not changed.
The two prereleases have no attached binary assets. All local work takes place
in an isolated WSL2 checkout, not the historical research repository. Personal
Windows/Mac files and researcher projects are excluded from inspection and tests.

The initial reachable-history scan covered 50 commits and 817 distinct blobs.
It found no obvious private-key/token patterns, private paths/contact information,
PDF/database/archive payloads or unclassified binary blobs. Its two
credential-URL-shaped findings are synthetic literals in the negative endpoint
policy test, targeting a reserved example hostname. All 263 historical binary
blobs are reviewed test-baseline PNGs. Commit emails are project-neutral. This
does not establish that no opaque/unknown secret exists; unreachable deleted
objects, other repositories, device credentials and server backups are outside
the scan. `tools/repository_audit.py` reproducibly checks all reachable local refs,
commit/tag text and blobs without printing matched values. Review findings,
rather than automatically deleting fixtures or rewriting history.

## Security findings and changes

* GitHub secret scanning, push protection and dependency security updates were
  disabled at inspection. Recommend owner review/enabling these free safeguards
  where available; repository settings are not changed by this task.
  `main` was reported unprotected and private vulnerability reporting disabled.
  Recommend protected/reviewed main updates and a private reporting channel.
  The workflow remains compatible with required checks and grants no approval authority.
* Workflows use read-only token permissions; fork-contributor policy requires
  first-time approval. No `pull_request_target`, publishing tokens, privileged
  releases or self-hosted runners are introduced. All used actions are pinned
  to official immutable commit SHAs; checkout credentials are not persisted.
  Jobs have timeouts and superseded branch runs are cancelled.
* Browser tests use only disposable synthetic data. Unexpected browser/backend
  external requests fail. Trace snapshots/network bodies are disabled and
  transient local tokens/paths are redacted. The previous successful CI log archive
  had no secret-signature matches; all 166 path-pattern matches were ephemeral
  hosted-runner paths, not researcher device paths. Browser artifacts expire after
  seven days; development bundles after fourteen. Old artifacts are not deleted.
* An advisory scan identified published vulnerabilities in development-only
  Pillow 12.0.0. The pin is updated to 12.3.0, then audited again. The local
  disposable installer is also updated from pip 24.0 to 26.2. Core still has
  zero production dependencies. These are not evidence of a runtime exploit.
* No credential exposure requiring rotation was demonstrated. If a future
  finding identifies a real credential, rotate/revoke first under owner control;
  do not rely on hiding a file or rewriting Git history.

## License and rights

LICENSE and package metadata agree on MIT. NOTICE identifies adaptations and
invented fixtures. No real article/PDF or research database is distributed.
Core vendors no dependency. Optional numerical libraries retain their BSD-style
and component notices; optional PyObjC uses its separate MIT terms. Developer
Playwright/browser and Pillow retain their Apache-2.0/browser-component and
HPND/MIT-CMU-family notices. Installed browser/font packages are not bundled.
Screenshots show synthetic application fixtures, not copyrighted article text.
Source-history receipts contain hashes, not private research datasets.

No obvious licensing blocker was found in this inspection. Dependency/bundled
asset rights still need review when new components or actual datasets are added.

## Cost and resources

The current public visibility and standard runner labels satisfy GitHub's free
compute eligibility. `macos-15` is a standard Apple Silicon label, not a paid
larger runner. No billing settings or capacity are changed. Baseline workflow
wall time was about 21 minutes: Linux acceptance 12–18 minutes/job, Linux browser
5 minutes, macOS smoke about 1.6 minutes, lifecycle 0.5–2.6 minutes, final bundle
about 3 minutes. Full Chromium plus WebKit reuses one macOS Python/tool/wheel
setup; estimate 8–12 minutes total instead of 1.6, bounded to 25 minutes.

At inspection 46 artifacts used 137,251,966 compressed bytes. Expect roughly
40–70 MB for both macOS reports per run, plus Linux screenshots and a small
wheel bundle. Seven-day browser retention limits steady growth but does not cap
frequent runs. GitHub artifact/Packages storage has account-wide allowances:
free compute does **not** establish unlimited free storage or a guaranteed zero
account bill. Review aggregate account usage/budgets; do not enable overages.

## WSL exposure and hardening recommendations

The runtime identifies as WSL2. Mount metadata shows Windows filesystem mounts
exist, although no Windows-host directory was accessed. The available process
environment had no GH/GITHUB token variable, SSH agent socket, proxy/CA override
or WSLInterop/WSLENV variable; the WSLInterop registration was not exposed to
this process. GitHub CLI authentication works, so absence of token environment
variables does not imply absence of credentials. Credential storage was not read.
These observations describe this process/sandbox, not host-wide isolation.

Recommend owner-controlled least-privilege GitHub credentials, no unnecessary
agent forwarding, project-local environment isolation and separate review of WSL
automount/interoperability. No Windows/macOS/WSL security settings are changed.

## Publication-readiness assessment

**NOT YET READY FOR PUBLICATION.** The repository is already public;
this assessment does not change visibility or claim a newly authorized release.
No actual secret or license blocker was demonstrated, but owner security-setting
review, final cross-platform/visual acceptance and residual audit-scope review
remain before a formal open-source publication/security sign-off. Prioritize
secret scanning/push protection, dependency-update notifications and storage
monitoring. Do not publish private datasets or article artifacts with the code.

References: [standard runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners),
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[Pillow advisories](https://github.com/python-pillow/Pillow/security/advisories).
