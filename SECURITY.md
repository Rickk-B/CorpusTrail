# Security and responsible reporting

CorpusTrail is a local research tool, not a formally certified security product
or an authenticated multi-user service. Review binds to localhost; do not expose
it through a remote proxy. Use patched Python/Expat and restrict project-directory
access. Hashes detect changes but are not signatures or authorization controls.

For a sensitive report, use this repository's private vulnerability-reporting
feature **if the owner has enabled it**, or an already-established private channel
to the repository owner. No disclosure email or public contact is invented here.
Until a private channel is available, do not post exploit details, credentials,
private project data or documents in public issues. A sanitized request for a
private contact is preferable. No response-time or bounty promise is made.

For public reproducible bug reports use generated inputs, not real copyrighted
articles or human review files. Include version, platform, minimal steps and typed
errors; never include API tokens, credential headers, private paths or raw responses
with personal data. Consult [privacy/security](docs/user/PRIVACY_SECURITY.md) and
[XML policy](docs/developer/XML_POLICY.md).

Only the current alpha is covered by development triage; compatibility/security
guarantees for earlier or future versions are not implied. The release process
keeps provider/model calls out of normal acceptance tests. No external model
extraction is enabled merely by installing CorpusTrail.
