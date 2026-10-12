# Safe project removal — development follow-up

This is the approved Checkpoint 2 extension, not Checkpoint 3 or a public release.
Only macOS removal is implemented. Linux/Windows normal use remains available;
their removal button explains that native Trash support is not enabled.

## Install the optional macOS dependency

Stop all older servers and activate your existing CorpusTrail Python environment.
Download/unzip the exact approved Actions artifact and substitute its wheel path:

```bash
python -m pip install --no-deps --force-reinstall "/path/to/corpus_trail-0.1.0a3.dev0-py3-none-any.whl"
python -m pip install --only-binary=:all: "/path/to/corpus_trail-0.1.0a3.dev0-py3-none-any.whl[macos-trash]"
corpustrail --version
corpustrail app --open-browser
```

**`--no-deps` alone does not install the extra.** The second command installs only
`pyobjc-framework-Cocoa==12.2.2` and its required `pyobjc-core==12.2.2`; the umbrella
framework collection is not used. Both have Apple Silicon universal2 binary wheels
for CPython 3.11, 3.12 and 3.13, verified by cross-platform pip downloads. Core use
requires neither binding and never imports Cocoa. Without them, removal is disabled
with installation guidance. There is no permanent-delete fallback.

## Disposable-project Mac acceptance

1. Create a uniquely named project, e.g. `trash-test-20261012-01`, using only synthetic
   topic text. Never use a real research project for acceptance testing.
2. Projects → **Close Project** on the card labelled **Active project**. The list
   reloads and the project stays listed. Closing releases only this launcher's use;
   other launchers/review servers/CLI operations can still prevent removal. Nothing
   else is terminated for you.
3. Click **Move to Trash…** on that disposable card. Check its exact name/location
   and the explanation. Cancel first; verify it still opens unchanged.
4. Close it again, reopen confirmation, type its exact folder name and explicitly
   press **Move Project to Trash**. Approximate/case-insensitive matches are refused.
5. Check the result and refreshed list. Open remaining projects to verify availability.
6. Open Finder Trash and inspect the disposable folder (the OS may rename it).
   Finder Put Back or careful manual restoration may recover it. Restored projects
   must pass normal validation. No in-app Trash browser/restore is implemented.

The complete project folder moves: publication/corpus records, reviews, settings,
stored evidence and scientific provenance. External Zotero libraries, original
imports and documents outside the selected folder remain untouched. Software and
other projects are not removed. Trash availability now is not guaranteed retention:
your computer or you may later empty it.

Only valid projects directly inside the launcher-approved root are eligible.
External launch paths can be opened but not removed through this interface.
Roots/parents, source repositories, software-containing folders and symlink/reparse
locations are refused. Native removal refuses unknown/nonlocal/ubiquitous cloud
storage; no network/cloud-filesystem removal support is promised.

## Failures and uncertainty

- Busy projects must be closed or allowed to finish their operations first.
- Failed moves report what was verified unchanged; check support, permissions and
  free space before making a fresh explicit attempt.
- Uncertain moves require inspection of both original location and Finder Trash.
  Do not retry blindly. That handle is blocked in the current launcher. Restarting
  is not a repair or verification; original confirmations cannot be reused.
- Changes to identity, configuration, database or folder inventory invalidate the
  selected snapshot. Rejected requests do not modify scientific state.

Confirmations last five minutes and permit one attempt. They are bounded session
memory, not scientific records or a persistent project registry. Cancellation and
ordinary page navigation never move anything. No bulk/permanent deletion or cleanup
of external references occurs.

## Project-use anchors and removal of software

Cooperating clients under the same OS account/on one machine use shared leases;
removal requires exclusive use. The OS releases leases on exit/crash. Small hashed,
zero-content anchors remain outside projects in application-owned locations:

- macOS: `~/Library/Application Support/CorpusTrail/project-locks/`
- Windows: OS LocalAppData, then `CorpusTrail/project-locks/`
- Linux: `~/.local/state/CorpusTrail/project-locks/`

Do not clear anchors while participating clients run. File existence does not mean
a stale lock. Pip uninstall removes neither anchors nor projects; optional bindings
also remain separately installed unless you remove them yourself.
Older versions, external programs, unwrapped custom Python callers, other OS users
and multi-host use do not cooperate. Close them yourself; no protection against
arbitrary external filesystem changes is claimed.

The artifact completion report gives exact hosted/native results. Mocks/Linux tests
alone are not macOS validation. Your own native Mac graphical acceptance, using
only disposable projects, remains a separate final check.
