# revhash File↔Text Flexible API Spec — Design Freeze v0.2.1 (M2)

> **Version:** 0.4.0 (Design Freeze 2026-08-28, sync v0.3 polish — không đổi logic, chỉ bump version)
> **Owner:** Coordinator (dựa trên `docs/research_filetext.md` §4)
> **Mục tiêu:** Freeze contract cho M3 Builder — `compress_file`/`decompress_file` linh hoạt **File ⇄ Văn bản**, `dst` tùy chọn, không break v0.2 embedded (142 tests).

---

## 1. Tổng quan

Mở rộng v0.2 (`compress_file(src: Path, dst: Path)`) thành **linh hoạt**:

- `src: str | Path | bytes | bytearray | memoryview` — 4 dạng (§4.1 research): `Path` explicit file, `str` path tồn tại → file, `str` text → encode, `bytes` raw.
- `dst: str | Path | None = None` — 3 dạng: `Path|str` → ghi file + `mkdir(parents=True)` + trả `dict info`; `None` → **trả `bytes`/`str` trong RAM**, không chạm filesystem.
- Thêm `encoding="utf-8"` strict, `force_text=False` (ép `str` src thành text), `as_text=False` (decompress `dst=None` trả `str`).

Giữ `compress`/`compress_text`/`decompress_text` v0.2 không đổi.

---

## 2. Signatures Frozen

```python
from pathlib import Path
import os

def compress_file(
    src: str | Path | bytes | bytearray | memoryview,
    dst: str | Path | None = None,
    codec: str | int = "zstd",
    level: int = 3,
    chunk_size: int = 4 * 1024 * 1024,
    dict_data: bytes | str | Path | None = None,
    encoding: str = "utf-8",
    force_text: bool = False,
    as_text: bool = False,  # kept for symmetry, unused in compress (reserve)
    show_progress: bool = False,
) -> bytes | dict:
    """Nén linh hoạt File↔Text.
    - src S1/S2 (file) → streaming O(1) via compress_stream
    - src S3/S4 (text/bytes) → in-memory via BytesIO
    - dst=None → trả bytes blob; dst=Path → ghi file + mkdir + trả dict
    """
    ...

def decompress_file(
    src: str | Path | bytes | bytearray | memoryview,
    dst: str | Path | None = None,
    dict_data: bytes | str | Path | None = None,
    encoding: str = "utf-8",
    as_text: bool = False,
    force_text: bool = False,
    show_progress: bool = False,
) -> bytes | str | dict:
    """Giải nén linh hoạt.
    - src có thể là Path blob file, bytes blob, hoặc str text (nếu force_text)
    - dst=None → trả bytes (as_text=False) hoặc str (as_text=True, decode strict)
    - dst=Path → ghi file + mkdir + trả dict
    """
    ...
```

**Backward compat:**
- `compress_file("a.txt", "b.rvh")` cũ (2 args Path) → vẫn `str|Path` 2 args → PASS.
- `compress_file(src, dst=None)` mới default `None` → nếu gọi 2 args như cũ không break; nếu gọi 1 arg `compress_file("hello")` → `dst=None` → trả `bytes` (new DX).
- `compress_file(b"raw", "out.rvh")` mới hỗ trợ `bytes` src → PASS.

---

## 3. Heuristic `_resolve_src` / `_resolve_dst` (Frozen)

```python
def _resolve_src(src, encoding="utf-8", force_text=False):
    if isinstance(src, (bytes, bytearray, memoryview)):  # S4
        return False, bytes(src), None
    if isinstance(src, Path):  # S1
        if not src.exists(): raise FileNotFoundError(f"source not found: {src}")
        if src.is_dir(): raise IsADirectoryError(f"source is directory: {src}")
        return True, None, src
    if isinstance(src, str):  # S2 vs S3
        if not force_text:
            p = Path(src)
            try:
                if p.exists() and p.is_file():
                    return True, None, p  # S2
            except OSError: raise
        # S3
        return False, src.encode(encoding, "strict"), None
    raise TypeError(f"src must be str|Path|bytes, got {type(src).__name__}")

def _resolve_dst(dst):
    if dst is None: return None
    if isinstance(dst, (str, Path)):
        p = Path(dst)
        if p.exists() and p.is_dir(): raise IsADirectoryError(f"destination is directory: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    raise TypeError(f"dst must be str|Path|None, got {type(dst).__name__}")

def _load_dict_data(d):  # giữ contract cũ stream.py:1035
    if isinstance(d, (str, Path)) and Path(d).exists(): return Path(d).read_bytes()
    return d

def _guard_large_file_for_ram(src_path: Path, dst):
    if dst is None and src_path.stat().st_size > 100*1024*1024:
        raise ValueError("refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming")
```

**Order:** S4 (`bytes`) > S1 (`Path`) > S2/S3 (`str` heuristic). Chỉ `str` cần `exists()` syscall.

**`mkdir` chỉ `dst`:** không `mkdir` cho `src`.

**Encoding:** Ném `UnicodeEncodeError`/`UnicodeDecodeError` strict, không `replace`.

---

## 4. Return Types (Frozen)

| Hàm | `dst` | `as_text` | Trả về | Ví dụ |
|-----|-------|-----------|--------|-------|
| `compress_file` | `Path|str` | — | `dict` info | `compress_file("hello", "out.rvh") -> {"codec":"zstd", ...}` |
| `compress_file` | `None` | — | `bytes` blob | `blob = compress_file("hello", None)` |
| `decompress_file` | `Path|str` | — | `dict` | `decompress_file("out.rvh", "restored.txt")` |
| `decompress_file` | `None` | `False` | `bytes` | `raw = decompress_file(blob, None)` |
| `decompress_file` | `None` | `True` | `str` | `text = decompress_file(blob, None, as_text=True)` |

**`as_text=True` chỉ cho `decompress_file` + `dst=None`:** decode `bytes→str` strict.

---

## 5. Error Mapping (Frozen)

| Tình huống | Exception |
|------------|-----------|
| `src=123` | `TypeError` |
| `src=Path("missing.txt")` | `FileNotFoundError` |
| `src=Path("docs")` dir | `IsADirectoryError` |
| `src="\ud800"` encode fail | `UnicodeEncodeError` |
| `dst=Path("out_dir/")` dir tồn tại | `IsADirectoryError` |
| `dst=123` | `TypeError` |
| `decompress_file(as_text=True)` nhưng payload `b"\xff\xfe"` | `UnicodeDecodeError` |
| File lớn `>100MB` với `dst=None` | `ValueError` guard |
| Blob corrupt | `RevHashCorruptedError` |
| Codec thiếu | `RevHashUnsupportedCodecError` |

---

## 6. Module Layout — Frozen cho M3

```
D:\data optimization\
├── revhash_embedded.py (rebuild)
├── scripts/build_embedded.py (HASH_FILES += file_text.py)
├── src/revhash/
│   ├── file_text.py (NEW 120-180 dòng, _resolve_src/_dst/_guard)
│   ├── stream.py (PATCH compress_file/decompress_file dùng file_text helpers)
│   ├── __init__.py (re-export file_text helpers nếu cần, không break __all__)
│   ├── text.py, header.py, codec.py, exceptions.py (giữ)
│   └── stream.py:163 compress_stream O(1) giữ
├── examples/filetext_flex_demo.py (NEW 6 cases)
└── tests/test_filetext_flex.py (NEW 8+ cases)
```

**Ownership:** Builder sở hữu `file_text.py` + `stream.py` patch + bundle rebuild. Không sửa `text.py`/`header.py`.

---

## 7. 6 Ví dụ copy-paste phải PASS (M4 Integration)

```python
import revhash
from pathlib import Path
# 1 text→bytes (dst=None)
blob = revhash.compress_file("xin chào 🌍", None)
assert revhash.decompress(blob).decode() == "xin chào 🌍"
# 2 text→file
info = revhash.compress_file("hello 🌍\n"*1000, "out/nested/text.rvh")
assert Path("out/nested/text.rvh").exists()
# 3 file→text as_text
Path("sample.txt").write_text("nội dung", encoding="utf-8")
revhash.compress_file(Path("sample.txt"), "sample.rvh")
assert revhash.decompress_file("sample.rvh", None, as_text=True) == "nội dung"
# 4 file→file O(1)
revhash.compress_file("sample.txt", "sample2.rvh")
revhash.decompress_file("sample2.rvh", "restored.txt")
assert Path("restored.txt").read_text() == Path("sample.txt").read_text()
# 5 bytes→bytes
raw = b"\x00\xff raw"; assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw
# 6 force_text
Path("notes.txt").write_text("file content")
assert revhash.decompress_file(revhash.compress_file("notes.txt", None, force_text=True), None, as_text=True) == "notes.txt"
```

---

## 8. Performance & Compatibility

| Check | Target |
|-------|--------|
| `compress_file(Path 1GB, dst=Path)` | O(1) streaming, peak <150MB |
| `compress_file("hello", None)` | in-memory, byte-identical `compress("hello")` |
| `compress_file(Path 10MB, None)` >100MB guard | `ValueError` |
| 142 cũ PASS + 8 mới → 150+ total | Không regress >5% |

---

*— Coordinator, Design Freeze 2026-08-28 — Frozen.*
