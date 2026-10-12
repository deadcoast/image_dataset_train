"""Numeric error/fix registry and selector grammar; no runtime dependencies."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorRule:
    number: int
    description: str
    fixes: tuple[int, ...]
    patterns: tuple[str, ...] = ()

    @property
    def code(self) -> str:
        return f"te{self.number:03d}"


@dataclass(frozen=True)
class FixRule:
    number: int
    description: str
    detect: str | Callable
    apply: str | Callable
    pending: str | Callable | None = None

    @property
    def code(self) -> str:
        return f"tf{self.number:03d}"


class RepairRegistry:
    def __init__(self) -> None:
        self.errors: dict[int, ErrorRule] = {}
        self.fixes: dict[int, FixRule] = {}

    def register(self, fix: FixRule, *errors: ErrorRule) -> None:
        if fix.number < 1 or fix.number in self.fixes:
            raise ValueError(f"Duplicate or invalid fix number: {fix.number}")
        seen = set(self.errors)
        for error in errors:
            if error.number < 1 or error.number in seen:
                raise ValueError(f"Duplicate or invalid error number: {error.number}")
            if not error.fixes or set(error.fixes) - (set(self.fixes) | {fix.number}):
                raise ValueError(f"{error.code} references an unregistered fix.")
            seen.add(error.number)
        self.fixes[fix.number] = fix
        self.errors.update((error.number, error) for error in errors)

    def error_codes(self, number: int) -> tuple[str, ...]:
        return tuple(e.code for _, e in sorted(self.errors.items()) if number in e.fixes)

    def for_errors(self, codes: Iterable[str | None]) -> tuple[FixRule, ...]:
        numbers = set()
        for code in codes:
            if code and re.fullmatch(r"te\d+", code.lower()):
                rule = self.errors.get(int(code[2:]))
                if rule:
                    numbers.update(rule.fixes)
        return tuple(self.fixes[n] for n in sorted(numbers))

    def diagnose(self, message: str) -> ErrorRule | None:
        return next(iter(self.diagnoses(message)), None)

    def diagnoses(self, message: str) -> tuple[ErrorRule, ...]:
        lower = message.lower()
        codes = self._message_codes(lower)
        return tuple(
            rule
            for _, rule in sorted(self.errors.items())
            if ("te", rule.number) in codes
            or any(("tf", n) in codes for n in rule.fixes)
            or any(p.lower() in lower for p in rule.patterns)
        )

    @staticmethod
    def _message_codes(message: str) -> set[tuple[str, int]]:
        return {
            (prefix, int(number))
            for group in re.findall(r"\[([^\]]+)\]", message.lower())
            for prefix, number in re.findall(r"\b(te|tf)([0-9]+)\b", group)
        }

    def for_messages(self, messages: Iterable[str]) -> tuple[FixRule, ...]:
        numbers = set()
        for message in messages:
            numbers.update(
                f.number for f in self.for_errors(r.code for r in self.diagnoses(message))
            )
            numbers.update(
                n for kind, n in self._message_codes(message) if kind == "tf" and n in self.fixes
            )
        return tuple(self.fixes[n] for n in sorted(numbers))

    def select(self, value) -> tuple[FixRule, ...]:
        """Bare/all selects all definitions; execution still requires detection."""
        if value is None or value is False or value == "":
            return ()
        if value is True:
            value = "all"
        values = value if isinstance(value, (tuple, list)) else [value]
        numbers, all_requested = set(), False
        for entry in values:
            for token in str(entry).lower().split(","):
                token = token.strip()
                if token == "all":
                    all_requested = True
                    continue
                match = re.fullmatch(r"(te|tf)?([0-9]+)", token)
                if not match or int(match[2]) < 1:
                    raise ValueError(
                        f"Invalid fix selector {token!r}. Use a number, tfNNN, teNNN, or all."
                    )
                number = int(match[2])
                if match[1] == "te":
                    error = self.errors.get(number)
                    if error is None:
                        raise ValueError(f"Unknown error te{number:03d}. {self.available()}")
                    numbers.update(error.fixes)
                elif number not in self.fixes:
                    raise ValueError(f"Unknown fix tf{number:03d}. {self.available()}")
                else:
                    numbers.add(number)
        if all_requested:
            numbers.update(self.fixes)
        return tuple(self.fixes[n] for n in sorted(numbers))

    def available(self) -> str:
        return (
            "Registered fixes: " + ", ".join(self.fixes[n].code for n in sorted(self.fixes)) + "."
        )


REGISTRY = RepairRegistry()
REGISTRY.register(
    FixRule(
        1,
        "Give each image a unique filename stem.",
        "image_dataset_train.collision_fix:detect_collisions",
        "image_dataset_train.collision_fix:repair_collisions",
        "image_dataset_train.collision_fix:pending_repairs",
    ),
    ErrorRule(
        1, "Same-stem image or caption collision.", (1,), ("same-stem", "ambiguous", "collision")
    ),
)


def normalize_selector(value) -> str:
    """Validate once and retain all as a request for automatic dispatch."""
    selected = REGISTRY.select(value)
    values = value if isinstance(value, (tuple, list)) else [value]
    if value is True or any(
        token.strip() == "all" for v in values for token in str(v).lower().split(",")
    ):
        return "all"
    return ",".join(rule.code for rule in selected)


def selector_argument(value: str) -> str:
    import argparse

    try:
        return normalize_selector(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def fix_arguments(value) -> str:
    selected = normalize_selector(value)
    return "" if not selected else " --fix" if selected == "all" else " --fix " + selected


def normalize_fix_argv(arguments: list[str]) -> list[str]:
    # Optional values must not swallow a following subcommand or directory path.
    output = []
    for index, token in enumerate(arguments):
        if token == "--":
            output.extend(arguments[index:])
            break
        if token == "--fix":
            following = arguments[index + 1] if index + 1 < len(arguments) else ""
            selector = re.fullmatch(
                r"(?i)\s*(?:all|(?:te|tf)?[+-]?[0-9]+)"
                r"(?:\s*,\s*(?:all|(?:te|tf)?[+-]?[0-9]+))*\s*",
                following,
            )
            if not selector:
                output.append("--fix=all")
                continue
        output.append(token)
    return output
