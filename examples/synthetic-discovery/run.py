"""Offline synthetic discovery fixture: not scientific data or validation."""

import argparse
import json
from pathlib import Path

from corpustrail._internal.values import canonical
from corpustrail.evidence import EuropePmcResolver
from corpustrail.identity import Identifier
from corpustrail.project import EvidencePolicy, Project, ProjectConfig, ProviderConfig, SearchConcept
from corpustrail.providers.metadata import MetadataProvider
from corpustrail.providers.network import HttpResponse


AT = "2026-01-01T00:00:00+00:00"


class RecordedTransport:
    network = False
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def request(self, url, *, method, headers, body):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("fixture permits one request")
        return HttpResponse(200, {}, self.body, url)


def run(target):
    directory = Path(__file__).parent
    responses = json.loads((directory / "responses.json").read_text(encoding="utf-8"))
    config = ProjectConfig("synthetic-discovery", "Materials sensors", "Invented offline software fixture",
        providers=tuple(ProviderConfig(x, x) for x in responses),
        search=(SearchConcept("porosity", "porous ceramic"),), evidence=EvidencePolicy(("europepmc",)))
    project = Project.create(target, config, created_by="fixture", created_at=AT)
    executions = {}
    for name, response in responses.items():
        provider = MetadataProvider(name)
        provider.network = False
        plan = project.discovery.plan(provider, run_id="fixture-" + name, concept_id="porosity", created_at=AT)
        executions[name] = project.discovery.execute(plan, provider,
            transport=RecordedTransport(canonical(response).encode("utf-8")), clock=lambda: AT)
        project.discovery.canonicalize(plan.run_id, approve_new_identities=True, approve_aliases=True)
    paper_id = project.identities.exact_owner(Identifier("doi", "10.1234/materials.1"))
    resolver = EuropePmcResolver()
    resolver.network = False
    request = project.evidence.plan(paper_id, created_at=AT)
    project.evidence.acquire(request, resolvers={"europepmc": resolver},
        transport=RecordedTransport((directory / "article.xml").read_bytes()), clock=lambda: AT)
    project.evidence.preserve_document(paper_id, b"%PDF-1.4\nUnverified invented fixture", representation="pdf",
        media_type="application/pdf", source_uri="fixture://unverified.pdf", legitimate_basis="synthetic_fixture",
        resolver="fixture", resolver_version="v1", created_at=AT)
    before = {"project": project.status(), "metadata": [project.discovery.metadata(x) for x in project.identities.papers()],
              "evidence": [project.evidence.status(x) for x in project.identities.papers()]}
    reopened = Project.open(target)
    assert before["project"] == reopened.status()
    assert before["metadata"] == [reopened.discovery.metadata(x) for x in reopened.identities.papers()]
    assert len(project.discovery.observations()) == 3
    assert len(project.identities.papers()) == 2
    assert all(project.reviews.membership(x)["state"] == "not_reviewed" for x in project.identities.papers())
    assert project.evidence.status(paper_id)["pending_identity"] == 1
    return {"warning": "Synthetic software fixture only", "network_used": False,
            "raw_observations": 3, "canonical_papers": 2, "executions": executions, **before}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    print(json.dumps(run(parser.parse_args().project), ensure_ascii=False, sort_keys=True, indent=2))
