# Updating, removing and retaining research data

## Current Python/wheel installations

CorpusTrail software is installed into the Python environment you selected. Its
projects are separate researcher-owned directories. Stop running CorpusTrail
servers before changing/removing the installed software.

Activate the intended environment and inspect it:

```bash
source "/path/to/environment/bin/activate"
python -m pip show corpus-trail
```

Installing a newer wheel replaces the previous CorpusTrail package in **that
environment**, not in every environment on the machine. For development checkpoints
that share the same package version, explicitly force replacement:

```bash
python -m pip install --no-deps --force-reinstall "/path/to/checkpoint.whl"
```

Substitute the actual complete wheel filename. `--no-deps` is appropriate for the
current lightweight core; it deliberately does not install/update optional ML
dependencies. Do not use `--ignore-installed` to layer incompatible packages.

To remove the installed package:

```bash
python -m pip uninstall corpus-trail
```

Review pip's prompt. This removes the distribution and its CLI from that environment.
It **does not delete project directories**, original imports, external document
libraries or your downloaded wheel. Wheel/ZIP files can be deleted independently
in Finder/File Explorer; they are not the installed application. An editable
source checkout is also not deleted by uninstalling the editable installation.

Pip uninstall does not automatically remove optional dependencies, pip's shared
cache, virtual environments, CorpusTrail project data or future application-data
directories. Do not clear a shared pip cache or remove a whole environment without
understanding what other software uses it. Uninstall does not revoke remote API
credentials or alter your shell's environment variables.

For rollback, reinstall a saved earlier wheel in the intended environment. Software
rollback cannot reverse a database migration automatically; inspect compatibility
and keep backups for explicitly approved future migrations.

References: [pip installation](https://pip.pypa.io/en/stable/cli/pip_install/),
[pip uninstall](https://pip.pypa.io/en/stable/cli/pip_uninstall/).

## Ownership boundaries

| Material | Owner/category | Default removal |
|---|---|---|
| Installed code, CLI, packaged migrations/frontend | Application software | Package/OS uninstaller |
| Future global preferences, recent-project pointers, disposable cache/logs/temp | Application-owned state | Separate clearly scoped cleanup |
| Future downloaded optional runtime/model assets or rebuildable indexes | Application-owned only when explicitly enrolled there | Optional removal, with impact warning |
| Project configuration/database, observations, evidence artifacts, reviews, assertions, snapshots, exports and project-level models | Researcher-owned project | Retained unless separately selected and strongly confirmed |
| Original imported bibliography, external Zotero libraries, external documents | Researcher-owned external material | Never automatically removed |

**Downloading a file does not make it disposable cache.** Evidence and provenance
inside a project are research data, even when CorpusTrail acquired/generated them.
Immutable artifacts, model outputs, summaries used as evidence, assertion lineage,
review histories and ranking snapshots must not be removed by “Clear cache”.
Project-specific configuration, reviewer authority and scientific state are not
global application preferences and must not be changed by “Reset settings”.

The current read-only browser creates no global app settings/cache/log store and
no browser storage. Scientific data remains in explicit project paths. The storage
controls below are approved **future design**, not working a3 Checkpoint 1 features.

## Future removal experience

```text
Remove CorpusTrail

✓ Application
✓ Settings
✓ Cache
✓ Logs
✓ Downloaded optional assets

□ Also permanently delete CorpusTrail research projects
```

Project deletion is unchecked by default and needs another explicit confirmation
showing the selected projects/locations, irreversible consequences and backup
options. Uninstall must never silently include projects in an application-data wipe.
Unknown/unregistered material must be preserved, not guessed to be disposable.

Later desktop distribution should use normal operating-system application removal:
macOS first, Windows second, retaining Linux compatibility. OS application removal
does not necessarily remove user settings/data; a separate, explicit storage-cleanup
screen or reviewed platform mechanism should handle that. There is no self-deleting
CorpusTrail CLI that attempts to pip-uninstall its own active package.

## Future Settings → Storage & Data

Planned controls, not implemented in this checkpoint:

- Show application-data location and separately show project locations.
- Clear cache; clear temporary files; remove downloaded optional assets.
- Reset application settings, without changing project configuration or authority.
- Delete selected project with strong confirmation.
- Delete all CorpusTrail application data, explicitly excluding projects/external files.
- Delete all registered/selected CorpusTrail projects, with strong per-population
  confirmation, not a filesystem-wide search.

Cleanup must be ownership-aware, path-confined and safe against symlinks, shared
directories, project/app-data overlap and active jobs. Prefer recoverable removal
where possible, and accurately label permanent deletion. Do not clear project
provenance under a convenience label. Removing optional assets may prevent replay
until the same version is restored; keep scientific run/provenance records intact.
