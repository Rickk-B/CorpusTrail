# Evaluate the researcher-accepted CP10 alpha on macOS

CP1–10 and the warm visual refresh are researcher-accepted. This is the accepted
alpha baseline, not a beta, public release, native installer or validated real
assessment engine. These instructions were checked against the delivered CLI,
tutorial, shutdown implementation and accepted installed-package evidence; no
new Mac execution or acceptance rerun was performed for this guide.

## 1. Identify and download the accepted build

Sign in to GitHub and download [development bundle 12495277511](https://github.com/Rickk-B/CorpusTrail/actions/runs/39935463128/artifacts/12495277511)
from [run 39935463128, attempt 1](https://github.com/Rickk-B/CorpusTrail/actions/runs/39935463128).
Unzip in Finder. Put the extracted folder at `~/CorpusTrailDemo/CP10-accepted`,
with the wheel and `build-provenance.json` directly inside it. Use this folder
name only if it is unused; do not replace an older saved build or project.
Keep all six bundle files together, including `SHA256SUMS`.

Check `build-provenance.json` by opening it as text, without editing it:

- Source commit: `f077bb7722ac2b6f3c911a434cb8a541dc8a5745`.
- Source tree: `affc087d36c57b1157f40f656c55f0657b3fe567`.
- Run/attempt: `39935463128` / `1`.
- Wheel: `corpus_trail-0.1.0a3.dev0-py3-none-any.whl`, 379,534 bytes.
- Wheel SHA-256: `34b1315558ceee6a993d69660e230d1034ca4f921022ea60d2b93ef8a8467487`.

The bundle expires **21 January 2027 at 09:56:09 UTC**, 90 days from run creation,
not upload. The later handover commit `79996f64b8c09fa525b692e3e980a743af05db0d`
and subsequent documentation-only commits are not new wheel builds. The shared
version `0.1.0a3.dev0` alone cannot identify CP10.

## 2. Update the existing isolated environment

Stop any running CorpusTrail instance with Ctrl+C and wait for its terminal prompt.
Run these blocks in order; stop on an error or unexpected interpreter path.
No new environment, optional dependency or account is needed.

```bash
cd ~/CorpusTrailDemo
source .venv/bin/activate
python --version
python -m pip --version
shasum -a 256 CP10-accepted/corpus_trail-0.1.0a3.dev0-py3-none-any.whl
```

Expect your Python **3.13.16** and a pip path inside `CorpusTrailDemo/.venv`.
Compare the printed SHA-256 with the value above before installing. To check the
other files too, run `(cd CP10-accepted && shasum -a 256 -c SHA256SUMS)`.

```bash
python -m pip install --no-index --no-deps --force-reinstall CP10-accepted/corpus_trail-0.1.0a3.dev0-py3-none-any.whl
corpustrail --version
```

Expect `0.1.0a3.dev0`. `--no-index --no-deps` uses the downloaded wheel and leaves
optional numerical dependencies alone. This replaces software in this environment;
it does not delete research projects or reverse database migrations. Leave existing
research projects closed and use only the new demonstration directories below.

## 3. Create and open the existing offline demonstration

The following destination must not already exist. If it does, retain it and
choose a different unused demo name consistently; do not delete or overwrite it.

```bash
python -I -m corpustrail.tutorial ~/CorpusTrailDemo/CP10-offline-demo
corpustrail app ~/CorpusTrailDemo/CP10-offline-demo --open-browser
```

Keep Terminal open. Use the printed `127.0.0.1` URL if the browser does not open.
The project is called **Materials sensors**, with invented publications and
scripted decisions. The tutorial uses recorded provider responses, no network,
credentials or model. Expected tutorial output includes `network_used=false`,
9 source observations, 8 canonical papers, 3 included, 2 excluded, 1 insufficient,
1 unresolved, 1 unreviewed, one pending document and a three-record export.
These are software fixtures, not scientific labels or your own decisions. The
historical unresolved membership is not a new Guided Review response option.

Spend about 15–20 minutes on the following checks; exact button text and deeper
workflows are described in [Research tools](ALPHA_WORKFLOWS.md).

| Workspace | Useful evaluation action | Boundary to notice |
|---|---|---|
| Home / dashboard | Read the local/free/open-source explanation; follow the next-action links. | Available features and future integrations are distinguished. |
| Corpus | Search for `Porous`; inspect equal-looking titles, identifiers and source observations. Open a paper, abstract, structured text and pending-document information. | Nine observations resolve to eight identities; equal titles alone do not merge. Pending PDF is not trusted text. |
| Explore | Inspect configured search services and search history. | Recorded tutorial discovery is real stored history; executing a new search would contact a provider. Do not run it in this offline tour. |
| Candidate sets | Preview all collected candidates; optionally freeze a version named `Offline evaluation` with actor `demo_reviewer`, then inspect its count and lineage. | Preview does not save; freeze does not publish membership. Existing versions do not grow. |
| Reference collections | Inspect the available collection/context controls. Optionally stage an explicitly fictional, personally attested label with rationale and actual evidence, preview and commit it only in this demo. | Membership is not copied into reference truth; labels and successor corrections remain separate. |
| Knowledge | Inspect the synthetic sensor assertion, producer and exact evidence/history. | A parser assertion is not a validated scientific fact or corpus decision. |
| Models / Curation | Inspect capability notices and the Manual only choice. | The normal launcher installs no assessment engine and seeds no classifier runs/audits. Browser-test synthetic engines are not packaged product engines. Do not run connection/task actions during this offline tour. |
| Review order | Inspect the capability notice; if numerical extras were already installed, optionally preview and confirm local ordering. | No dependency installation is needed for the tour; missing extras should remain unavailable. Ranking changes order, not membership, and preserves the tail. |
| Export | Inspect `fixture-corpus`; download the unlabelled CSV, receipt and frozen snapshot. Inspect returned-result mapping controls. | Three confirmed synthetic members are exported; downstream labels remain separate. Earlier scripted mappings do not change membership. |

**Guided Review limitation of this older tutorial:** it predates the mandatory
explicit review scope and seeds historical authoritative events. Its scope cannot
now be rewritten under the existing guard. Do not edit JSON, migrate policy or
try to add scope to this fixture to force a Guided Review session. Its useful
coverage is stored lineage/evidence/Knowledge/export and the population/reference
controls, not a complete interactive Guided Review demonstration. The accepted
[macOS browser evidence](https://github.com/Rickk-B/CorpusTrail/actions/runs/39935463128/artifacts/12493989570)
contains the fully exercised synthetic review/audit workflows; that artifact has
separate seven-day retention. A scoped, ready-to-review packaged offline demo is
a small proposed follow-up, not implemented by this documentation task.

## 4. Optional empty, scoped setup sandbox

After stopping the first server, run:

```bash
corpustrail app --projects-root ~/CorpusTrailDemo/SandboxProjects --open-browser
```

Choose New Project: name `Manual alpha sandbox`, folder `manual-alpha-sandbox`,
with an explicit corpus definition such as `Fictional materials-sensor literature
for software evaluation only`. Choose search/evidence services through their
separate forms and enter `demo_reviewer` as configuration author. Leave publication
authority unchecked unless you deliberately want to exercise that authority later.
Confirm the summary. Opening/configuring this sandbox makes no network request.
It starts empty: no importer or automatic folder scanner is available.

This lets you evaluate project creation, settings and empty review states offline.
A populated, explicitly scoped project supports the real manual workflow:
select a reviewer and frozen candidates, Save & Next, Finish Review, then separate
authorized Preview/Confirm Corpus Updates. No model is required. Reference
correction and reassessment remain explicit, separate operations.

Collecting real papers through Explore or retrieving eligible Europe PMC text is
an **optional, separately deliberate network action**, not part of this offline
tour and not executed when preparing it. Inspect the exact transfer/approval
before choosing to execute. The native MacBook Europe PMC discovery transport
cause remains unresolved; this guide does not promise it works on that Mac.
Do not use this fictional-scope sandbox for real scientific judgments.

## 5. Stop, reopen and record feedback

Wait for active commands to finish and for intended drafts/saves to be confirmed.
Save & Next records observations; autosaved drafts and Finish Review are not
membership publication. Close the browser tab, press Ctrl+C in the serving
Terminal, and wait for the shell prompt. Closing a tab alone does not stop the
server. Stop gracefully rather than force-killing work.

Reopen the same offline demo later; do not rerun the tutorial creation command:

```bash
cd ~/CorpusTrailDemo
source .venv/bin/activate
corpustrail app ~/CorpusTrailDemo/CP10-offline-demo --open-browser
```

If port 8766 is occupied, preserve the other process and use the supported option:
`corpustrail app ~/CorpusTrailDemo/CP10-offline-demo --port 0 --open-browser`.
The printed URL then identifies the chosen port. To leave the environment after
stopping the server, run `deactivate`. No project removal or software uninstall is
necessary for this evaluation. See [data ownership](REMOVAL_STORAGE.md).

For feedback, note the page/action, expected result and actual result. Prioritize
unclear next actions, evidence/status confusion, keyboard/reading problems and
save/reopen behavior. Keep real article text/credentials out of screenshots.
Technical acceptance is already complete; this tour is usability evaluation,
not a request to repeat the automated acceptance matrix.
