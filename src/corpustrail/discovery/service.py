"""Bounded execution, immutable observations, and explicit exact enrollment."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime

from corpustrail._internal.database import connection
from corpustrail._internal.pipeline import append, artifact, events, preserve, events_in_connection, artifact_in_connection
from corpustrail._internal.values import ContractError, canonical, identifier, now
from corpustrail.identity import SourceReference
from .contracts import SearchPlan, record_from_dict


class DiscoveryService:
    def __init__(self, project):
        self.project = project

    def plan(self, provider, *, run_id, query=None, concept_id=None, created_at=None, **bounds):
        config = self.project.config
        if not any(x.provider_id == provider.name and x.adapter == provider.name for x in config.providers):
            raise ContractError("adapter must be explicitly configured")
        if concept_id is not None:
            concepts = [x for x in config.search if x.concept_id == concept_id]
            if len(concepts) != 1:
                raise ContractError("unknown configured search concept")
            query = query or concepts[0].label
        plan = SearchPlan(config.project_id, run_id, provider.name, provider.version, query,
                          self.project.configuration_history()[-1]["event_id"], created_at or now(),
                          concept_id, **bounds)
        plan.validate()
        return plan

    def execute(self, plan, provider, *, transport=None, confirm_external=False, clock=now, sleeper=None):
        from corpustrail.providers.network import UrlLibTransport, outcome, rate_headers, retry_after, safe_url, sleep
        plan.validate()
        if (plan.project_id != self.project.config.project_id or plan.provider != provider.name
                or plan.adapter_version != provider.version
                or plan.config_event_id != self.project.configuration_history()[-1]["event_id"]):
            raise ContractError("stale, foreign or changed discovery plan")
        configured = [x for x in self.project.config.providers if x.provider_id == provider.name and x.adapter == provider.name]
        if len(configured) != 1:
            raise ContractError("provider no longer configured")
        transport = transport or UrlLibTransport()
        if (provider.network or transport.network) and confirm_external is not True:
            raise ContractError("external transfer requires explicit confirmation")
        prior = events(self.project, scope_id=plan.run_id, kind="discovery_plan")
        if prior and prior[0]["payload"] != asdict(plan):
            raise ContractError("run ID already reserved by another plan")
        append(self.project, "discovery_plan", plan.run_id, asdict(plan), config_event_id=plan.config_event_id)
        finished = events(self.project, scope_id=plan.run_id, kind="discovery_complete")
        if finished:
            return finished[0]["payload"]
        if events(self.project, scope_id=plan.run_id, kind="request_started"):
            raise ContractError("interrupted execution requires explicit inspection; no implicit replay")
        from corpustrail import __version__
        headers = {"Accept": "application/json", "User-Agent": "CorpusTrail/" + __version__}
        credential = configured[0].credential_env
        if credential:
            secret = os.environ.get(credential)
            if not secret:
                append(self.project, "discovery_complete", plan.run_id,
                       {"outcome": "requires_configuration", "error": "missing_credential", "observations": 0,
                        "logical_requests": 0, "physical_attempts": 0, "next_cursor": None,
                        "provider": provider.name, "credential_env": credential,
                        "message": f'Set {credential} for {provider.name}; use a new run ID after configuration.'}, config_event_id=plan.config_event_id)
                return events(self.project, scope_id=plan.run_id, kind="discovery_complete")[0]["payload"]
            if provider.name not in {"semantic_scholar", "openalex"}:
                raise ContractError("credential headers unsupported for this adapter")
            headers["x-api-key" if provider.name == "semantic_scholar" else "Authorization"] = (
                secret if provider.name == "semantic_scholar" else "Bearer " + secret)
        cursor, count, physical, status, next_cursor = None, 0, 0, "exhausted", None
        logical = 0
        for page_number in range(1, plan.max_pages + 1):
            spec = provider.request(plan, cursor)
            safe_url(spec.url, provider.hosts)
            logical += 1
            request_id = identifier("request", {"plan": plan.plan_id, "page": page_number, "cursor": cursor, "spec": asdict(spec)})
            body, final_state = None, None
            for attempt in range(1, plan.max_attempts + 1):
                at = clock()
                attempt_id = identifier("attempt", [request_id, attempt])
                append(self.project, "request_started", plan.run_id, {
                    "request_id": request_id, "attempt_id": attempt_id, "page": page_number,
                    "attempt": attempt, "cursor": cursor, "request": asdict(spec), "timestamp": at},
                    config_event_id=plan.config_event_id, exclusive=True)
                physical += 1
                try:
                    response = transport.request(spec.url, method=spec.method, headers=headers, body=None)
                    safe_url(response.final_url, provider.hosts)
                    state, http = outcome(response.status), response.status
                    body = response.body
                    sha = preserve(self.project, body, "application/json", at)
                    delay = retry_after(response.headers, clock=datetime.fromisoformat(at))
                    error, rate = None, rate_headers(response.headers)
                except Exception as exc:
                    # Typed error name only; credentials never enter logs.
                    state, http, sha, delay, body = "retryable_error", None, None, None, None
                    error = type(exc).__name__
                    rate = {}
                    if isinstance(exc, ContractError):
                        state = "permanent_error"
                wait = delay if delay is not None else plan.retry_delay_seconds
                will_retry = state == "retryable_error" and attempt < plan.max_attempts and wait <= plan.max_retry_wait_seconds
                append(self.project, "request_result", plan.run_id, {
                    "request_id": request_id, "attempt_id": attempt_id, "attempt": attempt,
                    "timestamp": at, "status": state, "http_status": http, "error": error,
                    "rate_limit": rate,
                    "retry_after_seconds": delay, "will_retry": will_retry,
                    "retry_blocked": state == "retryable_error" and wait > plan.max_retry_wait_seconds},
                    source_sha256=sha, config_event_id=plan.config_event_id)
                final_state = state
                if not will_retry:
                    break
                (sleeper or sleep)(wait)
            if final_state != "success":
                status = final_state
                next_cursor = cursor
                break
            try:
                page = provider.normalize(body, plan, cursor)
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                append(self.project, "request_result", plan.run_id, {"request_id": request_id,
                    "status": "malformed_response", "error": type(exc).__name__, "timestamp": clock()},
                    source_sha256=sha, config_event_id=plan.config_event_id)
                status, next_cursor = "malformed_response", cursor
                break
            # Record all observations before attempting identity or canonical metadata selection.
            for index, observation in enumerate(page.observations):
                payload = {"schema": "corpustrail-candidate-observation/v1", "provider": provider.name,
                    "provider_version": provider.version, "provider_record_id": observation.provider_record_id,
                    "query": plan.query, "concept_id": plan.concept_id, "run_id": plan.run_id,
                    "request_id": request_id, "record_index": index, "raw_record": observation.raw_record,
                    "record": asdict(observation.record), "identity_evidence": observation.identity_evidence,
                    "response_sha256": sha, "source_uri": spec.url, "observed_at": clock()}
                append(self.project, "candidate_observation", plan.run_id, payload,
                       source_sha256=sha, config_event_id=plan.config_event_id)
                count += 1
            next_cursor = page.next_cursor
            if page.provider_limit:
                status = "truncated_provider_limit"
                break
            if not next_cursor:
                break
            if page_number == plan.max_pages:
                status = "truncated_page_limit"
            cursor = next_cursor
        result = {"outcome": status, "observations": count, "logical_requests": logical,
                  "physical_attempts": physical, "next_cursor": next_cursor}
        append(self.project, "discovery_complete", plan.run_id, result, config_event_id=plan.config_event_id)
        return result

    def observations(self, run_id=None):
        return events(self.project, scope_id=run_id, kind="candidate_observation")

    def canonicalize(self, run_id, *, approve_new_identities=False, approve_aliases=False):
        # Approval is explicit and concerns identity only, never corpus membership.
        if approve_new_identities is not True or approve_aliases is not True:
            raise ContractError("canonicalization requires explicit identity/source approval")
        if not events(self.project, scope_id=run_id, kind="discovery_complete"):
            raise ContractError("incomplete discovery must be inspected before canonicalization")
        results = []
        for observation in self.observations(run_id):
            obs_id, payload = observation["event_id"], observation["payload"]
            linked = events(self.project, scope_id=obs_id, kind="canonical_link")
            if linked:
                results.append(linked[0]["payload"])
                continue
            try:
                if payload["identity_evidence"] == "normalization_failed":
                    raise ContractError("provider record normalization failed; inspect preserved raw record")
                record = record_from_dict(payload["record"])
                raw = artifact(self.project, payload["response_sha256"]).read_bytes()
                # Co-occurrence in an explicitly approved provider record is exact alias evidence.
                source = SourceReference("provider:" + payload["provider"],
                    payload["provider_record_id"] or obs_id, payload["response_sha256"], len(raw),
                    payload["provider"], payload["observed_at"], media_type="application/json", identity_status="verified")
                plan = self.project.identities.plan(record, source)
                paper_id = self.project.identities.apply(plan, approve_new_identity=True, approve_aliases=True)
                link = {"observation_id": obs_id, "paper_id": paper_id, "enrollment_plan_id": plan.plan_id,
                        "identity_method": "approved_exact_provider_identifiers_or_origin/v1",
                        "action": plan.action, "aliases_added": [list(x) for x in plan.new_aliases]}
                append(self.project, "canonical_link", obs_id, link, paper_id=paper_id)
                results.append(link)
            except (ContractError, KeyError) as exc:
                issue = {"observation_id": obs_id, "status": "unresolved", "reason": str(exc)}
                append(self.project, "identity_issue", obs_id, issue)
                results.append(issue)
        return results

    def metadata(self, paper_id):
        """Canonical view: first nonempty enrolled value, never implicit provider precedence.

        Stable provenance is selected by original observed_at then observation ID. Conflicts remain visible.
        This conservative v1 selector is a view, not an overwrite or scientific authority.
        """
        with connection(self.project.database_path) as db:
            return self._metadata(db, paper_id)

    def _metadata(self, db, paper_id):
        """Shared selector within a caller's read snapshot; same field-selection semantics."""
        observations = self.project.identities._observations(db, paper_id)
        ordered = sorted(observations, key=lambda x: (x["source"]["observed_at"], x["observation_id"]))
        fields, provenance, alternatives = {}, {}, {}
        for key in ("title", "abstract", "authors", "year", "source"):
            values = [x for x in ordered if x["record"][key] not in (None, [], "")]
            fields[key] = values[0]["record"][key] if values else ([] if key == "authors" else None)
            provenance[key] = values[0]["observation_id"] if values else None
            alternatives[key] = [{"value": x["record"][key], "observation_id": x["observation_id"]} for x in values]
        ids = [{"scheme": x[0], "value": x[1]} for x in db.execute(
            "SELECT scheme,normalized_value FROM paper_identifiers WHERE paper_id=? ORDER BY scheme,normalized_value", (paper_id,))]
        if fields["abstract"] is None:
            recovered = [x for x in events_in_connection(db, kind="representation", paper_id=paper_id)
                         if x["payload"]["representation"] == "abstract" and x["payload"]["trusted"]]
            if recovered:
                selected = sorted(recovered, key=lambda x: (x["payload"]["created_at"], x["event_id"]))[0]
                fields["abstract"] = artifact_in_connection(self.project, db, selected["source_sha256"]).read_text(encoding="utf-8")
                provenance["abstract"] = selected["event_id"]
                alternatives["abstract"] = [{"value": artifact_in_connection(self.project, db, x["source_sha256"]).read_text(encoding="utf-8"),
                    "observation_id": x["event_id"]} for x in recovered]
        return {"paper_id": paper_id, "selection_rule": "first_supported_nonempty/v1", "fields": fields,
                "field_provenance": provenance, "alternatives": alternatives, "identifiers": ids}
