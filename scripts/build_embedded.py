#!/usr/bin/env python3
"""Build revhash_embedded.py single-file bundle.

Reads src/revhash/exceptions.py, header.py, codec.py, stream.py, text.py, __init__.py
(public API part), concatenates in dependency order (exceptions→header→codec→stream→text),
writes revhash_embedded.py at repo root with header AUTO-GENERATED, sha256 bundle hash,
__version__="0.2.0-embedded", and verifies <512000 bytes.

Usage:
    python scripts/build_embedded.py        # rebuild
    python scripts/build_embedded.py --check  # fail if bundle drift
"""
from __future__ import annotations

import argparse
import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "revhash"
OUT = ROOT / "revhash_embedded.py"

# Core files that contribute to bundle hash (sorted for determinism)
HASH_FILES = ["exceptions.py", "header.py", "codec.py", "stream.py", "file_text.py", "text.py", "__init__.py"]

def compute_bundle_hash() -> str:
    h = hashlib.sha256()
    for name in sorted(HASH_FILES):
        p = SRC / name
        if p.exists():
            h.update(p.read_bytes())
            h.update(b"\x00")
    return "sha256:" + h.hexdigest()

def clean_source(path: pathlib.Path) -> str:
    """Return file content stripped of relative imports and __future__/__all__/__version__."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[str] = []
    skipping_relative_block = False
    skipping_all = False
    for line in lines:
        stripped = line.strip()
        # handle continuation of multi-line relative import block
        if skipping_relative_block:
            if ")" in line:
                skipping_relative_block = False
            continue
        # handle continuation of multi-line __all__ block
        if skipping_all:
            if "]" in line:
                skipping_all = False
            continue
        # skip future
        if stripped.startswith("from __future__"):
            continue
        # skip relative imports (from . or from revhash)
        if stripped.startswith("from .") or stripped.startswith("from revhash") or stripped.startswith("import revhash"):
            if "(" in line and ")" not in line:
                skipping_relative_block = True
            continue
        # skip __version__ single line
        if stripped.startswith("__version__"):
            continue
        # skip __all__ block (single or multi-line)
        if stripped.startswith("__all__") or "__all__" in line and "=" in line and "[" in line:
            # detect if multi-line
            if "[" in line and "]" not in line:
                skipping_all = True
            # single-line __all__ = [...] skip entirely
            continue
        out.append(line)
    return "\n".join(out)

def patch_stream_mkdir(content: str) -> str:
    """Ensure compress_file/decompress_file have mkdir(parents=True) for dst."""
    # If already has mkdir, return as is
    if "dst_path.parent.mkdir" in content:
        return content
    # Insert mkdir after dst_path = pathlib.Path(dst_path)
    # For both compress_file and decompress_file, pattern appears twice
    # Replace each occurrence of "dst_path = pathlib.Path(dst_path)" followed by newline
    # with same plus mkdir line
    pattern = r"(dst_path\s*=\s*pathlib\.Path\(dst_path\))"
    repl = r"\1\n    dst_path.parent.mkdir(parents=True, exist_ok=True)"
    patched = re.sub(pattern, repl, content)
    # Also ensure src existence checks are present (research §5.1)
    # If not present, we add them after src_path = pathlib.Path(src_path)
    if "if not src_path.exists():" not in patched:
        # insert after src_path line
        patched = re.sub(
            r"(src_path\s*=\s*pathlib\.Path\(src_path\))",
            r"\1\n    if not src_path.exists():\n        raise FileNotFoundError(f\"source not found: {src_path}\")\n    if src_path.is_dir():\n        raise IsADirectoryError(f\"source is directory: {src_path}\")",
            patched,
        )
    # Ensure dict_data path handling exists? stream.py already has it, keep
    return patched

def build_content(bundle_hash: str) -> str:
    parts: list[str] = []

    # Header comment
    header_comment = f'''"""
revhash_embedded — single-file bundle (<500KB), copy 1 file la chay.
AUTO-GENERATED from src/revhash/ — do not edit.
Source hash: {bundle_hash}  Sync: python scripts/build_embedded.py
Usage: import revhash_embedded as revhash; revhash.compress_text("xin chao")
"""
# AUTO-GENERATED — do not edit, source: src/revhash/, {bundle_hash}
from __future__ import annotations

import hashlib
import struct
import zlib
import gzip
import io
import os
import pathlib
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import BinaryIO, Tuple

__version__ = "0.4.0"
__bundle_hash__ = "{bundle_hash}"
__all__ = ["compress","decompress","compress_text","decompress_text","compress_file","decompress_file","compress_stream","decompress_stream","verify","get_info","get_available_codecs","RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError","RevHashHeader"]

'''
    parts.append(header_comment)

    # Exceptions (leaf)
    exc_path = SRC / "exceptions.py"
    if exc_path.exists():
        exc_clean = clean_source(exc_path)
        # exc_clean still contains class definitions; strip initial docstring? keep
        parts.append("# ── exceptions.py ───────────────────────────────────────────────────")
        parts.append(exc_clean.strip())
        parts.append("")

    # Header
    hdr_path = SRC / "header.py"
    if hdr_path.exists():
        hdr_clean = clean_source(hdr_path)
        # Remove any remaining from .exceptions that clean_source missed due to not starting with from . ?
        # Already removed. Keep rest.
        parts.append("# ── header.py ───────────────────────────────────────────────────────")
        parts.append(hdr_clean.strip())
        parts.append("")

    # Codec
    codec_path = SRC / "codec.py"
    if codec_path.exists():
        codec_clean = clean_source(codec_path)
        # Ensure lzma guard is kept: codec_clean should contain HAS_LZMA try block
        parts.append("# ── codec.py ────────────────────────────────────────────────────────")
        parts.append(codec_clean.strip())
        parts.append("")

    # Stream (with mkdir patch)
    stream_path = SRC / "stream.py"
    if stream_path.exists():
        stream_clean = clean_source(stream_path)
        stream_clean = patch_stream_mkdir(stream_clean)
        parts.append("# ── stream.py ───────────────────────────────────────────────────────")
        parts.append(stream_clean.strip())
        parts.append("")

    # File_text helpers (flex File<->Text)
    ft_path = SRC / "file_text.py"
    if ft_path.exists():
        ft_clean = clean_source(ft_path)
        parts.append("# ── file_text.py ────────────────────────────────────────────────────")
        parts.append(ft_clean.strip())
        parts.append("")

    # Public API from __init__.py (compress etc) — clean
    init_path = SRC / "__init__.py"
    if init_path.exists():
        init_text = init_path.read_text(encoding="utf-8")
        # Extract public API part: from "# ── Codec availability helpers" through before tail text import?
        # Clean whole file but keep functions compress, decompress, verify, get_info, get_available_codecs, _resolve_codec
        # Our clean_source will strip relative imports and __all__ etc, leaving helpers and functions
        init_clean = clean_source(init_path)
        # Remove the tail dict_builder / text lazy blocks that would duplicate? Keep but adapt.
        # The cleaned init will contain try: from . import dict_builder etc which we skipped, but also contains
        # the fallback definitions for text = None etc. We want to keep compress_text import? Actually init_clean after cleaning
        # will have lost the text import block because it starts with "from . import text". Since we skip from . lines, that block will be gone,
        # leaving only the alias definitions inside try? Let's reconstruct.
        # Simpler: keep init_clean but manually remove the tail blocks that reference dict_builder/text and re-add correctly later.
        # Remove any remaining "try:" blocks that were for dict_builder/text import (they will have been stripped of from . lines but still have try: and except)
        # Instead we will extract only up to "def get_info" and helpers, not tail.
        # Find marker for Optimization Builder section and cut before it, then we will add text helpers separately.
        # Locate "# ── Optimization Builder"
        marker = "# ── Optimization Builder"
        if marker in init_clean:
            init_clean = init_clean.split(marker)[0]
        # Also remove "# ── Text helpers" if present
        marker2 = "# ── Text helpers"
        if marker2 in init_clean:
            init_clean = init_clean.split(marker2)[0]
        parts.append("# ── __init__.py public API (compress/decompress/verify/get_info) ─")
        parts.append(init_clean.strip())
        parts.append("")

    # Text helpers (compress_text/decompress_text) — after public API so _compress alias works
    text_path = SRC / "text.py"
    if text_path.exists():
        text_raw = text_path.read_text(encoding="utf-8")
        # Clean text: remove from . import, but keep functions
        # Replace _compress/_decompress alias handling
        # First remove future and relative import lines
        lines = []
        for line in text_raw.splitlines():
            s = line.strip()
            if s.startswith("from __future__"):
                continue
            if s.startswith("from .") or s.startswith("import revhash"):
                continue
            lines.append(line)
        text_clean = "\n".join(lines).strip()
        # Ensure functions use compress/decompress directly; they currently use _compress/_decompress which we will alias
        parts.append("# ── text.py ─────────────────────────────────────────────────────────")
        parts.append("# alias for text helpers (original used from . import compress as _compress)")
        parts.append("_compress = compress")
        parts.append("_decompress = decompress")
        parts.append(text_clean)
        parts.append("")
    else:
        # Fallback: define compress_text/decompress_text manually if text.py missing
        parts.append("# ── text fallback (text.py missing) ───────────────────────────────")
        parts.append("""
def compress_text(text: str, codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None, encoding="utf-8") -> bytes:
    if not isinstance(text, str):
        raise TypeError(f"text must be str, got {type(text).__name__}")
    return compress(text.encode(encoding, "strict"), codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)

def decompress_text(blob: bytes, dict_data=None, encoding="utf-8") -> str:
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        raise TypeError("blob must be bytes")
    return decompress(blob, dict_data=dict_data).decode(encoding, "strict")
""")
        parts.append("")

    # Join
    content = "\n".join(parts)
    # Ensure file ends with newline
    if not content.endswith("\n"):
        content += "\n"
    # Basic cleanup: collapse excessive blank lines
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content

def main() -> None:
    parser = argparse.ArgumentParser(description="Build revhash_embedded.py bundle")
    parser.add_argument("--check", action="store_true", help="fail if bundle drift (hash mismatch)")
    args = parser.parse_args()

    bundle_hash = compute_bundle_hash()
    # If --check, compare existing file's hash
    if args.check:
        if not OUT.exists():
            print(f"[build_embedded] --check: {OUT} missing, need rebuild", file=sys.stderr)
            sys.exit(1)
        existing = OUT.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'__bundle_hash__\s*=\s*["\'](sha256:[0-9a-f]+)["\']', existing)
        if not m:
            print(f"[build_embedded] --check: no __bundle_hash__ in {OUT}", file=sys.stderr)
            sys.exit(1)
        existing_hash = m.group(1)
        if existing_hash != bundle_hash:
            print(f"[build_embedded] --check FAILED: bundle drift", file=sys.stderr)
            print(f"  expected (from src): {bundle_hash}", file=sys.stderr)
            print(f"  existing (in bundle): {existing_hash}", file=sys.stderr)
            print(f"  run python scripts/build_embedded.py to rebuild", file=sys.stderr)
            sys.exit(1)
        # also check content drift? Compare built content vs existing (ignoring hash line already)
        built = build_content(bundle_hash)
        if existing != built:
            # If content differs beyond hash, also drift
            # But hash already indicates drift; we also check size
            print(f"[build_embedded] --check FAILED: bundle content drift (hash matches but content differs)", file=sys.stderr)
            sys.exit(1)
        print(f"[build_embedded] --check OK: {bundle_hash} ({OUT.stat().st_size} bytes)")
        sys.exit(0)

    # Normal build
    content = build_content(bundle_hash)
    OUT.write_text(content, encoding="utf-8")
    size = OUT.stat().st_size
    print(f"[build_embedded] wrote {OUT} ({size} bytes) hash={bundle_hash}")
    if size >= 512000:
        print(f"[build_embedded] ERROR: bundle too large {size} >=512000 (must be <500KB)", file=sys.stderr)
        sys.exit(1)
    # Verify import
    try:
        import importlib.util, importlib.machinery
        spec = importlib.util.spec_from_file_location("revhash_embedded", str(OUT))
        mod = importlib.util.module_from_spec(spec)  # type: ignore
        assert spec and spec.loader
        # Ensure sys.modules entry for dataclass __module__ lookup
        sys.modules[spec.name] = mod
        spec.loader.exec_module(mod)  # type: ignore
        assert hasattr(mod, "__bundle_hash__")
        assert mod.__bundle_hash__ == bundle_hash
        # quick roundtrip
        blob = mod.compress_text("copy 1 file la chay")
        assert mod.decompress_text(blob) == "copy 1 file la chay"
        print(f"[build_embedded] verify import OK: compress_text roundtrip PASS, get_available_codecs={mod.get_available_codecs()}")
    except Exception as e:
        print(f"[build_embedded] verify import FAILED: {e}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)
    finally:
        # cleanup sys.modules to avoid polluting
        try:
            if "revhash_embedded" in sys.modules:
                del sys.modules["revhash_embedded"]
        except Exception:
            pass

if __name__ == "__main__":
    main()
