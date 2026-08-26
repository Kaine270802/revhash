"""Flexible File<->Text helpers for revhash v0.2.1-filetext.

Frozen contract docs/api_filetext.md Section 3:

- _resolve_src / _resolve_dst heuristic file-vs-text (Path.exists + is_file)
- _load_dict_data (Path exists -> read_bytes)
- _guard_large_file_for_ram (100MB guard for dst=None)

All helpers are strict encoding, raise TypeError/FileNotFoundError/
IsADirectoryError/UnicodeError/ValueError per spec.

Owner: Unified I/O Builder — file_text.py 120-180 lines
"""

from __future__ import annotations

from pathlib import Path


def _load_dict_data(d: bytes | str | Path | None) -> bytes | None:
    """Load dict_data if it is a Path/str pointing to existing file.

    Mirrors stream.py:1035 legacy behaviour.
    """
    if isinstance(d, (str, Path)):
        p = Path(d)
        if p.exists() and p.is_file():
            return p.read_bytes()
        return None
    return d  # type: ignore[return-value]  # d is bytes|None here


def _resolve_src(src, encoding: str = "utf-8", force_text: bool = False):
    """Resolve src -> (is_file: bool, data: bytes|None, path: Path|None).

    4 forms:
      S4 bytes|bytearray|memoryview -> (False, bytes(src), None)
      S1 Path explicit file -> (True, None, Path) with exists/is_dir checks
      S2/S3 str heuristic: if not force_text and Path(src).exists() and is_file()
            -> file, else -> text encode strict

    Raises:
      TypeError if src is not str|Path|bytes-like
      FileNotFoundError if Path explicit not exists
      IsADirectoryError if Path is directory
      UnicodeEncodeError strict if str cannot be encoded
    """
    if isinstance(src, (bytes, bytearray, memoryview)):
        return False, bytes(src), None
    if isinstance(src, Path):
        p = src
        if not p.exists():
            raise FileNotFoundError(f"source not found: {p}")
        if p.is_dir():
            raise IsADirectoryError(f"source is directory: {p}")
        return True, None, p
    if isinstance(src, str):
        if not force_text:
            p = Path(src)
            try:
                if p.exists() and p.is_file():
                    return True, None, p
            except OSError:
                raise
        # S3 — text direct
        try:
            data = src.encode(encoding, "strict")
        except UnicodeEncodeError:
            raise
        return False, data, None
    raise TypeError(f"src must be str|Path|bytes, got {type(src).__name__}")


def _resolve_dst(dst):
    """Resolve dst -> Path|None with mkdir for dst.parent.

    - None -> None (RAM)
    - str|Path -> Path with parent.mkdir(parents=True, exist_ok=True)
      and IsADirectoryError if dst itself is existing directory.

    Raises:
      TypeError if dst is not str|Path|None
      IsADirectoryError if dst is existing directory
    """
    if dst is None:
        return None
    if isinstance(dst, (str, Path)):
        p = Path(dst)
        if p.exists() and p.is_dir():
            raise IsADirectoryError(f"destination is directory: {p}")
        # mkdir only for dst parent, not for src
        # parents=True handles nested out/nested/file.rvh
        # exist_ok=True safe for race
        # For dst with no parent (e.g., "file.rvh" -> parent "." ), mkdir "." is no-op
        # Use try to handle edge where parent is ""? Path("file").parent is "." which exists.
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            # parent is file? Let open raise later
            pass
        return p
    raise TypeError(f"dst must be str|Path|None, got {type(dst).__name__}")


def _guard_large_file_for_ram(src_path: Path, dst):
    """Guard OOM when src is large file and dst is None (RAM).

    Raises ValueError if dst is None and st_size > 100MB.

    Note: uses stat() syscall; caller should have validated src_path exists/is_file.
    """
    if dst is None:
        try:
            size = src_path.stat().st_size
        except OSError:
            return
        if size > 100 * 1024 * 1024:
            raise ValueError(
                "refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )


def _guard_large_bytes_for_ram(data: bytes, dst):
    """Guard OOM for bytes src with dst=None (Critic HIGH #2).

    Raises ValueError if data length >100MB and dst is None.
    """
    if dst is None and isinstance(data, (bytes, bytearray, memoryview)):
        if len(data) > 100 * 1024 * 1024:
            raise ValueError(
                "refusing to load large bytes (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )


def _guard_large_decompress_for_ram(src_blob_or_path, dst, encoding="utf-8"):
    """Guard OOM for decompress dst=None (Critic HIGH #1).

    Checks header.original_size from blob (bytes or file) without full decompress.
    Raises ValueError if decompressed size >100MB and dst is None.
    """
    if dst is not None:
        return
    try:
        from .header import RevHashHeader

        header = None
        if isinstance(src_blob_or_path, (bytes, bytearray, memoryview)):
            blob = bytes(src_blob_or_path)
            if len(blob) >= 23:
                header, _ = RevHashHeader.from_bytes(blob, 0)
        elif isinstance(src_blob_or_path, (str, Path)):
            p = Path(src_blob_or_path)
            if p.exists() and p.is_file() and p.stat().st_size >= 23:
                # Read only header (23 + dict_len) to get original_size
                with open(p, "rb") as f:
                    hdr = f.read(23)
                    if len(hdr) >= 23:
                        import struct

                        _, _, _, _, _, dict_len, original_size = struct.unpack("<4sBBBIIQ", hdr)
                        # Use header parse for dict_len
                        if dict_len <= 256 * 1024:
                            # Need full header for original_size already in hdr
                            # original_size is in hdr
                            if original_size != 0xFFFFFFFFFFFFFFFF and original_size > 100 * 1024 * 1024:
                                raise ValueError(
                                    f"refusing to decompress large blob (original {original_size} bytes >100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
                                )
                            return
                        # Fallback: parse full header
                        f.seek(0)
                        hdr_full = f.read(23 + dict_len)
                        header, _ = RevHashHeader.from_bytes(hdr_full, 0)
        if (
            header is not None
            and header.original_size != 0xFFFFFFFFFFFFFFFF
            and header.original_size > 100 * 1024 * 1024
        ):
            raise ValueError(
                f"refusing to decompress large blob (original {header.original_size} bytes >100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming"
            )
    except ValueError:
        raise
    except Exception:
        # If header parsing fails, let decompress fail later with CorruptedError
        pass


# ── End of file_text.py ───────────────────────────────────────────────
# This module is intentionally small (120-180 lines) and has no circular
# imports. It is inlined into revhash_embedded.py after stream.py per
# TEAM_PLAN_FILETEXT M3 checklist.
