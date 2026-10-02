# Code and fixture provenance

CorpusTrail code, documentation and bundled synthetic fixtures are distributed
under the [MIT License](LICENSE). LICENSE uses the approved project-level notice,
`Copyright (c) 2026 CorpusTrail contributors`, not personal attribution. This
does not change the MIT terms or remove required third-party notices.

Native parsing, the optional TF-IDF/logistic algorithm, transport/metadata mapping,
resolver and knowledge/export infrastructure include adaptations of earlier
MIT-licensed project code. Bundled code-origin hashes and migration receipts
preserve that lineage without requiring the original development repository.
Those receipts describe past adaptation state, not the current feature set or
license. The current software license is MIT as declared in LICENSE/metadata.
Schema resources are immutable code, not bundled scientific records. No upstream
research data, article text or model output is required at runtime.

All bundled article/record fixtures are invented software examples. They are
not actual articles, licensed research datasets, reviewer labels or validation
results. No real PDFs or full article text are distributed.

## Separate dependency licenses

Core has no runtime dependencies and vendors no third-party libraries.
Optional numerical libraries are installed separately under their own terms:
scikit-learn, joblib and threadpoolctl have BSD-style licenses; NumPy and SciPy
include permissive/component notices. Their installed wheels contain the complete
applicable terms. Those libraries are not relicensed or bundled by CorpusTrail.

ASReview is optional downstream software (the tested SDK is Apache-2.0); it is
neither copied nor a core dependency. Its importer was inspected for bibliographic
interoperability, not included. Build/development tools also retain their own
licenses. Provider names/links identify integration targets, not endorsement.

No separate third-party code attribution was identified as required beyond the
MIT notice for adapted project code. This notice adds no restrictions
to the MIT License. Article acquisition does not grant redistribution rights:
keep actual project evidence outside the software repository.
