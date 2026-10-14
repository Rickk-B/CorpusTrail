# Read-only original-response diagnosis and autonomous evidence acceptance

## Environment and permission boundary

The development environment is Linux/WSL2, not a MacBook. The explicitly checked
local `evidence-test` project was absent; no unrelated folders were searched and no
Mac filesystem/remote-desktop connection was available. Native macOS hosted tests
are a different environment and have only their own disposable fixtures.

The fixed public API route implemented by the existing Europe PMC resolver is
`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13558126/fullTextXML`.
One separately authorized current-response request may help reproduce a failure;
it cannot identify the original response without its bytes/hash. Do not issue it
without explicit permission, retry it, search other publications or contact another
endpoint. Opening the UI or running the original-response diagnostic never makes
provider requests.

## Diagnostic for an existing installation

`tools/evidence_diagnostic.py` works with the existing standalone CorpusTrail
installation; it needs only Python and the already installed core. It is not a
new acquisition route, scientific verifier or normal browser endpoint. Download
the exact committed script if MacBook-only original-response inspection is needed,
then run it using the existing environment and the explicitly supplied project:

```bash
~/CorpusTrail/.venv/bin/python -I ~/Downloads/evidence_diagnostic.py \
  --project ~/CorpusTrailProjects/evidence-test --pmcid PMC13558126
```

No internal files, IDs or XML need to be located manually. The script:

- Takes the existing shared project-use lease and opens only a validated project.
- Selects the verified owner of the supplied PMCID, never a title/fuzzy match.
- Reads integrity-checked acquisition pages (at most 1,000 records), reporting at
  most five invalid Europe PMC representations and explicitly flagging truncation.
- Finds each enrolled artifact through the read-only registry, confines its path,
  bounds reads and checks byte count and SHA-256 before inspection.
- Uses `parse_xml` and `_document_ids` from the installed scientific implementation
  to report the actual current validation stage/reason, without changing trust.
- Reports stored HTTP status if available, response size/hash, policy outcome,
  structural counts and public supplied-PMCID matching. It never exports article
  text, titles, arbitrary identifiers, source URLs, personal paths or credentials.
- Reports Python, OS, Expat and installed distribution versions for reproducibility.
- Classifies only fixed byte signatures (gzip/ZIP/PDF/BOM), never decoding compressed
  data, rewriting input or exporting byte snippets. Parser error codes/locations are
  numeric rather than arbitrary exception text.
- Uses SQLite `mode=ro` and `query_only`, makes no network requests or database
  writes, and never acquires, retries, repairs, migrates or updates anything.

The existing guard can create/reuse application-owned external lock anchors, not
scientific project content. It coordinates cooperating versions, not arbitrary
external writers. Changed/corrupt artifacts fail closed. Output is concise JSON on
stdout; unexpected errors are redacted rather than printed as stack traces.

Historical acquisition does not preserve the observed response Content-Type.
The resolver's declared XML media type must not be presented as that HTTP header.
Stored invalid records only contain the exception class, so their enrolled original
bytes—not that class alone—are needed to identify the precise condition.

## Structural inventory is not trust

A bounded Expat *diagnostic-only token inventory* can observe a DOCTYPE and inspect
structure without resolving its external subset. Parameter-entity parsing is
disabled; entity declarations, external/skipped entity references and resource-limit
excess abort inventory. No loader/network callback exists, no tree is constructed,
and input bytes are never stripped or rewritten. Well-formed-without-external-loading
is not DTD/schema validity or scientific verification. Incomplete/refused inventory
is reported honestly. The installed scientific policy remains authoritative:
`bounded-no-dtd/v1` refused every DTD; the later narrowly reviewed
[`bounded-inert-jats/v2` boundary](XML_POLICY.md) supports only inert allowlisted
JATS declarations. Reports distinguish stored validity/policy from current parser
diagnostics. Matching diagnostic IDs/body counts cannot make rejected content trusted.

## Automated acceptance

The existing Playwright evidence scenario now performs a **real graceful server
and controller restart** after verified acquisition and mismatch rejection. It
reopens the same disposable project through the browser, reads persisted history
and trusted prior text, and checks that no extra provider request or scientific-file
change occurred. This does not promise crash-resume. All ordinary browser/CI
providers remain controlled offline fixtures; none of these tests needs live access.

Run the existing full browser/visual suite and focused diagnostics:

```bash
python tools/browser_acceptance.py --visual compare --output /tmp/ct-evidence-acceptance
python -I -m unittest discover -s tests -p test_evidence_diagnostic.py -v
python -I -m unittest discover -s tests -p test_evidence_app.py -v
python -I -m unittest discover -s tests -p test_xml_safety.py -v
```

Keep current live integration distinct from fixture acceptance and from original
MacBook diagnosis. No scientific pipeline correction is justified without concrete
evidence. Changes to XML/trust policy require separate approval. Checkpoint 5 is
not part of this work; Checkpoint 4 is not automatically accepted by a test report.

## Earlier read-only acceptance (2026-10-14; source 2fcacca)

Local Linux/WSL2 / Python 3.12 / pinned Chromium: all 12 browser scenarios and 46
existing visual comparisons passed, including restart/history/no-replay evidence
acceptance at all three sizes. No baseline or application asset was changed. Direct
image inspection included reviewer permissions, Welcome, approval and verified/
rejected evidence. No significant new application layout issue was observed.

The first full run exposed nondeterministic viewport scrolling in the Discovery
progress *test snapshot* and a worker-dictionary teardown race. Test-only explicit
scroll anchoring and locked worker snapshots corrected these; screenshot tolerances
and scientific/provider retry/timeout policies were not changed. Fixture gates remain
bounded. Existing native macOS Trash/lease coverage is retained, and the seven
read-only diagnostic tests are added to the native macOS/Windows Python 3.11–3.13
lifecycle matrix, without adding a native dependency.

Local standalone/optional-ML: 462 tests passed (one native-only skip). Independent
wheel/sdist core and ML acceptance also passed 462 tests per installation with
expected optional/native skips, installed CLI/tutorials and uninstall/reinstall
preservation. Recorded tutorial network-use flags were false. Seven new diagnostic
tests verify read-only SQLite connections, project file fingerprints, hash corruption,
entity/encoding/resource refusals, no text export and redacted failures. Evidence
application (16) and XML policy (8) regressions passed. Ruff/JavaScript checks passed.

That read-only acceptance made no live request. A separately authorized follow-up
on 2026-10-14 made exactly one GET: HTTP 200, application/xml, 417,134 bytes,
SHA-256 `0a9f6b9202435e3074865506ba516c5c9456f55945125341e2a4adbfcf5ecdec`.
The current response's external DOCTYPE caused the unchanged v1 policy rejection
before identity verification. This reproduced the reported behavior, not the
historical MacBook bytes. The full response was discarded with its disposable
project; only sanitized diagnostics remained. The later [compatibility review](JATS_COMPATIBILITY.md)
uses synthetic fixtures, with no automatic new live request or historical
reclassification. The original MacBook cause still requires original-byte evidence
for certainty. A researcher is not asked to repeat graphical testing or interpret XML.
