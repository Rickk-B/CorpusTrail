# Privacy, credentials and local security

Local-only implemented operations: project/config/identity operations, offline
fixtures, human review, knowledge reads/writes, local TF-IDF fitting/ranking,
CSV export and exact-ID mapping. No automatic model/external extraction exists.

Discovery sends exact queries, requested bibliographic fields and pagination to
the chosen provider. Evidence resolution sends identifiers (e.g. PMCID) to the
configured legitimate source. Execution requires explicit external confirmation;
there is no automatic provider switch. Provenance identifies provider/version,
request, attempts, safe rate-limit headers, response hash and failures.

Opening an external link lets the browser contact that source. Import into a
remote ASReview deployment is a user-controlled downstream transfer, not a core
service call. Future external model integrations must require explicit scoped
authorization/configuration and record exact evidence inputs; none is activated
by installing this alpha.

Use credential_env variable names in project config, set values privately in the
process environment. Never commit API keys, personal correspondence or sensitive
queries. Unknown credential fields are rejected; supplied free text cannot be
guaranteed secret-free. Header credentials are not logged. Raw provider responses
are preserved and may contain contacts/article content; they are not universally
redacted. Providers/proxies/browser extensions may retain data. CorpusTrail does
not guarantee third-party retention, security, privacy or legal compliance.

The review UI binds only 127.0.0.1, checks Host/Origin/CSRF and renders text without
executing document markup. It is not an authenticated multi-user service; other
local processes/users/extensions are outside this boundary. Do not reverse-proxy
or expose it remotely. Stable reviewer role IDs are provenance, not identity proof.

Project paths reject traversal/symlink escapes; artifacts use no-clobber writes,
SQL parameters and immutable scientific events. No shell/pickle/model deserialization
is required. Pending PDFs remain untrusted. XML follows the bounded no-DTD policy.
These are practical safeguards, not formal security certification. Filesystem
owners can tamper with files/databases; hashes detect changes but are not signatures.
Back up your project, restrict access and use patched Python/Expat libraries.

Use the [security-reporting guidance](../../SECURITY.md). No disclosure contact or
third-party retention promise is invented. No secrets were rotated/deleted or
historical evidence rewritten during alpha preparation.
