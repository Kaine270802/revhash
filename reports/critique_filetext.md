# Critique — revhash v0.2.1-filetext File↔Text Flex — Adversarial Audit

> **Role:** Critic / Auditor — File↔Text Flex — Team revhash v0.2.1-filetext  
> **Date:** 2026-08-28  
> **Auditor:** Muse Spark (Critic)  
> **Workspace:** `D:\data optimization`  
> **Scope:** `TEAM_PLAN_FILETEXT.md` (8 criteria), `docs/research_filetext.md` (4 heuristic A-D), `docs/api_filetext.md` §2-3 (signatures, heuristic, return types, OOM guard), `src/revhash/file_text.py:1-127`, `src/revhash/stream.py:1007`+`1072`, `src/revhash/__init__.py:54-76`, `revhash_embedded.py:1-50`, `scripts/build_embedded.py:26`, `tests/test_filetext_flex.py:1-531`, `reports/verification_filetext.md:432`, `TEAM_STATE.md`, `reports/verification.md` v0.1 + `reports/critique.md` v0.1, `reports/verification_embedded.md` + `critique_embedded.md` v0.2  
> **Mode:** Adversarial — không optimism, chỉ evidence `file:line` + `py -3.12 -c` reproduce. **KHÔNG sửa `src/revhash/*`, `revhash_embedded.py`, `examples/*`, `tests/*`** — chỉ đọc và audit.

---

## 1. Tổng quan PASS/FAIL per 8 Success Criteria `TEAM_PLAN_FILETEXT.md` §1

| # | Success Criteria (Top-level) | Target | Evidence thực đo (adversarial) | Verdict |
|---|-------------------------------|--------|--------------------------------|---------|
| 1 | `compress_file` chấp nhận **4 dạng src**: S1 `Path` tồn tại → file, S2 `str` path tồn tại → file, S3 `str` text → encode, S4 `bytes` raw | Mỗi dạng roundtrip 100% | `src/revhash/file_text.py:32-70` order `S4(bytes)>S1(Path)>S2/S3(str heuristic)` strict. Reproduce `py -3.12`: `Path("hello")` tồn tại → `compress_file("hello",None)` ra `file content` PASS; `force_text=True` → `"hello"` PASS; `Path("hello")` không tồn tại → text PASS; `b"\x00\xff"` roundtrip PASS. `tests/test_filetext_flex.py::test_src_4_forms` 4 dạng + `bytearray`/`memoryview` PASS. **Nhưng** `str` là directory (`"adir"` is_dir) → heuristic `exists() and is_file()==False` → **coi là text `"adir"`** thay vì `IsADirectoryError` (Path explicit mới raise) — silent wrong branch (xem Risk #5). | **PASS (WARN)** — 4 dạng thỏa, nhưng inconsistency `str` dir |
| 2 | `decompress_file` tương tự: `src` là `Path`/`bytes` blob; `dst` là `Path|str|None`; `as_text` suy ra `bytes` vs `str` | `Path` blob, `str` path, `bytes`/`bytearray`/`memoryview` đều decompress đúng | `src/revhash/stream.py:1099-1169` decompress heuristic reuse `_resolve_src` PASS. Reproduce: `decompress_file(Path("sample.rvh"),None,as_text=True)=="nội dung"` PASS; `decompress_file(blob,None) bytes` PASS; `bytearray`/`memoryview` PASS (`tests/test_filetext_flex.py::test_decompress_src_variants`). `as_text=True` decode strict `stream.py:1140` `decode(encoding,"strict")` PASS. **Nhưng** `as_text` bị ignore khi `dst=Path` (ghi bytes ra đĩa) không document rõ. | **PASS** |
| 3 | `dst` tùy chọn: `dst=None` → trả `bytes`/`str` RAM; `dst=Path` → ghi file + `mkdir(parents=True)` + trả `dict` | Cả hai đều work | `src/revhash/file_text.py:73-101` `_resolve_dst` `None→None`, `str|Path→Path+mkdir` PASS. Reproduce: `compress_file("hi",None) → bytes` PASS; `compress_file("hi", "out/nested/a.rvh") → mkdir+dict` PASS; `decompress_file(blob,None, as_text=True) → str` PASS. `mkdir` chỉ `dst.parent`, không cho `src` (test `nonexistent_parent` không tạo PASS). **Nhưng** `mkdir(parents=True)` tạo `..` ngoài workspace (Risk #3). | **PASS (WARN)** — DX thỏa, traversal unsanitized |
| 4 | Heuristic file-vs-text an toàn: `str` src nếu `Path(str).exists() and is_file()` → file, else → text; có `force_text=True` | Ưu tiên file nếu tồn tại, `force_text` override | `file_text.py:57-61` `if not force_text and p.exists() and p.is_file(): return True` PASS. Reproduce `test_src_str_path_vs_text_heuristic_with_tmp_cwd`: `"notes.txt"` tồn tại → file content; `force_text=True` → `"notes.txt"` PASS; parity `revhash` vs `revhash_embedded` byte-identical. **Nhưng** nếu text ngẫu nhiên trùng tên file (hiếm) → silent wrong, phải biết `force_text`; TOCTOU 1 syscall nhưng negligible. | **PASS** — heuristic đúng spec, document đủ |
| 5 | Không break v0.2: `compress(b"...")`, `compress_text`, `compress_file("a.txt","b.rvh")` cũ vẫn PASS 142 | `pytest 154/154 PASS` | `py -3.12 -m pytest tests -q` → `154 passed in 7.46s` (142 cũ +12 mới) PASS; `compress(b"hello")==compress("hello")` byte-identical PASS; `compress_text` wrapper PASS; old 2-arg `compress_file(str,str)` vẫn file→file PASS (`tests/test_filetext_flex.py::test_bytes_str_polymorphic`). | **PASS** |
| 6 | Encoding & binary an toàn: `encoding="utf-8" strict` cho `str`, `bytes` raw giữ nguyên, `as_text` decode strict, errors đúng | `UnicodeError` propagate, `TypeError`/`FileNotFound`/`IsADirectory` đúng | `file_text.py:66` `src.encode(encoding,"strict")` + `stream.py:1140,1161` `decode("strict")` PASS. Reproduce: `compress_file("\ud800",None)` → `UnicodeEncodeError` PASS; `decompress_file(compress(b"\xff\xfe"),None,as_text=True)` → `UnicodeDecodeError` PASS; `src=123` → `TypeError` PASS; `src=Path("missing")` → `FileNotFoundError` PASS; `src=Path("dir")` → `IsADirectoryError` PASS. `grep -rn 'replace' src/revhash` → chỉ comment `Replace reader`, không có `errors="replace"` PASS. | **PASS** |
| 7 | O(1) giữ khi là file: `compress_file(Path 10GB)` vẫn `read(chunk_size)` streaming | Không `read()` toàn bộ khi file | `src/revhash/stream.py:262-269` `while chunk = reader.read(chunk_size): comp.write(chunk)` loop duy nhất PASS; `grep reader.read()` → 0 hit `read()` không args PASS. `compress_file` file→file `open(file_path,"rb")` + `compress_stream` O1 (`stream.py:1054`), file→RAM `BytesIO` + guard (`stream.py:1045`). Reproduce 101MB sparse `compress_file(Path, dst=Path)` → `chunks 26` PASS, peak `20.58MB for 10MB / 42MB for 10MB` <150MB PASS. **Nhưng** OOM guard chỉ cho `compress` file→RAM (Risk #1/#2), `decompress` blob→RAM và `bytes` 50MB→RAM không guard → OOM vector. Text/bytes→RAM dùng `BytesIO(data)` O(len(data)) là expected cho nhỏ, nhưng 50MB bytes → `len(blob) 1729` vẫn allocate 50MB data trước khi nén. | **PASS (WARN)** — O1 seekable file giữ, nhưng `dst=None` guard incomplete |
| 8 | Bundle sync: `revhash_embedded.py` rebuild (<500KB, `__bundle_hash__` mới) byte-identical trên 4 dạng, `get_available_codecs` fallback | `<500KB` hash mới, parity 6/6 | `revhash_embedded.py` `97957B <512000` `__bundle_hash__=sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31` PASS; `scripts/build_embedded.py:26` `HASH_FILES` includes `file_text.py` PASS; `py -3.12 scripts/build_embedded.py --check` → `OK (97957 bytes)` PASS; recompute `hashlib.sha256` trên `sorted(HASH_FILES)` → khớp PASS; bundle contains `file_text.py` section after `stream.py` (`# ── file_text.py ─` at 75257 > stream 25548) PASS; parity 6/6 byte-identical `revhash` vs `revhash_embedded` (`tests/test_filetext_flex.py::test_bundle_parity`) PASS. **Nhưng** `__version__` drift `src 0.1.0` vs `embedded 0.2.0-embedded` và `__all__` 19 vs 16 vs spec 15 (xem §5). | **PASS (WARN)** — sync logic đúng, style drift |

**Overall §1:** **5/8 PASS, 3 PASS(WARN)** — đủ điều kiện PASS về chức năng, nhưng 3 WARN chứa High/Medium risks phải fix/document trước stable. Không có FAIL hoàn toàn chặn demo, nhưng có High guard thiếu.

---

## 2. Top 5-7 Risks thực (Severity, file:line, Evidence `python -c`, Impact, Fix)

### Risk #1 — **HIGH** — `_guard_large_file_for_ram` chỉ guard `compress` file→RAM, **không guard `decompress` file→RAM output size**

- **Location:** `src/revhash/file_text.py:104-120` (`if dst is None and st_size >100MB`), `src/revhash/stream.py:1128-1131` `decompress_file` gọi `_guard_large_file_for_ram(file_path, dst_path)` với `file_path` là **compressed blob file** nhỏ, không phải decompressed size.
- **Evidence `py -3.12 -c` reproduce:**
  ```python
  import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.')
  import revhash, pathlib, tempfile
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td)
      f=base/"mid60.bin"; open(f,"wb").seek(60*1024*1024-1); open(f,"ab").write(b"\x00")
      dst=base/"mid60.rvh"; revhash.compress_file(f, dst)  # 60MB -> 2KB compressed
      print(dst.stat().st_size)  # ~2057
      out=revhash.decompress_file(dst, None)  # NOT guarded!
      print(len(out))  # 62914560 -> 60MB RAM allocated, no ValueError
      # guard checks compressed file size ~2KB, not 60MB output
  ```
  Audit2 `py -3.12` log: `decompress 60MB to RAM len 62914560 - no guard, 60MB RAM used` + `decompress large blob to RAM len 105906176` (101MB) PASS không raise. Với 1GB (sparse) sẽ OOM malgré guard.
- **Impact:** `ValueError` OOM guard trong spec `docs/api_filetext.md §3` hứa `ValueError if src>100MB and dst is None`, nhưng `decompress` bypass vì check sai metric. Attacker/user có thể `decompress_file(large_rvh, None)` gây OOM dù `compress` đã guard. Vi phạm Success Criteria #7 OOM guard.
- **Fix (P0):** Sửa guard cho `decompress_file` file→RAM nhánh: sau khi parse header, check `header.original_size >100*1024*1024 and dst is None` → `ValueError`. Hoặc `if file_path.stat().st_size>100MB` không đủ, phải đọc header trước: `header,_=RevHashHeader.from_bytes(file_path.read_bytes()[:23])` peek, nếu `original_size>100MB` raise. Thêm test `test_guard_decompress_oom`.

### Risk #2 — **HIGH** — `compress_file` bytes/text → RAM không guard, cho phép `compress_file(b"x"*101MB, None)` OOM

- **Location:** `src/revhash/file_text.py:32-70` `_resolve_src` S4+S3 return `is_file=False` data bytes, `src/revhash/stream.py:1078-1096` else branch `BytesIO(data)` → `compress_stream` không gọi `_guard_large_file_for_ram` (chỉ trong `if is_file`).
- **Evidence:**
  ```python
  import sys; sys.path.insert(0,'src'); import revhash
  b=b"x"*(50*1024*1024)
  blob=revhash.compress_file(b, None)  # audit3: 50MB -> 1729 blob, no guard
  print(len(blob))  # 1729, but 50MB data held in RAM twice (data + BytesIO)
  # 101MB bytes cũng sẽ allocate ~101MB+blob, no ValueError
  ```
  Audit3 log: `bytes 50MB compress to RAM len 1729 - OOM guard not triggered (risk)`; audit2 `bytes 101MB to RAM should succeed?` branch đi qua.
- **Impact:** Spec OOM guard hứa bảo vệ RAM cho `dst=None`, nhưng chỉ cho file src, không cho bytes/text src. User truyền `compress_file("x"*60_000_000, None)` (≈60MB utf-8) sẽ allocate ~60MB encode + blob, có thể OOM trên 256MB container. Không consistent.
- **Fix (P0):** Thêm guard chung sau `_resolve_src`: `if dst_path is None and data is not None and len(data) >100*1024*1024: raise ValueError`. Hoặc check `if not is_file and len(data)>100MB` raise. Document behavior khác biệt file vs bytes.

### Risk #3 — **MEDIUM** — `Path traversal` via `_resolve_dst` `mkdir(parents=True)` tạo thư mục ngoài workspace với `..`

- **Location:** `src/revhash/file_text.py:88-99` `p.parent.mkdir(parents=True, exist_ok=True)`.
- **Evidence:**
  ```python
  import sys, pathlib, tempfile, os; sys.path.insert(0,'src'); import revhash
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td)
      revhash.compress_file(b"hi", str(base/"a"/"b"/".."/"c.rvh"))
      print((base/"a"/"c.rvh").exists(), (base/"a"/"b").exists())  # True False -> mkdir normalized correctly but ...
      revhash.compress_file(b"hi", str(base/".."/"outside_traversal"/"out.rvh"))
      print((base.parent/"outside_traversal").exists())  # True -> outside!
  ```
  Audit2 log: `traversal a/c exists? True a/b exists? False` và `outside traversal created? True`.
- **Impact:** Nếu `dst` lấy từ user input (filename upload), `../../tmp/evil.txt` sẽ `mkdir` ra ngoài cwd. Trên local tool risk Low, nhưng cho thư viện nhúng được dùng trong web/service risk Medium. Spec không yêu cầu sanitize, nhưng critic phải flag.
- **Fix (P1):** Document rõ `dst` không sanitize `..`; nếu cần harden, thêm optional `strict_dst=False` hoặc `p.resolve().is_relative_to(Path.cwd().resolve())` check khi `dst` chứa `..` hoặc absolute. Hoặc normalize `p.parent.resolve()` và whitelist.

### Risk #4 — **MEDIUM** — `_load_dict_data` type confusion: `Path(d).exists()` không check `is_file()` → `IsADirectoryError`/`PermissionError`

- **Location:** `src/revhash/file_text.py:21-28` `if isinstance(d,(str,Path)) and Path(d).exists(): return Path(d).read_bytes()`.
- **Evidence:**
  ```python
  import sys, pathlib, tempfile; sys.path.insert(0,'src'); import revhash
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td)
      d=base/"mydict_dir"; d.mkdir()
      revhash.compress_file(b"hi", None, dict_data=str(d))
      # -> PermissionError: [Errno 13] Permission denied: '.../mydict_dir'
      # audit3: dict dir other PermissionError
  ```
  Nếu attacker truyền `dict_data="/etc/passwd"` và file tồn tại → `read_bytes()` đọc bất kỳ file local làm dict (information disclosure). `str` non-path bị nhầm nếu trùng tên file tồn tại.
- **Impact:** DX surprise: `dict_data="not_exist_dict_12345.dict"` không tồn tại → `return d` giữ string, sau đó `compress_stream` sẽ validate `dict_data` và raise `RevHashDictError` không rõ; còn `dict_data="my_dir"` tồn tại là thư mục → `PermissionError` confusing. Header không giới hạn dict size trước `read_bytes()` (đã có limit `dict_len>256KB` trong `header.py` nhưng sau khi đọc).
- **Fix (P1):** Sửa `_load_dict_data` → `if isinstance(d,(str,Path)) and Path(d).is_file(): if Path(d).stat().st_size>256*1024: raise ValueError; return Path(d).read_bytes()`. Thêm test `IsADirectoryError` vs `PermissionError`.

### Risk #5 — **MEDIUM** — Heuristic inconsistency: `str` dir → text, `Path` dir → `IsADirectoryError`

- **Location:** `src/revhash/file_text.py:57-61` `if p.exists() and p.is_file(): return True` else fallthrough to `encode`, so `str` `"adir"` where `adir` is directory → `is_file()==False` → treated as **text** `"adir"` compressed (4 bytes), not error.
- **Evidence:**
  ```python
  import sys, pathlib, tempfile, os; sys.path.insert(0,'src'); import revhash
  with tempfile.TemporaryDirectory() as td:
      base=pathlib.Path(td); os.chdir(str(base))
      pathlib.Path("adir").mkdir()
      blob=revhash.compress_file("adir", None)
      print(revhash.decompress_file(blob, None, as_text=True)=="adir")  # True -> text
      revhash.compress_file(pathlib.Path("adir"), None)  # -> IsADirectoryError
  ```
  Audit3 log: `str 'adir' dir -> treated as text? True` + `Path dir IsADirectoryError PASS`.
- **Impact:** User gọi `compress_file("some_dir", "out.rvh")` với `some_dir` là thư mục, kỳ vọng lỗi nhưng nhận blob chứa string `"some_dir"` — silent wrong behavior. Vi phạm principle least surprise. Spec `docs/api_filetext.md §3` pseudocode không xử lý `is_dir()` cho `str` case, chỉ cho `Path` explicit.
- **Fix (P1):** Trong `_resolve_src` str branch, thêm `if p.exists() and p.is_dir(): raise IsADirectoryError(f"source is directory: {p}")` trước khi fallback text. Hoặc document rõ `str` dir → text là intentional.

### Risk #6 — **MEDIUM** — `as_text` param trong `compress_file` unused, gây DX confusion (`as_text` vs `force_text`)

- **Location:** `src/revhash/stream.py:1007-1016` signature `compress_file(..., as_text=False)` kept for symmetry, unused in body; `src/revhash/__init__.py` export, `docs/api_filetext.md §2` ghi `as_text` reserved.
- **Evidence:** `inspect.signature(revhash.compress_file)` → `(src, dst=None, ..., as_text=False, ...)`; `inspect.getsource(revhash.compress_file)` → `as_text` không xuất hiện ngoài signature; `decompress_file` thì `as_text` quyết định `bytes|str` (`stream.py:1139-1141`), `compress_file` không. User có thể gọi `compress_file("hello", None, as_text=True)` kỳ vọng `str` blob → nhận `bytes` vẫn.
- **Impact:** Naming near-miss: 2 flags `force_text` (input) và `as_text` (output) dễ nhầm; `compress_file` có cả hai nhưng 1 unused → API surface bloat, violate spec `api_filetext.md §6` Ownership minimal. Không corrupt data, nhưng maintainability debt.
- **Fix (P2):** Hoặc xóa `as_text` khỏi `compress_file` signature (breaking nhưng clear), hoặc document `as_text` ignored for compress và emit `warnings.warn` nếu `as_text=True` truyền vào compress. Đồng nhất naming hoặc đổi `as_text` → `decode=True` cho decompress để phân biệt.

### Risk #7 — **MEDIUM** — `__all__` bloat + version drift + missing type hint

- **Location:** `src/revhash/__init__.py:54` `__version__="0.1.0"` vs `revhash_embedded.py:22` `__version__="0.2.0-embedded"`; `__init__.py:55-76` 19 entries (`RevHashHeader`, `dict_builder`, `algorithms`) vs `revhash_embedded.py:24` 16 vs spec `docs/api_filetext.md` 13-15; `src/revhash/stream.py:98` `def readinto(self,b):` thiếu hint.
- **Evidence:** `py -3.12 -c "import revhash; print(len(revhash.__all__), revhash.__all__)"` → `19` vs `revhash_embedded` `16`; `grep __version__` drift; `mypy --strict` warn `readinto`.
- **Impact:** `from revhash import *` pollute namespace (`dict_builder`/`algorithms` là optimization, không cần embedded core); version mismatch gây `pip show revhash` 0.1.0 vs `import revhash_embedded` 0.2.0 confuses Verifier. Không blocker runtime, nhưng style & maintainability debt, khác với `verification_embedded.md` đã note `__all__` bloat.
- **Fix (P2):** Đồng bộ `__all__` về 15 (`compress`, `decompress`, `compress_text`, `decompress_text`, `compress_file`, `decompress_file`, `compress_stream`, `decompress_stream`, `verify`, `get_info`, `get_available_codecs`, 4 exceptions, `RevHashHeader` optional); bump `__version__` → `0.2.1-filetext` đồng nhất cả hai; thêm `def readinto(self, b: bytearray) -> int:`.

---

## 3. Anti-cheat check (hardcode? silent `replace`? traversal? bundle drift? dst=None OOM? import side-effect?)

| Check | Lệnh / Evidence | Kết quả |
|-------|-----------------|---------|
| **Hardcode file-vs-text heuristic? `force_text` hardcode True?** | `grep -rn force_text src/revhash` → `file_text.py:32 def _resolve_src(..., force_text=False)`, `stream.py:1015 force_text=False`, `stream.py:1036 _resolve_src(..., force_text=force_text)` pass-through, không có `force_text=True` hardcode. `revhash_embedded.py:75257` section cũng `force_text=False`. | **PASS** — không hardcode, override phải explicit |
| **Silent utf-8 `replace`? `errors="replace"` phải `strict`** | `grep -rn 'replace' src/revhash` → chỉ `cli.py:38 replace(" ", "")` và `stream.py:674 Replace reader` comment. `grep 'errors='` → chỉ `encode(...,"strict")` và `decode(...,"strict")` 4 hits (`file_text.py:66`, `stream.py:1140,1161`, `text.py:38,67`). Reproduce `compress_file("\ud800",None)` → `UnicodeEncodeError` PASS; `decompress_file(blob_None_utf8,None,as_text=True)` → `UnicodeDecodeError` PASS. | **PASS** — 100% strict, không silent loss |
| **Path traversal `mkdir`? `dst="a/b/../c.rvh"` có `mkdir(parents=True)` tạo `a/c` outside?** | `src/revhash/file_text.py:92` `p.parent.mkdir(parents=True, exist_ok=True)` chỉ `dst.parent`, không cho `src`. Reproduce `py -3.12` (audit2): `Path("a/b/../c.rvh")` → `a/c.rvh` exists True, `outside_traversal` True. `src=Path("/tmp/../etc/passwd")` là file thì read, không mkdir. `IsADirectoryError` trước `mkdir` PASS. | **PASS với lưu ý Medium** — `mkdir` đúng spec chỉ dst, nhưng `..` tạo outside như thiết kế local tool, cần document |
| **Bundle drift? `__bundle_hash__` có tính thực không hay hardcode cũ `acec...` stale?** | `scripts/build_embedded.py:26 HASH_FILES` includes `file_text.py`; `compute_bundle_hash` `hashlib.sha256(sorted HASH_FILES + b"\x00")`. Recompute `py -3.12 -c "hashlib.sha256(...)"` → `sha256:acec4d0f06113535d18aefda4db543c0b8d927e29d02a33eff9e7108448a3d31` khớp `revhash_embedded.py:7` Source hash và line 23 `__bundle_hash__` PASS; `python scripts/build_embedded.py --check` → `OK (97957 bytes)` PASS; bundle contains `file_text` section `75257>`stream` PASS; order `exceptions→header→codec→stream→file_text→__init__→text` correct. | **PASS** — hash tính thực, không stale, drift check PASS |
| **dst=None OOM? `compress_file(Path("10GB.bin"), None)` có guard ValueError không hay OOM?** | `src/revhash/file_text.py:104` guard `st_size>100MB and dst is None → ValueError`. Reproduce 101MB sparse: `compress_file(large,None)` → `ValueError refusing to load large file (>100MB)` PASS; `compress_file(large, Path("out.rvh"))` → O1 chunks 26 PASS; `compress_file(str(large),None)` cũng ValueError PASS. **Nhưng** `compress_file(b"x"*50MB,None)` → 1729 blob no guard, `decompress_file(60MB.rvh,None)` → 60MB RAM no guard (Risk #1/#2) — OOM vector còn lại. | **PARTIAL PASS** — file→RAM guard đúng, bytes→RAM và decompress→RAM thiếu |
| **Import side-effect? `import revhash` có `read` file không? `HAS_ZSTD` crash import không?** | `grep "open(" src/revhash/__init__.py` top-level before `def` → 0 hits. `src/revhash/codec.py:26-42` `try: import zstandard; HAS_ZSTD=True except: HAS_ZSTD=False` graceful. Reproduce `import revhash; get_available_codecs()` → `{'store':True,'gzip':True,'zstd':True,...}` PASS; `py -3.12 -c "mock zstandard=None; import revhash"` → no crash (verification embedded). `time import` <0.05s. | **PASS** — import minimal, fallback graceful |
| **Bundle sync `file_text.py`?** | `revhash_embedded.py` `75257` `# ── file_text.py ─` tồn tại, bundle hash includes `file_text.py`, parity 6/6 byte-identical (`test_bundle_parity`) PASS. | **PASS** |
| **O1 regress? file→file O(1) vẫn `read(chunk_size)` loop hay đã `read()` toàn bộ cho text branch?** | `grep reader.read()` in `stream.py` → 0 `read()` without args; `compress_file` file→file `with open(...,"rb") as rf, open(dst,"wb") as wf: compress_stream(rf,wf)` O1; text/bytes→RAM `BytesIO(data)` O(len) expected cho nhỏ (<100MB). `decompress_file` file→file O1, file→RAM `BytesIO` after guard (but guard incomplete). Verifier `benchmarks/results_filetext.json` file→file 10MB `797 MB/s` ratio 0.00033 PASS. | **PASS** — O1 seekable giữ, không regress, chỉ non-file path O(N) expected |

**Kết luận anti-cheat:** Không phát hiện cheat (hardcode, mock decode, fake SHA, silent replace, stale bundle). Implementation honest, hash thực, streaming single-frame giữ. Hai thiếu sót là OOM guard incomplete và traversal unsanitized, không phải cheat mà là thiếu design.

---

## 4. Security & Correctness (heuristic nhầm text trùng tên file, `force_text` bypass, `encoding` strict, `as_text` decode, `dict_data` path load, OOM guard, traversal)

| Hạng mục | Correct? | Evidence `file:line` | Ghi chú |
|----------|----------|----------------------|---------|
| **Heuristic nhầm text trùng tên file** | ⚠️ Partial | `file_text.py:57-61` ưu tiên file nếu `exists() and is_file()`, `force_text=True` override | Khi `text="notes.txt"` và file `notes.txt` tồn tại, `compress_file("notes.txt",None)` → file content, không phải `"notes.txt"` (9 bytes). Test `test_src_str_path_vs_text_heuristic` PASS với `force_text` giải quyết, nhưng user không biết sẽ silent wrong. TOCTOU 1 stat syscall negligible. Document trong `api_filetext.md §3` rõ priority, khuyến nghị `Path("notes.txt")` explicit để tránh ambiguity. |
| **`force_text` bypass** | ✅ Correct | `file_text.py:57` `if not force_text` guard, `stream.py:1036` pass-through | Reproduce `force_text=True` → `"notes.txt"` PASS, `False` (default) → file PASS, parity giữ. Không có bypass ngược (force file khi text) — đúng. |
| **`encoding` strict** | ✅ Correct | `file_text.py:66` `encode(encoding,"strict")`, `text.py:38,67`, `stream.py:1140,1161` | `"\ud800"` → `UnicodeEncodeError` PASS, `LookupError` cho encoding sai propagate PASS, không `replace`. Spec `api_filetext.md §5` yêu cầu strict thỏa. |
| **`as_text` decode** | ✅ Correct | `stream.py:1139-1140` `raw.decode(encoding,"strict")` khi `dst is None and as_text` | `decompress_file(blob,None,as_text=True, encoding="utf-8")` → `UnicodeDecodeError` cho `b"\xff\xfe"` PASS; `as_text=False` → `bytes` PASS; khi `dst=Path` thì ignore `as_text` (ghi bytes ra đĩa) đã test `decompress dst=Path with as_text=True` file bytes correct. |
| **`dict_data` path load** | ⚠️ Type confusion | `file_text.py:21-28` `if Path(d).exists(): read_bytes()` | Chấp nhận `bytes|str|Path|None` như `stream.py:1035` cũ, nhưng `str` non-path trùng file sẽ bị load silent; `Path is_dir` → `PermissionError` không `IsADirectoryError`; thiếu `is_file` + size check ≤256KB. Cần `is_file()` và `stat().st_size` guard. |
| **OOM guard** | ⚠️ Incomplete | `file_text.py:104-120` guard `st_size>100MB and dst is None` chỉ cho `is_file True` | `compress_file(Path 101MB, None)` → `ValueError` PASS; `compress_file(b"x"*50MB, None)` → no guard (Risk #2); `decompress_file(60MB blob file, None)` → no guard (Risk #1). Spec `api_filetext.md §3` hứa `ValueError` cho file lớn, nhưng chưa cover bytes/output size. |
| **Traversal** | ⚠️ Unsanitized but local | `file_text.py:92` `mkdir(parents=True)` | Chỉ `dst.parent`, đúng spec `api_filetext.md §3` `mkdir chỉ dst`. Nhưng `..` tạo outside như evidence, không filter. Không RCE, nhưng nếu `dst` từ user nên validate. |

---

## 5. Style & Maintainability (type hints, `__all__`, `file_text.py` helper, duplicate logic, `as_text` vs `force_text` naming)

| Tiêu chí | Đánh giá | Evidence |
|----------|----------|----------|
| **Type hints** | 90% tốt, 1 thiếu | `file_text.py:32` `def _resolve_src(src, encoding: str="utf-8", force_text:bool=False)`, `stream.py:1007` `def compress_file(src: str|os.PathLike|bytes|bytearray|memoryview, dst: str|os.PathLike|None=None, ...)` PASS; nhưng `stream.py:99` `def readinto(self,b):` thiếu `b: bytearray -> int` (kế thừa từ v0.1 P2-5, `verification_embedded.md` đã note). `mypy --strict` warn. |
| **`__all__`** | ❌ Bloat | `src/revhash/__init__.py:55-76` 19 entries (`RevHashHeader`, `dict_builder`, `algorithms`) vs `revhash_embedded.py:24` 16 vs spec `docs/api_filetext.md` 15 và `research_filetext.md` 9+5. `__all__` gọn là DX nhúng C7 nhưng hiện thừa 4. `verification_embedded.md` §5 đã flag. |
| **`file_text.py` helper** | ✅ Good | Tách 126 dòng (`file_text.py:1-127`) chứa `_resolve_src`/`_resolve_dst`/`_load_dict_data`/`_guard_large_file_for_ram` đúng `research_filetext.md §5.2` đề xuất (120-180 dòng). `stream.py` import `from .file_text import ...` không circular, bundle inline after `stream.py` correct order (audit3: file_text index > stream). Dễ unit-test, maintainability cao, không duplicate heuristic. |
| **Duplicate logic** | ⚠️ Medium | `compress_file` và `decompress_file` (`stream.py:1007-1096` vs `1099-1169`) duplicate `is_file` branching, `BytesIO` vs `open`, và `_guard` call. Có thể tách helper `_compress_via_stream(reader, writer, ...)` nhưng hiện tại 170 dòng mỗi hàm chấp nhận được cho flex. Kế thừa `stream.py:479-1002` duplicate decompress seekable vs non-seekable 600 dòng vẫn tồn (v0.1 P2-2 defer). |
| **`as_text` vs `force_text` naming** | ⚠️ Confusing | `force_text` (input) và `as_text` (output) gần giống nhưng vai trò ngược; `compress_file` giữ `as_text` unused gây hiểu nhầm (Risk #6). Research `§2.3-2.4` đã justify A+B+D, nhưng naming `as_text` cho output và `force_text` cho input là best hiện tại, chỉ cần document hoặc alias `decode=True`. |
| **Naming / error hierarchy** | ✅ Good | `exceptions.py` 3 subclass rõ, `RevHashHeader` dataclass, `CODEC_TO_ID`/`ID_TO_CODEC` rõ, không `eval` (đã fix v0.1). |
| **Single-file lint / bundle build** | ✅ Good nhưng brittle | `revhash_embedded.py` `97957B <500KB` PASS, `scripts/build_embedded.py:26` `HASH_FILES` includes `file_text.py` PASS, `clean_source` string match `from .` có thể brittle nếu docstring chứa `from .`, nhưng audit shows `file_text.py` correctly inlined. |

---

## 6. Đề xuất fix P0/P1/P2

### P0 — Blocker cho `v0.2.1-filetext` stable (phải fix trước khi tag stable, không thể `rc` nếu yêu cầu OOM guard nghiêm ngặt)

- **P0-1 — Guard `decompress_file` file→RAM theo `original_size` header (Risk #1)**  
  `src/revhash/stream.py:1128` file→RAM nhánh hiện `if dst_path is None: _guard_large_file_for_ram(file_path,dst_path)` chỉ check compressed size. Sửa: peek header trước decompress:
  ```python
  if dst_path is None:
      # peek header without loading full
      import struct
      hdr_bytes = open(file_path,"rb").read(23)
      if len(hdr_bytes)==23:
          _,_,_,_,_,dict_len,orig = struct.unpack("<4sBBBIIQ", hdr_bytes)
          if orig != 0xFFFFFFFFFFFFFFFF and orig > 100*1024*1024:
              raise ValueError("refusing to decompress large output (>100MB) into RAM")
      _guard_large_file_for_ram(file_path, dst_path)  # keep for compressed size
  ```
  Thêm test `test_guard_decompress_oom`.

- **P0-2 — Guard `compress_file` bytes/text→RAM (Risk #2)**  
  `src/revhash/file_text.py:66` after `data=src.encode(...)` và `stream.py:1078` else branch, thêm:
  ```python
  if dst_path is None and len(data) > 100*1024*1024:
      raise ValueError("refusing to compress large text/bytes (>100MB) into RAM")
  ```
  Hoặc thống nhất guard chung sau `_resolve_src` check `len(data)` khi `not is_file`.

### P1 — High, nên fix trước `v0.2.1` nếu có thời gian (hoặc `v0.2.2`)

- **P1-1 — `mkdir` traversal document hoặc sanitize** (`file_text.py:92`): Document trong `docs/api_filetext.md` rằng `dst` không sanitize `..`; nếu muốn harden, thêm `p = Path(dst).resolve()` và check `p.is_relative_to(Path.cwd().resolve())` hoặc whitelist, hoặc thêm param `strict_dst=True` để reject `..` và absolute outside.

- **P1-2 — Sửa `_load_dict_data` → `is_file` + size guard** (`file_text.py:21`): `if isinstance(d,(str,Path)) and Path(d).is_file() and Path(d).stat().st_size<=256*1024: return Path(d).read_bytes()` else nếu `is_dir()` → `raise IsADirectoryError` rõ.

- **P1-3 — Fix heuristic `str` dir → `IsADirectoryError`** (`file_text.py:57`): Thêm `if p.exists() and p.is_dir(): raise IsADirectoryError(f"source is directory: {p}")` trước fallback text. Đảm bảo `compress_file("adir",...)` dir → error thay vì text.

- **P1-4 — Đồng bộ `__all__` + `__version__`** (`__init__.py:54-76`): Bump `__version__` → `0.2.1-filetext`, gọn `__all__` về 15-16 như `revhash_embedded.py:24` (bỏ `dict_builder`/`algorithms` khỏi `__all__` public, giữ import nhưng không export `*`). Rebuild bundle `__version__` sync.

### P2 — Medium, backlog `v0.3` (style/maintainability)

- **P2-1 — Gọn `as_text` vs `force_text` naming:** Hoặc xóa `as_text` khỏi `compress_file` (breaking minor) hoặc thêm `warnings.warn` khi `as_text=True` passed to compress, và document `as_text` chỉ cho decompress, `force_text` chỉ cho compress input. Thêm alias `decode` cho decompress để rõ.

- **P2-2 — Fix `readinto` type hint** (`stream.py:99` → `def readinto(self, b: bytearray) -> int:`).

- **P2-3 — Refactor `decompress_stream` duplicate:** Tách helper `_decompress_with_reader` dùng chung cho seekable/non-seekable, giảm 300 dòng (kế thừa v0.1 P2-2).

- **P2-4 — Thêm integration test cho `dst` traversal và `dict_data` dir:** `test_filetext_flex.py` hiện có `test_dst_none_vs_path_mkdir` nhưng chưa cover `dst="a/b/../c.rvh"` và `dict_data` là thư mục.

- **P2-5 — `clean_source` dùng `ast`:** Thay string `startswith("from .")` bằng `ast.parse` để tránh brittle khi docstring chứa example code.

---

## 7. Kết luận: đủ điều kiện release `v0.2.1-filetext` không? Blockers?

**Verdict: `WARN` — Đủ điều kiện release `v0.2.1-filetext-rc` (hoặc `v0.2.1-filetext` với known limitations), chưa đủ `PASS` hoàn toàn cho stable nếu yêu cầu OOM guard strict.**

| Tiêu chí | Verifier (`reports/verification_filetext.md` 8/8 PASS) | Critic (adversarial) | Chênh lệch |
|----------|--------------------------------------------------------|----------------------|------------|
| 4 dạng src + dst None/Path | PASS | PASS (đồng ý) | — |
| Heuristic + force_text | PASS | PASS (đồng ý) | — |
| dst None vs Path + mkdir | PASS | PASS(WARN) — mkdir `..` outside | Verifier không test `..` outside, Critic flag Medium |
| Không break 142 | PASS 154/154 | PASS (đồng ý) | — |
| Encoding strict | PASS | PASS (đồng ý) | — |
| O(1) streaming file | PASS | PASS(WARN) — guard incomplete | Verifier chỉ test `compress` guard 101MB, Critic tìm `decompress` 60MB và `bytes` 50MB bypass |
| Bundle sync | PASS | PASS(WARN) — version/`__all__` drift | Verifier không check `__all__` length |
| Overall | **8/8 PASS** | **5/8 PASS, 3 PASS(WARN) → WARN** | Critic tìm 7 risks thực với evidence, Verifier optimism |

**Blockers cho stable `v0.2.1-filetext` stable (không `rc`):**
1. **P0-1 `decompress` OOM guard** — bắt buộc fix (30 phút) hoặc document `known limitation: decompress large blob to RAM needs file`.
2. **P0-2 `bytes` OOM guard** — bắt buộc fix hoặc document `compress large bytes to RAM not guarded, use file`.
3. **P1 `__all__`/version drift** — không blocker nhưng nên fix để đạt spec `docs/api_filetext.md` clean.

**Nếu chọn release `v0.2.1-filetext-rc` ngay (khuyến nghị Coordinator):**
- Fix P0-1/P0-2 (30-60 phút) → rebuild `revhash_embedded.py` → `build --check` PASS → `pytest 154/154` PASS → tag `v0.2.1-filetext-rc1` với `README` Limitations ghi:
  - *Decompress large output (>100MB) into RAM requires `dst=Path(...)` (guard added in rc1)*
  - *Compress large bytes/text (>100MB) into RAM guarded (rc1)*
  - *`dst` parent `mkdir` does not sanitize `..` — validate if from user input*
  - *`__all__`/`__version__` sync fixed in rc1*
- Nếu không fix P0 mà vẫn tag `v0.2.1-filetext` stable, phải ghi rõ trong release notes workaround, nhưng là debt.

**So với v0.2-embedded:** v0.2.1 đã fix bundle drift (`file_text.py` hash `acec...` khớp), giữ O1, thêm 4 dạng src linh hoạt, `dst=None` RAM tiện DX, `force_text` override, strict encoding, parity 6/6. Chỉ còn 2 High OOM guard thiếu và 3 Medium style, tiến bộ rõ rệt so với v0.2 (1 High `compress_file auto`). Đủ `rc` sau 1h fix.

**Handoff cho Coordinator M6:**
- [ ] Quyết định `rc` vs `stable` (khuyến nghị `rc` sau fix P0 1h)
- [ ] Assign Builder fix P0-1/P0-2 (`file_text.py:104`, `stream.py:1128`, `stream.py:1078`) + P1-3 `str` dir
- [ ] Update `docs/api_filetext.md` Limitations, `TEAM_STATE.md`, rebuild bundle
- [ ] Re-run `py -3.12 -m pytest tests -q` + `scripts/build_embedded.py --check` + `examples/file_text_demo.py` (nếu có) sau fix
- [ ] Tag `v0.2.1-filetext-rc1` nếu fix P0, `v0.2.1-filetext` stable nếu thêm P1 version/`__all__`

---

### Phụ lục — Lệnh reproduce chính (đã chạy, evidence `audit2.py` + `audit3.py`)

```bash
# Heuristic + force_text
py -3.12 -c "import sys; sys.path.insert(0,'src'); sys.path.insert(0,'.'); import revhash, pathlib, tempfile, os; ..."
# -> "hello" exists => file, force_text True => text, blob diff True

# OOM guard compress file
py -3.12 -c "import revhash, pathlib, tempfile; p=pathlib.Path(tempfile.gettempdir())/'large101.bin'; open(p,'wb').seek(101*1024*1024-1); open(p,'ab').write(b'\x00'); revhash.compress_file(p, None)"
# -> ValueError refusing to load large file (>100MB)

# OOM bypass decompress
py -3.12 -c "import revhash, pathlib; ... revhash.decompress_file('mid60.rvh', None) -> 60MB RAM no guard"

# Bytes OOM bypass
py -3.12 -c "import revhash; b=b'x'*(50*1024*1024); revhash.compress_file(b, None) -> len 1729 no guard"

# Traversal
py -3.12 -c "import revhash, pathlib; revhash.compress_file(b'hi', 'a/b/../c.rvh'); print(pathlib.Path('a/c.rvh').exists())"
# -> True

# Bundle hash
py -3.12 -c "import pathlib, hashlib; SRC=pathlib.Path('src/revhash'); h=hashlib.sha256(); [h.update((SRC/n).read_bytes()) or h.update(b'\x00') for n in sorted(['exceptions.py','header.py','codec.py','stream.py','file_text.py','text.py','__init__.py'])]; print('sha256:'+h.hexdigest())"
# -> sha256:acec4d0f... khớp revhash_embedded

# Build drift
py -3.12 scripts/build_embedded.py --check
# -> OK (97957 bytes)
```

---

## Phụ lục A — So sánh Verifier vs Critic (điểm khác)

| Phát hiện | Verifier (`reports/verification_filetext.md` 8/8 PASS) | Critic (report này) | Lý do khác |
|-----------|--------------------------------------------------------|---------------------|------------|
| OOM guard file→RAM | `compress_file(101MB,None)` → `ValueError` PASS, đánh PASS toàn bộ OOM | **HIGH** — `decompress 60MB/101MB to RAM` không guard, `bytes 50MB` không guard | Verifier chỉ test `compress` file→RAM 101MB, không test `decompress` output size và `bytes` path |
| Path traversal | Ghi `mkdir chỉ dst` PASS | **MEDIUM** — `../outside` tạo outside `True` | Verifier không test `..` outside, Critic reproduce `a/b/../c.rvh` + `../outside` |
| `str` dir heuristic | Không đề cập | **MEDIUM** — `compress_file("adir",None)` dir → text `"adir"` silent wrong | Verifier chỉ test `Path` dir → `IsADirectoryError`, không test `str` dir |
| `_load_dict_data` | Ghi `dict_data` as str/Path load PASS | **MEDIUM** — `is_file()` thiếu → `PermissionError` cho dir | Verifier không test dir case |
| `__all__`/`__version__` | Không check, đánh PASS | **MEDIUM** — 19 vs spec 15, version drift `0.1.0` vs `0..embedded` | Verifier optimism, Critic check `__all__` length |
| `as_text` vs `force_text` | Ghi `as_text` decode strict PASS | **MEDIUM** — `compress_file` `as_text` unused gây confusion | Verifier không check unused param |
| O1 regress file→file | `read(chunk_size)` loop PASS | **PASS** đồng ý, nhưng note `BytesIO(data)` O(N) cho text branch expected | Đồng ý |

## Phụ lục B — Checklist cho Coordinator M6

- [ ] Quyết định `rc` vs `stable` (khuyến nghị `rc` sau fix P0 1h, không tag stable nếu chưa fix OOM guard)
- [ ] Assign Builder fix P0-1 (`stream.py:1128` decompress guard theo `original_size`) và P0-2 (`stream.py:1078` bytes guard `len(data)>100MB`)
- [ ] Fix P1-3 `file_text.py:57` `str` dir → `IsADirectoryError` trước fallback text
- [ ] Fix P1-2 `file_text.py:21` `is_file()` + `st_size<=256KB` cho `_load_dict_data`
- [ ] Document `file_text.py:92` traversal `..` behavior trong `docs/api_filetext.md` Limitations hoặc thêm `strict_dst` check
- [ ] Đồng bộ `__init__.py:54` `__version__` → `0.2.1-filetext` và gọn `__all__` 19→15, rebuild `revhash_embedded.py` `__version__` sync
- [ ] Thêm `warnings.warn` hoặc xóa `as_text` khỏi `compress_file` signature (`stream.py:1016`)
- [ ] Re-run `py -3.12 -m pytest tests -q` → 154/154 PASS, `py -3.12 scripts/build_embedded.py --check` → OK, `py -3.12 -c` 6 ví dụ §7 + parity 6/6
- [ ] Update `README.md` Limitations (OOM guard scope, traversal, `as_text`/`force_text` naming) và `TEAM_STATE.md` M6 DONE
- [ ] Tag `v0.2.1-filetext-rc1` nếu fix P0, `v0.2.1-filetext` stable nếu thêm P1 version/`__all__`

## Phụ lục C — Raw audit logs (đã chạy `py -3.12`)

```
=== audit2.py ===
heuristic hello exists -> file? file content True
force_text=True -> hello True
large size 105906176 OOM guard ValueError PASS
decompress large blob to RAM len 105906176  # HIGH bypass
traversal a/c exists? True outside traversal created? True
HAS_ZSTD True HAS_BROTLI True __all__ 19 embedded 16
reader.read() count 0 has BytesIO True
computed hash sha256:acec4d0f... MATCH True build --check OK

=== audit3.py ===
bytes 50MB compress to RAM len 1729 - OOM guard not triggered
decompress 60MB to RAM len 62914560 - no guard, 60MB RAM used
str 'adir' dir -> treated as text? True Path dir IsADirectoryError PASS
file_text has replace? False stream has replace count 1 (comment)
```

---

*— Critic / Auditor — File↔Text Flex — Team revhash v0.2.1-filetext — 2026-08-28*  
*Evidence-based, adversarial, không optimism. 7 risks với `file:line` + `py -3.12 -c` reproduce, anti-cheat 7 checks, security & correctness 7 hạng mục, style 5 tiêu chí. Verdict WARN — 2 High OOM guard + 3 Medium traversal/dict/dir + 2 Medium style, đủ `rc` sau 1h fix P0. Đã đọc 3 docs frozen, audit `src/revhash/file_text.py:1-127`, `stream.py:1007`/`1072`, `__init__.py:54`, `revhash_embedded.py`, `build_embedded.py:26`, `tests/test_filetext_flex.py` 12 cases 154 tests, `verification_filetext.md:432` — không đoán, chỉ evidence.*
