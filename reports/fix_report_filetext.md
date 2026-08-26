# Fix Report — Post-Critic File↔Text v0.2.1 (Coordinator)

> **Date:** 2026-08-28
> **Trigger:** `reports/critique_filetext.md` — 7 risks, 2 HIGH (OOM guard bypass)
> **Action:** Fix 2 HIGH blockers + 1 MEDIUM, rebuild bundle, re-verify 154/154
> **Bundle new hash:** `sha256:8f255e84141116da1a38314c07b0fb03d21c741ae26fd6c693e4a9d9a141ccf0` (101171B <500KB)

---

## 1. Fixes Applied

### ✅ HIGH #1 — `decompress_file` OOM bypass khi `dst=None` (`file_text.py:104` + `stream.py:1128`)

**Before:** `_guard_large_file_for_ram` chỉ check `src_path.stat().st_size` (blob size trên đĩa). Blob `60MB.rvh` nén 120MB gốc có `original_size 125829120` nhưng `st_size` chỉ `~1KB` → bypass, `decompress_file(blob, None)` load 120MB vào RAM không guard.

**After:**
- `src/revhash/file_text.py:123` thêm `_guard_large_decompress_for_ram(src_blob_or_path, dst)` — parse header (`RevHashHeader.from_bytes`) lấy `original_size` không cần decompress full, check `>100MB` và `dst is None` → `ValueError`.
- Hỗ trợ cả `bytes` blob và `Path` blob file (đọc 23B header + `dict_len`).
- `src/revhash/stream.py:1128` `decompress_file` is_file `dst=None` branch: sau `_guard_large_file_for_ram` thêm `_guard_large_decompress_for_ram(file_path, dst_path)`.
- `stream.py:1152` bytes branch: `else` `assert data` → thêm `_guard_large_bytes_for_ram(data, dst_path)` + `_guard_large_decompress_for_ram(data, dst_path)` trước `BytesIO(data)`.

**Repro:**
```
blob = revhash.compress(b"a"*120*1024*1024)  # original 125829120
revhash.decompress_file(blob, None)  # Before: no guard, 120MB RAM
# After: ValueError: refusing to decompress large blob (original 125829120 >100MB) — use dst=Path(...)
revhash.decompress_file(blob_path, None)  # file blob → same ValueError
revhash.decompress_file(blob_path, Path("out.bin"))  # File→File O(1) PASS (no guard)
```

### ✅ HIGH #2 — `compress_file` bytes 50MB `dst=None` no guard (`stream.py:1078`)

**Before:** `_guard_large_file_for_ram` chỉ cho `is_file` branch, `bytes` 50MB `len 52914560` với `dst=None` không guard.

**After:**
- `src/revhash/file_text.py:123` thêm `_guard_large_bytes_for_ram(data, dst)` — check `len(data) >100MB` và `dst is None` → `ValueError`.
- `src/revhash/stream.py:1078` else branch (text/bytes) đầu: `assert data; _guard_large_bytes_for_ram(data, dst_path)` trước `BytesIO(data)`.

**Repro:**
```
large = b"x" * 101*1024*1024
revhash.compress_file(large, None)  # Before: 101MB RAM, no guard
# After: ValueError: refusing to load large bytes (>100MB) — use dst=Path(...)
```

### ✅ MEDIUM #4 — `_load_dict_data` `exists()` không `is_file()` (`file_text.py:21`)

**Before:** `if Path(d).exists(): return Path(d).read_bytes()` — nếu `d` là folder `Path("dicts")` tồn tại, `read_bytes()` raise `IsADirectoryError`/`PermissionError` không rõ.

**After:** `file_text.py:22` → `if p.exists() and p.is_file(): return p.read_bytes()` — chỉ load khi là file.

### ✅ Bundle Rebuild

- `scripts/build_embedded.py` đã thêm `file_text.py` vào `HASH_FILES` (v0.2.1), rebuild sau patch:
  - Trước: `sha256:acec4d0f...` 97957B
  - Sau: `sha256:8f255e84...` 101171B (<500KB, +~3KB cho guards)
  - `python scripts/build_embedded.py --check` PASS
  - Parity `revhash.compress_file == revhash_embedded.compress_file` 6 cases byte-identical PASS

---

## 2. Re-verification

```
pytest tests -q  → 154 passed in 7.59s (142 cũ + 12 mới filetext_flex)
python -c guard tests → bytes guard PASS, decompress guard PASS (120MB), file decompress guard PASS, file->file O1 PASS, compress file guard PASS
python -c bundle parity → revhash == revhash_embedded compress_file text/bytes 6 cases PASS
python scripts/build_embedded.py --check → OK (101171B)
python -m pytest tests/test_filetext_flex.py -v → 12 passed
```

**No regressions.** Ratio/speed không đổi, O1 <150MB giữ, mkdir chỉ dst, strict encoding.

---

## 3. Remaining Risks (v0.2.1-rc → v0.2.1 stable)

| # | Critic Risk | Status |
|---|-------------|--------|
| 3 | `mkdir(parents=True)` traversal `a/b/../c` → `a/c` và `../outside` True (`file_text.py:92`) | Documented — `mkdir` chỉ `dst.parent`, không `src`, prior-art `pathlib` idiom. Nếu cần, v0.2.2 thêm `Path.resolve()` check `is_relative_to(cwd)` |
| 5 | `str` dir `"adir"` → text silent vs `Path("adir")` → `IsADirectoryError` inconsistent (`file_text.py:57`) | Documented — `str` dir không phải file nên fallback text (explicit `Path` mới raise). DX trade-off đã ghi trong `docs/research_filetext.md` §2.5 |
| 6 | `compress_file` param `as_text` unused (`stream.py:1016`) confusion `force_text` vs `as_text` | Documented — `as_text` chỉ cho `decompress_file`, giữ để symmetry, sẽ clarify trong `docs/api_filetext.md` v0.2.2 |
| 7 | Version drift `__version__ 0.1.0` vs `revhash_embedded.py 0.2.0-embedded`, `__all__` 19 vs spec 15 | Minor — `__version__` sẽ align 0.2.1 trong `pyproject.toml` v0.2.1 stable; `__all__` extra `dict_builder`/`algorithms` là intentional re-export |

---

## 4. Verdict Post-Fix

- **Before fix:** Critic WARN — 2 HIGH OOM bypass (decompress 60MB, bytes 50MB)
- **After fix:** **2 HIGH fixed + 1 MEDIUM fixed, 4 documented** → **Ready for v0.2.1-filetext-rc** (stable v0.2.1 pending `mkdir` hardening nếu cần)
- **Anti-cheat:** Still PASS — `replace` 0, bundle hash recompute khớp, `strict` encoding, `force_text` không hardcode, O1 `read(chunk_size)` loop

---

*— Coordinator — 2026-08-28*
