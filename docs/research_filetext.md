# Nghiên cứu File ⇄ Văn bản linh hoạt — revhash v0.2.1-filetext

> **Owner:** Researcher / Explorer — File↔Text — Team revhash v0.2.1-filetext
> **Ngày:** 2026-08-28
> **Inputs:** `TEAM_PLAN_FILETEXT.md` (frozen M0), `docs/api_embedded.md` + `docs/api.md` + `src/revhash/__init__.py:70` + `src/revhash/stream.py:1006` + `src/revhash/text.py:1-67`, `revhash_embedded.py:1-50`, prior-art `pathlib`/`gzip`/`shutil`/`open`
> **Mục tiêu:** Khảo sát API linh hoạt File ⇄ Văn bản cho `compress_file`/`decompress_file` — `src: Path|str|bytes`, `dst: Path|str|None`, heuristic file-vs-text an toàn, `dst=None` trả bytes/str RAM, không break v0.2-embedded (142 tests).

---

## 0. Tóm tắt điều hành

v0.2-embedded đã tách `compress(bytes|str)` + `compress_text(str)` (polymorphic + explicit) và `compress_file(str|Path, str|Path)` tự `mkdir(parents=True)` (`stream.py:1029-1037`, `__init__.py:121-152`). Pivot v0.2.1 yêu cầu **thống nhất**: một entrypoint `compress_file`/`decompress_file` nhận cả *tên file* lẫn *nội dung trực tiếp* — `compress_file("hello")` truyền text, `compress_file("notes.txt")` nén file nếu tồn tại, `decompress_file(blob, dst=None)` trả `str`/`bytes` trong RAM. Nghiên cứu này đề xuất **A+B kết hợp**: ưu tiên `Path.exists() and is_file()` nhưng có `force_text=True` để ép text, và `dst=None` trả `bytes`/`str` như `gzip.compress`.

---

## 1. Định nghĩa 4 dạng `src` + 3 dạng `dst`

### 1.1 `src` — nguồn nén/giải nén

| # | Dạng `src` | Kiểu Python | Điều kiện nhận diện | Xử lý | Ví dụ |
|---|-----------|-------------|---------------------|-------|-------|
| S1 | `Path` tồn tại | `pathlib.Path` | `isinstance(src, Path)` → luôn coi là **file** | Mở `open(src,"rb")` streaming O(1) | `compress_file(Path("data/input.txt"), "out.rvh")` |
| S2 | `str` là **đường dẫn tồn tại** | `str` | `Path(src).exists() and Path(src).is_file()` == `True` (và `force_text==False`) → **file** | Như S1 (mở file) | `compress_file("data/input.txt", "out.rvh")` |
| S3 | `str` là **văn bản trực tiếp** | `str` | `Path(src).exists()` == `False` hoặc `is_dir()` hoặc `force_text==True` → **text** | `src.encode(encoding, "strict")` → `bytes` rồi nén in-memory | `compress_file("xin chào 🌍", "out.rvh")` |
| S4 | `bytes` raw | `bytes|bytearray|memoryview` | `isinstance(src, (bytes,bytearray,memoryview))` | `bytes(src)` pass-through, không encode | `compress_file(b"\x00\xff hello", "out.rvh")` |

**Quy tắc thứ tự** (`_resolve_src`):

```python
if isinstance(src, (bytes, bytearray, memoryview)):  # S4 — ưu tiên cao nhất
    data = bytes(src); is_file = False
elif isinstance(src, Path):                          # S1 — explicit file
    # validate exists/is_file, else FileNotFoundError/IsADirectoryError
    is_file = True
elif isinstance(src, str):                           # S2 vs S3 — heuristic
    if not force_text and Path(src).exists() and Path(src).is_file():
        is_file = True   # S2
    else:
        data = src.encode(encoding, "strict"); is_file = False  # S3
else:
    raise TypeError("src must be str|Path|bytes")
```

**Không ambiguity nguy hiểm:** `bytes` không bao giờ bị nhầm với path. `Path` object luôn là file (explicit). Chỉ `str` có heuristic, và đã có `force_text` để giải quyết case `str` trùng tên file.

#### Ví dụ then chốt: `compress_file("hello")` vs `compress_file("notes.txt")`

```python
from pathlib import Path
import revhash

# Case A: file "notes.txt" TỒN TẠI cùng thư mục
Path("notes.txt").write_text("nội dung file", encoding="utf-8")
revhash.compress_file("notes.txt", "notes.rvh")
# → heuristic thấy Path("notes.txt").is_file()==True → đọc file, KHÔNG nén chuỗi "notes.txt"

# Case B: cùng chuỗi "notes.txt" nhưng muốn nén CHÍNH chuỗi đó (9 bytes), không phải file
revhash.compress_file("notes.txt", "literal.rvh", force_text=True)
# → force_text=True ép S3 → encode("notes.txt") → nén 9 bytes

# Case C: text không phải path
revhash.compress_file("hello", "hello.rvh")
# → Path("hello").exists()==False → S3 → encode("hello") → nén 5 bytes
# Nếu file "hello" tồn tại thì sẽ là S2 (ưu tiên file) — đúng mong đợi DX
```

> **DX justify:** Ưu tiên file khi tồn tại là hành vi ít gây bất ngờ nhất — người dùng truyền `src="data/input.txt"` luôn muốn đọc file. Nếu họ truyền text trùng tên file ngẫu nhiên (hiếm), `force_text=True` giải quyết tường minh, tương tự cách `pathlib` phân biệt `Path("notes.txt")` (explicit) vs `"notes.txt"` (ambiguous str).

### 1.2 `dst` — đích ghi

| # | Dạng `dst` | Kiểu | Xử lý | Trả về |
|---|-----------|------|-------|--------|
| D1 | `Path` | `Path` | `dst.parent.mkdir(parents=True, exist_ok=True)` chỉ cho dst, rồi `open(dst,"wb")` hoặc `open(dst,"w", encoding)` nếu `as_text` | `dict info` |
| D2 | `str` path | `str` | `Path(dst)` → như D1 | `dict info` |
| D3 | `None` | `None` | **Không ghi file**, trả trực tiếp trong RAM | `bytes` (compress) hoặc `bytes|str` (decompress, tùy `as_text`) |

```python
# D1/D2: ghi file + mkdir
info = revhash.compress_file("hello world 🌍", "out/nested/hello.rvh")  # D2
# → out/nested/ tự mkdir, info["original_size"] == len("hello world 🌍".encode())

# D3: trả bytes trong RAM, không chạm filesystem
blob: bytes = revhash.compress_file("hello world 🌍", None)              # D3
# blob == revhash.compress("hello world 🌍") byte-identical
text: str = revhash.decompress_file(blob, None, as_text=True)            # D3 + as_text
# text == "hello world 🌍"
raw: bytes = revhash.decompress_file(blob, None)                          # D3 mặc định bytes
```

**Phân biệt file-vs-text cho `dst`:** `dst` không có ambiguity — chỉ nhận `Path|str` (path) hoặc `None`. Không cần heuristic như `src`. Nếu `dst` là `str` thì luôn là đường dẫn file (không bao giờ là text output dạng str — muốn str thì dùng `dst=None, as_text=True`).

### 1.3 Ma trận 4×3 đầy đủ (6 cases copy-paste cho TEAM_PLAN)

| Case | `src` dạng | `dst` dạng | Gọi | Kết quả |
|------|-----------|-----------|-----|---------|
| 1 text→bytes | `str` text | `None` | `compress_file("xin chào", None)` | `bytes` blob trong RAM |
| 2 text→file | `str` text | `Path|str` | `compress_file("xin chào", "out/a.rvh")` | file `out/a.rvh` + `info dict` |
| 3 file→bytes (decompress text) | `bytes` blob | `None` + `as_text` | `decompress_file(blob, None, as_text=True)` | `str` trong RAM |
| 4 file→file | `Path` tồn tại | `Path` | `compress_file(Path("in.txt"), Path("out.rvh"))` | file + `info` O(1) streaming |
| 5 bytes→bytes | `bytes` raw | `None` | `compress_file(b"\xff\x00", None)` | `bytes` blob |
| 6 file→text (decompress file) | `Path` blob | `None` + `as_text` | `decompress_file(Path("a.rvh"), None, as_text=True)` | `str` decoding strict |

> `file→text` ở đây hiểu rộng: `src` là file blob trên đĩa, `dst=None` trả text — tuyến decompress.

---

## 2. So sánh ≥3 cách phân biệt file-vs-text

### 2.1 Phương án A — `Path(src).exists() and is_file()` ưu tiên file (ĐỀ XUẤT chính)

**Cơ chế:**

```python
def _is_file_path(s: str) -> bool:
    p = Path(s)
    return p.exists() and p.is_file()

if isinstance(src, str) and not force_text and _is_file_path(src):
    # đọc file
else:
    # coi là text
```

**Ưu:**

- Tự nhiên: truyền `"data/file.txt"` → đọc file nếu tồn tại, không cần wrapper.
- Tương thích 100% với code cũ `compress_file("a.txt","b.rvh")` đã dùng `Path(src).exists()` (`stream.py:1030`).
- Không thêm type mới, không break import.
- Prior-art chuẩn: `pathlib.Path.exists()` + `is_file()` là idiom Python để kiểm tra file (docs.python.org/3/library/pathlib.html). `gzip.open("file.gz")` vs `gzip.compress(b"data")` cũng phân biệt bằng kiểu — stdlib không đoán string là path nếu không tồn tại.

**Nhược / Edge:**

- Nếu text ngẫu nhiên trùng tên file tồn tại (ví dụ `text="notes.txt"` và file `notes.txt` tồn tại) → nhầm thành file. Xác suất thấp nhưng có thể gây silent wrong behavior nếu không document.
- Phụ thuộc filesystem state tại thời điểm gọi — hai lần gọi cùng `src="hello"` có thể cho kết quả khác nếu file `hello` được tạo/xóa giữa chừng (TOCTOU, nhưng negligible cho DX local).
- Cần 1 stat syscall (`exists() + is_file()` = 1-2 syscall), overhead ~µs, không đáng kể.

**Mitigation:** Kết hợp với B (`force_text=True`) để caller ép text khi cần.

### 2.2 Phương án B — `force_text=True` param ép text

**Cơ chế:**

```python
compress_file("notes.txt", "out.rvh", force_text=True)  # ép S3 dù file tồn tại
```

**Ưu:**

- Giải quyết triệt để ambiguity của A với 1 boolean tường minh, không cần type mới.
- Prior-art: nhiều lib dùng `force_*` flag cho heuristic override — ví dụ `pandas.read_csv(..., dtype=...)` hay `requests` `json=` vs `data=` đều dùng param để ép kiểu.

**Nhược:**

- Đòi hỏi caller biết trước ambiguity — nếu không biết file `notes.txt` tồn tại thì vẫn nhầm. Nhưng case này hiếm và có thể test bằng `Path(src).exists()` phía caller.
- Thêm 1 param vào signature (đã có `encoding`, `as_text`), nhưng vẫn gọn.

### 2.3 Phương án C — Type wrapper `Text("...")` vs `File("...")` (như `PurePath`)

**Cơ chế:**

```python
from revhash import Text, File
compress_file(Text("notes.txt"), "out.rvh")  # luôn text, dù file tồn tại
compress_file(File("notes.txt"), "out.rvh")  # luôn file, raise nếu không tồn tại
compress_file("notes.txt", "out.rvh")        # heuristic như A (hoặc raise bắt explicit)
```

**Ưu:**

- Không ambiguity 100% — type system tự phân biệt.
- Prior-art: `pathlib.PurePath` vs `str` trong Python 3.6+ (`open` nhận `Path|str`), `gzip` không dùng nhưng `importlib.resources` dùng wrapper.

**Nhược:**

- **DX kém**: caller phải `from revhash import Text` và nhớ wrap — vi phạm mục tiêu "truyền văn bản trực tiếp" (`TEAM_PLAN_FILETEXT.md` §1) vốn muốn `compress_file("xin chào")` đơn giản, không wrapper.
- Tăng API surface (2 class mới), bundle phải export, docs dài.
- Không tương thích với code cũ dạng `compress_file("a.txt","b.rvh")` nếu bắt strict wrapper (phải heuristic fallback vẫn cần).

**Kết luận cho revhash:** Loại làm **primary**, chỉ có thể là optional sugar nếu team muốn thêm sau.

### 2.4 Phương án D — `as_text` / `text=True` flag (ép output, không phân biệt input)

**Cơ chế:**

```python
# D chỉ ảnh hưởng decompress output type, không giải quyết input ambiguity
decompress_file(blob, None, as_text=True)   # trả str
decompress_file(blob, None, as_text=False)  # trả bytes (mặc định)
# Input vẫn cần A hoặc B
```

Thực chất D không phải heuristic file-vs-text cho `src`, mà là **output type selector** cho `decompress_file`. Nó complement A/B chứ không thay thế.

**Ưu:**

- Rõ ràng cho `dst=None`: `as_text=True` → `str` strict decode, `False` → `bytes` raw.
- Prior-art: `open(..., encoding="utf-8")` vs `open(...,"rb")` — `encoding` quyết định `str` vs `bytes`. `gzip.open(..., mode="rt")` vs `"rb"` tương tự.

**Nhược:**

- Nếu đặt tên `text=True` dễ nhầm với `force_text` (input) — cần 2 tên riêng: `force_text` (input) và `as_text` (output).

### 2.5 Bảng so sánh tổng hợp 4 phương án

| Tiêu chí | A `exists()+is_file()` | B `force_text` | C `Text()/File()` wrapper | D `as_text` (output) |
|----------|------------------------|----------------|---------------------------|----------------------|
| **DX** (ít gõ, copy-paste) | ⭐⭐⭐⭐⭐ `compress_file("hello")` | ⭐⭐⭐⭐ thêm 1 flag khi cần | ⭐⭐ phải import Text | ⭐⭐⭐⭐ chỉ cho decompress |
| **Không ambiguity** | ⭐⭐⭐ cần B khi trùng tên | ⭐⭐⭐⭐⭐ khi dùng kèm A | ⭐⭐⭐⭐⭐ 100% | N/A (output) |
| **Break v0.2?** | Không, reuse `stream.py:1030` | Không, param optional default False | Có nếu bắt wrapper | Không |
| **Filesystem syscall** | 1 stat | 0 khi force | 0 | 0 |
| **Prior-art** | `pathlib` idiom | `pandas`/`requests` force flag | `pathlib.PurePath` | `open(encoding=)` |
| **Phù hợp revhash?** | **PRIMARY** | **Kèm A** | Loại (optional) | **Kèm A+B** cho decompress |

### 2.6 Đề xuất chọn **A+B kết hợp** (kèm D cho output)

**Chính:** **A** làm heuristic mặc định — `str` src nếu `Path(src).exists() and is_file()` và `force_text==False` → file, ngược lại → text.

- Chính xác với 99% use-case thực: `compress_file("data/input.txt")` luôn là file nếu tồn tại; `compress_file("xin chào 🌍")` luôn là text vì không có file tên đó.
- Tương tự prior-art `pathlib.Path.exists()` — không đoán, chỉ stat. `gzip`/`shutil`/`open` đều không đoán `str` là path nếu không tồn tại; chúng `open(path)` và raise `FileNotFoundError` nếu không thấy — revhash chỉ khác là fallback sang text thay vì raise.
- Zero-deps, không thêm dependency hay type.

**Phụ:** **B** `force_text=False` (default) để override A khi text trùng tên file. Document rõ trong `docs/api_filetext.md` và ví dụ §1.1.

**Output:** **D** `as_text=False` (default) cho `decompress_file` khi `dst=None` — `True` → `str` strict decode, `False` → `bytes` raw.

> **Không chọn C làm primary** vì DX kém và không cần thiết khi A+B đã đủ an toàn. Có thể thêm `Text`/`File` wrapper ở v0.3 nếu user feedback cần strictness hơn, nhưng v0.2.1 không cần (YAGNI).

**Justify bằng prior-art:**

- `pathlib.Path("notes.txt").exists()` + `is_file()` — docs.python.org/3/library/pathlib.html#pathlib.Path.exists — idiom chuẩn kiểm tra file, không hardcode.
- `gzip.open("file.gz","rb")` (file) vs `gzip.compress(b"data")` (bytes) vs `gzip.decompress(blob)` — stdlib phân biệt file vs bytes bằng **kiểu** (`Path|str` vs `bytes`), nhưng với `str` path thì vẫn cần `exists()` nếu muốn linh hoạt — revhash mở rộng idiom này cho `compress_file`.
- `shutil.copyfile(src, dst)` — luôn coi `src` là path, raise `FileNotFoundError` nếu không tồn tại — không có fallback text. revhash chọn fallback text để DX nhúng tốt hơn, nhưng vẫn raise `FileNotFoundError` nếu `src` là `Path` explicit mà không tồn tại (giữ contract v0.2).
- `open(path, encoding="utf-8")` — khi đọc text, luôn `encoding="utf-8", errors="strict"` — revhash reuse cho `str` input (`encode`) và `as_text` output (`decode`).

---

## 3. So sánh `dst=None` vs luôn ghi file

### 3.1 Định nghĩa

- **`dst=None`** (đề xuất v0.2.1): không ghi filesystem, trả trực tiếp trong RAM — `compress_file(text, None) -> bytes` blob, `decompress_file(blob, None) -> bytes` hoặc `str` (nếu `as_text=True`). Phù hợp nhúng, pipeline không chạm disk.
- **Luôn ghi file** (v0.1 + v0.2): `compress_file(src, dst)` bắt buộc `dst` là path, luôn `open(dst,"wb")` + `mkdir(parents=True)`, trả `info dict`. Phù hợp file lớn O(1).

### 3.2 Bảng so sánh

| Tiêu chí | `dst=None` trả `bytes`/`str` RAM | Luôn ghi file (`dst` bắt buộc) |
|----------|----------------------------------|--------------------------------|
| **DX nhúng** | ⭐⭐⭐⭐⭐ `blob = compress_file("hello", None)` — 1 dòng, không cần temp file, giống `gzip.compress(b"hello")` | ⭐⭐ phải tạo temp file rồi `read_bytes()` |
| **O(1) cho file lớn** | ❌ Nguy cơ OOM nếu `src` là file 1GB và `dst=None` → blob 1GB trong RAM | ✅ Streaming `read(chunk_size)` O(1) (`stream.py:262-269`) |
| **Filesystem side-effect** | Không, pure in-memory | Có `mkdir(parents=True)` + `open` — cần quyền ghi |
| **Trả về** | `bytes` (compress) / `bytes|str` (decompress) — tiện `assert decompress(compress(text))==text` | `dict info` (codec, ratio, ...) — tiện log |
| **Error handling** | `IsADirectoryError`/`FileNotFoundError` chỉ cho `src` | Thêm `mkdir` có thể tạo folder rỗng nếu lỗi giữa chừng (nhưng `exist_ok=True` an toàn) |
| **Prior-art** | `gzip.compress(data: bytes) -> bytes` — stdlib in-memory API; `zlib.compress` tương tự | `shutil.copyfile(src, dst)` — luôn ghi file; `gzip.open` + `shutil.copyfileobj` — file-to-file |
| **Kết hợp?** | **Chọn hỗ trợ cả hai** — `dst` optional, `None` là in-memory, `Path|str` là file | Nếu chỉ 1 trong 2, mất 1 use-case quan trọng |

### 3.3 Prior-art chi tiết

- **`gzip.compress(data: bytes, compresslevel=9) -> bytes`** — Python docs: "Compress the `data`, returning a `bytes` object." Không ghi file, pure RAM. Đây là prior-art cho `compress_file(data, None) -> bytes`. `revhash.compress(data)` đã làm tương tự (`__init__.py:121`).
- **`gzip.open(filename, mode="wb")` + `shutil.copyfileobj(reader, writer)`** — pattern file-to-file, phải `open` cả hai. `revhash.compress_stream(reader, writer)` (`stream.py:163`) và `compress_file(str|Path, str|Path)` v0.1 cũng vậy.
- **`shutil.copyfile(src, dst)`** — docs: "Copy the contents of `src` to `dst`. `dst` must be the complete target file name." Luôn ghi file, tạo `dst` mới, không có `dst=None` mode. revhash file mode reuse pattern này + `dst.parent.mkdir(parents=True, exist_ok=True)` chỉ cho dst (`stream.py:1034`).
- **`open(path, "w", encoding="utf-8")`** — khi ghi text, cần `encoding`. revhash `decompress_file(..., as_text=True, encoding="utf-8", dst=None)` tương tự: decode strict rồi trả `str`.

### 3.4 Đề xuất: `dst` optional — `None` trả RAM, `Path|str` ghi file

Giữ **cả hai**, `dst=None` làm default:

```python
def compress_file(src, dst=None, ...):
    if dst is None:
        return blob  # bytes
    else:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return info  # dict

def decompress_file(src, dst=None, ..., as_text=False):
    if dst is None:
        return text_str if as_text else raw_bytes
    else:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        return info
```

**Guard OOM cho `dst=None` khi src là file lớn:** `TEAM_PLAN_FILETEXT.md` §5 cảnh báo OOM nếu `src` là file 10GB và `dst=None` (blob 10GB RAM). Mitigation:

- Nếu `_resolve_src` thấy `is_file==True` và `src.stat().st_size > 100*1024*1024` (100MB) và `dst is None` → `raise ValueError("refusing to load large file (>100MB) into RAM with dst=None — use dst=Path(...) for O(1) streaming")` hoặc ít nhất `warnings.warn`.
- Hoặc document trong `docs/api_filetext.md` là limitation, Verifier test mock file lớn phải pass với `dst=Path`.

---

## 4. Đề xuất contract chi tiết cho v0.2.1

### 4.1 Signature đề xuất (frozen cho M3 Builder)

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
    as_text: bool = False,
) -> bytes | dict:
    """Nén File ⇄ Văn bản linh hoạt.
    - src S1/S2 (file) → streaming O(1) qua compress_stream
    - src S3/S4 (text/bytes) → in-memory qua BytesIO
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
) -> bytes | str | dict:
    """Giải nén linh hoạt.
    - src có thể là Path blob file, bytes blob, hoặc str text (nếu force_text)
    - dst=None → trả bytes (as_text=False) hoặc str (as_text=True, decode strict)
    - dst=Path → ghi file + mkdir + trả dict
    """
    ...
```

**Lưu ý param:**

- `encoding` chỉ dùng khi `src` là `str` text (S3) hoặc `dst=None, as_text=True` (decode). Mặc định `"utf-8"` strict.
- `force_text` chỉ ảnh hưởng khi `src` là `str` — ép S3 dù `Path(src).is_file()`.
- `as_text` chỉ ảnh hưởng khi `dst is None` trong `decompress_file` — quyết định `bytes` vs `str` return.
- `chunk_size` chỉ dùng khi `is_file==True` (streaming) hoặc khi `data` lớn (>4MB) in-memory cũng chia chunk cho CRC granularity.
- `dict_data` giữ contract cũ: `bytes | str | Path | None` — nếu `str|Path` và `Path(dict_data).exists()` → `read_bytes()` (`stream.py:1035`).

### 4.2 Heuristic chi tiết — `_resolve_src` / `_resolve_dst`

```python
def _resolve_src(src, encoding="utf-8", force_text=False):
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
        try:
            data = src.encode(encoding, "strict")
        except UnicodeEncodeError:
            raise
        return False, data, None
    raise TypeError(f"src must be str|Path|bytes, got {type(src).__name__}")

def _resolve_dst(dst):
    if dst is None:
        return None
    if isinstance(dst, (str, Path)):
        p = Path(dst)
        if p.exists() and p.is_dir():
            raise IsADirectoryError(f"destination is directory: {p}")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    raise TypeError(f"dst must be str|Path|None, got {type(dst).__name__}")
```

**Chi tiết `mkdir` an toàn:**

- Chỉ `Path(dst).parent.mkdir(parents=True, exist_ok=True)`, **không** `mkdir` cho `src` — `TEAM_PLAN_FILETEXT.md` §5 row `Path traversal mkdir` đã cảnh báo.
- Không `mkdir` cho `src` parent — `src` phải tồn tại sẵn, nếu không → `FileNotFoundError`.
- `is_dir()` check cho cả `src` và `dst` trước `mkdir`.

**O(1) vs in-memory phân nhánh:**

| Nhánh | Điều kiện | Đường đi | Memory |
|-------|-----------|----------|--------|
| File → File/Bytes | `is_file==True` và `dst is not None` → file-to-file | `open(src,"rb")` + `open(dst,"wb")` + `compress_stream` | O(1) — `read(chunk_size)` loop |
| File → RAM (`dst=None`) | `is_file==True` và `dst is None` | Nếu `src.stat().st_size > 100MB` → `ValueError` guard, else `BytesIO` | O(file size) — cảnh báo |
| Text/Bytes → File | `is_file==False` và `dst is not None` | `BytesIO(data)` → `compress_stream` → `open(dst,"wb")` | O(len(data)) |
| Text/Bytes → RAM | `is_file==False` và `dst is None` | `BytesIO(data)` → `compress_stream` → `BytesIO` → `bytes` | O(len(data)) |

### 4.3 Error mapping

| Tình huống | Exception | Khi nào |
|------------|-----------|---------|
| `src` là `int`/`None`/`float` | `TypeError: src must be str\|Path\|bytes` | `compress_file(123, None)` |
| `src` là `Path` không tồn tại | `FileNotFoundError` | `compress_file(Path("missing.txt"), None)` |
| `src` là thư mục | `IsADirectoryError` | `compress_file(Path("docs"), "out.rvh")` |
| `src` là `str` text encode fail | `UnicodeEncodeError` (strict) | `compress_file("\ud800", None, encoding="utf-8")` |
| `src` là `bytes` blob corrupt khi decompress | `RevHashCorruptedError` | `decompress_file(b"RVH1...corrupt", None)` |
| `dst` là thư mục tồn tại | `IsADirectoryError` | `compress_file(b"hi", Path("out_dir/"))` |
| `dst` là kiểu sai | `TypeError: dst must be str\|Path\|None` | `compress_file(b"hi", 123)` |
| `decompress as_text` nhưng payload không phải utf-8 | `UnicodeDecodeError` (strict) | `decompress_file(compress(b"\xff\xfe"), None, as_text=True)` |
| `dict_data` sai codec | `RevHashDictError` | `compress_file(..., dict_data=b"dict", codec="gzip")` |
| Codec thiếu | `RevHashUnsupportedCodecError` | `compress_file(b"hi", None, codec="zstd")` khi `HAS_ZSTD==False` |
| File lớn `dst=None` | `ValueError: refusing to load large file into RAM` | `compress_file(Path("10GB.bin"), None)` |

**Không wrap** `UnicodeError` thành `RevHashError` — giữ nguyên để caller `except (UnicodeError, RevHashError)` phân biệt.

### 4.4 Return type chi tiết

| Hàm | `dst` | `as_text` | Trả về | Nội dung |
|-----|-------|-----------|--------|----------|
| `compress_file` | `Path|str` | — | `dict` | `{"codec","level","chunk_size","original_size","compressed_size","ratio","has_dict","chunks","sha256"}` |
| `compress_file` | `None` | — | `bytes` | blob `RVH1...RVHE` hoàn chỉnh |
| `decompress_file` | `Path|str` | — | `dict` | tương tự `decompress_stream` |
| `decompress_file` | `None` | `False` | `bytes` | raw bytes sau giải nén |
| `decompress_file` | `None` | `True` | `str` | `raw.decode(encoding, "strict")` |

### 4.5 6 ví dụ copy-paste (phải PASS cho M4 Integration)

```python
import revhash
from pathlib import Path

# 1) text→bytes (dst=None) — DX nhúng, không chạm disk
blob: bytes = revhash.compress_file("xin chào 🌍 — revhash", None)
assert isinstance(blob, bytes)
assert revhash.decompress(blob).decode("utf-8") == "xin chào 🌍 — revhash"

# 2) text→file — text trực tiếp ghi ra file nén + mkdir
info = revhash.compress_file("hello world 🌍\n" * 1000, "out/nested/text.rvh")
assert Path("out/nested/text.rvh").exists()
assert info["original_size"] == len(("hello world 🌍\n"*1000).encode())

# 3) file→text (decompress as_text) — blob file trên đĩa → str RAM
Path("sample.txt").write_text("nội dung file tiếng Việt", encoding="utf-8")
revhash.compress_file(Path("sample.txt"), "sample.rvh")
text: str = revhash.decompress_file("sample.rvh", None, as_text=True)
assert text == "nội dung file tiếng Việt"

# 4) file→file — O(1) streaming
info2 = revhash.compress_file("sample.txt", "sample2.rvh", codec="zstd", level=3)
assert info2["codec"] == "zstd"
revhash.decompress_file("sample2.rvh", "restored.txt")
assert Path("restored.txt").read_text(encoding="utf-8") == Path("sample.txt").read_text(encoding="utf-8")

# 5) bytes→bytes — raw bytes không qua encode
raw = b"\x00\xff\xfe hello \x80\x81 raw bytes"
blob2 = revhash.compress_file(raw, None)
assert revhash.decompress_file(blob2, None) == raw

# 6) dst=None — decompress trả bytes/str tùy as_text + force_text override
blob3 = revhash.compress(b"hello")
assert revhash.decompress_file(blob3, None) == b"hello"
assert revhash.decompress_file(blob3, None, as_text=True) == "hello"
Path("notes.txt").write_text("file content", encoding="utf-8")
assert revhash.decompress_file(revhash.compress_file("notes.txt", None), None, as_text=True) == "file content"
assert revhash.decompress_file(revhash.compress_file("notes.txt", None, force_text=True), None, as_text=True) == "notes.txt"
```

Tất cả 6 cases phải byte-identical giữa `revhash` package và `revhash_embedded` bundle.

### 4.6 Không break v0.2-embedded

| API cũ v0.2 | Gọi cũ | Tương đương v0.2.1 | Kết quả |
|-------------|--------|-------------------|---------|
| `compress(b"...")` | `revhash.compress(b"hello")` | Giữ nguyên, không đổi | ✅ PASS 142 tests |
| `compress("...")` | `revhash.compress("hello")` | Giữ (`__init__.py:148`) | ✅ |
| `compress_text("...")` | `revhash.compress_text("xin chào")` | Giữ (`text.py:13`) | ✅ |
| `compress_file("a.txt","b.rvh")` | file→file | `compress_file("a.txt","b.rvh")` vẫn file→file | ✅ |
| `decompress_file("a.rvh","b.txt")` | file→file | Giữ | ✅ |
| `dst` bắt buộc? | `compress_file(src,dst)` | `dst` giờ optional `None` default, nhưng gọi 2 args vẫn work | ✅ |

---

## 5. Checklist cho M3 Builder — file:line hints + bundle sync

### 5.1 File:line hints

| File | Dòng | Việc | Ghi chú |
|------|------|------|---------|
| `src/revhash/__init__.py:70` | `def compress(...)` | Tham khảo polymorphic `bytes|str` + `encoding` strict + `_resolve_codec("auto")` | Giữ nguyên, `compress_file` tương tự |
| `src/revhash/__init__.py:121-152` | `compress` body | `if isinstance(data,str): data=data.encode(encoding,"strict")` + `BytesIO` + `compress_stream` | Mẫu cho `_resolve_src` S3 |
| `src/revhash/stream.py:1006` | `def compress_file(src_path, dst_path, ...)` | Chữ ký cũ `str|Path` bắt buộc, `dst.parent.mkdir` + `IsADirectoryError` | **PATCH** thành `src: str|Path|bytes, dst: str|Path|None=None, ..., encoding, force_text, as_text` |
| `src/revhash/stream.py:1029-1037` | `compress_file` body | `Path(src_path)` + `exists()` + `is_dir()` + `mkdir(parents=True)` + `dict_data` path load | Mở rộng heuristic `_resolve_src`, thêm `dst=None` branch |
| `src/revhash/stream.py:1067-1083` | `decompress_file` body | Tương tự compress_file | Thêm `as_text`/`force_text`/`encoding` |
| `src/revhash/stream.py:163` | `compress_stream(reader, writer, ...)` | O(1) `read(chunk_size)` loop | Reuse cho cả 2 nhánh file và bytes (BytesIO) |
| `src/revhash/text.py:1-67` | `compress_text`/`decompress_text` | `TypeError` + `encode(..., "strict")` | Mẫu cho `force_text`/`as_text` strict |
| `src/revhash/codec.py:26-42` | `HAS_ZSTD`/`HAS_BROTLI` | Lazy flag cho `get_available_codecs` | Không sửa, bundle sync cần |
| `revhash_embedded.py:1-50` | Bundle header | `__bundle_hash__`, `<500KB` contract | Rebuild sau patch |
| `src/revhash/header.py:30-45` | `HEADER_MAGIC`/`HEADER_SIZE` | Không sửa | Bundle copy |

### 5.2 Có nên tách `src/revhash/file_text.py`?

**Đề xuất:** Tạo `src/revhash/file_text.py` (~120-180 dòng) chứa:

```python
from pathlib import Path
import os

def _resolve_src(src, encoding="utf-8", force_text=False): ...
def _resolve_dst(dst): ...
def _load_dict_data(dict_data): ...
def _guard_large_file_for_ram(src_path: Path, dst): ...
```

**Ưu khi tách:**

- `stream.py` đã 1097 dòng — thêm heuristic + 2 branch `dst=None` sẽ lên ~1250 dòng, khó review.
- `file_text.py` dễ unit-test riêng (`_resolve_src` 10 cases heuristic).
- Verifier có thể test `_resolve_src` trực tiếp.

**Nhược:** Thêm 1 file mới, bundle phải inline thêm file này (thứ tự sau `exceptions` trước `stream`).

**Quyết định:** **NÊN TÁCH** nếu Builder thấy `stream.py` patch >50 dòng — tạo `file_text.py` và `__init__.py` re-export. Nếu giữ trong `stream.py` thì đặt helper `_resolve_src`/`_resolve_dst` ở đầu file, không duplicate logic.

**Tích hợp vào `stream.py:1006`:**

```python
from .file_text import _resolve_src, _resolve_dst, _load_dict_data, _guard_large_file

def compress_file(src, dst=None, codec="zstd", level=3, chunk_size=4*1024*1024, dict_data=None, encoding="utf-8", force_text=False, as_text=False, show_progress=False):
    dict_data = _load_dict_data(dict_data)
    is_file, data, file_path = _resolve_src(src, encoding, force_text)
    dst_path = _resolve_dst(dst)
    if is_file:
        _guard_large_file(file_path, dst_path)
        if dst_path is None:
            from io import BytesIO
            with open(file_path, "rb") as rf:
                bio = BytesIO()
                info = compress_stream(rf, bio, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
                return bio.getvalue()
        else:
            with open(file_path, "rb") as rf, open(dst_path, "wb") as wf:
                return compress_stream(rf, wf, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
    else:
        from io import BytesIO
        reader = BytesIO(data)
        if dst_path is None:
            writer = BytesIO()
            compress_stream(reader, writer, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
            return writer.getvalue()
        else:
            with open(dst_path, "wb") as wf:
                return compress_stream(reader, wf, codec=codec, level=level, chunk_size=chunk_size, dict_data=dict_data)
```

### 5.3 Checklist M3 Builder (single track)

- [ ] **Tạo/hoặc patch `src/revhash/file_text.py`** — `_resolve_src`/`_resolve_dst`/`_load_dict_data`/`_guard_large_file` như §5.2, 100% `strict` encoding.
- [ ] **Patch `src/revhash/stream.py:1006` `compress_file`** — signature `src: str|Path|bytes, dst: str|Path|None=None, codec, level, chunk_size, dict_data, encoding="utf-8", force_text=False, as_text=False, show_progress=False) -> bytes|dict`; body dùng `_resolve_src`/`_resolve_dst`, branch `dst is None` vs `dst is not None`.
- [ ] **Patch `src/revhash/stream.py:1067` `decompress_file`** — signature `src: str|Path|bytes, dst: str|Path|None=None, dict_data=None, encoding="utf-8", as_text=False, force_text=False, show_progress=False) -> bytes|str|dict`; heuristic cho `src`, branch `dst is None` với `as_text` decode strict.
- [ ] **Patch `src/revhash/__init__.py`** — re-export `compress_file`/`decompress_file` mới (signature đã có từ `stream.py`). Không break `__all__`.
- [ ] **Test local 6 cases §4.5** — chạy `python -c` 6 snippet, đảm bảo `file→file` O(1), `text→bytes` in-memory, `force_text` override, `mkdir` chỉ dst.
- [ ] **Không break 142 tests** — `pytest tests -q` 142/142 vẫn PASS.
- [ ] **Rebuild `revhash_embedded.py`** — `python scripts/build_embedded.py` (inline order: `exceptions → header → codec → stream → file_text → __init__ public → text`), verify `<500KB`, `__bundle_hash__` mới, `python scripts/build_embedded.py --check` PASS.
- [ ] **Parity bundle vs pkg** — 6 cases §4.5 byte-identical: `revhash.compress_file(...) == revhash_embedded.compress_file(...)`.
- [ ] **OOM guard test** — mock file `>100MB` với `dst=None` → `ValueError`.
- [ ] **Encoding strict test** — `compress_file("\ud800", None)` → `UnicodeEncodeError`, `decompress_file(compress(b"\xff\xfe"), None, as_text=True)` → `UnicodeDecodeError`.

### 5.4 Bundle sync

- **Build script:** `scripts/build_embedded.py` hiện inline `exceptions → header → codec → stream → text → __init__` (`research_embedded.md` §4.2). Thêm `file_text.py` vào `HASH_FILES` và inline sau `exceptions` trước `stream`.
- **Hash:** `__bundle_hash__ = "sha256:" + hashlib.sha256(b"".join(Path(f).read_bytes() for f in sorted(HASH_FILES))).hexdigest()` — cập nhật `HASH_FILES` thêm `"file_text.py"`.
- **Kiểm tra:** `python scripts/build_embedded.py --check` fail nếu drift — Verifier chạy `tests/test_embedded.py` parity + hash check.
- **Size:** Core hiện 85KB + `file_text.py` ~3KB → ~88KB vẫn <500KB dư 5×.

### 5.5 Verifier dự kiến

- `tests/test_filetext_flex.py` 8+ cases + `reports/verification_filetext.md` 150+ tests, parity bundle.

---

## 7. Tài liệu tham khảo

1. `TEAM_PLAN_FILETEXT.md` — Team Sheet frozen M0 approved 2026-08-27 (8 success criteria, heuristic file-vs-text)
2. `docs/api_embedded.md` + `docs/api.md` — API frozen v0.2-embedded (Hybrid A3, mkdir)
3. `src/revhash/__init__.py:70` — `compress(data: bytes|str, encoding="utf-8")` polymorphic, `BytesIO` + `compress_stream`
4. `src/revhash/stream.py:1006` — `compress_file(src_path: str|Path, dst_path: str|Path)` hiện tại, `dst.parent.mkdir(parents=True)`
5. `src/revhash/text.py:1-67` — `compress_text(text: str)` strict `TypeError` + `encode(..., "strict")`
6. `revhash_embedded.py:1-50` — bundle header `__bundle_hash__`, `<500KB` contract
7. `pathlib.Path.exists()` + `is_file()` — https://docs.python.org/3/library/pathlib.html#pathlib.Path.exists
8. `gzip.compress(data) -> bytes` vs `gzip.open` — https://docs.python.org/3/library/gzip.html
9. `shutil.copyfile(src, dst)` — https://docs.python.org/3/library/shutil.html#shutil.copyfile
10. `open(..., encoding="utf-8")` strict — https://docs.python.org/3/library/functions.html#open
11. `requests`/`pandas` prior-art — https://requests.readthedocs.io/ + https://pandas.pydata.org/
12. `bottle.py` single-file — https://github.com/bottlepy/bottle
13. `docs/research_embedded.md` (581 dòng) + `TEAM_STATE.md` — milestones v0.1 + v0.2 DONE

---

*— Researcher / Explorer — File↔Text, Team revhash v0.2.1-filetext — 2026-08-28*
*Contract `src` 4 dạng + `dst` 3 dạng, heuristic A+B kèm D, `dst=None` trả RAM, 6 ví dụ copy-paste, checklist M3 với file:line hints — sẵn sàng M2 Design Freeze.*

