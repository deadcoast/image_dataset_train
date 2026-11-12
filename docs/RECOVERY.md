# Recovery and installed-package verification

This implements the recovery portion of the user-directed product phase in
[PREPARATION](PREPARATION.md). Recovery preserves original evidence and records
what changed. It does not establish caption accuracy or human dataset acceptance.

## Finding and inspecting preparation work

```powershell
dataset collections
dataset collections show artwork
dataset status --collection artwork --verify
dataset status --collection artwork --job <recorded-job-id> --verify
```

Only explicitly registered workspaces are inspected. Successful or interrupted
CLI preparation remembers its validated workspace; previews and status/listing
never create registrations. Use `dataset collections add <workspace> --name artwork`
to name an older workspace. Unregistering removes only that catalog entry.

Status separates the saved job status from artifact integrity. It shows stage
checkpoints, current/prior attempt paths and retained pending outputs. With
`--verify`, a damaged stage is reported alongside healthy verified stages; no
files are adopted, removed or repaired by inspection. Metadata-only listing is
explicitly marked, and a recorded running status does not establish process liveness.
Saved partial tagging evidence does not by itself prove that another runtime can
reuse the inference cache.

Generated resume commands include `--job <expected-current-job-id>`. If another
job has become current, the command fails before executing stages. Historical
jobs remain inspectable; viewing one does not change `collection.json`. Ambiguous
or malformed published outputs require artifact inspection, avoiding a repeated
resume that cannot resolve the ambiguity. Source/review changes retain their
existing new-job and review-refresh paths.

If application-data storage cannot accept an error log or collection registration,
the CLI still returns the original preparation failure and its recovery commands.
When logging itself raises, JSON includes `log_unavailable`; otherwise an unavailable
log may appear as `error.log: null`. Collection registration has its own result; a
catalog failure does not turn a completed dataset into a failed preparation. Cancellation
retains its own exit code and saved job evidence under the same conditions.

Collection listing reads publication metadata without opening the reviewer or
performing publication recovery. Open the selected QA record deliberately to use
the existing publication workflow. Caption restore and package/collision repair
retain their separate receipts and commands. See [collections](COLLECTIONS.md).

## Find saved recovery receipts

`dataset recovery` lists removal, caption-restoration, collision-repair and package
repair receipts from the selected application-data directory. Filter with
`--source`, `--kind` or `--status`, then use `dataset recovery show <full-id>` to
inspect affected paths, recovery locations and copyable continuation commands.
`--home` selects another explicitly supplied application-data root. See the
[recovery browser](RECOVERY-BROWSER.md) for exact commands and selection behavior.

List/show read recorded metadata without checking source or backup bytes, resuming
operations or creating application state. They remain available without UI/native
runtime dependencies. Old failure or running states describe saved history, not
current damage or a live process. Diagnosis and completed directory operations link
back to this history; malformed records are reported independently.

## Package files and resources

`trainime doctor` checks the installed package against the checksum-verified wheel
retained by the installer. It checks wheel-owned Python files, reviewer HTML and
JavaScript, trainer requirement pins, and other packaged resources. Unknown files
are left alone. An editable checkout is reported separately and is not compared
against an installed wheel. Native inference checks remain a separate result.

`trainime doctor --fix` uses the retained installer to repair damaged package
payloads even when the native/import probe still passes. If the retained wheel or
installer is unavailable or its checksum differs, rerun the original `install.cmd`.
Do not substitute an unverified wheel into the installation receipt.

The repair helper preflights archive paths, aliases, size bounds, ZIP checksums,
and destination paths before mutation. Each changed existing file is copied,
flushed and SHA256-verified before replacement. Missing files are published
exclusively, preserving a destination that appears during the operation.
Launchers, unknown package files, datasets, settings and review decisions are not
removed by package repair.

Under `TRAINIME_HOME/recovery/application/<attempt>/`, `repair.json` records the
wheel identity, desired and original file hashes, backup paths and progress.
`journal.jsonl` records backup and publication boundaries. Original bytes retain
their `image_dataset_train/...` relative paths. Receipts and backups are not expired
or deleted automatically. If interrupted, rerun the repair: files already matching
the exact wheel are left alone, and remaining differences receive a new receipt.
An interrupted receipt can remain incomplete even when its last file was published;
compare its recorded hashes rather than assuming an unfinished row means no write.

The installer serializes repairs. Stop other software from modifying the installed
package during recovery. These are verified per-file recovery operations, not a
filesystem-wide transaction or a guarantee against hardware failure.

## Restoring removed captions

Use the removal report printed by `trainime remove`:

```powershell
dataset restore-captions --receipt 'C:\path\to\operations\remove-run\operation.json' --dryrun --json
dataset restore-captions --receipt 'C:\path\to\operations\remove-run\operation.json' --json
```

The containing operation directory is also accepted. No repository configuration
file is needed. Preview reads the saved evidence without creating locks, reports,
captions or other application state. Apply uses the same source-directory lock as
Trainime, from the application home that owns the removal receipt.

Commands from the recovery browser include `--expected-sha256` and
`--expected-plan-sha256` to bind the selected `operation.json` and `plan.json`.
A changed receipt or plan rejects before restoring captions; the checks
are repeated under the source lock. Saved plan, journal and backup verification
remain additional checks, and legacy receipts retain their manual-recovery limits.

New removal receipts bind image bytes as well as caption bytes, without decoding
the images. They retain source identity, plan and journal hashes, and verified-backup
events. Restore validates the receipt, safe relative paths, original associations,
backup hashes and current image hashes before writing. It restores only missing
captions, byte for byte, including empty captions, BOMs and original line endings.
A current identical caption is reported as `already_present`. A changed image,
different caption, directory or ambiguous association is a conflict and is kept.
Other independently safe rows can complete. Exit code `1` means conflicts or
unverifiable legacy rows remain; invalid evidence produces an execution error.

Restoration never overwrites a destination. Each apply attempt retains a new
`operations/<attempt>-restore-.../restore.json` and journal. The original removal
receipt and backups remain unchanged. A verified backup from an interrupted
removal can be recovered even when the final `removed` journal entry was not
written. A rerun recognizes captions already restored, including a publication
completed immediately before interruption.

Legacy removal plans without image hashes cannot prove that the current image is
the one whose caption was removed. They are reported as `unverifiable`, without
automatic writes. For manual recovery, inspect the original plan and backup tree,
confirm the current image association and destination, and copy the chosen saved
caption yourself. Do not edit a legacy receipt to invent missing image evidence.

Hashes detect inconsistent or changed local artifacts; these local receipts are
not cryptographic signatures against an attacker rewriting every piece of evidence.
Keep the receipt, plan, journal and backup tree together. Source images are never
deleted or renamed by caption recovery.

## Recorded implementation identity

New stage metrics, including QA, capture the package identity at stage start.
Label workspaces, standalone catalog and trainer-check receipts carry the same
identity. It includes the application version, relative Python, HTML, JavaScript
and pin-file hashes and their canonical aggregate SHA256, with no absolute
installation paths or bytecode cache.
Preparation and publication jobs use it to avoid mixing different implementations
inside a resumed job. It identifies application payloads; model, trainer and
dependency identities retain their own existing evidence.

Historical receipts without this field remain readable. When an identity is
validated, its structure and aggregate must agree; historical evidence is not
required to match the current installed build. The installed smoke compares the
identity against exact wheel bytes and checks propagation into generated receipts.

## Reproducible verification

The tracked smoke runner installs a built wheel into a new temporary environment
outside the checkout using locked dependencies. Its private uv cache and copy mode
ensure deliberate corruption fixtures cannot alter another environment's hardlinks.
All images are generated fixtures; no real collection or pretrained model is used.

```powershell
uv build --out-dir .cache/ci-dist
uv export --locked --extra tag-cpu --no-dev --no-emit-project --output-file .cache/package-constraints.txt
uv run --no-sync python scripts/package_smoke.py --wheel .cache/ci-dist --constraints .cache/package-constraints.txt --require-catalog
```

The wheel directory must contain exactly one wheel. An explicit `--workspace`
must name a new directory; otherwise the runner creates one in the system temporary
directory. It retains setup and command logs plus `result.json`. The check covers
installed commands, all wheel payload bytes, native CPU inference, resource damage
detection/repair, Unicode paths, read-only previews, caption backup/restoration,
manual override precedence, whole-group export, QA resources, relocation, portable
catalog queries and tamper rejection. It also runs installed `dataset prepare` with
existing captions and offline mode, verifies the job, and repeats resume without
duplicating completed stage outputs. An alpha fixture checks that conversion to an
opaque derivative removes the exact transparency label while retaining the original
caption and recorded transformation. The smoke also checks the full
original-content label frame and aliases against a separate partition snapshot,
preserved judgments after label refresh, explicit QA
membership, assistant assessment attribution without human acceptance, and a
published snapshot comparison after the source is offline. Generated saved scores
exercise review persistence without downloading a model. When a source archive
accompanies the wheel, the runner checks its installer/development files and matches
every packaged payload file against the source archive. The final fixture export intentionally remains
tampered as negative-test evidence. This does not qualify real-image accuracy, CUDA,
trainer execution or human usability.

[CI](../.github/workflows/ci.yml) runs locked lint/tests/build and that same wheel
journey on Windows and Linux. Windows is the installer target; Linux CI checks
source/package behavior without claiming a native installer qualification.
The workflow has read-only repository permission and performs no deployment.
Its action pins were resolved from official release tags on 2026-11-09:
[checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1),
[setup-uv v10.3.3](https://github.com/astral-sh/setup-uv/releases/tag/v10.3.3), and
[upload-artifact v7.0.2](https://github.com/actions/upload-artifact/releases/tag/v7.0.2).
The uv setup follows [Astral's GitHub Actions guidance](https://docs.astral.sh/uv/guides/integration/github/).
Hosted CI results are evidence only after an actual run; a locally validated workflow
file is not a hosted pass.
