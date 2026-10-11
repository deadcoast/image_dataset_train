"""Local WD ONNX inference with explicit input, output, and provider contracts."""

from __future__ import annotations

import platform

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps
from PIL import __version__ as pillow_version

from image_dataset_train.model_bundle import ModelBundle, fingerprint

PREPROCESS_VERSION = "wd-exif-white-square-bicubic-bgr-f32-v1"


def prepare_image(image: Image.Image, size: int) -> np.ndarray:
    """Publisher WD geometry/color processing, preceded by EXIF orientation correction."""
    oriented = ImageOps.exif_transpose(image)
    rgba = oriented.convert("RGBA")
    background = Image.new("RGBA", rgba.size, "white")
    background.alpha_composite(rgba)
    rgb = background.convert("RGB")
    side = max(rgb.size)
    square = Image.new("RGB", (side, side), "white")
    square.paste(rgb, ((side - rgb.width) // 2, (side - rgb.height) // 2))
    if side != size:
        square = square.resize((size, size), Image.Resampling.BICUBIC)
    return np.ascontiguousarray(np.asarray(square, dtype=np.float32)[..., ::-1])


def validate_scores(scores: np.ndarray, count: int, batch: int | None = None) -> None:
    expected = (count,) if batch is None else (batch, count)
    if scores.shape != expected:
        raise ValueError(f"WD output shape {scores.shape} does not match {expected}")
    if not np.issubdtype(scores.dtype, np.floating):
        raise ValueError("WD scores must be floating-point values")
    if not np.isfinite(scores).all() or np.any(scores < 0) or np.any(scores > 1):
        raise ValueError("WD scores must be finite and within [0, 1]; logits are not supported")


class WDTagger:
    def __init__(self, bundle: ModelBundle, device: str = "auto") -> None:
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("device must be auto, cpu, or cuda")
        available = ort.get_available_providers()
        cuda = "CUDAExecutionProvider"
        cpu = "CPUExecutionProvider"
        if device == "cuda" and cuda not in available:
            raise RuntimeError("CUDA was requested, but CUDAExecutionProvider is unavailable")
        requested = [cuda, cpu] if device != "cpu" and cuda in available else [cpu]
        self.fallback = None
        if device == "auto" and cuda not in available:
            self.fallback = "CUDA unavailable; using CPU"
        try:
            self.session = ort.InferenceSession(
                str(bundle.directory / "model.onnx"), providers=requested
            )
        except Exception as exc:
            if device != "auto" or cuda not in requested:
                raise RuntimeError(f"ONNX session initialization failed: {exc}") from exc
            self.fallback = f"CUDA initialization failed; using CPU: {exc}"
            self.session = ort.InferenceSession(
                str(bundle.directory / "model.onnx"), providers=[cpu]
            )
        active = self.session.get_providers()
        if device == "cuda" and cuda not in active:
            raise RuntimeError("CUDA initialization failed; refusing silent CPU fallback")
        if device == "auto" and cuda in requested and cuda not in active:
            self.fallback = "CUDA registration failed; using CPU"
        self.session.disable_fallback()
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError("WD requires exactly one input and one output tensor")
        inp, out = inputs[0], outputs[0]
        shape = inp.shape
        if (
            inp.type != "tensor(float)"
            or len(shape) != 4
            or shape[3] != 3
            or type(shape[1]) is not int
            or not 1 <= shape[1] <= 4096
            or shape[1] != shape[2]
        ):
            raise ValueError(f"expected fixed square float32 NHWC WD input, got {inp.type} {shape}")
        if type(shape[0]) is int and shape[0] != 1:
            raise ValueError("only dynamic batches or fixed batch=1 WD models are supported")
        if out.type != "tensor(float)" or len(out.shape) != 2 or out.shape[1] != len(bundle.labels):
            raise ValueError("ONNX output label count/type does not match the CSV")
        self.size, self.input_name, self.output_name = shape[1], inp.name, out.name
        self.fixed_batch = 1 if type(shape[0]) is int else None
        self.label_count = len(bundle.labels)
        self.runtime = {
            "onnxruntime": ort.__version__,
            "numpy": np.__version__,
            "pillow": pillow_version,
            "python": platform.python_version(),
            "machine": platform.machine(),
            "providers": active,
            "provider_options": self.session.get_provider_options(),
        }
        self.cache_identity = {
            "artifact_id": bundle.metadata["artifact_id"],
            "preprocessing": PREPROCESS_VERSION,
            "runtime": self.runtime,
        }
        self.cache_namespace = fingerprint(self.cache_identity)

    def predict(self, batch: np.ndarray) -> np.ndarray:
        if batch.dtype != np.float32 or batch.shape[1:] != (self.size, self.size, 3):
            raise ValueError("invalid preprocessed WD batch")
        if self.fixed_batch and len(batch) != self.fixed_batch:
            raise ValueError("model requires batch=1")
        try:
            result = self.session.run([self.output_name], {self.input_name: batch})[0]
        except Exception as exc:
            raise RuntimeError(f"ONNX inference failed: {exc}") from exc
        validate_scores(result, self.label_count, len(batch))
        return result
