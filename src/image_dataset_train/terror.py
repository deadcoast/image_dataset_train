"""Stable tagging error and executable repair definitions."""

TERROR = {"te001": "Same-stem image or caption collision."}
TERROR_FIX = {"tf001": "Give each image a unique filename stem."}
FIX_FOR_ERROR = {"te001": "tf001"}


def fix_code(value: str | bool) -> str | None:
    if not value:
        return None
    if value is True or value in {"te001", "tf001"}:
        return "tf001"
    raise ValueError(f"Unknown tagging fix: {value}. Available: tf001 (repairs te001).")
