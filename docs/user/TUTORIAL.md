# Offline tutorial and release acceptance

Install from a supplied/cloned source tree or candidate wheel as in README. All records and scripted
decisions below are invented software fixtures, not human scientific validation.

```bash
python -I -m corpustrail.tutorial /tmp/materials-demo
corpustrail project status /tmp/materials-demo
corpustrail candidates /tmp/materials-demo --run-id fixture-discovery
corpustrail corpus /tmp/materials-demo
corpustrail knowledge conflicts /tmp/materials-demo
corpustrail export asreview preview /tmp/materials-demo
corpustrail export asreview inspect /tmp/materials-demo --export-id fixture-corpus
corpustrail export asreview mapping /tmp/materials-demo --review-id review-A --mapping-id result-1
```

The first command is the packaged canonical acceptance workflow: initialize and
configure → recorded offline discovery → exact enrollment/deduplication → verified
evidence and pending PDF → synthetic human membership events → optional ordering
→ evidence-linked parser assertion → unlabelled export → exact result mappings
for two independent questions. It refuses an existing target. No checkout,
PYTHONPATH, credentials or network is used.

Expected JSON: network_used=false, raw_observations=9, canonical_papers=8,
pending_documents=1, preview records=3; membership included=3, excluded=2,
insufficient_evidence=1, unresolved=1, not_reviewed=1; round_trip_records=[3,3],
membership_unchanged=true. Duplicate observations retain lineage; the two equal
titles are distinct works. One member lacks DOI/abstract; another is excluded for
downstream question A without changing broad membership.

Copy a canonical ID from candidates JSON for evidence/knowledge inspection:

```bash
corpustrail evidence /tmp/materials-demo --paper-id CANONICAL_ID
corpustrail knowledge show /tmp/materials-demo --paper-id CANONICAL_ID
```

Optional ML branch needs the prioritization extra and a new target:

```bash
python -I -m corpustrail.tutorial /tmp/materials-demo-ml --prioritize
corpustrail prioritize inspect /tmp/materials-demo-ml --run-id fixture-order
```

All eight candidates remain accessible. The fixture has both binary human classes
and a separate insufficient state; ordering never decides membership. It proves
plumbing, not predictive performance. For real work use a new project and the
user guide, never recycle fixture judgments. Smoke tests execute these installed
commands in isolated core/ML environments and compare counts/mappings.
