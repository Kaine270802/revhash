"""Dictionary builder for revhash — Optimization Builder (M3b).

Implements `docs/api.md §2.3` + `research.md §5.4 / §6.5 / B.1`:

- Offline training: collect 100-1000 samples (each 8-16 KB) from corpus,
  ``zstandard.train_dictionary(dict_size, samples)`` → embed dict into header.
- Benchmark shows dict 112 KB trained on 100×10 KB saves 80% on 10 KB,
  ~71% on 256 KB chunks.

API frozen:

    dict_data = dict_builder.train(samples, dict_size=112*1024)
    dict_data = dict_builder.train_from_files(paths, dict_size, sample_size)
    dict_builder.save(dict_data, "dicts/vi_text.dict")
    dict_data = dict_builder.load("dicts/vi_text.dict")
    samples   = dict_builder.get_samples_from_file(path, sample_size, max_samples)

Notes:
- ``zstandard>=0.20`` required; if missing or samples <10 → ValueError.
- Each sample should be 8-16 KB for optimal training (research B.1).
- Save/load are raw bytes (``dict_data.as_bytes()``).
"""

from __future__ import annotations

import pathlib
from typing import List

# ── constants ───────────────────────────────────────────────────────────────
DEFAULT_DICT_SIZE: int = 112 * 1024
DEFAULT_SAMPLE_SIZE: int = 16 * 1024
DEFAULT_MAX_SAMPLES: int = 100
MIN_SAMPLES: int = 10
MIN_SAMPLE_BYTES: int = 1024  # samples smaller than this are still usable but less effective

__all__ = ["train", "train_from_files", "save", "load", "get_samples_from_file"]


def _require_zstd():
    """Import zstandard or raise ValueError (frozen contract)."""
    try:
        import zstandard as zstd  # type: ignore

        return zstd
    except ImportError as exc:
        raise ValueError(
            "zstandard is required for dict training but not installed. Install with: pip install zstandard>=0.20.0"
        ) from exc


def _validate_samples(samples: List[bytes], dict_size: int) -> None:
    if not isinstance(samples, list):
        raise ValueError("samples must be list[bytes]")
    if len(samples) < MIN_SAMPLES:
        raise ValueError(
            f"need at least {MIN_SAMPLES} samples for training, got {len(samples)} "
            f"(collect 100-1000 samples of 8-16 KB each, see research.md §5.4)"
        )
    if dict_size <= 0:
        raise ValueError(f"dict_size must be >0, got {dict_size}")
    # Validate each sample is bytes-like
    for i, s in enumerate(samples):
        if not isinstance(s, (bytes, bytearray, memoryview)):
            raise ValueError(f"samples[{i}] is not bytes, got {type(s)}")
        # Empty samples are invalid
        if len(s) == 0:
            raise ValueError(f"samples[{i}] is empty")


def train(samples: List[bytes], dict_size: int = DEFAULT_DICT_SIZE) -> bytes:
    """Train a zstd dictionary from *samples*.

    Args:
        samples: list of bytes samples (each 8-16 KB, need ≥10).
        dict_size: target dictionary size bytes (default 112 KiB; 4 KiB for demo).

    Returns:
        Raw dictionary bytes (use ``dict_data`` for ``revhash.compress(..., dict_data=...)``).

    Raises:
        ValueError: if zstandard not installed, samples <10, or training fails.
    """
    _validate_samples(samples, dict_size)
    zstd = _require_zstd()

    # Convert to bytes (ensure not memoryview)
    byte_samples: List[bytes] = [bytes(s) for s in samples]

    # Optional: filter tiny samples but keep count check above
    # zstd train_dictionary requires total src size >= some threshold; we let backend raise.
    try:
        dict_obj = zstd.train_dictionary(dict_size, byte_samples)
    except Exception as exc:
        raise ValueError(
            f"zstd train_dictionary failed (samples={len(byte_samples)}, dict_size={dict_size}): {exc}"
        ) from exc

    # Dict object → raw bytes
    if hasattr(dict_obj, "as_bytes"):
        try:
            raw = dict_obj.as_bytes()
        except Exception as exc:
            raise ValueError(f"failed to get dict bytes: {exc}") from exc
    elif isinstance(dict_obj, (bytes, bytearray)):
        raw = bytes(dict_obj)
    else:
        # Fallback: try bytes conversion
        try:
            raw = bytes(dict_obj)  # type: ignore
        except Exception as exc:
            raise ValueError(f"unknown dict object type {type(dict_obj)}: {exc}") from exc

    if not raw:
        raise ValueError("trained dict is empty (try more/larger samples)")
    return raw


def get_samples_from_file(
    path: str | pathlib.Path,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    max_samples: int = DEFAULT_MAX_SAMPLES,
) -> List[bytes]:
    """Split file into samples for dictionary training.

    Reads ``path`` sequentially and cuts into chunks of ``sample_size``
    (default 16 KiB). Returns at most ``max_samples`` chunks.
    This mirrors ``research.md §B.1``: ``open(...).read()[:16*1024]`` per sample,
    but generalises to large files by chunking.

    Args:
        path: file path.
        sample_size: bytes per sample (8-16 KiB recommended).
        max_samples: maximum samples to return from this file.

    Returns:
        List of samples (each ``sample_size`` except last may be smaller).
        Empty list if file is empty.

    Raises:
        FileNotFoundError: if path not found.
        ValueError: on invalid params.
    """
    if sample_size <= 0:
        raise ValueError(f"sample_size must be >0, got {sample_size}")
    if max_samples <= 0:
        raise ValueError(f"max_samples must be >0, got {max_samples}")

    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"sample source not found: {p}")
    if p.is_dir():
        raise ValueError(f"path is directory, expected file: {p}")

    samples: List[bytes] = []
    # Stream file to avoid loading huge files fully
    with open(p, "rb") as f:
        while len(samples) < max_samples:
            chunk = f.read(sample_size)
            if not chunk:
                break
            # Optionally skip tiny tail (<1KB) if we already have many samples? But keep it for completeness.
            # For training effectiveness, very small samples (<100 bytes) are less useful but not harmful.
            samples.append(chunk)
            if len(chunk) < sample_size:
                # EOF reached (last partial chunk)
                break
    return samples


def train_from_files(
    paths: List[str],
    dict_size: int = DEFAULT_DICT_SIZE,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
) -> bytes:
    """Train dictionary from a list of files.

    For each file in *paths*, calls ``get_samples_from_file`` and
    collects samples (16 KB each). Then calls ``train``.

    Args:
        paths: list of file paths (str).
        dict_size: target dict size (default 112 KiB).
        sample_size: bytes per sample when chunking files.

    Returns:
        Raw dictionary bytes.

    Raises:
        ValueError: if collected samples <10 or training fails.
        FileNotFoundError: if any path not found (collects valid ones? Strict: raise).
    """
    if not isinstance(paths, (list, tuple)):
        raise ValueError("paths must be list[str]")
    if len(paths) == 0:
        raise ValueError("paths is empty, need at least one corpus file")

    all_samples: List[bytes] = []
    for pat in paths:
        # Allow Path objects as well
        p = pathlib.Path(pat)
        if not p.exists():
            raise FileNotFoundError(f"corpus file not found: {p}")
        # Use helper to chunk file
        # For train_from_files we allow up to max_samples per file, but to keep total reasonable
        # use default max_samples=100 per file; for many files this can be large but training handles.
        file_samples = get_samples_from_file(p, sample_size=sample_size, max_samples=DEFAULT_MAX_SAMPLES)
        # Filter empty?
        all_samples.extend(file_samples)

    if len(all_samples) < MIN_SAMPLES:
        raise ValueError(
            f"need at least {MIN_SAMPLES} samples, got {len(all_samples)} from {len(paths)} files "
            f"(sample_size={sample_size}). Provide more files or larger files."
        )

    return train(all_samples, dict_size=dict_size)


def save(dict_data: bytes, path: str | pathlib.Path) -> None:
    """Save raw dictionary bytes to *path*.

    Creates parent directories if needed.

    Args:
        dict_data: dictionary bytes from ``train``.
        path: output file path (e.g. ``dicts/vi_text.dict``).

    Raises:
        ValueError: if dict_data is empty/invalid.
        OSError: on write failure.
    """
    if not isinstance(dict_data, (bytes, bytearray, memoryview)):
        raise ValueError(f"dict_data must be bytes, got {type(dict_data)}")
    raw = bytes(dict_data)
    if len(raw) == 0:
        raise ValueError("dict_data is empty, nothing to save")
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)


def load(path: str | pathlib.Path) -> bytes:
    """Load raw dictionary bytes from *path*.

    Args:
        path: dictionary file path.

    Returns:
        Dictionary bytes.

    Raises:
        FileNotFoundError: if path not found.
        ValueError: if file is empty.
    """
    p = pathlib.Path(path)
    if not p.exists():
        raise FileNotFoundError(f"dict file not found: {p}")
    data = p.read_bytes()
    if len(data) == 0:
        raise ValueError(f"dict file is empty: {p}")
    return data
