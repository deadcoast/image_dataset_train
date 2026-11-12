# Find saved recovery operations

Use `dataset recovery` to find removal backups and repair receipts without searching
generated folders by hand. It reads the known operation and application-repair
directories under Trainime's application data. It does not search image directories,
create recovery records or run repairs.

```powershell
dataset recovery
dataset recovery --source 'D:\images\artwork'
dataset recovery --kind removal --status completed --json
```

The default home follows `TRAINIME_HOME`, or the normal Trainime application-data
directory when that variable is unset. Use `--home` to inspect another known home:

```powershell
dataset recovery --home 'D:\saved Trainime state' --json
```

Supported kinds are `removal`, `collision`, `restore` and `package`. Filters match
the exact recorded source and status. A package-repair receipt has no image source,
so it does not match a source-directory filter. Invalid or unavailable records are
reported alongside valid peers instead of hiding the entire history.

## Inspect one receipt

Copy the complete record ID from the listing, or use its printed Inspect command:

```powershell
dataset recovery show <full-record-id>
dataset recovery show <full-record-id> --expected-sha256 <receipt-sha256> --json
```

For a nondefault home, keep the same `--home` argument. `--home` and `--json` are
accepted before or after `show`. Source, kind and status filters apply to listing
only. Record IDs bind the saved artifact location and metadata identity; shortened
IDs and changed selections are rejected. A changed receipt requires a fresh listing.

The view includes affected paths, backup/recovery locations, recorded progress and
commands appropriate to the receipt's kind. JSON includes full paths, saved identity
fields, command argument arrays, environment settings and PowerShell/POSIX examples.
Long human-readable path lists are abbreviated; `--json` retains all rows.
Path counts describe rows in the saved receipt or plan, including planned or
unchanged entries. They are not counts of files changed or verified backups.

Listing and `show` are **metadata-only** and work with source images offline. Saved
status does not prove process liveness, backup integrity or that a pending operation
made no changes. Use the explicit preview or diagnosis command to inspect current
files. Recovery evidence does not establish caption quality or human acceptance.

## Recover removed captions

A removal record provides a read-only preview and a separate explicit apply command:

```powershell
dataset restore-captions --receipt 'D:\state\operations\remove-run\operation.json' `
  --expected-sha256 <receipt-sha256> --expected-plan-sha256 <plan-sha256> --dryrun
```

The selected checksums reject a changed removal receipt or plan, including legacy
receipts that do not themselves bind their plan. Existing restoration checks
also validate the plan, journal, image associations and backups before writing.
Preview creates no captions, locks or reports. The separate apply command restores
only missing captions; newer captions and conflicts are preserved. Legacy evidence
that cannot prove image identity remains unverifiable rather than gaining invented
identity from the browser. See [caption restoration](RECOVERY.md#restoring-removed-captions).

Generated commands preserve the receipt's application home through `TRAINIME_HOME`.
The PowerShell example explicitly sets that variable for the current terminal; the
POSIX example applies it to the one command. Keep the environment setting with the
copied command when working with an alternate home.

A `restore` record describes a previous restoration attempt and links its original
removal receipt. It does not provide an undo operation or remove restored captions.

## Inspect collision and package repairs

A collision record provides the existing `trainime fix <source> --fix 1 --dryrun`
command. This preview checks **all pending tf001 repairs for that source**, not just
the displayed receipt. It does not reverse image renames or decide which image an
ambiguous caption belongs to. Retained ambiguous captions need explicit inspection
and assignment; the browser shows their recovery paths without inventing an undo.

A package-repair record offers `trainime doctor --dryrun` for the current installed
command. It does not replay a historical wheel or write to a historical installation
target. Receipt state and saved backups remain available independently of today's
package integrity. See [package recovery](RECOVERY.md#package-files-and-resources).

Diagnosis output and operation summaries link back to this browser. The existing
four-choice Trainime Home menu stays unchanged. Preparation jobs and publication
recovery continue through [collections](COLLECTIONS.md) and
[preparation status](RECOVERY.md#finding-and-inspecting-preparation-work).
