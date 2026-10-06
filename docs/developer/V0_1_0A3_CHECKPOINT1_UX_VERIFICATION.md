# Checkpoint 1 researcher-facing UX correction

Scope: presentation/read projections only, on the existing a3 development branch.
No Checkpoint 2, scientific write capability, migration, dependency, model/provider
call, or change to existing review-session semantics is introduced.

## Changes and semantic guardrails

- Corpus counts use Papers / In corpus / Out of corpus / Insufficient evidence /
  Awaiting corpus decision. The underlying `unresolved` and `not_reviewed` values
  remain distinct in the read contract and filters; the shared presentation label
  is not a new scientific state.
- Review activity shows recorded human-review papers, published corpus-decision
  papers and review sessions. Draft/event counts and recorded historical identity
  warnings are secondary disclosures, not completed-review or unresolved counts.
- Project description is not repeated when it is the fallback definition; no
  separate definition is invented. Configured services are secondary and untested.
- Title-based catalogue navigation, bibliographic information and concise textual
  status badges replace repeated operational prose. Missing source metadata is
  omitted rather than presented as a retrieval failure. Pagination remains bounded.
- Normal read DTOs include DOI/PMID/PMCID, not operational provider identifiers.
  The explicit advanced response preserves all exact identifiers and records.
- Detail evidence state appears once; actual abstract/document content and concise
  helper text follow. Existing verified-body checks still control text access.
- Advanced provenance begins with a readable identifier/source/selection summary.
  Detailed lineage and complete raw page JSON have separate native disclosures.
  Copy uses the browser clipboard with a selectable read-only fallback; no state
  write occurs. Operational provenance is explicitly not method-blind review.
- Read-only header, active navigation, keyboard focus and local assets are retained.
  Host/Origin/session/CSP/path confinement logic is unchanged.

## Implementation and artifact provenance

Original implementation: `6e116118f05e53ec3694c60e9171cb873a437bf8`.
Previous CI/distribution follow-up: `7086456aabd4c4edd124bddc12d6fb93ecf5017e`.
The new artifact is built from the exact UX commit identified in its Actions run
and `source.commit_sha`, never either earlier commit. Both earlier identities are
retained in its receipt. The workflow permits only the reviewed frontend/read DTO
paths to differ; no other production module may change. It reports presentation
changes honestly instead of claiming all application source remains unchanged.

## Acceptance scope

The five-paper offline DOM walkthrough covers dashboard → title catalogue → detail
→ evidence → advanced summary → raw records → catalogue. It tests five recorded
non-authoritative human observations with zero published corpus decisions, then
published positive/negative/insufficient states. It covers missing evidence,
pending/mismatched/invalid documents, duplicate titles, identifier copying and
script-shaped source text. Separate loopback HTTP tests verify access guards and
byte-identical project state. The synthetic 20,000-record bounded-page test remains.

This is not a human visual acceptance on macOS: no graphical browser is available
in this development environment and the researcher's private five-paper project
was not accessed. Native macOS/browser appearance and clipboard permissions require
the researcher's retest of the downloadable wheel. No throughput or real-model
compatibility claim is made.

Final local and hosted test/build results are reported with the exact commit and
artifact checksum in the completion report. Only successful Python 3.11–3.13
hosted acceptance permits artifact upload. Published a1/a2 and main remain frozen.

## Local verification results

- UI/read/loopback/DOM regressions: 28 tests passed (9.617 seconds); includes the
  20,000-record bounded-page test. Final assertions additionally exercise clipboard
  fallback and identical separately configured corpus-description text.
- CI artifact/lineage contracts: 11 tests passed (0.404 seconds).
- Complete source suite: 344 tests passed (75.614 seconds).
- Clean wheel core: 344 tests, 46 optional-ML skips, passed (56.008 seconds).
- Clean wheel ML: 344 tests passed (71.287 seconds).
- Sdist-built wheel core: 344 tests, 46 optional-ML skips, passed (56.957 seconds).
- Sdist-built wheel ML: 344 tests passed (71.133 seconds).
- Core/ML tutorial, installed CLI version, packaged frontend assets and
  uninstall/reinstall/project reopen checks passed outside the source tree.
- Ruff correctness gate, JavaScript syntax and patch whitespace checks passed.
- Changed-file privacy heuristic scan reported no findings; code-only distribution
  population remained valid. No known personal data or credentials were added.
- Initial sandboxed artifact testing could not bind loopback sockets; it was
  rerun successfully with local binding allowed. This was an environment limit,
  not a change to network policy or application behavior.

These local figures do not substitute for the exact-source hosted receipt. The
hosted run must pass all three supported Python versions before the new wheel is
made available; its run URL, actual source SHA and wheel hash are reported separately.
