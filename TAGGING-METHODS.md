# IMAGE DATASET TRAINER

> Image Dataset Training Pipeline (v0.0.1)
>
> Original rough notes, preserved for reference. The reviewed design and work order
> are now in [PLAN.md](PLAN.md), unfinished work is in [TODO.md](TODO.md),
> completed work is in [docs/COMPLETED.md](docs/COMPLETED.md), and runnable commands
> are in [README.md](README.md). Code blocks below are
> historical proposals, not the current implementation.

## WD14

WD14 writes a `.txt` next to every file. You only fix the rules and the tags.

- comma-separated Danbooru tags plus a confidence score.
- keep tags above a threshold and drop the scores.

### Solo, threshold 0.35

```text
1girl, nude, completely nude, nipples, pussy, full body, standing, looking at viewer, simple background, clean lineart, flat color, solo
```

Yuri:

```text
2girls, yuri, nude, completely nude, nipples, pussy, french kiss, full body, looking at another, clean lineart, flat color
```

Hetero:

```text
1girl, 1boy, hetero, nude, completely nude, nipples, pussy, penis, sex, vaginal, standing sex, full body, clean lineart
```

> Use the WD14 ONNX tagger, not a GUI where you click one image at a time.

1. Install once:

```bash
pip install onnxruntime pillow huggingface_hub
```

1. Model people actually use: `SmilingWolf/wd-swinv2-tagger-v3` or `SmilingWolf/wd-vit-tagger-v3` from Hugging Face. SwinV2 is the usual quality pick. The older `wd-v1-4-moat-tagger-v2` still works and is what a lot of “Waifu Tagger” forks wrap.

2. Run a folder walk. This is the whole integration. It reads every image, writes `same_name.txt`, and never asks you to type.

```python
import csv
from pathlib import Path
from PIL import Image
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download

REPO = "SmilingWolf/wd-swinv2-tagger-v3"
MODEL = hf_hub_download(REPO, "model.onnx")
TAGS = hf_hub_download(REPO, "selected_tags.csv")

names, ratings = [], []
with open(TAGS, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        (ratings if row["category"] == "9" else names).append(row["name"])

sess = ort.InferenceSession(MODEL, providers=["CUDAExecutionProvider", "CPUExecutionProvider"])
inp = sess.get_inputs()[0]
size = inp.shape[1]


ROOT = Path("dataset/raw")


def prep(path):
    im = Image.open(path).convert("RGB")
    im = im.resize((size, size), Image.BICUBIC)
    arr = np.asarray(im, dtype=np.float32)[:, :, ::-1]  # RGB -> BGR
    return np.expand_dims(arr, 0)


for img in ROOT.rglob("*"):
    if img.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        continue
    probs = sess.run(None, {inp.name: prep(img)})[0][0]
    tag_probs = probs[len(ratings) :]
    kept = [
        names[i].replace("_", " ")
        for i, p in enumerate(tag_probs)
        if p >= THRESHOLD and names[i] not in DROP
    ]
    img.with_suffix(".txt").write_text(", ".join(kept), encoding="utf-8")
    print(img.name, len(kept))
```

That is the pipeline. Point `ROOT` at the folder. Come back when the printout finishes. One `.txt` per image, same stem, which is what Kohya, OneTrainer, and Comfy training loaders read.

### ComfyUI

Install **ComfyUI-WD14-Tagger** (or the node pack that includes `WD14Tagger`). Graph:

`Load Image Batch` → `WD14Tagger` (model `wd-swinv2-tagger-v3`, threshold `0.35`, character threshold `0.85`) → `Save Text` / `Text to File` with the image filename as the stem.

Set the batch node to the whole directory. Queue once. Do not use a single Load Image node. Character threshold higher than general threshold stops it from pasting random character names onto every file.

ComfyUI is slower to babysit at a few thousand images than the script above. Use Comfy if the rest of your prep is already a graph. Use the script if you just need captions.

> **Cleanup without opening the folder**

WD14 will not sort solo / yuri / hetero for you. Do that from the tags it just wrote:

- `1girl` and not `1boy` and not `2girls` → `solo/`
- `2girls` or `yuri` → `yuri/`
- `1girl` and `1boy` → `hetero/`

A 15-line move script does that. Add tags the tagger missed and you always want, in the same pass:

```python
FORCE = ["clean lineart", "flat color"]
text = img.with_suffix(".txt").read_text(encoding="utf-8")
tags = [t.strip() for t in text.split(",") if t.strip()]
for t in FORCE:
    if t not in tags:
        tags.append(t)
img.with_suffix(".txt").write_text(", ".join(tags), encoding="utf-8")
```

> **User Verification**

Open 30 random `.txt` files next to the image after the run. If hair and body count are mostly right, the set is usable. If everything is tagged `solo`, your threshold is too high or the model file did not load. Fix the script, rerun, overwrite the txt files. Do not hand-edit the folder.

JoyCaption or another vision model is still optional. For NoobAI / Illustrious, these tag files are the caption. A vision model does not replace this step, and it is the wrong tool to run first on thousands of images.

---
---

A vision model is optional. For NoobAI and Illustrious, the required artifact is a folder of images with a matching `.txt` of Danbooru-style tags. WD14 produces that. Everything else in this spec exists so those files are trainable instead of just tagged.

Treat the Python project in VS Code as the source of truth. ComfyUI is only a viewer and a spot-check, not the batch engine. Do not caption thousands of files by hand, and do not upload the folder to a caption API.

## What “done” means

Each kept image has:

- a sidecar `image.png` / `image.txt` with the same stem
- short side at least 768, preferably 1024
- no near-duplicate
- tags for count, nudity, and act (`1girl`, `2girls`, `1boy`, `nude`, `yuri`, `hetero`, …)

## Repo layout

```text
dataset-pipeline/
  pyproject.toml
  README.md
  config.yaml
  src/pipeline/
    ingest.py
    validate.py
    dedupe.py
    safety.py
    tag_wd14.py
    normalize.py
    split.py
    report.py
    cli.py
  comfy/
    review_batch.json
  data/                  # gitignored
    00_inbox/
    01_rejected/
      bad_file/
      too_small/
      duplicate/
    02_tagged/
    03_ready/
      solo/
      yuri/
      hetero/
      other/
    reports/
      manifest.jsonl
      qa_sample/
```

One image, one decision. Never edit files in `00_inbox`. Each stage writes the next folder so you can rerun a step without destroying the source.

## Config

```yaml
src_dir: data/00_inbox
min_short_side: 768
max_pixels: 4096
dedupe_threshold: 0.08          # imagededup CNN, lower = stricter
wd14_repo: SmilingWolf/wd-swinv2-tagger-v3
general_threshold: 0.35
character_threshold: 0.85
keep_character_tags: false      # true only if you are training those characters
force_tags: [clean lineart, flat color]
splits: {train: 0.95, val: 0.05}
seed: 20261011
```

## Stages, in order

**1. Ingest**  
Walk `00_inbox`. Accept png, jpg, jpeg, webp. Convert everything you keep to RGB PNG so Kohya does not care about the source format. Reject zero-byte files, unreadable images, and animated formats. Write a row to `manifest.jsonl` for every file: path, width, height, sha256, decision, reason.

**2. Validate**  
Reject if the short side is under `min_short_side`, the image is mostly one flat color, or either side exceeds `max_pixels` (resize a copy later; do not train a 100-megapixel scan). Also reject heavy letterboxing: if more than about 15% of the border is a solid bar, the tagger will miss the body and the LoRA will learn the bar.

**3. Dedupe**  
Use perceptual hashes, not filenames. `imagededup` CNN or a pHash pass. Keep the largest file in each cluster. Move the rest to `01_rejected/duplicate/` and record the keeper hash. Exact SHA256 duplicates are a separate, cheaper pass first.

**5. WD14**  
`SmilingWolf/wd-swinv2-tagger-v3` via ONNX Runtime. GPU if you have one, CPU if you do not. Resize to the model input (usually 448). Tags come back with scores. Keep general tags at or above `0.35`. Keep character tags only if `keep_character_tags` is true, and only at or above `0.85`. Replace underscores with spaces. Write `02_tagged/<stem>.txt`.

**6. Normalize**  
One script, no UI.

- If both `1girl` and `2girls` survived, keep the higher score and delete the other. Same for `solo` versus any count above 1.
- Map folders from tags, not filenames:
  - `1girl` and not `1boy` and not `2girls` → `solo`
  - `2girls` or `yuri`, and not `1boy` → `yuri`
  - `1girl` and `1boy` → `hetero`
  - anything else → `other` (multi-boy, unclear count, group). Do not silently dump `other` into the three LoRAs.
- Append `force_tags` if missing.
- If the image is in solo, yuri, or hetero and `nude` is missing, do not invent it. Leave it and flag `missing_nude` in the manifest. A batch that forces `nude` onto clothed images teaches the wrong thing.
- Sort tags in a stable order: count, nudity, act, pose, framing, style. Training does not need that order. Review does.

Example of a finished solo file:

```text
1girl, solo, nude, completely nude, nipples, pussy, full body, standing, looking at viewer, simple background, clean lineart, flat color
```

Yuri and hetero use the same format. The act tags (`french kiss`, `vaginal`, `penis`) have to be in the file. The folder name is not a caption.

**7. Buckets and repeats**  
Do not resize everything to square. Kohya and OneTrainer bucket by aspect. Record width and height in the manifest so you can see if one bucket (for example 2:3 full body) is 90% of the set. If solo is 4,000 images and hetero is 80, train three LoRAs or the small set will vanish. Aim for a few hundred distinct images per concept if anatomy is the point. Repeats of one pose teach that pose.

**8. Split**  
5% val, stratified by folder (`solo`, `yuri`, `hetero`), fixed seed. Val images get captions too. Do not put a near-duplicate of a train image in val; dedupe before the split.

**9. Report**  
`report.py` writes:

- counts per decision and per folder
- tag frequency top 100
- images missing `nude`, missing a count tag, or sitting in `other`
- a random 50-image contact sheet plus the txt, for QA

You review that sample. If body count is right on most of the 50, rerun is optional. If not, change the threshold and rerun stages 5–8. Do not hand-fix thousands of lines.

## VS Code project

Python 3.11. Packages: `onnxruntime-gpu` or `onnxruntime`, `pillow`, `huggingface_hub`, `imagededup`, `pyyaml`, `tqdm`. A `cli.py` with one subcommand per stage, plus `run-all`, is enough. Each stage must be idempotent: same input, same output, rejected files left where they were moved.

Log every decision in `manifest.jsonl`. That file is how you explain a bad LoRA later. Fields: `id`, `sha256`, `src`, `width`, `height`, `stage`, `decision`, `reason`, `tags`, `folder`.

## ComfyUI Stage

Use it after `03_ready` exists, not to build it.

Graph: Load Image Batch on `qa_sample` → WD14Tagger (same model, same thresholds) → display text beside the image. This checks that the node and the script agree. If they disagree, trust the script and fix the node, not the dataset.

Do not put Save Image in that graph. Review must not write a second copy of the training set.

Training itself is Kohya `ss-scripts` or OneTrainer, pointed at `03_ready/solo` (or yuri, or hetero) with `caption_extension: .txt`. Comfy’s training nodes are optional and worse to debug at this size.

## What you still add by hand

Only rules, not captions.

- Characters you refuse to train, as a blocklist of filenames or hashes.
- A short style prefix if every image shares one look and WD14 will not say it. That is the `force_tags` list, not a vision model.
- A trigger word (`mylineart`) prepended to every kept caption if this is a style LoRA. One token, same spelling, every file.

A vision model (JoyCaption or similar, local only) is a later pass on `other` and on the QA failures. It is not stage 1, and it does not replace WD14 for these checkpoints.

## Order of work

1. Scaffold the repo and `config.yaml`.
2. Ingest and validate on a 50-image copy.
3. Dedupe and the safety gate.
4. WD14 and normalize until the 50-image QA sheet matches the pictures.
5. Point the same commands at the full inbox.
6. Read the report. Train only `03_ready`, one folder at a time, on images you have the rights to use.

If you want this as files next, say your OS and whether the inbox is local paths only. The first code to write is `cli.py` plus `tag_wd14.py` and `safety.py`, not a Comfy graph.

---
---

Windows, local dataset paths only. The tagger weights still download once from Hugging Face into a local cache. Your images never leave the machine.

Put these under `dataset-pipeline/src/pipeline/`. Run from `dataset-pipeline` so `data/` resolves.

`src/pipeline/tag_wd14.py`

```python
"""Local WD14 / Waifu tagger. Writes a .txt next to each image. Never uploads the dataset."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
from PIL import Image

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
REPO = "SmilingWolf/wd-swinv2-tagger-v3"


class WD14:
    def __init__(self, repo: str = REPO, cache_dir: Path | None = None):
        from huggingface_hub import hf_hub_download
        import onnxruntime as ort

        cache = str(cache_dir) if cache_dir else None
        model = hf_hub_download(repo, "model.onnx", cache_dir=cache)
        tags_csv = hf_hub_download(repo, "selected_tags.csv", cache_dir=cache)

        self.names: list[str] = []
        self.rating_count = 0
        with open(tags_csv, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        # category 9 is the rating head (general/sensitive/questionable/explicit)
        rating = [r["name"] for r in rows if r.get("category") == "9"]
        general = [r["name"] for r in rows if r.get("category") != "9"]
        self.rating_count = len(rating)
        self.names = rating + general

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.sess = ort.InferenceSession(model, providers=providers)
        self.input_name = self.sess.get_inputs()[0].name
        shape = self.sess.get_inputs()[0].shape
        self.size = int(shape[1]) if isinstance(shape[1], int) else 448

    def score(self, path: Path) -> dict[str, float]:
        im = Image.open(path).convert("RGB")
        im = im.resize((self.size, self.size), Image.Resampling.BICUBIC)
        # model expects BGR, 0-255, NHWC
        arr = np.asarray(im, dtype=np.float32)[:, :, ::-1]
        arr = np.expand_dims(arr, 0)
        probs = self.sess.run(None, {self.input_name: arr})[0][0]
        return {self.names[i]: float(probs[i]) for i in range(min(len(self.names), len(probs)))}

    def caption(
        self,
        scores: dict[str, float],
        general_threshold: float = 0.35,
        character_threshold: float = 0.85,
        keep_character_tags: bool = False,
    ) -> list[str]:
        # selected_tags.csv marks characters as category 4. We did not store category
        # on the score dict, so character filtering is name-based: WD character tags
        # contain no spaces after we replace underscores only at write time.
        # Practical rule used by the WD forks: tags with a parenthesis are characters.
        kept = []
        for name, p in scores.items():
            if name in {"general", "sensitive", "questionable", "explicit"}:
                continue
            is_character = "(" in name and ")" in name
            cutoff = character_threshold if is_character else general_threshold
            if is_character and not keep_character_tags:
                continue
            if p >= cutoff:
                kept.append(name.replace("_", " "))
        return kept


def iter_images(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            yield path


def write_caption(image: Path, tags: list[str]) -> Path:
    dest = image.with_suffix(".txt")
    dest.write_text(", ".join(tags), encoding="utf-8")
    return dest
```

`src/pipeline/cli.py`

```python
"""Local dataset prep. Images stay on disk. No remote caption API.

Usage (from dataset-pipeline, Windows):

  py -3.11 -m pip install onnxruntime pillow huggingface_hub pyyaml tqdm numpy
  py -3.11 -m src.pipeline.cli safety-names --inbox data\\00_inbox --blocklist blocklist.txt
  py -3.11 -m src.pipeline.cli tag --inbox data\\00_inbox
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.pipeline.safety import (
    reject_scored,
    scan_inbox_names,
)
from src.pipeline.tag_wd14 import WD14, iter_images, write_caption

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
INBOX = DATA / "00_inbox"
REJECTED = DATA / "01_rejected"
MANIFEST = DATA / "reports" / "manifest.jsonl"
CACHE = DATA / "models" / "wd14"


def _inbox(value: str | None) -> Path:
    return Path(value) if value else INBOX


def cmd_safety_names(args: argparse.Namespace) -> int:
    inbox = _inbox(args.inbox)
    if not inbox.exists():
        print(f"missing inbox: {inbox}", file=sys.stderr)
        return 2
    names: set[str] = set()
    if args.blocklist:
        text = Path(args.blocklist).read_text(encoding="utf-8")
        names = {
            line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")
        }
    n = scan_inbox_names(inbox, REJECTED, MANIFEST, names)
    print(f"quarantined {n} by filename -> {REJECTED / 'safety'}")
    return 0


def cmd_tag(args: argparse.Namespace) -> int:
    inbox = _inbox(args.inbox)
    if not inbox.exists():
        print(f"missing inbox: {inbox}", file=sys.stderr)
        return 2
    images = list(iter_images(inbox))
    if not images:
        print(f"no images in {inbox}")
        return 0

    tagger = WD14(repo=args.repo, cache_dir=CACHE)
    kept = 0
    rejected = 0
    for i, image in enumerate(images, 1):
        scores = tagger.score(image)
        hits = reject_scored(
            image,
            scores,
            REJECTED,
            MANIFEST,
        )
        if hits:
            rejected += 1
            print(f"[{i}/{len(images)}] REJECT {image.name} {hits}")
            continue
        tags = tagger.caption(
            scores,
            general_threshold=args.threshold,
            character_threshold=args.character_threshold,
            keep_character_tags=args.keep_characters,
        )
        write_caption(image, tags)
        kept += 1
        print(f"[{i}/{len(images)}] {image.name} -> {len(tags)} tags")
    print(f"kept {kept}, quarantined {rejected}")
    print("txt files sit next to the images. rejected files are not in the inbox anymore.")
    return 0


def build() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("safety-names", help="move blocklisted filenames out of the inbox")
    s.add_argument("--inbox", default=None)
    s.add_argument("--blocklist", required=True, help="text file, one filename or stem per line")
    s.set_defaults(func=cmd_safety_names)

    t = sub.add_parser("tag", help="WD14 captions")
    t.add_argument("--inbox", default=None)
    t.add_argument("--repo", default="SmilingWolf/wd-swinv2-tagger-v3")
    t.add_argument("--threshold", type=float, default=0.35)
    t.add_argument("--character-threshold", type=float, default=0.85)
    t.add_argument("--keep-characters", action="store_true")
    t.set_defaults(func=cmd_tag)
    return p


def main() -> int:
    # so `py -3.11 -m src.pipeline.cli` works when cwd is dataset-pipeline
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    parser = build()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

Also add an empty `src/pipeline/__init__.py` and `src/__init__.py`, or the `-m` import fails.

Run it like this from `dataset-pipeline`:

```bat
py -3.11 -m pip install onnxruntime pillow huggingface_hub numpy
mkdir data\00_inbox data\01_rejected data\reports data\models\wd14
py -3.11 -m src.pipeline.cli safety-names --inbox data\00_inbox --blocklist blocklist.txt
py -3.11 -m src.pipeline.cli tag --inbox data\00_inbox
```

`blocklist.txt` is one filename or stem per line for characters you already know must not be trained. Lines starting with `#` are ignored. If you have nothing to block, still pass a file with only a comment or the command will refuse to run.

What this does and does not do:

- Reads only local image paths. Writes `.txt` beside each kept file.
- GPU is used if `onnxruntime-gpu` is installed and CUDA is visible. Otherwise it falls back to CPU and a few thousand images will take a while. That is expected.
- This does not yet dedupe, bucket, or split into `solo` / `yuri` / `hetero`. Those are the next two modules after you confirm a 50-image run writes sane txt files.

First check: run `tag` on a copy of 50 images, open ten of the txt files next to the pictures, and confirm body count and nudity tags match. If CUDA fails at import, install `onnxruntime` instead of `onnxruntime-gpu` and rerun. The caption text will be the same.

Windows, local paths only. These two stages run after `tag`. They do not upload images.

`src/pipeline/dedupe.py`

```python
"""Exact hash plus optional perceptual hash. First file wins. Copies go to rejected/duplicate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from src.pipeline.safety import IMAGE_EXTS, quarantine

try:
    import imagehash
except ImportError:  # exact hash still runs
    imagehash = None


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def phash(path: Path) -> str | None:
    if imagehash is None:
        return None
    with Image.open(path) as im:
        return str(imagehash.phash(im.convert("RGB")))


def dedupe_inbox(
    inbox: Path,
    rejected_root: Path,
    manifest: Path,
    use_phash: bool = True,
    hamming: int = 4,
) -> dict[str, int]:
    """Keep the first image for each exact hash and each near phash. Move the rest."""
    seen_exact: dict[str, Path] = {}
    seen_phash: list[tuple[str, Path]] = []
    stats = {
        "seen": 0,
        "exact": 0,
        "near": 0,
        "kept": 0,
        "phash": int(imagehash is not None and use_phash),
    }

    images = [p for p in sorted(inbox.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    for path in images:
        stats["seen"] += 1
        digest = file_sha256(path)
        if digest in seen_exact:
            quarantine(
                path,
                rejected_root,
                "duplicate",
                f"exact:{digest} kept={seen_exact[digest]}",
                manifest,
            )
            stats["exact"] += 1
            continue

        if use_phash and imagehash is not None:
            try:
                current = phash(path)
            except Exception as exc:
                current = None
                _log_skip(manifest, path, f"phash_fail:{exc}")
            if current:
                hit = _near(current, seen_phash, hamming)
                if hit is not None:
                    quarantine(
                        path,
                        rejected_root,
                        "duplicate",
                        f"phash:{current} dist<={hamming} kept={hit}",
                        manifest,
                    )
                    stats["near"] += 1
                    continue
                seen_phash.append((current, path))

        seen_exact[digest] = path
        stats["kept"] += 1
    return stats


def _near(current: str, seen: list[tuple[str, Path]], hamming: int) -> Path | None:
    cur = int(current, 16)
    for other, path in seen:
        if (cur ^ int(other, 16)).bit_count() <= hamming:
            return path
    return None


def _log_skip(manifest: Path, path: Path, detail: str) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    row = {"src": str(path), "decision": "keep", "reason": "dedupe_warn", "detail": detail}
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

`src/pipeline/normalize.py`

```python
"""Rewrite WD14 sidecars into a stable tag string."""

from __future__ import annotations

from pathlib import Path

from src.pipeline.safety import IMAGE_EXTS, quarantine

DROP = {
    "general",
    "lowres",
    "bad anatomy",
    "bad hands",
    "jpeg artifacts",
    "signature",
    "watermark",
    "artist name",
}

# tagger alias -> training tag. Keys and values are space-separated, lower case.
ALIAS = {
    "nude": "nude",
    "completely nude": "completely nude",
    "nsfw": "nsfw",
    "uncensored": "uncensored",
    "censored": "censored",
    "mosaic censoring": "censored",
    "bar censor": "censored",
    "convenient censoring": "censored",
    "1girl": "1girl",
    "2girls": "2girls",
    "3girls": "3girls",
    "1boy": "1boy",
    "2boys": "2boys",
    "1boy 1girl": "hetero",
    "yuri": "yuri",
    "hetero": "hetero",
    "solo": "solo",
}


def _norm(tag: str) -> str:
    return " ".join(tag.replace("_", " ").replace(",", " ").split()).lower()


def parse_tags(text: str) -> list[str]:
    out = []
    seen = set()
    for raw in text.split(","):
        tag = _norm(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        out.append(tag)
    return out


def rewrite(
    tags: list[str], trigger: str | None, drop_characters: bool
) -> tuple[list[str], list[str]]:
    """Returns (kept)"""
    hits = [t for t in tags]
    if hits:
        return []

    kept: list[str] = []
    seen = set()
    if trigger:
        trig = _norm(trigger)
        if trig:
            kept.append(trig)
            seen.add(trig)

    for tag in tags:
        if tag in DROP:
            continue
        if drop_characters and "(" in tag and ")" in tag:
            continue
        seen.add(tag)
        kept.append(tag)
    return kept


def normalize_inbox(
    inbox: Path,
    rejected_root: Path,
    manifest: Path,
    trigger: str | None = None,
    drop_characters: bool = True,
) -> dict[str, int]:
    stats = {"seen": 0, "written": 0, "rejected": 0, "missing_txt": 0}
    images = [p for p in sorted(inbox.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    for image in images:
        stats["seen"] += 1
        sidecar = image.with_suffix(".txt")
        if not sidecar.exists():
            stats["missing_txt"] += 1
            continue
        tags = parse_tags(sidecar.read_text(encoding="utf-8"))
        kept, hits = rewrite(tags, trigger, drop_characters)
        if hits:
            quarantine(
                image,
                rejected_root,
                "normalize:" + ",".join(hits),
                manifest,
            )
            stats["rejected"] += 1
            continue
        sidecar.write_text(", ".join(kept), encoding="utf-8")
        stats["written"] += 1
    return stats
```

Add these handlers to `cli.py` and register them in `build()`.

```python
from src.pipeline.dedupe import dedupe_inbox
from src.pipeline.normalize import normalize_inbox


def cmd_dedupe(args: argparse.Namespace) -> int:
    inbox = _inbox(args.inbox)
    if not inbox.exists():
        print(f"missing inbox: {inbox}", file=sys.stderr)
        return 2
    stats = dedupe_inbox(
        inbox, REJECTED, MANIFEST, use_phash=not args.exact_only, hamming=args.hamming
    )
    print(
        f"seen {stats['seen']} kept {stats['kept']} "
        f"exact {stats['exact']} near {stats['near']} phash_on {stats['phash']}"
    )
    print(f"duplicates -> {REJECTED / 'duplicate'}")
    return 0


def cmd_normalize(args: argparse.Namespace) -> int:
    inbox = _inbox(args.inbox)
    if not inbox.exists():
        print(f"missing inbox: {inbox}", file=sys.stderr)
        return 2
    stats = normalize_inbox(
        inbox,
        REJECTED,
        MANIFEST,
        trigger=args.trigger,
        drop_characters=not args.keep_characters,
    )
    print(
        f"seen {stats['seen']} written {stats['written']} "
        f"rejected {stats['rejected']} missing_txt {stats['missing_txt']}"
    )
    return 0
```

```python
    d = sub.add_parser("dedupe", help="drop exact and near-duplicate images")
    d.add_argument("--inbox", default=None)
    d.add_argument("--exact-only", action="store_true")
    d.add_argument("--hamming", type=int, default=4)
    d.set_defaults(func=cmd_dedupe)
    n.add_argument("--inbox", default=None)
    n.add_argument("--trigger", default=None, help="optional token prepended to every caption")
    n.add_argument("--keep-characters", action="store_true")
    n.set_defaults(func=cmd_normalize)
```

From `dataset-pipeline`:

```bat
py -3.11 -m pip install pillow imagehash
py -3.11 -m src.pipeline.cli dedupe --inbox data\00_inbox
py -3.11 -m src.pipeline.cli normalize --inbox data\00_inbox --trigger yourstyle
```

`imagehash` is only for near-duplicates (recompress, resize, resave). If the install fails, `--exact-only` still removes byte-identical files. Hamming 4 is tight. If a 50-image spot check shows distinct poses getting paired, raise it only after you look at the pairs in `data\01_rejected\duplicate`. Do not lower it to chase a bigger set.

Order stays `safety-names`, then `tag`, then `dedupe`, then `normalize`. Normalize reads the `.txt` that `tag` wrote, so running it before `tag` only increments `missing_txt`

These four files sit next to the stages you already have.

`config.yaml`

```yaml
paths:
  root: data
  inbox: data/00_inbox
  rejected: data/01_rejected
  train: data/02_train
  val: data/03_val
  manifest: data/manifest.jsonl
  report: data/report

ingest:
  # copy keeps the source. move is only for a folder you already own.
  mode: copy
  flatten: true
  skip_hidden: true

validate:
  min_side: 512
  max_side: 4096
  min_bytes: 8000
  max_bytes: 40000000
  allowed_modes: [RGB, RGBA, L]
  require_sidecar: false

dedupe:
  use_phash: true
  hamming: 4

tag:
  model: SmilingWolf/wd-swinv2-tagger-v3
  threshold: 0.35
  character_threshold: 0.85

normalize:
  trigger: null
  drop_characters: true

split:
  val_ratio: 0.05
  seed: 20261011
  # hash of file bytes, so a re-run with the same seed stays stable
  by: sha256

buckets:
  # repeats are a caption prefix count, not file copies
  solo: { match: ["1girl", "solo"], repeats: 1 }
  yuri: { match: ["2girls", "yuri"], repeats: 2 }
  hetero: { match: ["1boy", "hetero"], repeats: 2 }
  other: { match: [], repeats: 1 }

report:
  top_tags: 40
```

`src/pipeline/ingest.py`

```python
"""Copy or move images from a source tree into the inbox. Non-images are skipped, not deleted."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.pipeline.safety import IMAGE_EXTS


def _safe_name(src: Path, digest8: str) -> str:
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in src.stem)[:60]
    return f"{digest8}_{stem}{src.suffix.lower()}"


def ingest(
    source: Path,
    inbox: Path,
    manifest: Path,
    mode: str = "copy",
    flatten: bool = True,
    skip_hidden: bool = True,
) -> dict[str, int]:
    if mode not in {"copy", "move"}:
        raise ValueError("mode must be copy or move")
    if not source.exists():
        raise FileNotFoundError(source)
    inbox.mkdir(parents=True, exist_ok=True)
    stats = {"seen": 0, "ingested": 0, "skipped": 0, "exists": 0}
    op = shutil.copy2 if mode == "copy" else shutil.move

    for path in sorted(source.rglob("*")):
        if not path.is_file():
            continue
        if skip_hidden and any(part.startswith(".") for part in path.parts):
            continue
        stats["seen"] += 1
        if path.suffix.lower() not in IMAGE_EXTS:
            stats["skipped"] += 1
            _row(manifest, path, "skip", "not_image", "")
            continue
        digest8 = _short_hash(path)
        if flatten:
            dest = inbox / _safe_name(path, digest8)
        else:
            rel = path.relative_to(source)
            dest = inbox / rel.parent / _safe_name(path, digest8)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            stats["exists"] += 1
            _row(manifest, path, "skip", "dest_exists", str(dest))
            continue
        op(str(path), str(dest))
        stats["ingested"] += 1
        _row(manifest, path, "ingest", mode, str(dest))
    return stats


def _short_hash(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        h.update(f.read(1 << 20))
    return h.hexdigest()[:8]


def _row(manifest: Path, src: Path, decision: str, reason: str, detail: str) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    row = {"src": str(src), "decision": decision, "reason": reason, "detail": detail}
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

`src/pipeline/validate.py`

```python
"""Open every image. Corrupt, tiny, huge, or unreadable files go to rejected/invalid.

Does not crop, inpaint, or rewrite pixels. Sidecar text is not a substitute for the safety gate.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from src.pipeline.safety import IMAGE_EXTS, quarantine


def validate_inbox(
    inbox: Path,
    rejected_root: Path,
    manifest: Path,
    min_side: int = 512,
    max_side: int = 4096,
    min_bytes: int = 8000,
    max_bytes: int = 40_000_000,
    allowed_modes: set[str] | None = None,
    require_sidecar: bool = False,
) -> dict[str, int]:
    modes = allowed_modes or {"RGB", "RGBA", "L"}
    stats = {"seen": 0, "ok": 0, "invalid": 0, "missing_txt": 0}
    images = [p for p in sorted(inbox.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    for path in images:
        stats["seen"] += 1
        reason = _check(path, min_side, max_side, min_bytes, max_bytes, modes)
        if reason:
            quarantine(path, rejected_root, "invalid", reason, manifest)
            stats["invalid"] += 1
            continue
        if require_sidecar and not path.with_suffix(".txt").exists():
            stats["missing_txt"] += 1
        stats["ok"] += 1
    return stats


def _check(
    path: Path,
    min_side: int,
    max_side: int,
    min_bytes: int,
    max_bytes: int,
    modes: set[str],
) -> str | None:
    size = path.stat().st_size
    if size < min_bytes:
        return f"too_small_bytes:{size}"
    if size > max_bytes:
        return f"too_large_bytes:{size}"
    try:
        with Image.open(path) as im:
            im.verify()
        with Image.open(path) as im:
            im.load()
            w, h = im.size
            if im.mode not in modes:
                return f"mode:{im.mode}"
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        return f"unreadable:{type(exc).__name__}"
    short, long = min(w, h), max(w, h)
    if short < min_side:
        return f"short_side:{short}"
    if long > max_side:
        return f"long_side:{long}"
    return None
```

`src/pipeline/split.py`

```python
"""Stable train/val split by file hash. Copies images and their .txt. Does not delete the inbox."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from src.pipeline.safety import IMAGE_EXTS


def split_inbox(
    inbox: Path,
    train: Path,
    val: Path,
    manifest: Path,
    val_ratio: float = 0.05,
    seed: int = 20261011,
) -> dict[str, int]:
    if not 0.0 < val_ratio < 0.5:
        raise ValueError("val_ratio must be between 0 and 0.5")
    train.mkdir(parents=True, exist_ok=True)
    val.mkdir(parents=True, exist_ok=True)
    stats = {"seen": 0, "train": 0, "val": 0, "missing_txt": 0}
    images = [p for p in sorted(inbox.rglob("*")) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    for path in images:
        stats["seen"] += 1
        bucket = "val" if _in_val(path, val_ratio, seed) else "train"
        dest_root = val if bucket == "val" else train
        dest = dest_root / path.name
        if dest.exists():
            dest = dest_root / f"{_file_sha256(path)[:8]}_{path.name}"
        shutil.copy2(path, dest)
        sidecar = path.with_suffix(".txt")
        if sidecar.exists():
            shutil.copy2(sidecar, dest.with_suffix(".txt"))
        else:
            stats["missing_txt"] += 1
        stats[bucket] += 1
        _row(manifest, path, bucket, str(dest))
    return stats


def _in_val(path: Path, val_ratio: float, seed: int) -> bool:
    digest = _file_sha256(path)
    # first 8 hex chars, mixed with the seed, mapped onto 0..9999
    mixed = int(hashlib.sha256(f"{seed}:{digest}".encode()).hexdigest()[:8], 16)
    return (mixed % 10000) < int(val_ratio * 10000)


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(1 << 20)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _row(manifest: Path, src: Path, bucket: str, dest: str) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    row = {"src": str(src), "decision": "split", "reason": bucket, "detail": dest}
    with manifest.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
```

`src/pipeline/report.py`

```python
"""Read the manifest and the train sidecars. Writes a text summary. Does not move files."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from src.pipeline.safety import IMAGE_EXTS


def write_report(
    manifest: Path,
    train: Path,
    out_dir: Path,
    top_tags: int = 40,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    reasons: Counter[str] = Counter()
    decisions: Counter[str] = Counter()
    if manifest.exists():
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            decisions[row.get("decision", "?")] += 1
            reasons[f"{row.get('decision', '?')}:{row.get('reason', '?')}"] += 1

    tags: Counter[str] = Counter()
    images = 0
    missing = 0
    if train.exists():
        for path in train.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
                images += 1
                sidecar = path.with_suffix(".txt")
                if not sidecar.exists():
                    missing += 1
                    continue
                for raw in sidecar.read_text(encoding="utf-8").split(","):
                    tag = " ".join(raw.split()).lower()
                    if tag:
                        tags[tag] += 1

    lines = [
        f"train_images {images}",
        f"train_missing_txt {missing}",
        "",
        "decisions",
    ]
    lines += [f"  {k} {v}" for k, v in decisions.most_common()]
    lines += ["", "reasons"]
    lines += [f"  {k} {v}" for k, v in reasons.most_common(80)]
    lines += ["", f"top_tags {top_tags}"]
    lines += [f"  {k} {v}" for k, v in tags.most_common(top_tags)]

    dest = out_dir / "summary.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest
```

CLI handlers to drop into `cli.py`:

```python
from src.pipeline.ingest import ingest
from src.pipeline.report import write_report
from src.pipeline.split import split_inbox
from src.pipeline.validate import validate_inbox


def cmd_ingest(args: argparse.Namespace) -> int:
    stats = ingest(
        Path(args.source),
        _inbox(args.inbox),
        MANIFEST,
        mode=args.mode,
        flatten=not args.keep_tree,
    )
    print(
        f"seen {stats['seen']} ingested {stats['ingested']} skipped {stats['skipped']} exists {stats['exists']}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    inbox = _inbox(args.inbox)
    stats = validate_inbox(
        inbox, REJECTED, MANIFEST, min_side=args.min_side, max_side=args.max_side
    )
    print(f"seen {stats['seen']} ok {stats['ok']} invalid {stats['invalid']}")
    return 0


def cmd_split(args: argparse.Namespace) -> int:
    stats = split_inbox(
        _inbox(args.inbox), TRAIN, VAL, MANIFEST, val_ratio=args.val_ratio, seed=args.seed
    )
    print(
        f"seen {stats['seen']} train {stats['train']} val {stats['val']} missing_txt {stats['missing_txt']}"
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    dest = write_report(MANIFEST, TRAIN, REPORT, top_tags=args.top)
    print(dest)
    text = dest.read_text(encoding="utf-8")
    return 0
```

```python
    i = sub.add_parser("ingest")
    i.add_argument("source")
    i.add_argument("--inbox", default=None)
    i.add_argument("--mode", choices=["copy", "move"], default="copy")
    i.add_argument("--keep-tree", action="store_true")
    i.set_defaults(func=cmd_ingest)

    v = sub.add_parser("validate")
    v.add_argument("--inbox", default=None)
    v.add_argument("--min-side", type=int, default=512)
    v.add_argument("--max-side", type=int, default=4096)
    v.set_defaults(func=cmd_validate)

    s = sub.add_parser("split")
    s.add_argument("--inbox", default=None)
    s.add_argument("--val-ratio", type=float, default=0.05)
    s.add_argument("--seed", type=int, default=20261011)
    s.set_defaults(func=cmd_split)

    r = sub.add_parser("report")
    r.add_argument("--top", type=int, default=40)
    r.set_defaults(func=cmd_report)
```

Add the path constants next to `REJECTED` and `MANIFEST`:

```python
TRAIN = ROOT / "data" / "02_train"
VAL = ROOT / "data" / "03_val"
REPORT = ROOT / "data" / "report"
```

Order:

```bat
py -3.11 -m src.pipeline.cli ingest D:\raw\anime --mode copy
py -3.11 -m src.pipeline.cli validate --inbox data\00_inbox
py -3.11 -m src.pipeline.cli safety-names --inbox data\00_inbox
py -3.11 -m src.pipeline.cli tag --inbox data\00_inbox
py -3.11 -m src.pipeline.cli dedupe --inbox data\00_inbox
py -3.11 -m src.pipeline.cli normalize --inbox data\00_inbox
py -3.11 -m src.pipeline.cli split --inbox data\00_inbox --val-ratio 0.05
py -3.11 -m src.pipeline.cli report
```
