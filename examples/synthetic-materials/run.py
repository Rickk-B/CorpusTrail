"""Offline fixture demonstration, not a scientific validation study."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from corpustrail.curation import EvidenceBasis, ReviewEvent
from corpustrail.identity import BibliographicRecord, Identifier, SourceReference
from corpustrail.project import Project, ProjectConfig, ReviewPolicy


FIXTURE_TIME = "2026-10-01T00:00:00+00:00"


def run(target: Path) -> dict:
    body = Path(__file__).with_name("records.json").read_bytes()
    rows = json.loads(body)
    config = ProjectConfig("synthetic-materials-v1", "Synthetic materials sensors",
                           "Invented offline fixtures for software contracts only.",
                           review=ReviewPolicy(authorized_reviewers=("fixture_reviewer",)))
    project = Project.create(target, config, created_by="fixture_generator", created_at=FIXTURE_TIME)
    paper_ids = []
    for raw in rows:
        fields = {key: value for key, value in raw.items() if key not in {"record_key", "fixture_review"}}
        fields["authors"] = tuple(fields["authors"])
        fields["identifiers"] = tuple(Identifier(**x) for x in fields["identifiers"])
        source = SourceReference("fixture://synthetic-materials/v1", raw["record_key"],
                                 "sha256:" + hashlib.sha256(body).hexdigest(), len(body),
                                 "fixture_generator", FIXTURE_TIME, identity_status="verified")
        plan = project.identities.plan(BibliographicRecord(**fields), source)
        paper_id = project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
        assert project.identities.apply(project.identities.plan(plan.record, source)) == paper_id
        paper_ids.append(paper_id)
        state = raw["fixture_review"]
        if state is not None:
            sufficient = state in {"included", "excluded"}
            representation = "abstract" if fields["abstract"] else "metadata"
            event = ReviewEvent(paper_id, state,
                "sufficient" if sufficient else "insufficient" if state == "insufficient_evidence" else "undetermined",
                representation, "Synthetic fixture decision; not a real human scientific label.",
                "fixture_reviewer", FIXTURE_TIME,
                (EvidenceBasis(representation, source.source_sha256, source.source_uri,
                               raw["record_key"], "verified"),), authority_state="human_authorized")
            review_id = project.reviews.apply(project.reviews.plan(event))
            assert project.reviews.apply(project.reviews.plan(event)) == review_id
    assert paper_ids[0] == paper_ids[-1]
    assert paper_ids[0] != paper_ids[1]  # Duplicate title is not an identity join.
    before = project.status()
    assert Project.open(target).status() == before
    return {"raw_records": len(rows), "canonical_papers": len(set(paper_ids)),
            "paper_ids": paper_ids, "status": before,
            "warning": "Synthetic software fixture, not a scientific study"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    print(json.dumps(run(parser.parse_args().project), ensure_ascii=False, sort_keys=True, indent=2))
