# Installation, logs, and recovery

Run **install.cmd** from the extracted Trainime folder. It can be double-clicked,
and it works when launched from another directory. Then open a terminal and run
`trainime`. The menu and normal tagging questions are unchanged.

The Windows installer obtains a compatible Python automatically, prepares the CPU
runtime, verifies imports and real ONNX execution in a separate environment,
installs the command, and registers the user's PATH. It runs at normal user
privilege. The command printed as **Launch now** also works in an already-open
terminal whose PATH has not refreshed yet.

Existing usable uv/Python installations are reused. If uv is unavailable, the
installer downloads a pinned official release and verifies its embedded SHA256
before execution. If Python is unavailable, uv obtains it. The wrapper sets script
execution policy only for its child process; it does not alter system policy.
Paths with spaces, quotes in arguments, and Unicode are supported. A stale or
missing dependency lock is refreshed in a temporary project copy, leaving the
checkout intact. Failed cache extraction triggers a new cache rather than deletion
of the old cache. Network failures receive one bounded retry.

The installer retains a verified wheel, dependency pins, its own repair scripts,
and `install.json` under the application-data directory. Repair verifies checksums
before using those files. The native runtime is checked again after installation.
Previous receipts and failed build directories are retained for diagnosis.

These implementation choices follow the official documentation for
[uv tools](https://docs.astral.sh/uv/guides/tools/),
[automatic Python management](https://docs.astral.sh/uv/concepts/python-versions/),
and [the uv installer](https://docs.astral.sh/uv/reference/installer/).
The bootstrap archive is the tested
[uv 0.9.5 release](https://github.com/astral-sh/uv/releases/tag/0.9.5);
newer already-installed uv versions can be reused.

## Doctor

```powershell
trainime doctor
trainime doctor --fix
trainime doctor --path 'D:\images\anime'
trainime doctor --fix --dryrun
```

Doctor checks dependencies, native CPU inference, saved settings, storage, command
registration, model integrity, and cached score integrity. `--path` additionally
checks image/caption associations. `--fix` performs supported repairs;
`--dryrun` prevents writes and downloads, even with `--fix`. `--json` returns
structured findings for scripts. Diagnosis remains accessible when the UI or native
tagging libraries are broken because the startup and doctor code use the standard
library and probe the runtime in a separate process.

| Problem | Recovery |
| --- | --- |
| Missing/broken dependencies or application Python files | `trainime doctor --fix` restores the exact recorded runtime and rechecks native inference. |
| Command cannot start or is not found | Run `install.cmd` again. The installer prints a direct launch command and registers PATH for new terminals. |
| An older Trainime command takes precedence | `trainime doctor --fix` prioritizes the registered command in user PATH and rechecks resolution. Use the installer's direct launch command if a system PATH entry still takes precedence. |
| Broken settings or unavailable saved default | Doctor preserves the original settings and clears the default. The menu also remains usable without that saved preference. |
| Missing/damaged tagger model | Tagging automatically preserves damaged artifacts and fetches the pinned replacement. Doctor can prepare it in advance. |
| Damaged score cache | Tagging preserves the invalid vector and recomputes it. Doctor can check and preserve bad vectors in advance. |
| Download failure | Reconnect/check proxy and system clock, then repeat the action or run doctor. Partial download caches remain available. TLS verification stays enabled. |
| Full disk | Free space on the reported drive or choose another writable `TRAINIME_HOME`, then repeat the action. Completed captions and backups are kept. |
| Locked/read-only files | Close the writer or use a writable folder, then repeat the action. Errors name the file and retain a traceback. |
| Two images share a caption stem | Give the images distinct stems, such as `art-jpg.jpg` and `art-png.png`. Doctor reports collisions; it does not guess which caption belongs to which image. |
| Broken/animated/excessively large image | Re-export a single-frame PNG/JPEG with reasonable dimensions and retry that file. The original is retained. |
| App data overlaps the image folder | Select the image subfolder or set `TRAINIME_HOME` to a separate writable directory. |

On Windows, a running doctor cannot replace its own executable. Runtime repair
therefore reinstalls dependencies and restores the exact package's Python files
without replacing that launcher; verification runs in a new process. A broken
launcher is repaired by `install.cmd`, outside the affected process. Original
damaged application files are retained under `recovery/application`.

Doctor never renames source images, invents a caption association, weakens file
integrity checks, changes system security policy, or deletes dataset files to make
a check pass. Findings that require a data decision include a concrete manual fix.

## Logs

```powershell
trainime logs
trainime logs --tail 40
```

Default Windows location: `%LOCALAPPDATA%\trainime\logs`.
`TRAINIME_HOME` relocates application data and logs together.

- `install-<time>-<id>.log`: installer steps, native commands, stdout/stderr, exit
  codes, and failure stack traces. The adjacent JSON records completion or failure.
- `<time>-<id>.jsonl`: structured application events with version, process/session
  identifiers, action, source/report references, and completion counts.
- `<time>-<id>.errors.jsonl`: errors with a stable diagnosis code, a recovery action,
  exception type, full traceback, and operation context.
- `operations/<run>`: per-image plan, backup paths, and mutation journal, retained
  separately from diagnostic logging.

Each process rotates its own log after 5 MiB; old session and error logs are retained.
Logging avoids image bytes, caption content, and environment dumps, and redacts
common credential formats. Paths are included because they identify failed work.
If the normal log location is inaccessible, application logs fall back to the
system temporary directory and disclose that location. A logging failure never
replaces the original exception with a different crash.

Tag/remove previews create no logs or other files. Doctor writes a diagnostic
report unless `--dryrun` is present. Startup errors and failed normal operations
create logs; ordinary menu browsing does not.

## Installer recovery switches

Normal installation needs no options. For support or unattended use:

```powershell
.\install.cmd -NoPause
.\install.cmd -Repair -Offline -NoPause
```

`-Repair` uses the retained verified package; `-Offline` uses only available
downloads. If prerequisites are not cached, the installer explains that an online
run is needed. `-NoPath` is available for isolated test installations. Diagnostic
repair respects that choice. `-RuntimeOnly` is an internal mode used by doctor.

The verified host is Windows x64 with PowerShell 5.1 and 7. ARM64 has a bootstrap
mapping, but its native inference/runtime installation has not been qualified here.
The Python CLI remains portable; the automatic installation and runtime-repair
script in this release targets Windows.
