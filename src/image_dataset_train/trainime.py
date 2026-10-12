"""A short, path-first interactive CLI over the local tagging pipeline."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from image_dataset_train import __version__
from image_dataset_train.diagnostics import EventLog, diagnose, failure_text
from image_dataset_train.operations import Result, run_directory
from image_dataset_train.preferences import Preferences, app_home, image_directory

HOME_MENU = "[1] Tag Image Directory\n[2] Remove Tags\n[3] Help\n[0] Settings"
HELP = """1  Tag: create missing .txt captions beside images, including subfolders.
   Existing captions stay. First tagging run downloads the model.
2  Remove: back up and remove matching .txt captions, including manual ones.
   Images and unrelated text files stay. Results show the backup location.
0  Settings: session path takes priority over saved default path.

Type a number, then Enter. q exits from Home; 0 goes back from Settings.
Ctrl+C cancels the current action. Ctrl+D exits at a prompt.
Tab completes paths. Quoted paths pasted from Explorer work.

trainime tag "D:\\images" --dryrun
trainime remove "D:\\images" --dryrun
Omit --dryrun to apply. Preview performs no inference, downloads, or writes.
With a saved default path: trainime tag / trainime remove
To retag: Remove Tags, then Tag Image Directory.

trainime doctor --fix   Diagnose and repair installation, settings, and caches.
trainime logs          Show log locations and the latest error details.
trainime tag "D:\\images" --fix tf001   Repair te001 collisions, then tag.
Add --dryrun to preview. Ambiguous captions are preserved in recovery.
"""


def command_text(action: str, source: Path, dryrun: bool, fix: str | bool = False) -> str:
    text = str(source)
    quoted = "'" + text.replace("'", "''") + "'" if os.name == "nt" else shlex.quote(text)
    return (
        f"trainime {action} {quoted}"
        + (" --fix tf001" if fix else "")
        + (" --dryrun" if dryrun else "")
    )


class Terminal:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(
            highlight=False, markup=False, theme=Theme({"progress.elapsed": "dim"})
        )
        self._session = None
        self.home = app_home()
        self.dryrun = False

    def failure(self, error: BaseException, **context: object) -> None:
        self.heading("Could not finish", style="red")
        lines = failure_text(
            error, EventLog(self.home, enabled=not self.dryrun), **context
        ).splitlines()
        for index, line in enumerate(lines):
            style = "bold red" if index == 0 else "cyan" if line.startswith("Fix:") else None
            self.say(line, style=style)

    def say(
        self, text: str | Text = "", *, style: str | None = None, literal: bool = False
    ) -> None:
        self.console.print(
            text,
            style=style,
            markup=False,
            highlight=False,
            soft_wrap=literal or not self.console.is_terminal,
        )

    def heading(self, title: str, *, style: str = "cyan") -> None:
        self.say()
        self.console.print(
            Rule(Text(title, style=f"bold {style}"), style="dim", align="left"),
            width=min(self.console.width, 88),
        )
        self.say()

    def path(self, label: str, value: Path | str) -> None:
        self.say(Text.assemble((label, "dim"), "  ", (str(value), "cyan")), literal=True)

    def home_menu(self, preferences: Preferences, *, dryrun: bool) -> None:
        self.say()
        self.say(Text.assemble(("trainime", "bold cyan"), (f"  v{__version__}", "dim")))
        self.say(
            "Local anime tagging"
            + (" · images to training captions" if self.console.width >= 60 else ""),
            style="dim",
        )
        if dryrun:
            self.say("--dryrun active · inspect only; no files changed", style="cyan")
        self.say()
        menu = Table.grid(padding=(0, 3))
        menu.add_column(no_wrap=True)
        wide = self.console.width >= 72
        if wide:
            menu.add_column(style="dim")
        descriptions = (
            "Fill missing captions; keep existing tags",
            "Back up and remove paired captions",
            "Workflow, commands, and keyboard shortcuts",
            "Default and session image directories",
        )
        for label, description in zip(HOME_MENU.splitlines(), descriptions, strict=True):
            row = Text(label, style="bold")
            row.stylize("bold cyan", 0, 3)
            menu.add_row(row, *([description] if wide else []))
        self.console.print(menu)
        self.say()
        if preferences.selected_path:
            label = "Session" if preferences.session_path else "Default"
            self.path(label, preferences.selected_path)
        else:
            self.say("Directory will be requested when you choose an action.", style="dim")
        self.say(
            "q quit   ·   Ctrl+C cancel"
            + ("   ·   Tab complete paths" if self.console.width >= 60 else ""),
            style="dim",
        )

    def help(self) -> None:
        self.heading("Help")
        text = Text(HELP)
        text.highlight_regex(r"(?m)^trainime[^\n]*", "cyan")
        text.highlight_regex(r"(?m)^[120]  [^:]+:", "bold cyan")
        text.highlight_words(["--dryrun", "Ctrl+C", "Ctrl+D", "Tab"], "bold cyan")
        self.say(text)

    def ask(self, label: str, *, path: bool = False) -> str:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return input(label)
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import PathCompleter
        from prompt_toolkit.styles import Style

        if self._session is None:
            self._session = PromptSession()
        color = self.console.color_system is not None and not self.console.no_color
        return self._session.prompt(
            [("class:prompt", label)] if color else label,
            style=Style.from_dict({"prompt": "ansicyan bold"}) if color else None,
            completer=PathCompleter(only_directories=True, expanduser=True) if path else None,
            complete_while_typing=False,
            enable_history_search=False,
        )

    def work(
        self, action: str, source: Path, home: Path, dryrun: bool, fix: str | bool = False
    ) -> Result:
        self.home, self.dryrun = home, dryrun
        self.heading(
            ("Dry run" if dryrun else "Run")
            + " · "
            + {"tag": "Tag images", "remove": "Remove captions", "fix": "Fix te001"}[action]
        )
        self.say(command_text(action, source, dryrun, fix), style="dim", literal=True)
        self.say(
            "Checking eligibility only; no tags generated or files changed."
            if dryrun
            else "Including subfolders · "
            + (
                "tf001 renames collisions and preserves ambiguous captions in recovery"
                if fix or action == "fix"
                else "existing captions are kept"
                if action == "tag"
                else "captions are backed up first"
            ),
            style="dim",
        )
        self.say()
        last = 0.0
        last_phase = ""
        columns = [SpinnerColumn(style="cyan"), TextColumn("{task.description}", markup=False)]
        if self.console.width >= 72:
            columns.append(
                BarColumn(
                    bar_width=18, complete_style="cyan", finished_style="green", pulse_style="cyan"
                )
            )
        columns.append(TimeElapsedColumn())
        with Progress(
            *columns, console=self.console, transient=True, disable=not self.console.is_terminal
        ) as display:
            task = display.add_task("Inspecting directory…", total=None)

            def progress(message: str) -> None:
                nonlocal last, last_phase
                if message == "CUDA unavailable; using CPU":
                    return
                if message.startswith("Providers:"):
                    message = "Tagging locally on " + (
                        "GPU…" if "CUDAExecutionProvider" in message else "CPU…"
                    )
                phase = message.split(":", 1)[0].split(" ", 1)[0]
                fraction = re.search(r"([\d,]+)/([\d,]+)$", message)
                total = int(fraction[2].replace(",", "")) if fraction else None
                completed = int(fraction[1].replace(",", "")) if fraction else 0
                display.update(task, description=Text(message), total=total, completed=completed)
                now = time.monotonic()
                if message.startswith(("Cancelled;", "Stopped;")):
                    self.say(message, style="red" if message.startswith("Stopped;") else "yellow")
                elif not self.console.is_terminal and (phase != last_phase or now - last >= 5):
                    self.say(message, style="dim")
                    last, last_phase = now, phase

            return run_directory(action, source, home, dryrun=dryrun, progress=progress, fix=fix)

    def result(self, result: Result) -> None:
        if result.repairs is not None:
            repairs = result.repairs
            renames = [a for a in repairs.actions if a["kind"] == "image"]
            captions = [a for a in repairs.actions if a["kind"] == "caption"]
            self.heading("[tf001] " + ("Repair preview" if result.dryrun else "Repair results"))
            if result.dryrun:
                self.say(
                    f"Would rename {len(renames):,} images and preserve "
                    f"{len(captions):,} ambiguous captions in recovery."
                )
                for action in renames[:3]:
                    self.say(f"  {action['source']} → {action['target']}")
                if len(renames) > 3:
                    self.say(f"  …and {len(renames) - 3:,} more renames.")
                self.say("No files changed.", style="dim")
            else:
                self.say(
                    f"Renamed {repairs.renamed:,} images; preserved "
                    f"{repairs.archived:,} ambiguous captions in recovery."
                )
            for report in repairs.reports:
                self.path("tf001 journal / caption recovery", report)
        if result.action == "fix":
            for error in result.errors[:3]:
                self.say(error, style="red")
            if result.errors and result.log:
                self.path("Error log", result.log)
            if result.dryrun and result.repairs and result.repairs.actions:
                self.say(command_text("fix", result.source, False), style="cyan", literal=True)
            return
        counts = result.counts
        skipped = counts["blocked"] + counts["rejected"]
        if result.dryrun:
            self.heading(
                "Dry run · "
                + ("Tag eligibility" if result.action == "tag" else "Removal eligibility"),
                style="cyan",
            )
            count = counts["ready"]
            noun = ("image" if result.action == "tag" else "caption") + ("" if count == 1 else "s")
            self.say(
                Text.assemble(
                    ("--dryrun", "bold cyan"),
                    " found ",
                    (f"{count:,}", "bold green"),
                    f" {noun} that ",
                    ("can", "bold green"),
                    " be serviced for tags."
                    if result.action == "tag"
                    else " be removed after backup.",
                )
            )
        else:
            title = "Tagging complete" if result.action == "tag" else "Removal complete"
            if result.exit_code:
                title = "Finished with issues"
            elif not result.changed:
                title = "Nothing to tag" if result.action == "tag" else "Nothing to remove"
            style = (
                "red"
                if result.errors and not result.changed
                else ("yellow" if result.exit_code else "green")
            )
            self.heading(title, style=style)
            verb = "Written" if result.action == "tag" else "Removed"
            self.say(
                Text.assemble(
                    (f"{verb}: ", "bold"),
                    (f"{result.changed:,}", "bold green" if result.changed else "bold"),
                    " caption" + ("" if result.changed == 1 else "s") + ".",
                )
            )
        metrics = [(len(result.items), "images scanned", "dim")]
        if result.dryrun:
            metrics.append((counts["ready"], "eligible", "green"))
        if counts["existing"]:
            metrics.append((counts["existing"], "already tagged (kept)", "dim"))
        if counts["missing"]:
            metrics.append((counts["missing"], "without captions", "dim"))
        if skipped:
            metrics.append((skipped, "skipped", "yellow"))
        if result.errors:
            metrics.append((len(result.errors), "errors", "red"))
        summary = Text()
        for index, (count, label, style) in enumerate(metrics):
            if index:
                summary.append("\n" if self.console.width < 60 else "   ·   ", style="dim")
            summary.append(f"{count:,} {label}", style=style)
        self.say(summary)
        if result.dryrun:
            self.say(
                "No files changed. "
                + ("No tags generated." if result.action == "tag" else "No captions removed."),
                style="dim",
            )
        elif result.changed and result.action == "tag":
            self.say("Saved as matching .txt files beside your images.", style="dim")
        issues = [
            (item.image, item.reason)
            for item in result.items
            if item.status in {"blocked", "rejected"}
        ] + [("", error) for error in result.errors]
        if issues:
            self.say()
            self.say(
                f"Needs attention · {len(issues):,} " + ("issue" if len(issues) == 1 else "issues"),
                style="bold yellow",
            )
            for filename, reason in issues[:3]:
                diagnosis = diagnose(reason)
                detail = diagnosis.problem if diagnosis.code == "IMAGE_UNREADABLE" else reason
                self.say(
                    Text.assemble(
                        f"  [{diagnosis.code}] ",
                        (f"{filename}: " if filename else "", "bold"),
                        detail,
                    )
                )
            fixes = []
            for _, reason in issues[:3]:
                diagnosis = diagnose(reason)
                fix = diagnosis.fix.removeprefix("Run: ")
                if diagnosis.code == "te001":
                    fix = "[tf001] Apply: " + command_text(
                        result.action, result.source, False, True
                    )
                if diagnosis.code == "UNEXPECTED_ERROR" and not result.log:
                    fix = "Retry the action. If it still fails, run trainime doctor."
                fixes.append(fix)
            for fix in dict.fromkeys(fixes):
                self.say(f"Fix: {fix}", style="cyan")
            if len(issues) > 3:
                self.say(f"  …and {len(issues) - 3:,} more.")
        if not result.items:
            if not result.errors:
                self.say("No supported images found in this directory.")
        elif counts["existing"] == len(result.items):
            self.say("All images already have captions.")
        if result.review:
            self.say(
                f"Review suggested: {result.review:,} images; details in the report.",
                style="yellow",
            )
        if result.backup or result.report:
            self.say()
        if result.backup:
            self.path("Caption backup", result.backup)
        if result.report:
            self.path("Report", result.report)
        if issues and result.log:
            self.path("Error log", result.log)
        if result.dryrun and counts["ready"]:
            self.say()
            self.say("Run to apply", style="bold")
            self.say(
                command_text(result.action, result.source, False, result.repairs is not None),
                style="cyan",
                literal=True,
            )
        self.say()


class App:
    def __init__(
        self,
        preferences: Preferences,
        terminal: Terminal,
        worker: Callable[..., Result] | None = None,
        *,
        dryrun: bool = False,
        fix: str | bool = False,
    ) -> None:
        self.preferences = preferences
        self.terminal = terminal
        self.worker = worker or terminal.work
        self.dryrun = dryrun
        self.fix = fix
        self.terminal.home = preferences.home
        self.terminal.dryrun = dryrun

    def _path(self) -> Path | None:
        selected = self.preferences.selected_path
        if selected is not None:
            try:
                selected = image_directory(str(selected))
            except (OSError, ValueError) as exc:
                self.terminal.say(f"Saved/session path unavailable: {exc}", style="yellow")
            else:
                self.terminal.path("Image directory", selected)
                return selected
        self.terminal.say("Image directory (used for this session; Settings saves a default):")
        while True:
            value = self.terminal.ask("Path: ", path=True)
            if not value.strip():
                return None
            try:
                selected = image_directory(value)
            except (OSError, ValueError) as exc:
                self.terminal.say(str(exc), style="yellow")
            else:
                self.preferences.session_path = selected
                return selected

    def _preview(self) -> bool:
        if self.dryrun:
            return True
        while True:
            answer = self.terminal.ask("Preview only? --dryrun [y/N]: ").strip().lower()
            if answer in {"", "n", "no"}:
                return False
            if answer in {"y", "yes", "--dryrun", "--dry-run"}:
                return True
            self.terminal.say("Enter y for --dryrun, or Enter to apply.")

    def action(self, action: str) -> None:
        source = self._path()
        if source is None:
            return
        if action == "remove":
            self.terminal.say("Remove matching .txt captions; save a backup first.")
        dryrun = self._preview()
        options = {"fix": self.fix} if self.fix else {}
        result = self.worker(action, source, self.preferences.home, dryrun, **options)
        self.terminal.result(result)
        if (
            not dryrun
            and not self.fix
            and (
                any(i.error_code == "te001" for i in result.items)
                or any(diagnose(error).code == "te001" for error in result.errors)
            )
        ):
            self.terminal.say(
                "[tf001] Rename colliding images; preserve ambiguous captions in recovery."
            )
            while True:
                answer = self.terminal.ask("Apply tf001? --fix [y/N]: ").strip().lower()
                if answer in {"", "n", "no", "q"}:
                    break
                if answer in {"y", "yes", "--fix", "--fix tf001", "tf001"}:
                    repaired = self.worker(
                        action, source, self.preferences.home, False, fix="tf001"
                    )
                    self.terminal.result(repaired)
                    break
                self.terminal.say("Enter y to apply --fix tf001, or Enter to keep files unchanged.")

    def settings(self) -> None:
        while True:
            self.terminal.heading("Settings")
            for key, label, path, detail in (
                (
                    "1",
                    "Default image path",
                    self.preferences.default_path,
                    "Saved between sessions",
                ),
                (
                    "2",
                    "Session image path",
                    self.preferences.session_path,
                    "Overrides default until exit",
                ),
            ):
                self.terminal.say(Text.assemble((f"[{key}] ", "bold cyan"), (label, "bold")))
                self.terminal.say(
                    f"    {path or 'Not set'}", style="cyan" if path else "dim", literal=True
                )
                self.terminal.say(f"    {detail}", style="dim")
                self.terminal.say()
            self.terminal.say(Text.assemble(("[0] ", "bold cyan"), "Back"))
            choice = self.terminal.ask("> ").strip()
            if choice in {"0", "q"}:
                return
            if choice not in {"1", "2"}:
                self.terminal.say("Choose 1, 2, or 0.")
                continue
            value = self.terminal.ask("Directory (blank clears): ", path=True)
            try:
                path = image_directory(value) if value.strip() else None
                if choice == "1":
                    if self.dryrun:
                        self.terminal.say("--dryrun: default path was not saved.", style="cyan")
                    else:
                        self.preferences.save_default(path)
                        self.terminal.say(
                            "Default path saved." if path else "Default path cleared.",
                            style="green",
                        )
                else:
                    self.preferences.session_path = path
                    self.terminal.say(
                        "Session path set until exit."
                        if path
                        else "Session path cleared; saved default is active.",
                        style="green",
                    )
            except (OSError, ValueError) as exc:
                self.terminal.failure(exc, action="save_settings")

    def run(self) -> int:
        while True:
            try:
                self.terminal.home_menu(self.preferences, dryrun=self.dryrun)
                choice = self.terminal.ask("> ").strip().lower()
                if choice in {"q", "quit", "exit"}:
                    return 0
                if choice in {"1", "2"}:
                    self.action("tag" if choice == "1" else "remove")
                elif choice == "3":
                    self.terminal.help()
                elif choice == "0":
                    self.settings()
                else:
                    self.terminal.say("Choose 1, 2, 3, 0, or q.")
            except EOFError:
                return 0
            except KeyboardInterrupt:
                self.terminal.say("\nCancelled. Back at Home.")
            except Exception as exc:
                self.terminal.failure(exc, action="interactive")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trainime", description="Tag anime image directories locally."
    )
    parser.add_argument("--version", action="version", version=f"trainime {__version__}")
    parser.add_argument(
        "--fix",
        nargs="?",
        const="tf001",
        choices=["tf001", "te001"],
        help="apply tf001 collision repair during menu actions",
    )
    parser.add_argument(
        "--dryrun",
        "--dry-run",
        action="store_true",
        help="preview only; no inference, downloads, or writes",
    )
    sub = parser.add_subparsers(dest="action")
    for name, help_text in (
        ("tag", "write missing image captions"),
        ("remove", "back up and remove matching image captions"),
        ("fix", "apply tf001 collision repair without tagging"),
    ):
        command = sub.add_parser(name, help=help_text, description=help_text.capitalize() + ".")
        command.add_argument("path", nargs="?", help="image directory; defaults to saved path")
        command.add_argument(
            "--fix",
            nargs="?",
            const="tf001",
            choices=["tf001", "te001"],
            dest="action_fix",
            help="repair te001 with tf001 before this action",
        )
        command.add_argument(
            "--dryrun",
            "--dry-run",
            dest="action_dryrun",
            action="store_true",
            help="preview without changing files",
        )
    sub.add_parser("help", help="show workflow and essential keys")
    sub.add_parser("doctor", help="diagnose and repair problems; trainime doctor --help")
    sub.add_parser("logs", help="show logs and the latest errors")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"doctor", "logs"}:
        from image_dataset_train.doctor import main as doctor_main

        return doctor_main(arguments)
    args = _parser().parse_args(arguments)
    terminal = Terminal()
    terminal.dryrun = args.dryrun or getattr(args, "action_dryrun", False)
    if args.action == "help":
        terminal.help()
        return 0
    try:
        try:
            preferences = Preferences.load(app_home())
        except ValueError as exc:
            terminal.failure(exc, action="load_settings")
            # A corrupt saved preference should never lock the user out of the menu.
            preferences = Preferences(app_home())
            terminal.say("Continuing without a saved default. The original settings are kept.")
        if args.action is None:
            return App(preferences, terminal, dryrun=args.dryrun, fix=args.fix).run()
        source = image_directory(args.path) if args.path else preferences.default_path
        if source is None:
            terminal.say(
                "Supply an image directory: trainime "
                + args.action
                + ' "D:\\images" [--dryrun], or save one in trainime → Settings.'
            )
            return 2
        result = terminal.work(
            args.action,
            source,
            preferences.home,
            args.dryrun or args.action_dryrun,
            fix=args.fix or args.action_fix,
        )
        terminal.result(result)
        return result.exit_code
    except KeyboardInterrupt:
        terminal.say("Cancelled.")
        return 130
    except Exception as exc:
        terminal.failure(exc, action=args.action)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
