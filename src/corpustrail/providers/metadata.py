"""Optional API dialects factored from existing keyword and graph normalizers.

Search concepts, credentials and budgets belong to the project, not adapters.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

from corpustrail._internal.values import ContractError
from corpustrail.discovery.contracts import CandidateObservation, DiscoveryPage, RequestSpec
from corpustrail.identity import BibliographicRecord, Identifier


def _abstract_from_index(value):
    # Preserved algorithm from discovery_methods._abstract_from_index.
    if not isinstance(value, dict):
        return None
    words = {}
    for word, positions in value.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int) and position >= 0:
                words[position] = str(word)
    return " ".join(words[index] for index in sorted(words)) or None


def _text(value):
    return value if isinstance(value, str) and value.strip() else None


def _year(value):
    try:
        number = int(value)
        return number if 1 <= number <= 9999 else None
    except (TypeError, ValueError):
        return None


class MetadataProvider:
    version = "keyword/v1"
    network = True

    def __init__(self, name):
        if name not in {"openalex", "crossref", "europepmc", "semantic_scholar"}:
            raise ContractError("unknown metadata adapter")
        self.name = name
        self.hosts = {"openalex": ("api.openalex.org",), "crossref": ("api.crossref.org",),
            "europepmc": ("www.ebi.ac.uk",), "semantic_scholar": ("api.semanticscholar.org",)}[name]

    def request(self, plan, cursor):
        size = plan.page_size
        if self.name == "openalex":
            base, params = "https://api.openalex.org/works", {
                "search": plan.query, "per_page": size, "cursor": cursor or "*"}
        elif self.name == "crossref":
            base, params = "https://api.crossref.org/works", {
                "query.bibliographic": plan.query, "rows": size, "cursor": cursor or "*"}
        elif self.name == "europepmc":
            base, params = "https://www.ebi.ac.uk/europepmc/webservices/rest/search", {
                "query": plan.query, "format": "json", "resultType": "core", "pageSize": size,
                "cursorMark": cursor or "*"}
        else:
            base, params = "https://api.semanticscholar.org/graph/v1/paper/search", {
                "query": plan.query, "offset": cursor or "0", "limit": size,
                "fields": "title,abstract,externalIds,year,venue,authors"}
        return RequestSpec(base + "?" + urlencode(params))

    def normalize(self, body, plan, cursor):
        data = json.loads(body)
        if self.name == "openalex":
            items = data["results"]
            total, nxt = data["meta"].get("count"), data["meta"].get("next_cursor")
        elif self.name == "crossref":
            items = data["message"]["items"]
            total, nxt = data["message"].get("total-results"), data["message"].get("next-cursor")
        elif self.name == "europepmc":
            items = data["resultList"]["result"]
            total, nxt = data.get("hitCount"), data.get("nextCursorMark")
        else:
            items = data["data"]
            total = data.get("total")
            nxt = str(data["next"]) if data.get("next") is not None else None
        if not isinstance(items, list) or any(not isinstance(x, dict) for x in items):
            raise ContractError("malformed provider records")
        if not items or (self.name != "openalex" and len(items) < plan.page_size) or nxt == (cursor or "*"):
            nxt = None
        limit = self.name == "semantic_scholar" and nxt is not None and int(nxt) >= 1000
        observations = []
        for item in items:
            try:
                observations.append(self._observation(item))
            except (ValueError, TypeError, KeyError, AttributeError):
                observations.append(CandidateObservation(None, BibliographicRecord(), item, "normalization_failed"))
        return DiscoveryPage(tuple(observations), str(nxt) if nxt else None,
                             int(total) if total is not None else None, limit)

    def _observation(self, item):
        ids, authors, year, source, abstract = [], [], None, None, None
        record_id = None
        if self.name == "openalex":
            record_id = _text(item.get("id"))
            doi, title, year = item.get("doi"), item.get("title"), item.get("publication_year")
            abstract = _abstract_from_index(item.get("abstract_inverted_index"))
            authors = [x["author"]["display_name"] for x in item.get("authorships", [])
                       if x.get("author", {}).get("display_name")]
            source = ((item.get("primary_location") or {}).get("source") or {}).get("display_name")
            if record_id:
                ids.append(Identifier("openalex", record_id))
            external = item.get("ids") or {}
            for key in ("pmid", "pmcid"):
                if external.get(key):
                    ids.append(Identifier(key, str(external[key]).rsplit("/", 1)[-1]))
        elif self.name == "crossref":
            doi = item.get("DOI")
            record_id, title = _text(doi), " ".join(item.get("title") or [])
            abstract = item.get("abstract")
            authors = [" ".join(filter(None, (x.get("given"), x.get("family"))))
                       for x in item.get("author") or []]
            dates = (item.get("published") or {}).get("date-parts") or []
            year = dates[0][0] if dates and dates[0] else None
            source = " ".join(item.get("container-title") or [])
        elif self.name == "europepmc":
            doi, title, year = item.get("doi"), item.get("title"), item.get("pubYear")
            record_id = (str(item.get("source") or "") + ":" + str(item["id"])) if item.get("id") else None
            if item.get("source") == "MED" and item.get("id"):
                ids.append(Identifier("pmid", str(item["id"])))
            if item.get("pmcid"):
                ids.append(Identifier("pmcid", item["pmcid"]))
            if record_id:
                ids.append(Identifier("europepmc.record", record_id))
            abstract, source = item.get("abstractText"), item.get("journalTitle")
            authors = [x["fullName"] for x in (item.get("authorList") or {}).get("author", []) if x.get("fullName")]
        else:
            external = item.get("externalIds") or {}
            doi, title, year = external.get("DOI"), item.get("title"), item.get("year")
            record_id = _text(item.get("paperId"))
            if record_id:
                ids.append(Identifier("semantic_scholar", record_id))
            for key, scheme in (("PubMed", "pmid"), ("PubMedCentral", "pmcid")):
                if external.get(key):
                    ids.append(Identifier(scheme, str(external[key])))
            abstract, source = item.get("abstract"), item.get("venue")
            authors = [x["name"] for x in item.get("authors") or [] if x.get("name")]
        if doi:
            ids.append(Identifier("doi", str(doi)))
        record = BibliographicRecord(_text(title), _text(abstract), tuple(x for x in authors if x),
                                     _year(year), _text(source), tuple(ids))
        # Bad identifiers must preserve the observation for review, not invalidate its whole page.
        return CandidateObservation(record_id, record, item)
