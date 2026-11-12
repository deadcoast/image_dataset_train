"""Validate saved or inferred score arrays without loading an inference runtime."""

from __future__ import annotations

import numpy as np


def validate_scores(scores: np.ndarray, count: int, batch: int | None = None) -> None:
    expected = (count,) if batch is None else (batch, count)
    if scores.shape != expected:
        raise ValueError(f"WD output shape {scores.shape} does not match {expected}")
    if not np.issubdtype(scores.dtype, np.floating):
        raise ValueError("WD scores must be floating-point values")
    if not np.isfinite(scores).all() or np.any(scores < 0) or np.any(scores > 1):
        raise ValueError("WD scores must be finite and within [0, 1]; logits are not supported")
