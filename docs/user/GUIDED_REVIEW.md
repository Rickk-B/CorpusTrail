# Guided Review

Open a project, then choose **Review**, or **Start or Resume Review** on its
dashboard. Viewing this page does not create a session or contact any provider.
Review assesses the project's broad scientific topic, not eligibility for a
particular systematic-review question.

## Start or resume

Enter your reviewer pseudonym explicitly. It is an attribution, not a login.
Configuration authorship does not select a reviewer or grant corpus-publication
authority. Choose either all currently collected canonical publications or those
awaiting a corpus decision, or a saved [population version](POPULATIONS.md).
No selection is made silently. An explicit broad-corpus
definition must already exist in Project Settings.

**Start Guided Review** freezes that publication set, corpus definition,
configuration revision and evidence snapshot. New discoveries and evidence do not
enter it automatically. Method-blind presentation hides discovery methods and
earlier judgments; operational presentation shows frozen source attribution.
Other application pages are operational and are not blinded.

Existing sessions show their reviewer, progress and status. Open one to resume.
Saved drafts and observations survive refresh and application restart. Unsaved
browser edits cannot be guaranteed after a crash. Legacy sessions are inspectable;
resume their original workflow using `corpustrail review serve`, or start a new
Guided Review. Do not use an older CorpusTrail build to modify new guided sessions.

## Read and assess

The workspace shows one publication, its identifiers, abstract attribution and
frozen evidence availability. **Read verified structured text** uses the existing
safe text reader, with further segments for long documents. Opening text is not an
attestation that you read it. New retrieval belongs on the publication's Evidence
page and will require a new session to enter a frozen snapshot.

Choose **Include**, **Exclude** or **Insufficient evidence**, the evidence actually
reviewed, and a brief rationale. The existing scientific model requires a rationale.
Metadata-only review is permitted. Missing evidence is never automatic exclusion.
**Choose review extent** is a disabled placeholder, not an assessment or default.
**Verified structured text — selected sections** and **Verified structured text —
full document** are offered only when trusted body text was frozen into this
session. Open that text before explicitly choosing the extent you actually read.
Availability and display never attest that reading occurred.

Edits autosave as drafts in the local project, not as scientific observations.
**Save & Next** records a non-authoritative human observation and advances only
after the save succeeds. On the last paper it reads **Save assessment**. A failed
save keeps your input and does not advance. An unchanged saved assessment does not
create a duplicate observation. Explicitly changed assessments preserve earlier
observations rather than overwriting them.

**Skip for now** records navigation, not a scientific judgment. Previous/Next also
do not record an assessment. Drafts are flushed before navigation; failed saves
leave you in place. A recovery action reloads committed state while retaining your
edits. If another window moved to a different paper, retained input is not applied
to that different paper.

## Finish, then optionally publish

The summary separates saved judgments, incomplete/changed drafts and undecided
papers. **View Review Summary** inspects these counts without finishing.
**Finish Review** completes the session and
freezes its selected saved observations. Skipped, unassessed and changed-unsaved
drafts remain undecided; they are not converted to insufficient-evidence judgments.
Completion does not publish corpus membership. Completed sessions are read-only;
start a new session for corrections. Only after completion is acknowledged does
the application return to the project dashboard, with a completion message and
**View Review Summary** link. Failed completion leaves the session and input in
place. Completed sessions open directly as **Review completed — read only**, with
saved rationale, reviewed extent and expandable observation provenance, not
disabled editable forms. Use **Back to Review Overview** or **Back to Project
Dashboard** to leave the summary. There is no repeated Finish action.

Only an identity already authorized by the project's review policy can choose
**Preview corpus updates**. Inspect the decisions, acting reviewer, policy and
definition. The preview replaces its own button with **Confirm corpus updates**
and **Back to Review Summary**. Returning or refreshing does not confirm anything;
an explicitly opened preview is needed before the confirmation is displayed.
The preview identifies included/excluded/insufficient-evidence judgments and
undecided papers that will not be published. Confirmation covers all selected
saved judgments across the paginated summary, not just the visible page.
**Confirm corpus updates** separately publishes the selected saved
judgments, including insufficient evidence, in one atomic operation. Its provenance
links every authoritative decision to its source observation. No partial batch is
published if validation fails. Other historical decisions are preserved.

Changed configuration invalidates writes to a frozen session. Changed paper history
invalidates a pending publication preview: inspect and explicitly prepare a new
confirmation. Nothing is automatically retried or published on refresh, completion,
navigation or shutdown. Pseudonyms and permissions are local research-policy
controls, not authentication against a hostile person using your computer.

After publication, Corpus and the dashboard show authoritative membership. Saved
observations, published decisions and included publications remain different counts.
Review sends no notes, judgments or identifiers to scholarly or model services.
