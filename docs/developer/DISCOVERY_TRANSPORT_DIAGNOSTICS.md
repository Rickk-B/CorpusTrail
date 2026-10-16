# Discovery transport diagnostics

The built-in metadata transport is standard-library `urllib.request`, with its
default HTTPS trust/hostname checks and environment/system proxy handling.
It refuses redirects, bounds reads to the configured maximum plus one detection
byte, and uses the configured socket timeout. That timeout is not a newly claimed
whole-operation deadline. No certificate installation or TLS bypass is provided.

## No-response failures versus HTTP responses

`retryable_error` is an existing operational category, not proof of rate limiting.
HTTP 429 is a recorded rate-limit response; HTTP 500/503 are server responses.
`http_status: null` means no HTTP response was recorded. Older generic
`ProviderTransportError` records cannot establish their underlying cause.

The local application now inspects typed urllib causes and records fixed
certificate/TLS/DNS/timeout/refusal exception categories through the existing
executor's type-name-only diagnostic field. Unknown failures, including opaque
proxy/tunnel errors, stay generic. A DNS/refusal primitive does not identify
whether the failing peer was a provider or a configured proxy. Exception strings,
credentials, certificate paths, proxy URLs and stack traces are not persisted.
The original transport, scientific executor, retry states, attempt/wait limits,
identity rules and historical records are unchanged. The application derives
read-only explanations from preserved request results, including older records.

## One optional native-only offline check

After installing the updated development wheel, run this single command using
the same interpreter that launches CorpusTrail:

```bash
~/CorpusTrail/.venv-py313/bin/python -c 'import json; from corpustrail.application.discovery import offline_environment_report; print(json.dumps(offline_environment_report(), indent=2))'
```

It reads only Python/TLS configuration, counts trust certificates and reports
whether overrides/proxy configuration are present. It performs no DNS lookup,
network request, project access or writes, and prints neither paths nor secrets.
It needs no Codex installation, elevated privilege, remote agent or system change.
The equivalent developer wrapper is `python tools/discovery_environment_diagnostic.py`.

A missing default trust store is useful evidence, not a complete native diagnosis.
A populated store likewise does not prove the Europe PMC certificate chain will
validate. No live provider request is included or authorized by this diagnostic.
The reported MacBook failure remains causally unresolved without native evidence;
hosted macOS fixture success cannot prove the MacBook's trust/proxy setup is correct.
