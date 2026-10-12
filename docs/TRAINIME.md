# Trainime workflow contract

Designed and implemented 2026-10-11. The initial workflow is version 0.3.0;
version 0.4.0 adds the [installer, diagnostics, and repair system](INSTALLATION.md).
Version 0.4.1 refines the terminal presentation and makes dry-run eligibility explicit.
Version 0.5.0 adds executable `te001` / `tf001` collision repair.
Version 0.5.1 replaces its single-fix dispatch with a numeric error/fix registry.

## Interaction

The home menu has exactly the four requested numbered choices. There is no
pipeline wizard. Tag and Remove resolve session path → saved default → one path
prompt, then ask `Preview only? --dryrun [y/N]:`. The entered path lasts for the
session. Both actions print the equivalent direct command. Blank answers to the
preview question apply the operation; `y` or `--dryrun` previews. Ctrl+C cancels
back to Home, including from Settings. Ctrl+D exits at a prompt. Nothing asks
whether to continue to another stage.
When a registered error occurs, the menu offers one conditional repair question
with its mapped fix codes, for example `Apply tf001? --fix [y/N]:`. Accepting applies
those repairs and continues the selected action. There are no additional normal-path
menus. Starting with `trainime --fix` opts into detected registered repairs for menu
actions. Direct commands also accept numeric or error/fix code selections.

Settings exposes two paths and Back. It stores only the default path. Session
state and input history stay in memory. Paths accept quotes, spaces, Unicode,
environment variables, and `~`; Tab provides directory completion. A stale saved
path leads to a replacement path prompt. Subcommands never prompt, making them
usable in scripts; a missing path and missing default produce an actionable error.

The CLI uses standard scrolling output with one active progress line. Redirected
output receives periodic text progress. Summaries show counts, at most three
issues, and the report/backup path. Detailed data stays in files. The root
`--dryrun` also makes interactive actions previews and prevents saving settings.

### Terminal presentation

Home uses aligned action labels and short descriptions at 72 columns and wider;
narrower terminals keep the same four choices without the descriptions. The active
session/default directory is visible before selecting an action. Settings separates
each path from its persistence explanation. There is no screen clearing or alternate
screen; previous results remain in scrollback.

Dry-run headlines say `--dryrun found N images that can be serviced for tags`
(or `N captions that can be removed after backup`). Both `can` and the eligible
count are green. A separate tally distinguishes scanned images, eligible work,
existing captions kept, skipped items, and errors. A preview explicitly says no
files changed and prints a copyable command to apply eligible work. Actual runs
report captions written/removed, including zero-work and partial-result states.

Use cyan for navigation, commands, and preview headings; green for eligibility and
completed work; amber for skips/review; red for failure. Text labels carry the same
meaning without color. Honor `NO_COLOR` and terminal color capabilities. Paths and
commands stay literal and copyable, including brackets and spaces.

Progress uses one transient line with elapsed time. Inspection and inference pulse
while totals are unknown; caption writing/removal shows actual completed/total
counts and a bar. Below 72 columns the bar is omitted. Redirected output receives
bounded plain progress messages, without terminal animation.

These choices apply the guidance on concise prompts, discoverable commands,
progress, and cancellation in the [Command Line Interface Guidelines](https://clig.dev/).
PromptSession and its interrupt/EOF behavior follow the
[prompt_toolkit documentation](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html).
The persistent command installation follows [uv's tool workflow](https://docs.astral.sh/uv/guides/tools/).

## Tagging decisions

The local WD SwinV2 v3 profile is pinned, with a general threshold of 0.35,
character names omitted, rating scores retained separately, and batch size 4
(or 1 for a fixed-batch model). Available CUDA is used by the GPU installation;
the CPU installation works without CUDA. Model research and limitations are in
[TAGGING.md](TAGGING.md). These are defaults, not user-facing decisions.

1. Validate and inventory the directory recursively. Small images remain eligible;
   corrupted, animated, excessive-pixel, or excessive-byte inputs are skipped.
2. Preserve existing captions, including empty/manual captions. Same-stem images,
   case-folded collisions, linked captions, and directory-shaped caption paths are
   blocked. Same-stem collisions report `[te001]` and an executable `[tf001]`
   command. Explicit `--fix tf001` repairs them before this tagging pass.
3. If no captions are missing, finish without model setup. Otherwise, obtain the
   pinned model automatically, validate its artifact hashes, and publish an inventory.
4. Infer only eligible images missing captions. Apply the existing reference
   preprocessing, verified source hashes, duplicate score reuse, raw-score caching,
   deterministic threshold rules, and review flags. No folder-name content tags are
   invented. Nudity does not exclude an image.
5. Recheck each source and caption association before publication. Write UTF-8,
   comma-separated tags to the image's matching `.txt`, using a staged file and
   exclusive publication. Never replace a caption that appeared during processing.
   If no tags clear the threshold, report it and leave the caption absent.

Raw scores, full manifests, runtime identity, and review flags remain under the
application directory. A caption is an automatic model prediction; writing it does
not establish training acceptance or anime tagging accuracy.

## Tagging error repairs

The numeric definitions and explicit error-to-fix mappings live in
`src/image_dataset_train/terror.py`. The current production entry is:

```json
{
  "te001": "Same-stem image or caption collision.",
  "tf001": "Give each image a unique filename stem.",
  "fixes_for_error": {"te001": ["tf001"]}
}
```

This JSON illustrates the definitions, not an external configuration file.

The shared dispatcher serves `trainime tag <path> --fix`,
`trainime remove <path> --fix`, `trainime fix <path>`, the menu's conditional fix
option, and `trainime doctor --path <path> --fix`. Selection rules:

- Bare `--fix` or `--fix all` detects and applies every applicable registered fix.
  `trainime fix <path>` uses this selection by default.
- `--fix 1`, `--fix 001`, and `--fix tf001` select fix number 1.
- `--fix te001` follows the error's registered mapping. Error and fix numbers are
  independent; an error can require multiple fixes.
- Comma-separated selectors and repeated `--fix` options combine selections.
  The dispatcher deduplicates them and executes in numeric order.
- Every selector is validated before mutation. Unknown or malformed codes fail
  with the registered choices. IDs are positive integers with at least three
  digits in displayed codes, not a three-digit limit.
- All these commands accept `--dryrun`, which previews without writes or downloads.
  The printed apply command retains the selected fixes.

Only `tf001` is currently a production directory repair. Adding a repair means
registering a `FixRule` with a number, description, detector, handler, and optional
pending-recovery detector, plus its `ErrorRule` mappings. References can be lazy
`module:function` strings; diagnostics remain usable without the tagging runtime.
CLI parsing, menu choices, doctor, and result rendering need no per-fix branches.
Handlers return `RepairResult` actions, metrics, errors, recovery report paths,
and optional per-image dry-run projections. The caller holds the source lock;
handlers own their saved intent and recovery. A handler failure stops later fixes
and tagging/removal; earlier completed repairs remain recorded. Rerunning detects
remaining work. Unselected unfinished repairs block tagging/removal and identify
the required resume codes.

### tf001: same-stem repair

The rule applies recursively to every same-stem group, with case-folded comparison
inside each directory. Each regular image gets `<stem>-<extension>` with a numeric
suffix if occupied; reservations include existing files, folders, captions, and
other planned destinations. Long stems are shortened with a hash suffix to leave
room. Images keep their directory, extension, and bytes. Unique image/caption pairs
are left alone; directories and links are never moved as files.

Existing captions in a collision have no reliable owner. Before any image in that
group moves, preserve every regular ambiguous caption under
`operations/<time>-tf001-<id>/captions/<original-relative-path>`, flush and verify its
SHA256, then remove the original ambiguous sidecar. Tagging generates independent
captions for the renamed images. Fix-only/doctor commands stop after repair.

Before mutation, `fix.json` records `error_code`, `fix_code`, source root, original
and destination paths, SHA256 hashes, and per-action completion. The append-only
`journal.jsonl` records intent and completion. Exclusive publication avoids
overwriting a raced destination. An interrupted repair resumes from its saved plan;
a publication completed before journaling is recognized by its hash. Retrying
refreshes remaining file snapshots and retains changed snapshots/partial backups.
Tag/remove without `--fix` will not proceed through an unfinished repair. Completed
groups are not renamed again. Repair and tagging share the source-directory lock.

Output and structured error events carry `[te001]` and `[tf001]`; tag-operation
receipts store a list of dispatched repairs with their codes, metrics, errors,
and recovery reports. Repair results show counts and recovery paths.
These journals provide process-interruption recovery, not filesystem-wide atomicity
or a guarantee against hardware failure or hostile external file changes.
Completed inventory/tag reports retry brief Windows sharing locks with bounded
backoff before reporting failure; a persistent lock leaves staged reports intact.

## Removal, recovery, and interruptions

Remove Tags means removal of paired text caption files, including manual captions.
It does not mean changing image metadata. Removal inspects file associations and
caption hashes without decoding images or loading a model. A caption beside a
corrupt image with a supported extension can still be removed. Orphan `.txt`
files and ambiguous image/caption stems remain untouched unless `--fix tf001`
explicitly requests the repair described above.

For each matched caption, copy its bytes under
`operations/<run>/captions/<original-relative-path>`, flush the backup, verify its
SHA256, journal the verified backup, recheck the original, then unlink the caption.
The backup tree mirrors the source tree so files can be copied back to the original
directory. There is no automatic expiry or backup deletion.

Every mutating operation records its original plan, completion/failure state, and
an append-only journal. A Ctrl+C arriving during a caption publication/removal is
handled after that individual file and journal commit. Earlier completed files
remain completed; later files remain untouched. A rerun fills missing captions
and reuses completed score cache entries. If the process is killed abruptly,
inspect `journal.jsonl`: `create_intent` can precede a completed publication;
`backup_verified` guarantees the recovery copy existed before any removal.
These records support recovery; they do not claim full power-loss transactions.

A per-directory OS file lock prevents simultaneous Trainime actions on the same
directory; a separate lock protects shared model setup. Neither lock blocks other
software from editing images. Stop external writers while applying changes:
portable filesystem checks cannot eliminate every hostile rename/edit race.
Symlinks and Windows junctions inside a collection are not followed.

## State, preview, and exit status

On Windows, the application root is `%LOCALAPPDATA%\trainime`; on other platforms,
the standard user data directory is used. `TRAINIME_HOME` overrides the entire
root for an isolated installation or test. Settings are atomic JSON. Models,
scores, operation journals, and technical run artifacts occupy separate children.
The source and application-data directories must not overlap.

Dry run performs the same discovery and eligibility decisions, but creates no
settings, locks, reports, caches, backups, or captions and does not load/download
models. It counts intended work, not predicted tag output. Applying after a
preview always rescans current files.

Direct command exit codes: `0` completed without reported issues, `1` completed
with skipped/failed image operations, `2` could not run due to path/configuration/
runtime failure, `130` cancelled. Interactive errors return to Home. The older
`dataset` technical commands remain available and retain their separate semantics.

## Verification scope

Automated coverage includes the exact menu and prompt count, saved/session path
precedence and expiry, cancellation, literal/narrow-terminal output, read-only
previews, source preservation, inference filtering, cache reuse, caption collisions,
concurrent jobs, file changes before publication/removal, backup failures, and
partial-run recovery. Test graphs validate the complete ONNX-to-caption workflow.
Installed-command and real pinned-model evidence is recorded in `TODO.md`.

Remaining qualification: accuracy on a reviewed anime collection, physical CUDA
execution, very large collections, trainer import, and human dataset acceptance.
