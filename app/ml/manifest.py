"""Integrity / compatibility checks for the model folder exported from the notebook.

Folder layout (written by the export cell, published to Hugging Face):

    manifest.json   version, trained_through, library versions, sha256 of every file
    clf.txt reg.txt l2.txt      LightGBM text models (3-class, L1 partial-drop, L2 mean)
    text.joblib     {"vec": TfidfVectorizer, "text_models": {"low": ..., "nodrop": ...}}
    config.joblib   {"features", "cats", "gm", "cap"}
    store.parquet   history of finished purchases (organizer / type / product codes / protocol time / outcome)

Deliberately light (stdlib only) so scripts/download_model.py can import it without pandas/LightGBM.
"""

from __future__ import annotations

import hashlib
import json
from importlib import metadata
from pathlib import Path

REQUIRED_FILES = ("clf.txt", "reg.txt", "l2.txt", "text.joblib", "config.joblib", "store.parquet")
# manifest key -> distribution name
LIBRARIES = {"sklearn": "scikit-learn", "lightgbm": "lightgbm", "pandas": "pandas", "numpy": "numpy"}


class ModelFilesError(Exception):
    """The model folder is missing, incomplete or corrupted. The message is user-readable."""


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def read_manifest(folder: str | Path) -> dict:
    p = Path(folder) / "manifest.json"
    if not p.is_file():
        raise ModelFilesError(f"manifest.json not found in {folder}. Is this the folder downloaded from Hugging Face?")
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ModelFilesError(f"manifest.json is not valid JSON ({exc.msg}).") from exc
    if not isinstance(m.get("files"), dict):
        raise ModelFilesError("manifest.json has no 'files' section.")
    return m


def verify_files(folder: str | Path, manifest: dict) -> None:
    """Every required file must be listed in the manifest, exist, and match its sha256."""
    folder = Path(folder)
    problems = []
    for name in REQUIRED_FILES:
        expected = manifest["files"].get(name)
        path = folder / name
        if expected is None:
            problems.append(f"{name}: not listed in manifest.json")
        elif not path.is_file():
            problems.append(f"{name}: file is missing")
        elif sha256_file(path) != expected:
            problems.append(f"{name}: checksum mismatch (incomplete download or modified file)")
    if problems:
        raise ModelFilesError("Model files failed verification: " + "; ".join(problems))


def library_warnings(manifest: dict) -> list[str]:
    """Library versions used for training vs. installed (pickles in text.joblib / config.joblib depend on them)."""
    out = []
    for key, dist in LIBRARIES.items():
        trained = manifest.get(key)
        try:
            installed = metadata.version(dist)
        except metadata.PackageNotFoundError:
            installed = None
        if trained and installed and trained != installed:
            out.append(f"{dist}: model was trained with {trained}, installed {installed}")
    return out
