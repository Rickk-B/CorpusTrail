# Contributing

Keep generic scientific software separate from any particular research project's
data, vocabulary or authority. Do not commit real articles, review labels, credentials
or operational databases. Use invented fixtures and explicit evidence/provenance.

Install in a dedicated environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -c tools/validation-constraints.txt -e '.[dev,prioritization]' setuptools
python -m ruff check src tests tools
python -m unittest discover -s tests -p 'test_*.py'
python -m build --no-isolation
python tools/smoke_install.py
```

Without numerical extras, the same test suite skips optional ML cases. To validate
both clean artifact-install environments offline, supply a directory of compatible
numerical dependency wheels with `--dependency-wheels DIRECTORY`.

Propose one logical change per commit with tests. Preserve minted paper IDs,
append-only scientific events, exact identity, no-clobber outputs and source hashes.
Ranking never establishes membership; insufficient evidence never becomes a
negative automatically. Do not rewrite frozen migrations or reinterpret scoped
fields. No live external provider/model calls belong in ordinary tests or CI.

Use the repository's issue/pull-request facilities once available. Discuss scope
or compatibility changes first; follow [alpha API boundaries](docs/developer/API.md).
Keep PR examples sanitized. Report security concerns privately as in SECURITY.md.
No named contributor list, institutional affiliation or special contribution
governance is required. Contributions are considered under the project's MIT license;
do not submit material you lack rights to share.
