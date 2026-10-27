# Optional ChatGPT-plan relevance assessment

This optional adapter is implemented and tested with **offline protocol fixtures**.
It has not been verified against a real ChatGPT account or scientifically validated.
Core/manual workflows need no account, model or runtime dependency. CP1–10 and the
presentation refresh remain researcher-accepted; RIS/demo acceptance remains pending.

## Install in an isolated environment

Use the exact development bundle linked in the current
[development handover](../developer/DEVELOPMENT_BUILDS.md#current-handover).
An older wheel with the same `0.1.0a3.dev0` version is insufficient. Download the
bundle, extract it into `~/Downloads/CorpusTrail-ChatGPT/`, and verify its wheel
SHA-256 against the delivered receipt before installation. Stop the running app.
Using the researcher's existing environment:

```bash
source ~/CorpusTrailDemo/.venv/bin/activate
cd ~/Downloads/CorpusTrail-ChatGPT
shasum -a 256 corpus_trail-0.1.0a3.dev0-py3-none-any.whl
python -m pip install --no-index --no-deps --force-reinstall ./corpus_trail-0.1.0a3.dev0-py3-none-any.whl
python -m pip install './corpus_trail-0.1.0a3.dev0-py3-none-any.whl[chatgpt]' 'PyJWT==2.15.1' 'cryptography==50.0.2' 'cffi==2.1.1' 'pycparser==3.12'
corpustrail --version
corpustrail app --open-browser
```

The optional extra installs separately licensed cryptographic libraries from the
Python package index. No OpenAI SDK, API key, model download or paid service is
installed. Installation does not sign in or make a model request. Core remains
`dependencies = []`. From an approved source checkout, the equivalent optional
installation is `python -m pip install '.[chatgpt]'`.

Software replacement preserves independently located research projects. Do not
replace a research project with a demo, remove originals, or interpret a software
reinstall as undoing a scientific database upgrade.

## Local inspection before sign-in

These existing commands create a new synthetic, scoped project without networking.
Use this destination only if it does not exist; retain any existing project and
choose another unused name rather than overwriting it.

```bash
corpustrail demo ~/CorpusTrailDemo/ChatGPT-evaluation
corpustrail app ~/CorpusTrailDemo/ChatGPT-evaluation --open-browser
```

Inspect Corpus, the available abstract and **Models → Open ChatGPT assessment**.
Do not connect during an offline tour. To close, press Ctrl+C in the launching
terminal and wait for its prompt. To reopen, run only the same `corpustrail app`
command; do not rerun demo creation. Manual Guided Review remains available.

## Researcher walkthrough

Live sign-in and assessment have **not** been executed by automated acceptance.
Owner participation and the no-extra-charge decision below are still pending.

1. Open a disposable, explicitly synthetic project for initial evaluation. The
   [offline demo/RIS guide](RIS_EXCHANGE.md) creates one without overwriting an
   existing directory. Inspect its title, abstracts and missing-evidence states.
2. In **Candidate sets**, explicitly freeze a selection of one to ten papers.
   In **Reference collections**, select or explicitly create a suitable version.
   This alpha protocol requires a reference-version identity even for its first
   remote adapter; it never fabricates a human-attested reference. For a synthetic
   walkthrough, any examples must be deliberately labelled as such by their reader.
   Eligible examples using metadata or abstracts are included; full-text examples
   are refused, not silently truncated or downgraded. Large reference inputs require
   a different explicitly chosen version/selection, not hidden omission.
3. Open **Research tools → Models → Open ChatGPT assessment**. The page is local:
   opening it neither signs in nor contacts a provider. Manual review remains
   separately available. Existing legacy endpoint configuration is for structured
   Knowledge extraction, not a billing fallback for this relevance adapter.
4. When owner sign-in is authorized, select **Continue with ChatGPT**. OpenAI handles
   the first account/workspace choice and permissions. Reconnection reuses that
   registration and verifies the same bound identity; this initial interface does
   not provide multi-account switching. No password or token belongs in chat.
   The separate loopback callback offers **Back to CorpusTrail**. Acknowledge the
   one-time plan-use notice. The app validates signed identity, nonce, registration
   and granted plan scope; a successful identity login alone is insufficient.
5. Explicitly **Refresh available models** and choose one offered by that account.
   There is no guessed default or hidden model substitution. Enter the acting
   person and select the frozen candidate/reference versions by readable names.
6. **Freeze inputs and preview cloud request** preserves exact local inputs but
   sends no model request. Inspect every selected title/abstract, corpus criteria,
   instructions, eligible reference text, model, destination and request hashes.
   Missing abstracts remain explicitly missing. Nothing is full-text evidence merely
   because it was imported or a model produced an answer.
7. **Live assessment stays blocked until zero-extra-charge conditions are verified.**
   See below. After that separate verification and owner authorization, check the
   exact-transfer consent and choose **Authorize and assess**. Each paper is a
   separately reserved, bounded request. Changing the actual request invalidates
   earlier consent. There are no tools, filesystem access, external URL following,
   automatic retries or API-key billing fallback.
8. Inspect stored proposals in **Curation and audits**. The paper inspector shows
   the requested/reported model, rationale, sufficiency, uncertainty and limitations,
   alongside the exact frozen input and provenance. No generated confidence is
   presented as calibrated probability. Failure is a separate state, not exclusion
   or an uncertain scientific judgment. A limit/error stops later submissions;
   completed work persists and the remaining tail stays unassessed.
9. Use existing assisted or manual human review. A saved assessment is a proposal;
   human observation and authorized **corpus confirmation remain separate actions**.
   No preview, model response, cancellation or reference change publishes membership.
10. Close with Ctrl-C in the launching terminal. Reopen the same project using the
    normal app launcher; inspect preserved Curation history. No request reruns on
    startup. Connection records persist separately from scientific projects; a model
    list is explicitly refreshed again rather than silently queried on page open.
11. **Disconnect** stops new submissions and clears local access/refresh/ID tokens.
    It attempts provider revocation. If unconfirmed, also disconnect CorpusTrail in
    ChatGPT **Settings → Security and login → Sign in with ChatGPT**. Completed
    scientific history remains in the project. Non-secret registration/host mapping
    stays available for a later sign-in; reconnect is never an automatic retry.

## Zero extra charges and cloud boundary

[OpenAI's official open-source route](https://developers.openai.com/siwc/token-sharing-open-source)
uses public-client OAuth and the public Responses endpoint, not API-key billing.
Actual eligibility is account/workspace-dependent. [ChatGPT usage controls](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions)
can allow credits after plan limits. Neither sign-in, plan scope, a model catalog,
a weekly allowance nor a consent checkbox establishes that extra charges are
prevented. No documented request-level "never use credits" switch was established.

The adapter therefore defaults to a **closed inference gate**. There is no HTTP
form that grants no-charge verification. Before the first live test, the owner
must verify the applicable credit-fallback setting is disabled and supply a
sanitized observation for the explicitly authorized account/registration, followed
by separate authorization of one bounded synthetic payload. Do not send tokens,
passwords, raw authorization URLs or broad account dumps. Account-bound verification
has an expiry and is invalidated on a new sign-in. No billing settings are changed,
credits purchased or usage limits automatically retried by CorpusTrail.

Actual text leaves the computer only after those conditions and exact consent.
`store:false` is required but is **not a guarantee of zero provider retention**;
OpenAI's applicable service/privacy terms govern cloud processing. Local project
stores retain frozen text, exact wire requests, actual responses, hashes and
non-authoritative proposals/failures as researcher-owned scientific history.

## Security, compatibility and limitations

Credentials reside outside projects in a dedicated per-user store: macOS
Application Support, Windows LocalAppData, or Linux XDG config. POSIX files require
private account ownership and 0600 permissions; Windows records use current-user
DPAPI. No other application's credentials are discovered. No secrets appear in
project configuration, provenance, ordinary exports or software/recovery bundles.
Back up only the explicitly owned scientific/source material, not the private
credential store. Removing software does not delete research projects.

The versioned extension preserves legacy offline records and their original
shapes. There is no scientific schema migration or reference/membership taxonomy
change. Existing assertion extraction is unchanged. Optional dependency/platform
verification and final artifact identities are recorded in the handover.

The initial capability is title/abstract assessment with bounded metadata/abstract
reference examples: at most ten papers per explicit authorization, 32,000 request
bytes and 20,000 retained terminal-response bytes per paper. These are operational
request budgets, not a corpus collection-size limit. Over-budget input fails
explicitly. Streaming failures preserve categories, exact hashes and bounded
partial output with any truncation clearly identified; they never invent a result.

Offline fixtures demonstrate protocol and authority boundaries, not real-account
interoperability, native Safari compatibility or scientific relevance performance.
Native MacBook Europe PMC transport causation remains separately unresolved.
