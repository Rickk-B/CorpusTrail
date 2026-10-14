# Checkpoint 4 final refinement and unresolved Europe PMC investigation

## Presentation consent audit

Project creation's application guard requires `confirm_authority=True` when
`authorized_reviewers` is nonempty. There is no scientific requirement for two
independent UI confirmations. Creation now uses an explicit radio choice, default
**No publication authority**, followed by a readable final summary. **Create
Project** confirms that displayed choice. Only the explicitly selected authorization
radio can supply creation's authority confirmation; settings retain their separate
authority-change checkbox. The pseudonym remains configuration authorship, not a
default session reviewer. Existing Project/configuration guards are unchanged.

Discovery already records both required consent flags in one `approved` event,
bound to the frozen plan hash and one-time preview nonce. The backend requires both
flags but does not require independent checkbox events. **Approve Search Plan** now
deliberately authorizes both clearly disclosed operations: selected-provider network
requests and exact-ID/source-provenance organization. Its accessible description
contains both disclosures and the absence of membership decisions. The flags are
submitted only on that deliberate approval action for a current visible preview.
The existing backend guards, provenance, API contract and separate **Run Discovery**
action are unchanged. No approval or navigation performs provider requests.

## Europe PMC: evidence available on 2026-10-14

The researcher reported an HTTP-successful acquisition for PMC13558126 (PMID
42723954, DOI 10.3389/ebm.2026.11146) followed by `invalid` content validation.
The actual Mac project's records and failed response bytes are not present in this
workspace. No live scholarly request or retry has been authorized/performed by this
task. The matching public website described by the researcher is not evidence of
what the structured-XML endpoint returned during that attempt.

The installed resolver constructs a GET to
`https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13558126/fullTextXML`, with
`Accept: application/xml`, no query parameters and no browser-supplied URL. Its
declared representation is JATS XML. The transport refuses redirects and bounds
response size (20 MB by default) and socket timeout (30 seconds by default).

Acquisition preserves raw response bytes by hash and records HTTP status, final
request specification, outcome, attempt and rate-limit diagnostics. The stored
media type is the resolver's declaration, **not the observed Content-Type header**;
that header is not preserved in acquisition provenance. A representation records
the artifact hash, source URI, resolver, identity identifiers, trust state and
error **class**, not the detailed validation condition.

`_document_ids` first calls `parse_xml` under `bounded-no-dtd/v1`: malformed/
unsupported XML, DTD/entity declarations and byte/node/depth/text limits fail
closed. It then requires an `article` root and normalizes only front/article-meta
identifiers. A caught `ContractError` produces `artifact_validity=invalid` with
`error=ContractError`; these records alone cannot identify which check failed.
Identifier mismatch is a separate `mismatch` state. Identity matching and subsequent
substantive body-text parsing are distinct stages; body parsing is not reached when
initial content/identifier validation fails. HTTP 200 alone establishes none of them.

An offline synthetic test demonstrates that HTTP 200 plus matching article IDs and
body text can still correctly be rejected when a DTD is declared. Earlier trusted
evidence and acquisition provenance remain intact, and no review/membership event
is created. **This is a policy example, not proof that the reported response had a
DTD or reproduction of that specific failure.** No validation/parser/trust change
has been made.

Current classification: **insufficient information (Case E)**. Exact original
status, Content-Type, XML structure, substantive text and failing condition remain
unknown. Obtain redacted advanced acquisition/representation records and, ideally,
inspect the original hash-verified response locally through the existing artifact
interface. A separately authorized bounded read-only live diagnostic request could
describe the endpoint's *current* response but cannot prove the original bytes.
Do not rerun the project operation, delete rejected evidence, relax the DTD policy
or infer identity from the website/title. Checkpoint 4 remains open pending this
investigation and native researcher acceptance.

## Local refinement validation

Linux / Python 3.12: complete standalone suite with optional ML, **455 tests,
one native-macOS-only skip**. Focused project forms: 38; discovery application: 21;
evidence application: 16; scientific discovery/evidence: 39; project-use/Trash: 33
(one native skip); XML policy: 8. Browser infrastructure self-tests: 8.

Actual installed packaged Chromium acceptance: **12 scenarios across three
viewports**, 46 screenshots, no runtime errors or unexpected external requests.
A separate reviewed-baseline comparison run passed all 46 comparisons. Viewports
are 1440×900, 1280×800 and 390×844. Representative Welcome, reviewer choices, final
summary, dashboard, approval and evidence unavailable/verified/rejected captures
were directly inspected. That inspection caught and corrected the radio controls'
inherited text-input minimum height. Intentional baselines were approved explicitly,
not by CI. This is not native macOS graphical or live-resolver acceptance.

Ruff, JavaScript syntax and whitespace checks passed. All production changes are
packaged presentation assets; no scientific Python service, schema, migration,
production dependency or project-use/trash implementation changed. Tests use only
disposable synthetic projects. Existing Python 3.11–3.13, macOS/Windows lifecycle,
native macOS Trash and offline browser CI gates remain required.

Independent clean installs also passed all 455 tests: wheel core (47 optional/native
skips), wheel ML (one native skip), sdist core (47 skips) and sdist ML (one native
skip). Installed CLI, offline tutorials, exports and uninstall/reinstall preservation
passed; every recorded tutorial/network-use flag was false. Browser resources were
absent from the wheel and sdist. The wheel text/privacy scan found nothing; the sdist
scanner's single credential-URL match is the unchanged synthetic rejection fixture
in `test_compatible_endpoint.py`, not a real credential. No actual research data was
used or removed.
