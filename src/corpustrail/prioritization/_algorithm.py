"""Opt-in broad-corpus ordering, with no manifest, authority or stopping API.

Artifacts are self-contained JSON, content-bound and published without clobber.
No pickle/model code is deserialized. Insufficient labels are retained but not fit.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Protocol, Sequence

SCHEMA = "corpustrail-prioritization/v0"
CONCEPT = "broad_topic_corpus_membership"
NOTICE = "Non-authoritative review-ordering aid; not an inclusion, exclusion or stopping decision."


def canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def digest(value) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must specify a timezone")
    return parsed


def seal(kind: str, value: dict) -> dict:
    body = {"schema": SCHEMA, "kind": kind, **deepcopy(value)}
    return {**body, "artifact_id": digest(body)}


def check(value: dict, kind: str) -> None:
    if (value.get("schema") != SCHEMA or value.get("kind") != kind
            or value.get("artifact_id") != digest({k: v for k, v in value.items()
                                                   if k != "artifact_id"})):
        raise ValueError(f"invalid or changed {kind} artifact")


def write_new(path: str | Path, value: dict) -> None:
    """Publish complete bytes atomically, refusing even a dangling existing link."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".prioritization-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(name, target)
    finally:
        os.unlink(name)


def candidate(row: dict) -> dict:
    """Allowlist scientific text inputs; never forward judgments or provider arms."""
    paper_id = row.get("paper_id")
    if not isinstance(paper_id, str) or not paper_id.strip():
        raise ValueError("canonical paper_id is required; identity must be resolved upstream")
    title, abstract = row.get("title") or "", row.get("abstract") or ""
    if not isinstance(title, str) or not isinstance(abstract, str):
        raise ValueError("title and abstract must be strings")
    evidence = row.get("evidence_availability") or {}
    if not isinstance(evidence, dict):
        raise ValueError("evidence_availability must be an object")
    if set(evidence) - {"abstract_available", "verified_full_text_available", "representation"}:
        raise ValueError("unrecognized evidence availability field")
    if "abstract_available" in evidence and (type(evidence["abstract_available"]) is not bool
                                             or evidence["abstract_available"] != bool(abstract.strip())):
        raise ValueError("abstract availability disagrees with supplied text")
    if "verified_full_text_available" in evidence and type(evidence["verified_full_text_available"]) is not bool:
        raise ValueError("verified_full_text_available must be boolean")
    if evidence.get("representation") not in (None, "metadata", "abstract", "structured_text", "pdf_text", "ocr_text"):
        raise ValueError("unknown evidence representation")
    return {"paper_id": paper_id, "title": title, "abstract": abstract,
            "evidence_availability": {**evidence, "abstract_available": bool(abstract.strip())}}


def candidates(rows: Sequence[dict]) -> list[dict]:
    result = [candidate(row) for row in rows]
    if not result or len({row["paper_id"] for row in result}) != len(result):
        raise ValueError("candidate population must be nonempty with unique paper_id values")
    return result


def training_snapshot(*, project_id: str, rows: list[dict], label_cutoff: str,
                      eligibility_policy: str, parent_snapshot_id: str | None = None,
                      input_provenance: dict | None = None) -> dict:
    """Caller supplies independently audited human eligibility, never model labels.

    Each row: candidate fields plus label, labelled_at, provenance_class,
    relevance_concept, source_artifact, source_sha256 and source_record.
    Input order is preserved explicitly because it is part of fitting provenance.
    """
    if not project_id.strip() or not eligibility_policy.strip():
        raise ValueError("project and human eligibility policy are required")
    cutoff = _time(label_cutoff)
    texts = candidates(rows)
    normalized = []
    for row, text in zip(rows, texts):
        if (row.get("provenance_class") != "authoritative_human_judgment"
                or row.get("relevance_concept") != CONCEPT):
            raise ValueError("only eligible human broad-corpus judgments may fit this prioritizer")
        if row.get("label") not in ("include", "exclude", "insufficient_evidence"):
            raise ValueError("invalid human label")
        available_by = row.get("label_available_by") or row.get("labelled_at")
        if not available_by or _time(available_by) > cutoff:
            raise ValueError("label is later than the approved cutoff")
        if row.get("labelled_at") and _time(row["labelled_at"]) > _time(available_by):
            raise ValueError("label availability predates the judgment")
        if any(not isinstance(row.get(key), str) or not row[key].strip()
               for key in ("source_artifact", "source_sha256", "source_record")):
            raise ValueError("human source artifact/hash/record lineage is required")
        source_hash = row["source_sha256"].removeprefix("sha256:")
        if len(source_hash) != 64 or any(c not in "0123456789abcdef" for c in source_hash):
            raise ValueError("invalid human source SHA-256")
        normalized.append({**text, **{key: row[key] for key in (
            "label", "provenance_class", "relevance_concept",
            "source_artifact", "source_sha256", "source_record")},
            "labelled_at": row.get("labelled_at"), "label_available_by": available_by,
            "timestamp_basis": row.get("timestamp_basis", "recorded_judgment_time")})
    if {r["label"] for r in normalized if r["label"] != "insufficient_evidence"} != {"include", "exclude"}:
        raise ValueError("fitting requires both include and exclude human examples")
    return seal("training_snapshot", {
        "project_id": project_id, "label_cutoff": label_cutoff,
        "eligibility_policy": eligibility_policy, "parent_snapshot_id": parent_snapshot_id,
        "rows": normalized, "insufficient_policy": "preserve_but_do_not_fit",
        "relevance_concept": CONCEPT,
        "input_provenance": deepcopy(input_provenance or {}),
    })


class Prioritizer(Protocol):
    """Model-agnostic adapter. Scores order work; they never decide membership."""
    method: str
    version: str

    def fit(self, snapshot: dict, *, purpose: str, parent_model_id: str | None = None) -> dict: ...
    def scores(self, model: dict, rows: Sequence[dict]) -> list[float]: ...


class TfidfLogistic:
    method = "tfidf_logistic"
    version = "0"

    @staticmethod
    def _text(row: dict) -> str:
        return (row["title"] + "\n" + row["abstract"]).strip()

    def fit(self, snapshot: dict, *, purpose: str, parent_model_id: str | None = None) -> dict:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        import sklearn
        import numpy
        import scipy

        check(snapshot, "training_snapshot")
        # Validate eligibility even if a caller has manually constructed a sealed object.
        rebuilt = training_snapshot(**{key: snapshot[key] for key in (
            "project_id", "rows", "label_cutoff", "eligibility_policy", "parent_snapshot_id", "input_provenance")})
        if rebuilt != snapshot:
            raise ValueError("training snapshot validation mismatch")
        if purpose not in ("evaluation_reconstruction", "operational"):
            raise ValueError("model purpose must explicitly separate evaluation from operations")
        train = [r for r in snapshot["rows"] if r["label"] != "insufficient_evidence"]
        vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1, sublinear_tf=True)
        estimator = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000,
                                       solver="liblinear", random_state=20260916)
        matrix = vectorizer.fit_transform([self._text(row) for row in train])
        estimator.fit(matrix, [int(row["label"] == "include") for row in train])
        params = vectorizer.get_params()
        params["dtype"] = "float64"
        params["ngram_range"] = list(params["ngram_range"])
        return seal("model", {
            "method": self.method, "method_version": self.version, "purpose": purpose,
            "parent_model_id": parent_model_id, "training_snapshot_id": snapshot["artifact_id"],
            "training_snapshot": snapshot, "non_authoritative": True,
            "features": "title + newline + abstract; evidence availability recorded, not fitted",
            "versions": {"sklearn": sklearn.__version__, "numpy": numpy.__version__, "scipy": scipy.__version__},
            "vectorizer_parameters": params, "estimator_parameters": estimator.get_params(),
            "vocabulary": {k: int(v) for k, v in vectorizer.vocabulary_.items()},
            "idf": vectorizer.idf_.tolist(), "coefficients": estimator.coef_.tolist(),
            "intercept": estimator.intercept_.tolist(), "classes": estimator.classes_.tolist(),
            "iterations": estimator.n_iter_.tolist(),
        })

    def scores(self, model: dict, rows: Sequence[dict]) -> list[float]:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        import numpy as np
        import sklearn
        import scipy

        check(model, "model")
        if model["method"] != self.method or model["method_version"] != self.version:
            raise ValueError("incompatible prioritizer adapter")
        if model["versions"] != {"sklearn": sklearn.__version__, "numpy": np.__version__, "scipy": scipy.__version__}:
            raise ValueError("reproduction requires the recorded numerical-library versions")
        params = dict(model["vectorizer_parameters"])
        params["dtype"] = np.float64
        params["ngram_range"] = tuple(params["ngram_range"])
        params["vocabulary"] = model["vocabulary"]
        vectorizer = TfidfVectorizer(**params)
        vectorizer.idf_ = np.array(model["idf"])
        estimator = LogisticRegression(**model["estimator_parameters"])
        estimator.classes_ = np.array(model["classes"])
        estimator.coef_ = np.array(model["coefficients"])
        estimator.intercept_ = np.array(model["intercept"])
        estimator.n_features_in_ = len(model["idf"])
        return estimator.predict_proba(vectorizer.transform([self._text(r) for r in candidates(rows)]))[:, 1].tolist()


def rank(adapter: Prioritizer, model: dict, rows: list[dict], *, created_at: str,
         population_source_sha256: str, previous_run_id: str | None = None) -> dict:
    check(model, "model")
    if model.get("non_authoritative") is not True:
        raise ValueError("prioritization cannot grant authority")
    raw_hash = population_source_sha256.removeprefix("sha256:")
    if len(raw_hash) != 64 or any(c not in "0123456789abcdef" for c in raw_hash):
        raise ValueError("candidate source SHA-256 is required")
    _time(created_at)
    items = candidates(rows)
    if model["purpose"] == "evaluation_reconstruction" and (
        {r["paper_id"] for r in items} & {r["paper_id"] for r in model["training_snapshot"]["rows"]}
    ):
        raise ValueError("evaluation candidates overlap training labels")
    scores = adapter.scores(model, items)
    if len(scores) != len(items) or any(not math.isfinite(score) for score in scores):
        raise ValueError("prioritizer must return one finite score per candidate")
    result = []
    for row, score in zip(items, scores):
        result.append({"paper_id": row["paper_id"], "raw_score": score,
                       "evidence_inputs_used": ["title"] + (["abstract"] if row["abstract"].strip() else []),
                       "evidence_availability": row["evidence_availability"],
                       "non_authoritative": True})
    result.sort(key=lambda row: (-row["raw_score"], hashlib.sha256(row["paper_id"].encode("utf-8")).hexdigest()))
    result = [{**row, "rank": index, "method": adapter.method, "method_version": adapter.version,
               "training_snapshot_id": model["training_snapshot_id"], "timestamp": created_at}
              for index, row in enumerate(result, 1)]
    return seal("ranking", {
        "created_at": created_at, "model_id": model["artifact_id"],
        "training_snapshot_id": model["training_snapshot_id"], "purpose": model["purpose"],
        "project_id": model["training_snapshot"]["project_id"],
        "method": adapter.method, "method_version": adapter.version,
        "population_source_sha256": population_source_sha256,
        "candidate_population": items, "candidate_population_sha256": digest(items),
        "previous_run_id": previous_run_id, "notice": NOTICE, "non_authoritative": True,
        "scores": result,
    })
