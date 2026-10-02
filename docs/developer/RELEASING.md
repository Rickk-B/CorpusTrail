# Local alpha acceptance and personal-GitHub handoff

These instructions are a plan, not authorization to create/push a remote, change
visibility, tag a public release or publish to PyPI. First inspect the clean local
candidate and approve the particular next action. Repository URLs below are
placeholders, not an assertion that such a repository exists.

## Local inspection

The initial tree must contain only approved code, safe invented fixtures, docs,
license, build/CI configuration and bounded code-origin receipts. No source
repository history is included. Code-origin hashes are not links to private data;
the original repository is not needed to install, test or operate the package.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
corpustrail --version
corpustrail --help
python -I -m corpustrail.tutorial /tmp/materials-release-inspection
```

Use a new tutorial target. For developer/artifact checks follow CONTRIBUTING.md.
The standard MIT license applies to the code/docs/synthetic fixtures. Dependency
licenses are separate and no actual articles or datasets are bundled. Package
authors/maintainers are omitted. CITATION.cff is omitted: formal authorship/citation
can be added later, without fabricating an entity author to satisfy a schema.
Its absence is not a build or open-source-release blocker.

## After explicit approval: create an empty private repository

In your personal GitHub account create an empty private repository named
`CorpusTrail`, with **no** auto-generated README, license or .gitignore. Enable
private vulnerability reporting if desired. Do not import the original research
history. Then, in the vetted tree (not another existing repository):

```bash
git init --initial-branch=main
git config --local user.name CorpusTrail
git config --local user.email noreply@corpustrail.invalid
git config --local user.useConfigOnly true
# Remove inherited per-process author/committer overrides before verification.
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL EMAIL
git config user.name
git config user.email
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
python tools/verify_git_identity.py .
git status --short
git add .
git diff --cached --stat
git diff --cached --check
# Proceed only if BOTH identities above are CorpusTrail <noreply@corpustrail.invalid>.
git -c user.name=CorpusTrail -c user.email=noreply@corpustrail.invalid \
  commit -m "CorpusTrail 0.1.0a1 release candidate"
CORPUSTRAIL_GITHUB_OWNER='YOUR_PERSONAL_GITHUB_LOGIN'
git remote add origin "https://github.com/${CORPUSTRAIL_GITHUB_OWNER}/CorpusTrail.git"
git push -u origin main
```

The `.invalid` address is a non-deliverable Git identifier, not a support mailbox
or a claim that a GitHub account exists. It deliberately does not link authorship
to a personal account. GitHub-provided noreply addresses may contain account IDs
and usernames; do not substitute one without a separate privacy decision. No
global Git configuration should be changed. Git's environment/conditional config
may override repository settings: inspect effective identities and stop if either
is personal. Do not infer an identity from reviewer roles or a coding tool. Never
copy a source .git directory. Remote ownership necessarily remains visible on
GitHub; neutral commit metadata does not anonymize the hosting account, issue
activity, merge/web edits or signatures. Inspect those separately before sharing.

Alternatively, after local initialization/commit and separate remote authorization:

```bash
gh repo create "${CORPUSTRAIL_GITHUB_OWNER}/CorpusTrail" --private --source=. --remote=origin --push
```

Use either remote-creation route, not both. Requires authenticated GitHub CLI and
permission; no such command is executed by the preparation workflow.

## Private inspection, then public sharing

Inspect rendered README/docs/license and the full initial file tree in GitHub.
Wait for CI on 3.11/3.12/3.13, then clone the **private** repository into a new
directory, repeat local/artifact acceptance and verify no private state was committed.
Only after a new explicit approval change visibility in repository Settings →
General → Danger Zone → Change visibility. Public Git history, issues and metadata
then become visible; this is a deliberate publication step, not an automated test.

After approval you may tag the inspected commit:

```bash
python tools/verify_git_identity.py .
git -c user.name=CorpusTrail -c user.email=noreply@corpustrail.invalid \
  tag -a v0.1.0a1 -m "CorpusTrail initial alpha"
git push origin v0.1.0a1
```

No package-index upload is part of this handoff. PyPI name availability, account,
trusted publishing and upload authorization are separate later decisions.

References: [GitHub repository creation](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository),
[gh repo create](https://cli.github.com/manual/gh_repo_create),
[CFF schema](https://github.com/citation-file-format/citation-file-format/blob/main/schema.json),
[Python package metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/),
[GitHub commit email configuration](https://docs.github.com/en/account-and-profile/how-tos/email-preferences/setting-your-commit-email-address),
[Git effective identity](https://git-scm.com/docs/git-var).
