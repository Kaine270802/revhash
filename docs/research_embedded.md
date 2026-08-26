# Nghiên cứu Thư viện Nhúng revhash v0.2-embedded — File + Text trực tiếp

> **Owner:** Researcher / Explorer — Embedded — Team revhash v0.2-embedded
> **Ngày:** 2026-08-27
> **Inputs:** `TEAM_PLAN_EMBEDDED.md`, `src/revhash/__init__.py`, `stream.py`, `header.py`, `codec.py`, `docs/research.md`, `docs/api.md`, `TEAM_STATE.md`
> **Mục tiêu:** Khảo sát ≥4 pattern nhúng Python prior-art, so sánh DX file+text, đề xuất bundle `revhash_embedded.py` `<500KB` và API thống nhất cho M3a/M3b.

---

## 1. Định nghĩa "Thư viện Nhúng" (Embedded Library)

### 1.1 Định nghĩa vận hành

> **Embedded = vendored**: copy **1 file** (`revhash_embedded.py`) hoặc **1 folder** (`src/revhash/`) vào repo khác → `import` ngay, **không** service/daemon/server, không build step ngoài `pip`.

Khác v0.1-rc (tập trung benchmark unlimited O(1) tới 10GB+), v0.2 tập trung **trải nghiệm nhúng**: copy xong dùng được cả `str` (text) và `path` (file) với cùng mental model.

### 1.2 Tiêu chí kiểm định

| # | Tiêu chí | Diễn giải kỹ thuật | Cách kiểm |
|---|----------|---------------------|-----------|
| C1 | Copy 1 file/folder là chạy | `cp revhash_embedded.py ./vendor/` → `import revhash_embedded` không cần `pip install` | `python -c "import revhash_embedded"` trong thư mục trống |
| C2 | Không service | Không port/subprocess/ENV config | `grep -r "socket\|daemon"` = 0 |
| C3 | API trực tiếp file+text | `compress_text(str)->bytes`, `decompress_text`, `compress_file(Path,Path)->dict` | `examples/embed_demo.py` copy 1 file vẫn chạy |
| C4 | Import side-effect tối thiểu | `import revhash` không đọc file/mạng, không crash khi thiếu `zstandard`/`brotli` | `time python -c "import revhash"` <100ms |
| C5 | Zero-deps graceful | Thiếu `zstandard` → không `ImportError` lúc import; `get_available_codecs()` báo, `compress(codec="zstd")` raise `RevHashUnsupportedCodecError`, `codec="auto"` fallback `gzip`/`store` | mock `sys.modules['zstandard']=None` |
| C6 | Single-file <500KB, hash-verifiable | `revhash_embedded.py` chứa core (header+codec+stream+exceptions+text), kèm `sha256` verify drift | `sha256sum revhash_embedded.py` |
| C7 | DX copy-paste | 5 snippet trong `README_EMBEDDED.md` chạy được, `__all__` gọn ≤15 symbol, type hints | Verifier chạy từng snippet |

### 1.3 Các mức nhúng

```
M0  pip install        — pip install -e . → import revhash
M1  vendored package   — cp -r src/revhash ./vendor/ → from vendor import revhash
M2  single-file bundle — cp revhash_embedded.py ./project/ → import revhash_embedded  ← BẮT BUỘC v0.2
M3  zipapp executable  — python -m zipapp -o revhash.pyz → python revhash.pyz            (optional)
```

v0.2 phải hỗ trợ **M0+M2** đồng thời (M1 là hệ quả tự nhiên của `hatchling` package `pyproject.toml:36`, M3 optional).

### 1.4 Anti-goals

- Không binary/extension `.so`, không yêu cầu `setup.py` khi vendored, không `import hook` phức tạp (chỉ liệt kê để loại trừ §2.5).

---

## 2. Khảo sát 5 Pattern Nhúng Python Prior-Art

### 2.1 Pattern A — Single-file bundle (1 file)

**Mô tả:** Toàn bộ lib gộp vào **1 file `.py`** (~1–10k LOC), copy là chạy, không `__init__.py` phức tạp.

**Prior-art:**
- **bottle.py** — micro web framework 1 file `bottle.py` (~4500 LOC, 180KB), stdlib-only, `★9k`. https://github.com/bottlepy/bottle
- **tinydb** giai đoạn đầu + `httpie` compat shim cũng dùng pattern này.

**Ưu:** Copy 1 file thật sự, không xung đột namespace (`import revhash_embedded` ≠ `revhash` pip), dễ audit diff.
**Nhược:** Cần tooling sync tránh drift `src/` vs bundle; file >500KB linter chậm; không tận dụng namespace `revhash.algorithms.selector`.

**Phù hợp revhash?** ✅ **PRIMARY — bắt buộc**. Core `revhash` ~129KB source (không `__pycache__`), bundle core ước ~85KB → dư 5× margin <500KB (xem §4.1).

### 2.2 Pattern B — Vendored package (copy 1 folder)

**Mô tả:** Copy `src/revhash/` nguyên cấu trúc vào `vendor/`, giữ module boundaries.

**Prior-art:**
- **pip `_vendor`** — `src/pip/_vendor/` chứa `requests`, `urllib3`, `packaging` copy nguyên bản, patch import `pip._vendor.requests`. https://github.com/pypa/pip/tree/main/src/pip/_vendor — https://pip.pypa.io/en/stable/development/vendoring/
- **requests** vendored `urllib3` (pre-2.28): `requests/packages/urllib3/`.

**Ưu:** Giữ type hints/test isolation, không cần build, namespace đầy đủ (`revhash.dict_builder`).
**Nhược:** Copy 1 folder không thỏa "1 file" strict; phải chỉnh `sys.path` nếu dưới `vendor/`.

**Phù hợp?** ✅ **SUPPORT song song** với A. `src/revhash` đã là package chuẩn `hatchling` (`pyproject.toml:36`), không cần thêm việc, chỉ document.

### 2.3 Pattern C — Stdlib-only fallback / graceful degradation

**Mô tả:** Chạy được chỉ với stdlib nếu C-extension thiếu: `try: import zstandard` → fallback `gzip`/`store`, không crash tại import.

**Prior-art:**
- **python-zstandard** docs khuyên `try: import zstandard; HAS_ZSTD=True`. https://github.com/indygreg/python-zstandard
- **Pillow** `try: import _imaging` else pure python; **orjson→json** fallback trong `fastapi`.
- **revhash hiện tại** đã làm đúng: `src/revhash/codec.py:26-42` (`HAS_ZSTD`, `HAS_BROTLI`), `stream.py:249-250` raise `RevHashUnsupportedCodecError` nếu thiếu.

**Ưu:** Zero-deps graceful đúng nghĩa C5, không tăng bundle size (dùng `gzip`/`lzma` stdlib), dễ mock `HAS_ZSTD=False`.
**Nhược:** Ratio kém khi fallback (`gzip` 32× kém `zstd` trên 10MB text lặp `docs/research.md §3.6`).

**Phù hợp?** ✅ **BẮT BUỘC logic trong A+B**. Giữ `codec.py` flags, thêm `get_available_codecs()` (§4.4).

### 2.4 Pattern D — Lazy import / optional deps (`find_spec`)

**Mô tả:** Không import nặng ở top-level; check `importlib.util.find_spec("zstandard") is not None` thay vì `import`, hoặc `try: import` trong function body.

**Prior-art:**
- **pandas** `pandas.compat._optional.import_optional_dependency("openpyxl")`. https://github.com/pandas-dev/pandas/blob/main/pandas/compat/_optional.py
- **scikit-learn** soft-dependency: `try: import pyarrow` inside function, raise `ImportError` với hint chỉ khi cần.
- **importlib** docs: https://docs.python.org/3/library/importlib.html#checking-if-a-module-can-be-imported

**Ưu:** `import revhash` <50ms, lỗi chỉ khi `compress(codec="zstd")` thiếu backend.
**Nhược:** Lỗi phát hiện muộn (runtime), cần message rõ.

**Phù hợp?** ✅ **Áp dụng cho `zstandard`/`brotli`**. `codec.py` đã lazy flag, `stream.py:251` đã `import zstandard` inside branch. Giữ eager cho stdlib (`zlib`, `hashlib`) và lazy cho `zstandard`/`brotli`, thêm `get_available_codecs()` cache (§4.4).

### 2.5 Pattern E — Import hook / zipapp (PEP 441)

**Mô tả:** `importlib.abc.MetaPathFinder` intercept `import`, hoặc đóng gói `python -m zipapp -o revhash.pyz`.

**Prior-art:**
- **zipapp** stdlib: https://docs.python.org/3/library/zipapp.html (PEP 441) — cho CLI executable, không phải library import.
- **shiv** (LinkedIn): https://github.com/linkedin/shiv — zipapp với dependencies, bootstrap `sys.path`.
- **import hook** docs: https://docs.python.org/3/library/importlib.html#setting-up-an-importer

**Ưu:** Đóng gói `.so` dependencies, chạy `python revhash.pyz compress file.txt out.rvh`.
**Nhược:** Không `import` như module thường (phải `sys.path.insert(0,"revhash.pyz")`), IDE/mypy không hiểu, `.so` platform-specific.

**Phù hợp?** ❌ **LOẠI cho M2 library**; chỉ optional CLI. Liệt kê để M3a không đi sai hướng.

### 2.6 Bảng so sánh tổng hợp

| Pattern | Artifact | Copy gì | Zero-deps | Import side-effect | IDE thân thiện | <500KB | Ref | Đề xuất |
|---------|----------|---------|-----------|-------------------|----------------|--------|-----|---------|
| **A Single-file** | `revhash_embedded.py` | 1 file | ✅ gzip/store | Minimal | ✅ | ✅ ~95KB | bottle.py https://github.com/bottlepy/bottle | **PRIMARY** |
| **B Vendored pkg** | `src/revhash/` | 1 folder | ✅ | Minimal | ✅ | ✅ 129KB | pip `_vendor` https://github.com/pypa/pip/tree/main/src/pip/_vendor | **SUPPORT** |
| **C Stdlib fallback** | logic | — | ✅ `HAS_ZSTD` | None | ✅ | — | python-zstandard https://github.com/indygreg/python-zstandard | **BẮT BUỘC** |
| **D Lazy import** | logic | — | ✅ `find_spec` | Deferred | ✅ | — | pandas `_optional.py` https://github.com/pandas-dev/pandas/blob/main/pandas/compat/_optional.py | **Áp dụng zstd/brotli** |
| **E zipapp/hook** | `revhash.pyz` | 1 zip | ❌ `.so` lock | Hook overhead | ❌ | ❌ >2MB | zipapp https://docs.python.org/3/library/zipapp.html, shiv https://github.com/linkedin/shiv | **LOẠI** |

**Kết luận:** Chọn **A+B+C+D** kết hợp: build **single-file bundle (A)** từ vendored package (B) bằng inline, dùng stdlib fallback (C) + lazy import (D) cho zero-deps graceful. Loại E.

---

## 3. So sánh DX cho File + Text — Đề xuất API thống nhất v0.2

### 3.1 Hiện trạng v0.1 (`src/revhash/__init__.py:70-148`)

```python
def compress(data: bytes, codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None) -> bytes: ...
def decompress(blob: bytes, dict_data=None) -> bytes: ...
def compress_file(src: str|Path, dst: str|Path, codec="zstd", ...) -> dict: ...
def decompress_file(src: str|Path, dst: str|Path, ...) -> dict: ...
def compress_stream(reader: BinaryIO, writer: BinaryIO, ...) -> dict: ...
```

- `compress()` chỉ nhận `bytes` (`__init__.py:94` `isinstance(data,(bytes,bytearray,memoryview))`), chưa có `compress_text(str)`.
- `compress_file()` đã `str|Path` (`stream.py:1029` `Path(src_path)`) nhưng **chưa** `mkdir(parents=True)` cho `dst` → `FileNotFoundError` nếu parent chưa tồn tại.
- Chưa `str` utf-8 handling, chưa `get_available_codecs()`.

### 3.2 Lựa chọn DX đã cân nhắc

#### A. `compress_text(str)` vs `compress(bytes|str)` polymorphic

| Lựa chọn | Ví dụ | Ưu | Nhược |
|----------|-------|----|-------|
| **A1 Riêng biệt** `compress_text(str)` + `compress(bytes)` | `compress_text("xin chào")` / `compress(b"raw")` | Explicit, type-safe, không ambiguity | Nhiều hàm hơn |
| **A2 Polymorphic** `compress(bytes|str)` | `compress("xin chào")` auto utf-8 | Ít hàm, DX magic | Ambiguity silent |
| **A3 Hybrid** cả hai | `compress(b"...")`/`compress("...")` đều chạy, `compress_text` canonical | Linh hoạt, backward compat | Nhiều entrypoint |

**Đề xuất v0.2: A3 Hybrid** — `compress(data: bytes|str, encoding="utf-8", ...)` polymorphic + `compress_text(text: str, ...)` explicit, `decompress_text(blob, encoding="utf-8")->str`.

- Không break v0.1: `compress(b"...")` giữ nguyên.
- `compress(str)` detect `isinstance(data,str)` → `data.encode(encoding, "strict")`.
- Prior-art: `gzip.compress(data: bytes)` không nhận `str` (explicit), nhưng `Pillow`/`pandas` hybrid (`Image.open(path|bytes)`) là chuẩn hiện đại cho DX nhúng.

#### B. `compress_file` vs `compress_path` alias

| Lựa chọn | Đề xuất | Lý do |
|----------|---------|-------|
| `compress_file(src,dst)` | **PRIMARY** | Rõ ràng, khớp `decompress_file`, prior-art `gzip`/`shutil` |
| `compress_path` alias | **KHÔNG** | Duplicate, vi phạm YAGNI (`TEAM_PLAN_EMBEDDED.md §5` Coordinator enforce 4 hàm chính) |

Giữ `compress_file` canonical, document `str|Path` đều được.

#### C. Encoding / Path / Errors

| Vấn đề | Đề xuất v0.2 | Lý do |
|--------|-------------|-------|
| **Encoding** | `utf-8` **strict** (`errors="strict"`) | `str.encode` raise `UnicodeEncodeError`, `bytes.decode` raise `UnicodeDecodeError`, không `replace` (silent loss). Test emoji/tiếng Việt `b"xin ch\xc3\xa0o \xf0\x9f\x98\x80"` roundtrip 100%. Prior-art `Path.read_text(encoding="utf-8", errors="strict")`. |
| **`bytes` raw** | Pass-through raw | `compress(b"\xff\xfe")` giữ nguyên, decompress đúng `b"\xff\xfe"`. Đảm bảo `compress(b"hello")==compress("hello".encode())` byte-identical. |
| **`Path` mkdir** | **Có** `dst.parent.mkdir(parents=True, exist_ok=True)` chỉ cho output | DX nhúng: `compress_file("a.txt","out/nested/a.rvh")` không fail. Chỉ output, không input. Prior-art `shutil.copy` CLI thường tự mkdir. |
| **Errors** | `TypeError` (sai type), `FileNotFoundError`, `IsADirectoryError`, `RevHashUnsupportedCodecError`, `UnicodeError` — **không** wrap thành `RevHashError` | Caller phân biệt `except (UnicodeError, RevHashError)` rõ ràng. |

### 3.3 Bảng quyết định API v0.2 (Frozen cho M3a/M3b)

| API | Signature đề xuất | Input → Output | Ghi chú |
|-----|-------------------|---------------|---------|
| `compress` | `compress(data: bytes|str, codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None, encoding="utf-8") -> bytes` | `str`→`encode(strict)`, `bytes`→raw → `bytes` blob | Hybrid polymorphic, backward compat |
| `decompress` | `decompress(blob: bytes, dict_data=None) -> bytes` | `bytes`→`bytes` | Giữ v0.1 |
| `compress_text` | `compress_text(text: str, codec="zstd", ..., encoding="utf-8") -> bytes` | `str` (bắt buộc, `bytes` raise TypeError) → `bytes` | Explicit strict |
| `decompress_text` | `decompress_text(blob: bytes, dict_data=None, encoding="utf-8") -> str` | `bytes`→`str` strict | `decompress(...).decode(strict)` |
| `compress_file` | `compress_file(src: str|Path, dst: str|Path, codec="zstd", ..., dict_data=None|str|Path) -> dict` | `str|Path` → `dict` info | Tự `mkdir(parents=True)` output, `dict_data` có thể là path |
| `decompress_file` | `decompress_file(src: str|Path, dst: str|Path, ...) -> dict` | `str|Path` | Tương tự |
| `compress_stream`/`decompress_stream` | Giữ v0.1 | `BinaryIO` | Không đổi |
| `get_available_codecs` **mới** | `get_available_codecs() -> dict[str,bool]` | — → `{"store":True,"gzip":True,"zstd":bool,"lzma":True,"brotli":bool}` | Lazy `HAS_*` flags |
| `get_info`/`verify` | Giữ v0.1 | `bytes` | Không đổi |

**`__all__` gọn v0.2 (11 core + 4 errors = 15, vẫn gọn):**
```python
__all__ = ["__version__","compress","decompress","compress_text","decompress_text",
           "compress_file","decompress_file","compress_stream","decompress_stream",
           "verify","get_info","get_available_codecs",
           "RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError"]
```

### 3.4 Ví dụ copy-paste (phải chạy sau khi copy 1 file)

**Ví dụ 1 — Text tiếng Việt + emoji (utf-8 strict):**
```python
import revhash
text = "xin chào thế giới 🌍 — revhash lossless"
blob = revhash.compress_text(text)              # str -> bytes
assert revhash.decompress_text(blob) == text
blob2 = revhash.compress(text)                  # polymorphic cũng chạy
assert revhash.decompress(blob2).decode() == text
```

**Ví dụ 2 — Bytes raw:**
```python
import revhash
data = b"\x00\xff\xfe hello \x80\x81"
assert revhash.decompress(revhash.compress(data)) == data
try: revhash.compress_text(b"oops")  # type: ignore
except TypeError: print("expected TypeError for bytes in compress_text")
```

**Ví dụ 3 — File tự mkdir:**
```python
from pathlib import Path; import revhash
src = Path("examples/hello.txt"); src.write_text("xin chào\n"*1000, encoding="utf-8")
info = revhash.compress_file(src, "out/nested/hello.rvh")  # tự mkdir out/nested/
print(info)  # {codec: zstd, ratio: 0.002, ...}
revhash.decompress_file("out/nested/hello.rvh", "out/restored.txt")
assert Path("out/restored.txt").read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
```

**Ví dụ 4 — Fallback khi thiếu zstandard:**
```python
import revhash
print(revhash.get_available_codecs())  # {'store':True,'gzip':True,'zstd':False,...}
blob = revhash.compress(b"hello"*1000, codec="auto")  # fallback gzip, không crash
print(revhash.get_info(blob)["codec"])  # gzip nếu zstd missing
try: revhash.compress(b"hi", codec="zstd")
except revhash.RevHashUnsupportedCodecError as e: print("need pip install zstandard:", e)
```

**Ví dụ 5 — Single-file vendored:**
```python
# cp revhash_embedded.py ./myproject/  →  import revhash_embedded as revhash
import revhash_embedded as revhash
assert revhash.decompress_text(revhash.compress_text("copy 1 file là chạy")) == "copy 1 file là chạy"
revhash.compress_file("input.txt", "output.rvh")
```

Tất cả 5 ví dụ phải PASS trong `tests/test_text_file.py` và `tests/test_embedded.py`.

---

## 4. Đề xuất Bundle Strategy — `revhash_embedded.py` (<500KB)

### 4.1 Kích thước hiện tại (thực đo 2026-08-27)

```
python -c "import pathlib; p=pathlib.Path('src/revhash'); print(sum(f.stat().st_size for f in p.rglob('*.py') if '__pycache__' not in str(f)))"
→ 128626 bytes (~125.6 KB)
```

| File | Size | Bundle? |
|------|------|---------|
| `stream.py` | 47,119 B | ✅ Bắt buộc (O1 streaming) |
| `selector.py` | 18,923 B | ❌ Loại (optimization, không cần trong bundle) |
| `cli.py` | 16,612 B | ❌ Loại (CLI) |
| `header.py` | 13,439 B | ✅ |
| `__init__.py` | 11,136 B | ✅ inline public API |
| `codec.py` | 10,378 B | ✅ |
| `dict_builder.py` | 9,419 B | ❌ Loại (cần zstd train) |
| `exceptions.py` | 541 B | ✅ |
| **Core bundle** | **~83KB** + `text.py` ~2KB → **~85KB** | Vẫn <500KB dư 5× |
| Tổng `src/revhash` | 128.6KB | — |

**Kết luận:** Bundle `<500KB` khả thi 100% — core 85KB, giữ docstring vẫn <120KB.

### 4.2 Cách gộp 1 file (cắt import vòng)

Dependency graph `src/revhash`:
```
exceptions.py (leaf)
header.py → exceptions
codec.py → exceptions, header.CODEC_TO_ID
stream.py → codec.HAS_*, header, exceptions
__init__.py → codec, header, stream
text.py (new) → __init__.compress
```

**Thứ tự inline để tránh forward ref:**
```python
# revhash_embedded.py
# 1. Header comment + __version__ + docstring
# 2. Stdlib imports (hashlib, struct, zlib, gzip, lzma, io, os, pathlib, tempfile)
# 3. Exceptions (inline exceptions.py:9-22)
# 4. Header (inline header.py:30-303, bỏ from .exceptions)
# 5. Codec (inline codec.py:26-291, local _normalize_codec_id)
# 6. Stream (inline stream.py:24-1095, dùng local HAS_* thay from .codec)
# 7. Public API (inline __init__.py:70-268 + text.py)
# 8. get_available_codecs(), __all__
```

**Kỹ thuật:**
- Cắt `from .codec import HAS_ZSTD` → local `try: import zstandard; HAS_ZSTD=True`.
- Bỏ `from .header import RevHashHeader` → inline định nghĩa.
- Không bundle `cli.py`/`dict_builder.py`/`selector.py`.
- Build script `scripts/build_embedded.py` (~50 dòng) đọc `src/revhash/*.py`, nối theo thứ tự, ghi `revhash_embedded.py` với header `# AUTO-GENERATED — do not edit, source: src/revhash/`, chạy `ruff format`.

**Skeleton đầu file:**
```python
"""
revhash_embedded — single-file bundle (<500KB), copy 1 file là chạy.
AUTO-GENERATED from src/revhash/ — do not edit.
Source hash: sha256:abc123...  Sync: python scripts/build_embedded.py
Usage: import revhash_embedded as revhash; revhash.compress_text("xin chào")
"""
from __future__ import annotations
import hashlib, struct, zlib, gzip, lzma, io, os, pathlib, tempfile
from pathlib import Path
__version__ = "0.2.0-embedded"
__bundle_hash__ = "sha256:..."
__all__ = ["compress","decompress","compress_text","decompress_text","compress_file","decompress_file",
           "compress_stream","decompress_stream","verify","get_info","get_available_codecs",
           "RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError"]
class RevHashError(Exception): ...
```

**Ước size:** Core 85KB + text 2KB + header 1KB → **~88KB**, sau `ruff format` ~95KB, 5× dư so với 500KB.

### 4.3 Handle `zstandard` missing → fallback `gzip`/`store`

Giữ logic `codec.py`/`stream.py` trong bundle:

```python
try:
    import zstandard as _zstd; HAS_ZSTD = True
except Exception: _zstd = None; HAS_ZSTD = False
try:
    import brotli as _brotli; HAS_BROTLI = True
except Exception: _brotli = None; HAS_BROTLI = False

def get_available_codecs() -> dict[str, bool]:
    return {"store": True, "gzip": True, "zstd": HAS_ZSTD, "lzma": True, "brotli": HAS_BROTLI}

def _resolve_codec(codec: str) -> str:
    if codec == "auto":
        avail = get_available_codecs()
        if avail["zstd"]: return "zstd"
        if avail["gzip"]: return "gzip"
        return "store"
    avail = get_available_codecs()
    if not avail.get(codec, False):
        raise RevHashUnsupportedCodecError(f"codec '{codec}' not available. Available: {[k for k,v in avail.items() if v]}. pip install zstandard brotli hoặc dùng codec='auto'/'gzip'")
    return codec
```

- `stream.py:248-346` đã `if codec=="zstd" and not HAS_ZSTD: raise RevHashUnsupportedCodecError` — giữ nguyên.
- **Bug cần fix M3a:** `__init__.py:98-99` hiện `if codec=="auto": codec="zstd"` hardcode, không check `HAS_ZSTD` → sửa thành `_resolve_codec("auto")` (§5.1).
- `gzip`/`zlib` stdlib luôn có, `lzma` cũng stdlib (guard `try: import lzma` cho Alpine minimal).

### 4.4 Lazy deps, `get_available_codecs()`, `__all__` gọn

| Module | Khi import | Cách lazy |
|--------|-----------|-----------|
| `zstandard` | Top-level `try` + inside `compress_stream` branch | `HAS_ZSTD` flag, không crash import |
| `brotli` | Tương tự | `HAS_BROTLI` |
| `lzma` | Top-level `try` (stdlib) | `HAS_LZMA` guard |
| `dict_builder` | Tail `try: from . import dict_builder` (`__init__.py:274-281`) | Đã lazy, bundle bỏ luôn |
| `algorithms.selector` | Tail lazy | Bundle bỏ |

`get_available_codecs()` dùng cached `HAS_*` flags (không `find_spec` mỗi lần), không side-effect. `__all__` chỉ 15 entries, không export `dict_builder` trong bundle.

### 4.5 `sha256` bundle verify drift & sync với `src/revhash`

**Vấn đề drift:** Bundle và `src/revhash/` là 2 copy, sửa `header.py` quên rebuild → drift.

**Giải pháp 3 lớp:**

1. **Embed hash trong bundle:**
   ```python
   __bundle_hash__ = "sha256:4f8a..."  # hash của src/revhash/*.py core lúc build
   ```
2. **Build script tính hash:**
   ```python
   # scripts/build_embedded.py
   import hashlib, pathlib
   src_dir = pathlib.Path("src/revhash")
   h = hashlib.sha256()
   for name in sorted(["exceptions.py","header.py","codec.py","stream.py","text.py"]):
       h.update((src_dir/name).read_bytes())
   bundle_hash = h.hexdigest()  # ghi vào __bundle_hash__ và reports/bundle_hash.txt
   ```
3. **Verifier parity byte-identical:**
   ```python
   # tests/test_embedded.py
   import revhash, revhash_embedded
   def test_parity():
       data = b"hello world"*1000
       assert revhash.compress(data) == revhash_embedded.compress(data)
   def test_hash(): assert revhash_embedded.__bundle_hash__.startswith("sha256:")
   ```

**CI:** `python scripts/build_embedded.py --check` fail nếu bundle cũ hơn `src`. Mỗi khi `src/revhash/*.py` đổi, chạy rebuild trước commit (Coordinator enforce M4).

### 4.6 Import side-effect tối thiểu & vendored

**Checklist:**
- [ ] Không `open()`/`os.environ`/`print` ở top-level
- [ ] Chỉ `try: import zstandard` / `brotli` là side-effect cho phép, đã guard
- [ ] Verify `python -c "import revhash_embedded"` chạy khi `zstandard` missing (mock `sys.modules`)

**Vendored usage (cả 3 byte-identical):**
```bash
cp revhash_embedded.py myproject/              # M2 single-file: import revhash_embedded as revhash
cp -r src/revhash myproject/vendor/revhash     # M1 vendored: sys.path.insert(0,"vendor"); import revhash
pip install -e .                               # M0 pip: import revhash
```

---

## 5. Khuyến nghị cho M3a/M3b — Checklist với file:line hint

### 5.1 Core Embed Builder (owns `revhash_embedded.py`, `src/revhash/__init__.py` patch, `src/revhash/text.py`)

> Inputs: `docs/research_embedded.md` + `src/revhash/*` v0.1 — Outputs: `revhash_embedded.py`, `src/revhash/__init__.py` (patch), `src/revhash/text.py`

**Checklist M3a:**

- [ ] **Tạo `src/revhash/text.py` (~80 dòng)** — `compress_text`/`decompress_text` wrapper:
  ```python
  from __future__ import annotations
  from . import compress as _compress, decompress as _decompress
  def compress_text(text: str, codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None, encoding="utf-8") -> bytes:
      if not isinstance(text, str): raise TypeError(f"text must be str, got {type(text).__name__}")
      return _compress(text.encode(encoding, "strict"), codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
  def decompress_text(blob: bytes, dict_data=None, encoding="utf-8") -> str:
      if not isinstance(blob, (bytes,bytearray,memoryview)): raise TypeError("blob must be bytes")
      return _decompress(blob, dict_data=dict_data).decode(encoding, "strict")
  ```
  Tránh circular: `__init__.py` import `text.py` ở **tail** sau khi `compress` defined, như `dict_builder` lazy `__init__.py:274-281`.

- [ ] **Patch `src/revhash/__init__.py`:**
  - `47-65` `__all__` thêm `"compress_text"`, `"decompress_text"`, `"get_available_codecs"`
  - `70-93` `compress()` thêm `encoding="utf-8"` + `if isinstance(data,str): data=data.encode(encoding,"strict")` trước `isinstance(bytes)` check
  - `94-99` `codec=="auto"` sửa thành `_resolve_codec("auto")` (fallback thực sự, không hardcode `zstd`)
  - `274-281` tail thêm `try: from . import text; from .text import compress_text, decompress_text` guard
  - Thêm `get_available_codecs()` delegate `from .codec import HAS_ZSTD, HAS_BROTLI`

- [ ] **Tạo `scripts/build_embedded.py`** — inline theo §4.2, test `python scripts/build_embedded.py && python -c "import revhash_embedded; print(revhash_embedded.__version__)"` PASS khi thiếu `zstandard`.

- [ ] **Build `revhash_embedded.py`** — verify `<500KB` (`Path("revhash_embedded.py").stat().st_size < 512000`), `__bundle_hash__`, import không crash khi `HAS_ZSTD=False`.

- [ ] **Test local:** `pytest tests/test_embedded.py -q` parity 10 cases byte-identical.

**File:line hints:**

| File | Dòng | Việc |
|------|------|------|
| `src/revhash/__init__.py:23-30` | imports | Thêm `from .codec import HAS_ZSTD, HAS_BROTLI` |
| `src/revhash/__init__.py:47-65` | `__all__` | Thêm 3 entries |
| `src/revhash/__init__.py:70-99` | `compress()` | `str` handling + `encoding` + fix `auto` fallback |
| `src/revhash/__init__.py:270-281` | tail | Thêm `text` import block |
| `src/revhash/codec.py:26-42` | `HAS_*` | Thêm `HAS_LZMA` guard + `get_available_codecs()` |
| `src/revhash/header.py:13-23` | constants | Không sửa, bundle copy |
| `src/revhash/exceptions.py:9-22` | hierarchy | Không sửa |

### 5.2 API DX Builder (owns `stream.py` patch, `examples/*`)

> Inputs: `docs/research_embedded.md` + Core interfaces — Outputs: `stream.py` patch, `examples/embed_demo.py`, `examples/file_text_demo.py`

**Checklist M3b:**

- [ ] **Review `src/revhash/text.py`** — ensure `compress_text` TypeError khi `bytes`, `decompress_text` strict decode, docstring ví dụ copy-paste.

- [ ] **Patch `src/revhash/stream.py:1006-1087` `compress_file`/`decompress_file`** — thêm `mkdir` cho output:
  ```python
  src_path = pathlib.Path(src_path); dst_path = pathlib.Path(dst_path)
  if not src_path.exists(): raise FileNotFoundError(f"source not found: {src_path}")
  if src_path.is_dir(): raise IsADirectoryError(f"source is directory: {src_path}")
  dst_path.parent.mkdir(parents=True, exist_ok=True)  # MỚI chỉ cho dst
  if isinstance(dict_data, (str, os.PathLike)) and pathlib.Path(dict_data).exists():
      dict_data = pathlib.Path(dict_data).read_bytes()
  ```
  Test: `compress_file("a.txt","out/nested/deep/b.rvh")` với `out/nested/deep/` chưa tồn tại → PASS.

- [ ] **Tạo `examples/embed_demo.py`** — copy-1-file demo (dùng `revhash_embedded`):
  ```python
  import revhash_embedded as revhash
  from pathlib import Path
  assert revhash.decompress_text(revhash.compress_text("xin chào 🌍")) == "xin chào 🌍"
  Path("tmp_demo.txt").write_text("hello\n"*100, encoding="utf-8")
  revhash.compress_file("tmp_demo.txt", "tmp_demo.rvh")
  revhash.decompress_file("tmp_demo.rvh", "tmp_demo_restored.txt")
  assert Path("tmp_demo_restored.txt").read_text() == Path("tmp_demo.txt").read_text()
  print("embed_demo PASS", revhash.get_available_codecs())
  ```

- [ ] **Tạo `examples/file_text_demo.py`** — 5 demos từ §3.4 (`demo_text`, `demo_bytes`, `demo_file`, `demo_fallback`, `demo_bundle`).

- [ ] **Test DX:** `pytest tests/test_text_file.py -k test_mkdir -k test_utf8` — emoji/tiếng Việt roundtrip, `compress(123)` TypeError, `decompress_text` strict error.

**File:line hints:**

| File | Dòng | Việc |
|------|------|------|
| `src/revhash/stream.py:1029-1037` | `compress_file` | Thêm `dst.parent.mkdir(parents=True, exist_ok=True)` + `IsADirectoryError` |
| `src/revhash/stream.py:1067-1083` | `decompress_file` | Tương tự |
| `examples/embed_demo.py` | new | Copy-1-file demo với `revhash_embedded` |
| `examples/file_text_demo.py` | new | 5 demos §3.4 |

### 5.3 Rủi ro chung

| Rủi ro | Mitigation | Owner |
|--------|------------|-------|
| Bundle drift | `build_embedded.py --check` + `__bundle_hash__` + parity 10 cases | Core+Verifier |
| `str` vs `bytes` silent loss | `utf-8` strict + test emoji/tiếng Việt | API+Verifier |
| `Path` mkdir side-effect | Chỉ mkdir `dst`, không `src` | API+Critic |
| Over-engineering | Enforce 4 hàm chính, không `compress_path` alias | Coordinator |
| Fallback ratio kém | `get_available_codecs()` + docs | Core+API |

---

## 6. Tài liệu tham khảo

1. bottle.py — https://github.com/bottlepy/bottle (single-file 4500 LOC)
2. pip vendoring — https://github.com/pypa/pip/tree/main/src/pip/_vendor + https://pip.pypa.io/en/stable/development/vendoring/
3. requests vendored urllib3 — https://github.com/psf/requests
4. python-zstandard — https://github.com/indygreg/python-zstandard
5. importlib.find_spec — https://docs.python.org/3/library/importlib.html#checking-if-a-module-can-be-imported
6. zipapp (PEP 441) — https://docs.python.org/3/library/zipapp.html
7. shiv — https://github.com/linkedin/shiv
8. pandas `_optional.py` — https://github.com/pandas-dev/pandas/blob/main/pandas/compat/_optional.py
9. pathlib.Path — https://docs.python.org/3/library/pathlib.html
10. `docs/research.md` (409 dòng) + `docs/api.md` (260 dòng) — baseline v0.1 streaming 0% overhead
11. `src/revhash/__init__.py:70-148` — `compress()` via `BytesIO` + auto-store
12. `src/revhash/codec.py:26-42` — `HAS_ZSTD`/`HAS_BROTLI` flags
13. `src/revhash/stream.py:248-346` — `stream_writer` single-frame O(1)
14. `src/revhash/header.py:30-45` — `HEADER_MAGIC`, `HEADER_SIZE=23`
15. `TEAM_PLAN_EMBEDDED.md` — Team Sheet frozen M0 approved 2026-08-26

---

## 7. Phụ lục — Số liệu

### A. Kích thước `src/revhash` (thực đo 2026-08-27, `__pycache__` excluded)

```
Total .py: 128626 bytes (125.6 KB)
stream.py 47119 | selector.py 18923 (không bundle) | cli.py 16612 (không bundle)
header.py 13439 | __init__.py 11136 | codec.py 10378 | dict_builder.py 9419 (không bundle)
exceptions.py 541 | algorithms/__init__.py 1059 (không bundle)
→ Core bundle (stream+header+codec+exceptions+__init__+text): ~85KB <500KB ✅ (dư 5×)
Header 23B + footer 4*Nc+36 (100MB/4M → Nc=25 → footer 136B, docs/api.md §3.1)
```

### B. Migration v0.1 → v0.2 (không break)

```python
# v0.1 vẫn chạy:
blob = revhash.compress(b"hello world"*1000)
revhash.compress_file("in.txt", "out.rvh")
# v0.2 thêm:
revhash.compress_text("xin chào")              # NEW str
revhash.compress("xin chào")                   # NEW polymorphic
revhash.compress_file("in.txt", "out/nested/out.rvh")  # NEW tự mkdir
revhash.get_available_codecs()                 # NEW
```

### C. Decision Log

- 2026-08-27: Chọn **Hybrid A3** (`compress_text` explicit + `compress` polymorphic) — justify prior-art `Pillow`/`pandas` hybrid + backward compat.
- 2026-08-27: Loại `compress_path` alias (YAGNI, Coordinator enforce 4 hàm chính).
- 2026-08-27: Bundle inline thứ tự dependency, `scripts/build_embedded.py` + `__bundle_hash__` verify drift.
- 2026-08-27: `codec="auto"` fix bug `__init__.py:98` hardcode `zstd` → `_resolve_codec("auto")` fallback thực sự.

---

*— Researcher / Explorer — Embedded, Team revhash v0.2-embedded — 2026-08-27*
*Size thực đo 128626 bytes (không `__pycache__`), bundle core ~85KB <500KB. ≥4 pattern có bảng so sánh + link, API có snippet copy-paste, bundle strategy khả thi.*
