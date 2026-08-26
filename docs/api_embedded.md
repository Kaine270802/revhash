# revhash Embedded API Spec — Design Freeze v0.2 (M2)

> **Version:** 0.3.0-awesome (Design Freeze 2026-08-27, sync v0.3 polish — không đổi logic, chỉ bump version)
> **Owner:** Coordinator (dựa trên `docs/research_embedded.md` §3-4)
> **Mục tiêu:** Freeze contract cho M3a (Core Embed) + M3b (API DX) song song — **thư viện nhúng** file + text trực tiếp, single-file bundle, zero-deps graceful. Không break v0.1.

---

## 1. Tổng quan

v0.2 là **pivot nhúng** từ v0.1-rc unlimited streaming. Giữ nguyên core O1 streaming + header `RVH1`/`RVHE` + 5 codecs, thêm:

- **Nhúng 1 file:** `revhash_embedded.py` (<500KB) + `get_available_codecs()` + graceful fallback.
- **Thống nhất text+file:** `compress(bytes|str)` polymorphic + `compress_text(str)` explicit strict, `compress_file(str|Path)` tự `mkdir(parents=True)`.
- **Không break v0.1:** `compress(b"...")`, `decompress`, `compress_file`, `stream` giữ nguyên signature.

---

## 2. Public API — Frozen cho v0.2

### 2.1 Core bytes (mở rộng `docs/api.md` §2)

```python
import revhash

# Polymorphic: nhận cả bytes|str (NEW encoding param)
blob: bytes = revhash.compress(
    data: bytes | str,
    codec: str = "zstd",  # "zstd"|"gzip"|"lzma"|"brotli"|"store"|"auto" (auto fallback)
    level: int = 3,
    chunk_size: int = 4*1024*1024,
    dict_data: bytes | None = None,
    encoding: str = "utf-8",  # NEW — chỉ khi data là str
) -> bytes

# Khi data là str → data.encode(encoding, "strict") trước khi nén (raise UnicodeEncodeError)
# Khi data là bytes|bytearray|memoryview → pass-through raw (không encode)

orig: bytes = revhash.decompress(blob: bytes, dict_data: bytes | None = None) -> bytes
# Giữ nguyên v0.1, trả bytes (caller tự .decode nếu cần)

# NEW — explicit text API (strict)
blob2: bytes = revhash.compress_text(
    text: str,  # bắt buộc str, nếu truyền bytes → TypeError
    codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None, encoding="utf-8"
) -> bytes

text: str = revhash.decompress_text(
    blob: bytes, dict_data=None, encoding="utf-8"
) -> str  # = decompress(blob).decode(encoding, "strict") → raise UnicodeDecodeError nếu blob không phải utf-8 text

# NEW — codec introspection
codecs: dict[str, bool] = revhash.get_available_codecs()
# -> {"store": True, "gzip": True, "zstd": bool, "lzma": True, "brotli": bool}
# Dùng HAS_ZSTD/HAS_BROTLI/HAS_LZMA lazy flags

# Giữ nguyên
info: dict = revhash.get_info(blob)
ok: bool = revhash.verify(blob)
```

**Contract:**
- `compress(b"hello") == compress("hello")` và `compress("hello".encode())` byte-identical.
- `compress_text(b"oops")` → `TypeError`, `decompress_text(b"\xff\xfe blob")` với text nonsense → `UnicodeDecodeError` (strict), không `replace`.
- `codec="auto"` → `_resolve_codec("auto")`: nếu `zstd` available → `zstd`, else `gzip`, else `store` (không hardcode `zstd` như v0.1 `__init__.py:98` bug).
- `__all__` v0.2 gọn 15: `["__version__","compress","decompress","compress_text","decompress_text","compress_file","decompress_file","compress_stream","decompress_stream","verify","get_info","get_available_codecs","RevHashError","RevHashCorruptedError","RevHashDictError","RevHashUnsupportedCodecError"]`

### 2.2 File (patch `stream.py:1006` — tự mkdir)

```python
info: dict = revhash.compress_file(
    src: str | Path,
    dst: str | Path,
    codec="zstd", level=3, chunk_size=4*1024*1024,
    dict_data: bytes | str | Path | None = None,  # NEW: nếu là str/Path tồn tại → load bytes
) -> dict

info = revhash.decompress_file(src: str | Path, dst: str | Path, dict_data=...) -> dict
```

**Contract patch:**
- `src` phải tồn tại, nếu `src.is_dir()` → `IsADirectoryError`
- `dst.parent.mkdir(parents=True, exist_ok=True)` **chỉ cho output** (trước `open(dst,"wb")`), không cho `src`.
- `dict_data` nếu là `str|Path` và `Path(dict_data).exists()` → `read_bytes()`.

**Giữ nguyên:** `compress_stream(reader: BinaryIO, writer: BinaryIO, ...)` / `decompress_stream` — không đổi.

### 2.3 Single-file bundle contract

- **File:** `revhash_embedded.py` ở **root** (`D:\data optimization\revhash_embedded.py`), `<500KB` (`stat <512000`), `__version__ = "0.2.0-embedded"`, `__bundle_hash__ = "sha256:..."` (hash của `src/revhash/*.py` core lúc build).
- **Cách dùng embedded (3 mức đều byte-identical):**
  ```python
  # M0 pip
  import revhash; revhash.compress_text("xin chào")
  # M1 vendored
  # cp -r src/revhash ./myproject/vendor/; sys.path.insert(0,"vendor"); import revhash
  # M2 single-file (PRIMARY)
  # cp revhash_embedded.py ./myproject/; import revhash_embedded as revhash; revhash.compress_text("xin chào")
  ```
- **Build script:** `scripts/build_embedded.py` (~50 dòng) inline theo thứ tự `exceptions→header→codec→stream→text`, header `# AUTO-GENERATED — do not edit`, chạy `python scripts/build_embedded.py` để rebuild, `python scripts/build_embedded.py --check` fail nếu drift.
- **Zero-deps:** Bundle top-level `try: import zstandard; HAS_ZSTD=True except: HAS_ZSTD=False` tương tự `codec.py:26`. Khi thiếu, `import revhash_embedded` vẫn OK, `get_available_codecs()["zstd"]==False`, `compress(..., codec="zstd") → RevHashUnsupportedCodecError`, `codec="auto" → fallback`.
- **Không bundle:** `cli.py`, `dict_builder.py`, `algorithms/selector.py` (chỉ core).

---

## 3. Module Layout — Frozen cho M3a/M3b

```
D:\data optimization\
├── revhash_embedded.py          # NEW M3a — single-file bundle <500KB
├── scripts/build_embedded.py    # NEW M3a — inline builder + --check
├── src/revhash/
│   ├── __init__.py              # PATCH M3a — thêm compress_text/decompress_text/get_available_codecs, fix auto fallback, tail import text
│   ├── text.py                  # NEW M3a — compress_text/decompress_text (~80 dòng)
│   ├── codec.py                 # PATCH M3a — thêm HAS_LZMA guard + get_available_codecs() (hoặc keep HAS_ZSTD/BROTLI)
│   ├── stream.py                # PATCH M3b — thêm mkdir(parents=True) cho compress_file/decompress_file
│   ├── header.py                # Giữ v0.1 (không đổi)
│   ├── exceptions.py            # Giữ
│   ├── dict_builder.py          # Giữ
│   └── algorithms/selector.py   # Giữ
├── examples/
│   ├── embed_demo.py            # NEW M3b — demo copy 1 file (5 dòng chính)
│   └── file_text_demo.py        # NEW M3b — 5 demos §3.4 research_embedded
└── tests/
    ├── test_text_file.py        # NEW Verifier — utf-8 strict, mkdir, polymorphic
    └── test_embedded.py         # NEW Verifier — bundle vs pkg parity 10 cases + fallback mock
```

**Ownership:**
- M3a Core Embed owns `revhash_embedded.py`, `scripts/build_embedded.py`, `src/revhash/text.py`, `src/revhash/__init__.py` patch, `src/revhash/codec.py` patch
- M3b API DX owns `src/revhash/stream.py` patch, `examples/*`
- Không overlap: M3a không sửa `stream.py`, M3b không sửa `__init__.py` (tránh conflict)

---

## 4. Chi tiết hành vi — Edge Cases

| Case | compress | decompress_text | compress_file |
|------|----------|-----------------|---------------|
| `str` tiếng Việt emoji `"xin chào 🌍"` | `encode("utf-8","strict")` → bytes | `decompress(...).decode("utf-8","strict")` → str | N/A (file đọc bytes raw, không decode) |
| `bytes` raw `b"\xff\xfe"` | pass-through | nếu blob chứa `b"\xff\xfe"` text thì `decompress_text` → `UnicodeDecodeError` | N/A |
| `compress_text(b"bytes")` | — | — | N/A → `TypeError: text must be str` |
| `compress(123)` | `TypeError` | — | `FileNotFoundError` nếu `src` không tồn tại |
| `src` là folder | — | — | `IsADirectoryError` |
| `dst` parent chưa tồn tại `"out/nested/a.rvh"` | — | — | `mkdir(parents=True, exist_ok=True)` → PASS |
| Thiếu `zstandard` | `codec="auto" → gzip`, `codec="zstd" → Unsupported` | — | Tương tự |
| `dict_data` là path string `"dicts/vi_text.dict"` | Nếu `Path(dict_data).exists()` → `read_bytes()` | — | Tương tự cho `compress_file` |

---

## 5. Performance & Compatibility Contract (cho Verifier)

| Metric | Target |
|--------|--------|
| `compress_text("xin chào")` vs `compress("xin chào")` | byte-identical |
| Bundle vs pkg parity | 10 cases (0B, emoji, 1MB, file) byte-identical + `__bundle_hash__` khớp |
| Fallback mock `HAS_ZSTD=False` | `get_available_codecs()["zstd"]==False`, `compress(auto)→gzip`, `compress(zstd)→Unsupported` |
| `compress_file` mkdir | `out/nested/deep/a.rvh` với parent chưa tồn tại → PASS |
| Không regress | 108 cũ vẫn PASS + 12 mới → 120+ total, ratio/speed không chậm >5% |

---

## 6. Decisions Frozen (từ research)

- **Hybrid A3:** Giữ `compress(bytes|str)` polymorphic + `compress_text(str)` explicit — không break v0.1, DX nhúng tốt (prior-art Pillow/pandas hybrid).
- **Không `compress_path` alias:** YAGNI, chỉ `compress_file` canonical.
- **Bundle inline order:** exceptions→header→codec→stream→text, bỏ `cli`/`dict_builder`/`selector`.
- **Lazy deps:** `HAS_ZSTD/BROTLI` flags + `get_available_codecs()` cached, không `find_spec` mỗi lần.

---

## 7. Handoff cho M3a/M3b

- **M3a:** Tạo `text.py` → patch `__init__.py` (encoding, auto fallback, tail import) → `codec.py` `get_available_codecs` → build `revhash_embedded.py` → test `import revhash_embedded` khi thiếu zstd.
- **M3b:** Review `text.py` → patch `stream.py` mkdir → tạo `examples/embed_demo.py` + `file_text_demo.py` (§3.4 research) → test `mkdir` + `utf-8 strict`.

---

*— Coordinator, Design Freeze 2026-08-27 — Frozen, không đổi sau khi M3a/M3b bắt đầu trừ khi lỗi P0.*
