# Development checkpoint wheels — not public releases

## Chosen workflow and approval boundary

Use the existing **Standalone alpha acceptance** GitHub Actions workflow. Its
new `development-artifact` job runs only for pushes or manual workflow dispatch
on a `development/…` branch, after **all** Python 3.11–3.13 acceptance jobs succeed.
It does not run for pull-request merge refs, main or release tags. A push is still
a deliberate, separately approved publication of that development branch; this
document and the local workflow changes do not authorize it.

There is no GitHub Release, tag, PyPI publication or binary committed to source
history. Versions must remain alpha development versions, e.g. `0.1.0a3.dev0`.
The current public a1/a2 releases remain untouched.

For the first build, approve a commit containing these CI/docs changes on the
current development branch, then approve its push. The first artifact identifies
that new source commit, a descendant of Checkpoint 1 (`6e116118…`), not falsely the
older Checkpoint 1 SHA. The workflow cannot manufacture an artifact at a source
commit that does not contain it. No source-history or release rewrite is needed.

Every receipt explicitly records **both**:

- `checkpoint.implementation_commit_sha`:
  `6e116118f05e53ec3694c60e9171cb873a437bf8`, the completed scientific/application
  implementation checkpoint, preserved unchanged in history.
- `source.commit_sha`: the exact new CI/distribution follow-up commit checked out
  and built by this run. The wheel is built from **this** commit, not directly from
  the earlier implementation checkpoint.

The build verifies implementation ancestry and unchanged `src/corpustrail/` content.
Both identities also appear in the job's download summary. Future scientific
checkpoints must explicitly update this lineage contract, not retain an incorrect
claim that their application source is still Checkpoint 1.

Manual `workflow_dispatch` normally requires the workflow file to exist on the
default branch. Until that is explicitly merged, use the approved development
branch push trigger; do not assume the GitHub **Run workflow** button is available.

## Build and receipt

1. Check out exactly the run's full `github.sha`, with checkout credential
   persistence disabled. Reject a dirty source tree or non-development version.
2. Install only the existing constrained developer/build tools. Build one wheel.
3. Install that wheel into a clean core environment outside the checkout. Run the
   complete offline suite, offline tutorial and CLI version check. The upstream
   matrix also covers core, optional ML, wheel/sdist, isolation and lint checks.
4. Validate wheel version, MIT/anonymous metadata, lightweight core and packaged
   frontend resources. Bundle the **same validated wheel**, never rebuild it after
   that installation test.
5. Upload the uniquely named bundle and place its download link in the run summary.

Bundle name:

```text
corpustrail-dev-VERSION-FULL_COMMIT_SHA-run-RUN_ID-ATTEMPT
```

Contents: the wheel, `build-provenance.json`, `SHA256SUMS`, installed test output,
offline tutorial receipt and installed CLI version. Provenance identifies the
full source/tree SHA, version, wheel hash/size, public repository/branch, run/attempt,
build time and build Python/setuptools versions. It labels the artifact
`unreleased_development_checkpoint`. It does not dump environment variables,
credentials, Git author metadata or the triggering user's identity.

The standard wheel filename is retained so pip accepts it. Different checkpoints
may share `0.1.0a3.dev0`; distinguish them by artifact name, source SHA and checksum.
Do not pretend pip package version alone identifies the checkpoint. Preserve the
receipt alongside the downloaded wheel. `--force-reinstall` is needed to replace
an installed build with another build of the same version.

This is traceable build provenance, **not** a signed cryptographic attestation or
a promise of byte-identical rebuilds. The source SHA and wheel SHA are different
identities. Check the manifest's commit against the GitHub run before installing.
Build-tool downloads and GitHub Actions infrastructure use network access; tests
make no real scholarly-provider/model calls and require no provider/API keys.
GitHub's normal read-only checkout token is not a CorpusTrail shared credential.

## Download and install on another machine

After an approved push and successful workflow run:

1. Sign into GitHub; open **CorpusTrail → Actions → Standalone alpha acceptance**.
2. Select the successful run for the approved development commit, not main or a
   different checkpoint. Check its full source SHA.
3. Click the development bundle in **Artifacts** or its job-summary download link.
4. Extract the ZIP. Check `build-provenance.json`, version and `SHA256SUMS`.
5. On macOS, from the extracted directory, verify checksums:

   ```bash
   shasum -a 256 -c SHA256SUMS
   ```

6. Activate the intended environment; install the specific local wheel:

   ```bash
   source "/path/to/existing/environment/bin/activate"
   python -m pip install --no-deps --force-reinstall "./corpus_trail-0.1.0a3.dev0-py3-none-any.whl"
   corpustrail --version
   corpustrail app "/path/to/project" --open-browser
   ```

The `--no-deps` example is for the current dependency-free core and leaves already
installed optional numerical packages alone. Software replacement does not migrate
or delete projects. Keep an older wheel/environment if you need to return to a2.

## Access, retention and trade-offs

GitHub requires sign-in and repository read access to download Actions artifacts.
Even a public repository's workflow artifact is not an anonymous permanent download.
The workflow requests **90 days**, subject to repository/organization retention
limits; artifacts can disappear earlier if the artifact/run/repository is deleted.
Save a local copy and receipt before expiry. Re-running builds the pinned run commit
again, producing a new run-attempt artifact; it does not guarantee identical bytes.

Actions artifacts are appropriate for the owner's checkpoint testing, avoid cluttering
Releases and require no release/tag-writing permission. They are less convenient
for anonymous colleagues or permanent distribution. If that later becomes necessary,
consider a clearly labelled development prerelease with a separate explicit user
approval; do not silently switch channels or create a3.

Official references: [GitHub artifact downloads](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts),
[artifact storage and retention](https://docs.github.com/en/actions/tutorials/store-and-share-data),
[upload-artifact](https://github.com/actions/upload-artifact),
[manual workflow requirements](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).

## Validation status

The receipt helper and gating contracts can be tested locally with synthetic wheels
and temporary clean repositories. The real wheel-install/sdist surfaces already
have their own tests. Hosted artifact creation/download cannot be claimed until
an explicitly approved push runs the workflow. No such push has occurred here.

Local follow-up verification: nine focused receipt/gating tests passed; the full
standalone suite ran 339 tests successfully. The workflow parsed using existing
developer YAML tooling and all nine shell blocks passed `bash -n` without running
Actions. Temporary wheel/sdist builds included the new tooling/docs/tests; a clean
core install ran the nine build tests and offline tutorial successfully. A separate
temporary pip uninstall/reinstall/force-reinstall check preserved project and external
original bytes. The original Checkpoint 1 wheel/report were not overwritten.
These results are local checks, not hosted Actions/artifact download acceptance.

The subsequently approved dual-commit lineage requirement has ten focused tests
passing and a full source suite of 340 tests passing (71.700 seconds). The user
authorized committing/pushing this CI-only follow-up on
`development/v0.1.0a3-read-only-local-ui`; no main merge, tag or release is authorized.
The first hosted run must still validate the matrix and uploaded receipt before
the artifact is described as available for testing.
