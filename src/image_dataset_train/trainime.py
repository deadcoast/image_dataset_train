"""A short, path-first interactive CLI over the local tagging pipeline."""

from __future__ import annotations

import argparse
import os
import shlex
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from rich.console import Console
from rich.text import Text

from image_dataset_train import __version__
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
"""


def command_text(action: str, source: Path, dryrun: bool) -> str:
    text = str(source)
    quoted = "'" + text.replace("'", "''") + "'" if os.name == "nt" else shlex.quote(text)
    return f"trainime {action} {quoted}" + (" --dryrun" if dryrun else "")


class Terminal:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console(highlight=False, markup=False)
        self._session = None

    def say(self, text: str = "", *, style: str | None = None, literal: bool = False) -> None:
        self.console.print(
            text,
            style=style,
            markup=False,
            highlight=False,
            soft_wrap=literal or not self.console.is_terminal,
        )

    def ask(self, label: str, *, path: bool = False) -> str:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            return input(label)
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import PathCompleter

        if self._session is None:
            self._session = PromptSession()
        return self._session.prompt(
            label,
            completer=PathCompleter(only_directories=True, expanduser=True) if path else None,
            complete_while_typing=False,
            enable_history_search=False,
        )

    def work(self, action: str, source: Path, home: Path, dryrun: bool) -> Result:
        self.say(command_text(action, source, dryrun), style="dim", literal=True)
        last = 0.0
        last_phase = ""
        with self.console.status(Text("Inspecting directory…"), spinner="dots") as status:

            def progress(message: str) -> None:
                nonlocal last, last_phase
                if message == "CUDA unavailable; using CPU":
                    return
                if message.startswith("Providers:"):
                    message = "Tagging locally on " + (
                        "GPU…" if "CUDAExecutionProvider" in message else "CPU…"
                    )
                status.update(Text(message))
                phase = message.split(":", 1)[0]
                now = time.monotonic()
                if message.startswith(("Cancelled;", "Stopped;")):
                    self.say(message)
                elif not self.console.is_terminal and (phase != last_phase or now - last >= 5):
                    self.say(message)
                    last, last_phase = now, phase

            return run_directory(action, source, home, dryrun=dryrun, progress=progress)

    def result(self, result: Result) -> None:
        counts = result.counts
        if result.dryrun:
            description = "images need captions" if result.action == "tag" else "captions to remove"
            self.say(f"Dry run: {counts['ready']:,} {description}. No files changed.")
        else:
            verb = "Written" if result.action == "tag" else "Removed"
            self.say(
                f"{verb}: {result.changed:,} captions.",
                style="yellow" if result.exit_code else "green",
            )
        if counts["existing"]:
            self.say(f"Kept: {counts['existing']:,} existing captions.")
        if counts["missing"]:
            self.say(f"No caption: {counts['missing']:,} images.")
        issues = [
            f"{item.image}: {item.reason}"
            for item in result.items
            if item.status in {"blocked", "rejected"}
        ] + result.errors
        if issues:
            self.say(f"Skipped / issues: {len(issues):,}.", style="yellow")
            for issue in issues[:3]:
                self.say(f"  {issue}")
            if len(issues) > 3:
                self.say(f"  …and {len(issues) - 3:,} more.")
        if not result.items:
            self.say("No supported images found in this directory.")
        if result.review:
            self.say(f"Caption review flags: {result.review:,} images; details in the report.")
        if result.backup:
            self.say(f"Caption backup: {result.backup}", literal=True)
        if result.report:
            self.say(f"Report: {result.report}", literal=True)


class App:
    def __init__(
        self,
        preferences: Preferences,
        terminal: Terminal,
        worker: Callable[..., Result] | None = None,
        *,
        dryrun: bool = False,
    ) -> None:
        self.preferences = preferences
        self.terminal = terminal
        self.worker = worker or terminal.work
        self.dryrun = dryrun

    def _path(self) -> Path | None:
        selected = self.preferences.selected_path
        if selected is not None:
            try:
                selected = image_directory(str(selected))
            except (OSError, ValueError) as exc:
                self.terminal.say(f"Saved/session path unavailable: {exc}", style="yellow")
            else:
                self.terminal.say(f"Image directory: {selected}")
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
        result = self.worker(action, source, self.preferences.home, self._preview())
        self.terminal.result(result)

    def settings(self) -> None:
        while True:
            self.terminal.say("\nSettings")
            self.terminal.say(
                f"[1] Default image path: {self.preferences.default_path or 'not set'}"
            )
            self.terminal.say(
                f"[2] Session image path: {self.preferences.session_path or 'not set'}"
            )
            self.terminal.say("[0] Back")
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
                        self.terminal.say("--dryrun: default path was not saved.")
                    else:
                        self.preferences.save_default(path)
                        self.terminal.say(
                            "Default path saved." if path else "Default path cleared."
                        )
                else:
                    self.preferences.session_path = path
                    self.terminal.say(
                        "Session path set until exit."
                        if path
                        else "Session path cleared; saved default is active."
                    )
            except (OSError, ValueError) as exc:
                self.terminal.say(str(exc), style="red")

    def run(self) -> int:
        while True:
            try:
                self.terminal.say("\ntrainime", style="bold")
                if self.dryrun:
                    self.terminal.say("--dryrun: preview only", style="yellow")
                self.terminal.say(HOME_MENU)
                self.terminal.say("q quit", style="dim")
                choice = self.terminal.ask("> ").strip().lower()
                if choice in {"q", "quit", "exit"}:
                    return 0
                if choice in {"1", "2"}:
                    self.action("tag" if choice == "1" else "remove")
                elif choice == "3":
                    self.terminal.say("\n" + HELP)
                elif choice == "0":
                    self.settings()
                else:
                    self.terminal.say("Choose 1, 2, 3, 0, or q.")
            except EOFError:
                return 0
            except KeyboardInterrupt:
                self.terminal.say("\nCancelled. Back at Home.")
            except (OSError, ValueError, RuntimeError) as exc:
                self.terminal.say(f"Could not finish: {exc}", style="red")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trainime", description="Tag anime image directories locally."
    )
    parser.add_argument("--version", action="version", version=f"trainime {__version__}")
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
    ):
        command = sub.add_parser(name, help=help_text, description=help_text.capitalize() + ".")
        command.add_argument("path", nargs="?", help="image directory; defaults to saved path")
        command.add_argument(
            "--dryrun",
            "--dry-run",
            dest="action_dryrun",
            action="store_true",
            help="preview without changing files",
        )
    sub.add_parser("help", help="show workflow and essential keys")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    terminal = Terminal()
    if args.action == "help":
        terminal.say(HELP)
        return 0
    try:
        preferences = Preferences.load(app_home())
        if args.action is None:
            return App(preferences, terminal, dryrun=args.dryrun).run()
        source = image_directory(args.path) if args.path else preferences.default_path
        if source is None:
            terminal.say(
                "Supply an image directory: trainime "
                + args.action
                + ' "D:\\images" [--dryrun], or save one in trainime → Settings.'
            )
            return 2
        result = terminal.work(
            args.action, source, preferences.home, args.dryrun or args.action_dryrun
        )
        terminal.result(result)
        return result.exit_code
    except KeyboardInterrupt:
        terminal.say("Cancelled.")
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        terminal.say(f"Could not finish: {exc}", style="red")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
