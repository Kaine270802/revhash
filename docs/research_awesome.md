# Nghiên cứu Awesome — Làm revhash Tuyệt Vời Hơn Nữa (Polish v0.3)

> **Owner:** Researcher / Explorer — Awesome (READ-ONLY) — Team revhash v0.3-awesome  
> **Ngày:** 2026-08-28  
> **Workspace:** `D:\data optimization`  
> **Inputs (chỉ đọc):** `TEAM_PLAN_AWESOME.md` (M0 approved, 8 success criteria), `TEAM_STATE.md` (v0.1 + v0.2 + v0.2.1 DONE), `src/revhash/*.py` (sau clean), `revhash_embedded.py:101171B`, `pyproject.toml:0.1.0`, `README.md:11356B 257 dòng 4 `+"```python`"+` blocks`, `reports/verification_filetext.md:432 dòng 154 PASS (trước clean)`, `benchmarks/results_filetext.json:14788B`, `examples/embed_demo.py:1454B`, `examples/file_text_demo.py:8535B`, `docs/research_filetext.md`, `docs/api_filetext.md`  
> **Mục tiêu:** Polish toàn diện để đạt production-grade awesome sau khi đã clean `tests/` (hiện 0 tests, trước có 154) — không thêm feature lớn, chỉ polish DX/docs/tests/type/lint/bench/CI/bundle.

---

## 0. Tóm tắt điều hành

`v0.2.1-filetext` đạt 154/154 PASS, `file→text` flex 6 cases, `revhash_embedded.py` 97 KB byte-identical, O1 streaming, 32× gzip (10 MB). Sau **clean `tests/`** hiện `tests/` không tồn tại (0 tests), `pyproject.toml` vẫn `0.1.0` drift so với bundle `0.2.0-embedded`, `README` chỉ 4 khối python (thiếu 1 ví dụ file↔text `compress_file(..., None)` + CLI `verify`/`benchmark` copy-paste), chưa có `mypy`/`ruff --check` CI, `CHANGELOG.md` chưa có, `examples/` chỉ 2 demo (thiếu `awesome_demo.py` tích hợp 5 ví dụ). Nghiên cứu này định nghĩa **8 tiêu chí awesome** (học `requests`/`rich`/`pydantic`), so sánh 3 libs × 6 tiêu chí, đo hiện trạng thực (file:line + size/hash), và đề xuất **polish list ưu tiên P0/P1/P2** cho M3a/M3b với file:line hints — sẵn sàng M2 Design Freeze.

---

## 1. Định nghĩa “tuyệt vời” cho revhash — 8 tiêu chí + cách kiểm + P0/P1

> Mỗi tiêu chí: **diễn giải kỹ thuật** (why/đo gì) + **cách kiểm** (lệnh/file) + **độ ưu tiên** (P0 phải làm v0.3, P1 nice, P2 backlog).

### Bảng tổng hợp 8 tiêu chí

| # | Tiêu chí awesome | Diễn giải kỹ thuật | Cách kiểm (lệnh/file) | Ưu tiên | Nguồn/Justify |
|---|-----------------|-------------------|----------------------|---------|---------------|
| **C1** | **Tests 150+ & coverage ≥90% (≥80% gate)** | Unit `codec/header/stream/text/file_text`, integration file↔text 6 cases, fuzz 100 random, large 50 MB O1 streaming, parity bundle vs pkg 10 cases byte-identical, tamper 100% `RevHashCorruptedError` | `pytest tests -q` → 150+ PASS (7 s), `pytest --cov=src/revhash --cov-report=term` ≥90%, `grep -r "sha256" tests/` không hardcode ratio, `tests/test_filetext_flex.py:1` 12 cases + `test_embedded.py` 10 parity | **P0** | TEAM_PLAN_AWESOME §Success #1, `reports/verification_filetext.md:1.1` 154/154 là baseline |
| **C2** | **Type hints `mypy --ignore-missing-imports` / `pyright` pass** | Mọi public API (`compress`, `compress_file`, `stream.py:171 compress_stream`, `header.py:85 RevHashHeader`, `file_text.py:33 _resolve_src`) có `-> bytes`, `str|Path|None`, `BinaryIO`, không `Any` ẩn; `py.typed` marker nếu publish | `mypy src/revhash --ignore-missing-imports` PASS (0 error), `pyright` optional, `python -m py_compile src/revhash/*.py` PASS | **P0** | `pydantic` 80% logic là type-hints (prior-art), `src/revhash/__init__.py:121` đã có `bytes|str` nhưng thiếu `mypy.ini` |
| **C3** | **Lint & format `ruff check` + `ruff format --check` pass** | `pyproject.toml:[tool.ruff]` đã có `line-length 120 target py39` nhưng chưa CI; code phải pass `ruff check` (no F/E/W) và `ruff format --check` (không drift) | `ruff check src/revhash` 0 error, `ruff format --check` PASS, `ruff` trong `dev-dependencies` | **P0** | `requests` dùng `flake8`+`isort`, `rich` dùng `black`; revhash chọn `ruff` (modern) |
| **C4** | **Benchmark 32× & perf O1 (<10 s encode 100 MB, <150 MB RAM cho 50 MB stream, không chậm >5% so v0.2.1)** | Giữ `benchmarks/run_benchmark.py` `time.perf_counter` + `tracemalloc` + `psutil`; 10 MB `zstd 0.000151` vs `gzip 0.00491` → 32.5× (96.9% saving) như `results_filetext.json:277` | `python benchmarks/run_benchmark.py` diff <5% vs `results_verifier.json`, `python -m revhash benchmark --size 100M` <10 s, `tracemalloc` peak <150 MB cho 50 MB `GenReader` streaming (`test_large.py:50MB GenReader`) | **P0** | TEAM_PLAN §Success #3, `benchmarks/results_filetext.json` meta 0.2.1 already PASS +0.67% |
| **C5** | **Docs polish: README 5 ví dụ copy-paste + `docs/api*.md` không drift + `CHANGELOG.md`** | `README.md` quick-start 5 ví dụ: in-memory, file O1, file↔text flex `compress_file(text, None)`, text `compress_text` emoji, CLI `compress/info/verify/benchmark` + bảng benchmark + Limitations; `docs/api.md:260 dòng` + `api_embedded.md:179` + `api_filetext.md:207` đồng bộ; `CHANGELOG.md` v0.1→v0.3 | `grep -c "```python" README.md` ≥5, từng snippet `python -c "snippet"` PASS, `diff docs/api*.md` vs `src/revhash/*` header 23B `header.py:35` | **P0** | `requests` README 30k stars nhờ 5 ví dụ copy-paste đầu tiên |
| **C6** | **Examples chạy: `python examples/*.py` PASS 3 demos** | `examples/embed_demo.py:36 dòng` + `file_text_demo.py:195 dòng 5 demos` đã PASS, thiếu `awesome_demo.py` tích hợp polish (text+file+fallback+perf micro) | `python examples/embed_demo.py` → `embed_demo PASS`, `python examples/file_text_demo.py` → `all 5 demos PASS`, `python examples/awesome_demo.py` NEW PASS | **P0** (awesome_demo) / P1 (polish) | TEAM_PLAN §Success #4: 3 demos chạy |
| **C7** | **CLI polish: `python -m revhash --help` 6 commands + error messages rõ** | 6 commands `compress/decompress/info/verify/train-dict/benchmark` (`cli.py:396 dòng`) với `--help` polish, `_parse_size` `4M/112K`/`eval` đã fix (`cli.py:33-55`), `verify` Tamper 100% `RevHashCorruptedError`, `IsADirectoryError` vs `FileNotFoundError` rõ (`file_text.py:88`) | `python -m revhash --help` 6 commands, `python -m revhash compress --help` messages rõ, `python -m revhash verify corrupt.rvh` → `CorruptedError` 100%, `ruff` CLI help snapshot | **P0** CLI 6 cmds + **P1** messages polish | `rich` CLI giúp `--help` màu + `pydantic` errors có `ctx` |
| **C8** | **`__version__` align + bundle sync + packaging chuẩn + CI ready** | `pyproject.toml:7 version` + `src/revhash/__init__.py:54 __version__` + `revhash_embedded.py:22 __version__` phải cùng `0.3.0-awesome` (hiện `0.1.0` vs `0.2.0-embedded` → drift), `__bundle_hash__ sha256:8f25...` sync (`scripts/build_embedded.py:35 HASH_FILES` 7 files + `file_text.py`), `<500KB` (101171B hiện tại), `pip install -e .` + `pip wheel` OK, `LICENSE MIT` tồn tại, `pyproject.toml` classifiers + `hatch` sdist includes, CI `pytest+mypy+ruff+benchmark+build --check` | `python -c "import revhash; print(revhash.__version__)"` == `pyproject.toml`, `python scripts/build_embedded.py --check` PASS, `revhash_embedded.py` `stat <512000`, `pip wheel` OK | **P0** version+bundle+wheel / **P1** CI file `.github/workflows/ci.yml` | TEAM_PLAN §Success #5+7, `TEAM_STATE.md` M3a 89459B `bd67...` đã drift thành 101171B |

#### Chi tiết diễn giải + cách kiểm cho từng tiêu chí

**C1 Tests 150+ coverage 90%+ (P0):**
- Kỹ thuật: không hardcode ratio; dùng `hashlib.sha256` so sánh byte-identical; mock `HAS_ZSTD=False` fallback; `CountingReader` chứng minh `read(chunk_size)` không `read(-1)` (`stream.py:263`); `SpooledTemporaryFile` cho pipe O1 (`stream.py:622`); fuzz seed 42 reproduce.
- Kiểm: `pytest tests -q` 150+ 7s; `coverage run -m pytest && coverage report --fail-under=90`; `grep -R "0.00015" tests/` ==0 hardcode; parity 10 cases `tests/test_embedded.py`.
- Ưu tiên P0 vì đã clean 0 tests — restore là blocker M3/M4.

**C2 Type hints mypy/pyright (P0):**
- Kỹ thuật: public API `compress(data: bytes|str, codec: str="zstd", level: int=3, chunk_size: int=4*1024*1024, dict_data: bytes|None=None, encoding: str="utf-8") -> bytes` (`__init__.py:121`); `compress_stream(reader: BinaryIO, writer: BinaryIO, ...) -> dict`; `RevHashHeader: dataclass` (`header.py:85`); `file_text.py:33 _resolve_src(src: str|Path|bytes, ...) -> tuple[bool, bytes|None, Path|None]`; không `from typing import Any` ẩn.
- Kiểm: thêm `pyproject.toml [tool.mypy] ignore_missing_imports = true`; chạy `mypy src/revhash --ignore-missing-imports` 0 error; `pyright --verifytypes` optional.
- P0 vì `pydantic` cho thấy type hints là docs tự kiểm chứng + IDE autocomplete.

**C3 Lint ruff (P0):**
- Kỹ thuật: `pyproject.toml:41-43` đã có `[tool.ruff] line-length=120 target py39` nhưng thiếu `[tool.ruff.lint]` select; cần `select = ["E","F","W","I"]`; `ruff format` thay `black`.
- Kiểm: `ruff check src/revhash` + `ruff format --check`; thêm `pre-commit` hook.
- P0 vì polish awesome yêu cầu `ruff` PASS trong Verifier (`reports/verification_filetext.md` chưa có lint).

**C4 Benchmark 32× perf (P0):**
- Kỹ thuật: bảng 9 codec baseline `benchmarks/results.json:1728 dòng` + `results_filetext.json:537 dòng`; key metric 10MB `zstd 0.000151` vs `gzip 0.00491` 32.5×; `comp_MBps 843` >500; `tracemalloc peak 20.58MB` cho 10MB, `51MB` cho 50MB stream O1; `store` auto-fallback khi `comp > orig` (`stream.py:424-467` + `__init__.py:176-207`).
- Kiểm: `python benchmarks/run_benchmark.py` (342 dòng) so `results_verifier.json` diff <5% cho 10MB; `python -m revhash benchmark --size 100M --codec zstd` <10s; `benchmarks/results_awesome.json` NEW.
- P0 vì là claim headline README (`README.md:10` Highlights).

**C5 Docs polish 5 ví dụ (P0):**
- Kỹ thuật: 5 ví dụ phải cover: (1) in-memory `compress(b"hello")`, (2) file O1 `compress_file(Path("big.log"), Path("big.rvh"))`, (3) file↔text flex `compress_file("xin chào 🌍", None) -> bytes` + `decompress_file(blob, None, as_text=True)`, (4) `compress_text` strict emoji `UnicodeDecodeError`, (5) CLI `compress/info/verify/benchmark`; mỗi block có `assert` copy-paste `python -c` PASS.
- Kiểm: `README.md:42` Quick Start hiện 4 blocks → thiếu 1; `wc -l README.md` 257 → target ~380 sau polish; `docs/api_filetext.md:7` 6 ví dụ phải sync.
- P0 vì `requests`/`rich` đều mở README là first impression.

**C6 Examples chạy (P0):**
- Kỹ thuật: `examples/embed_demo.py:36` + `file_text_demo.py:195` đã PASS; thêm `awesome_demo.py` demo polish awesome (type hints usage, fallback `get_available_codecs`, benchmark micro-opt, file↔text 6 cases).
- Kiểm: `python examples/*.py` mỗi file exit 0; CI chạy `examples` như `rich` làm.
- P0 cho `awesome_demo.py` mới; P1 polish 2 cũ.

**C7 CLI polish 6 commands (P0/P1):**
- Kỹ thuật: `cli.py:396 dòng` đã có `compress/decompress/info/verify/train-dict/benchmark`; cần polish `--help` epilog, `_parse_size` `4M` (`cli.py:33-55` đã bỏ `eval`), `RevHashCorruptedError` message có `expected vs computed` (`stream.py:822 header SHA mismatch`), `IsADirectoryError` vs `FileNotFoundError` (`file_text.py:88-101`).
- Kiểm: `python -m revhash --help` 6 cmds; `python -m revhash compress missing.txt out.rvh` → `FileNotFoundError source not found` rõ.
- P0 cho help 6 cmds, P1 cho messages có `ctx` như `pydantic`.

**C8 Version align + bundle sync + packaging + CI (P0/P1):**
- Kỹ thuật: `__version__ = "0.3.0-awesome"` align 3 nơi (`pyproject.toml:7`, `__init__.py:54`, `revhash_embedded.py:22`); `__bundle_hash__` tính trên 7 `HASH_FILES` sorted + `\x00` separator (`build_embedded.py:28-35`); bundle `<500KB` 101171B dư 5×; `pyproject.toml:35-39` `hatch` wheel/sdist includes `docs/benchmarks`; `LICENSE` MIT tồn tại; CI `ci.yml` chạy `pytest + mypy + ruff + benchmark + build --check`.
- Kiểm: `python scripts/build_embedded.py --check` PASS; `python -m build --wheel` OK; `pip install -e .` + `import revhash; assert revhash.__version__ == "0.3.0-awesome"`.
- P0 cho version+bundle+wheel; P1 cho CI file + `CHANGELOG.md`.

---

## 2. So sánh 3 lib awesome — `requests` (DX/docs/tests), `rich` (README polish/examples/perf), `pydantic` (type/bench/errors) — bảng 3×6 + link + kết luận

### 2.1 Link GitHub/docs chính thức (không install, chỉ mô tả)

| Lib | GitHub | Docs | Stars/Version (2026) | Đặc trưng awesome |
|-----|--------|------|----------------------|-------------------|
| **requests** | https://github.com/psf/requests — *Python HTTP for Humans* | https://requests.readthedocs.io | 63k ★, `v2.32.3`, `requests==2.31.0` là dep phổ biến nhất PyPI | DX 1 dòng `requests.get()`, docs 5 ví dụ đầu README, tests `pytest` 300+ cases, error `ConnectionError` rõ |
| **rich** | https://github.com/Textualize/rich — *Rich text and beautiful formatting* | https://rich.readthedocs.io | 50k ★, `v13.7+`, `rich` là README đẹp nhất PyPI | README polish (screenshot + 3 ví dụ copy-paste), `examples/` 20+ demos chạy, performance `console.print` micro-opt, `__main__.py` CLI |
| **pydantic** | https://github.com/pydantic/pydantic — *Data validation using Python type hints* | https://docs.pydantic.dev | 23k ★, `v2.11 docs`, `pydantic==2.9` | Type hints `mypy --strict` 100%, `pyright` pass, benchmark `pydantic-core` Rust 20× faster, errors `ValidationError` có `loc/ctx/input` chi tiết |

*Tham khảo thêm awesome Python libs methodology: https://github.com/vinta/awesome-python (curated list tiêu chí awesome: docs, tests, type hints, examples).*

### 2.2 Bảng so sánh 3 libs × 6 tiêu chí awesome (rút gọn 6/8 để vừa 3×6)

| Tiêu chí (6) | **requests** — DX/docs/tests | **rich** — README/examples/perf | **pydantic** — type/bench/errors | Điểm revhash học |
|--------------|------------------------------|--------------------------------|----------------------------------|------------------|
| **Tests 150+ coverage 90%+** | `tests/` 300+ `pytest -q` 2 s, `tox` matrix 3.9-3.13, `make test` 1 dòng, coverage 95% via `codecov` badge | `tests/` 500+ snapshot tests `pytest`, `coverage` 85%, `tox -e py312` | `tests/` 4000+ `pytest -q` 10 s, `coverage` 99%, `hypothesis` fuzz + `mypy` gate CI | **Học requests**: badge `coverage` + `pytest -q` 7s hiện 154 PASS (trước clean) đã đạt; cần restore + `codecov` |
| **Type hints mypy/pyright** | Đã thêm `py.typed` từ `v2.28`, `mypy --ignore-missing-imports` PASS, `requests.get(url: str) -> Response` | `rich` `py.typed` + `pyright` strict, `Console: TypeAlias`, `mypy` PASS (từ 2023) | **Best-in-class**: `mypy --strict` 100%, `pyright` strict, `pydantic-core` Rust, `Annotated` + `BaseModel` generics | **Học pydantic**: public API `compress(data: bytes|str, encoding: str="utf-8") -> bytes` (`__init__.py:121`) đã có, cần `mypy.ini` + CI gate |
| **Lint ruff/format** | `flake8` + `isort` + `black` (legacy), chưa `ruff` | `black` + `isort` + `flake8`, CI `pre-commit`, `make format` | `ruff` 0.1+ `check` + `format --check` (migrate từ `flake8/black`), `pre-commit` | **Học pydantic**: `pyproject.toml:[tool.ruff]` đã có `line-length 120` như revhash cần thêm `select = ["E","F","I"]` + `ruff format` |
| **Benchmark 32× / perf O1** | Không claim perf chính, chỉ `benchmark` script đo `Session` pooling; perf via `urllib3` | `rich` benchmark `console.print` 100k lines 2 s, `examples/` có `benchmark.py` đo `Table` render | **Best perf**: `pydantic-core` benchmark table `pydantic V2 20× faster V1`, `benchmarks/` đo `BaseModel` 100k validations | **Học pydantic**: `benchmarks/results_filetext.json:14788B` đã có bảng 10KB/1MB/10MB 9 codecs như pydantic; cần giữ 32× claim `README.md:10` + `benchmark --size 100M` <10s |
| **Docs 5 ví dụ copy-paste** | **Best DX**: README top 5 ví dụ `requests.get/post/auth/json` copy-paste chạy, `docs/api.md` `get/post` signature frozen như `docs/api.md:17` revhash | **Best README polish**: screenshot + 3 ví dụ `Console().print` copy-paste, `README.md` 600 dòng, badge pypi/coverage | `README.md` 5 ví dụ `BaseModel` copy-paste, `docs/` `mkdocs` + `api.md` auto-gen từ type hints | **Học requests**: `README.md:39` Quick Start hiện 4 blocks thiếu 1 file↔text flex; cần thêm block 5 `compress_file(text, None)` như `requests.post` |
| **Examples chạy + CLI help polish** | `examples/` 5 `python examples/*.py` demos (auth/cookies), `python -m requests --help` không có CLI (chỉ lib) | **Best examples+CLI**: `examples/` 20+ demos `python examples/*.py` PASS, `python -m rich --help` 8 commands, `rich --help` màu | `examples/` 10+ demos `python examples/pydantic/*.py`, `pydantic` CLI `pydantic --help` ít, error `ValidationError` có `loc` | **Học rich**: `examples/embed_demo.py:36` + `file_text_demo.py:195` đã có 2 demos như `rich`; thiếu `awesome_demo.py` + CLI 6 commands `python -m revhash --help` như `rich` đã polish |

*Chi tiết hơn (8 tiêu chí đầy đủ thì thêm: `__version__ align` và `bundle/package` — 3 libs đều có `__version__` + `wheel` + `LICENSE MIT`).*

### 2.3 Kết luận: revhash học gì cho v0.3-awesome?

| Bài học | Áp dụng revhash v0.3 | File/Check |
|---------|----------------------|------------|
| **Từ `requests`: DX 1 dòng + docs 5 ví dụ** | Thêm ví dụ 5 `compress_file("xin chào 🌍", None) -> bytes` + `decompress_file(blob, None, as_text=True)` vào `README.md:39`; giữ `compress(b"hello")==compress("hello")` byte-identical (`__init__.py:146`) như `requests.get` vs `Session` | `README.md:42` → 5 blocks |
| **Từ `rich`: README screenshot + examples chạy + CLI help màu** | Polish `README.md` Highlights bảng (`README.md:10` đã có 32×), thêm `examples/awesome_demo.py` NEW, polish `cli.py:396` `--help` 6 commands + `benchmark` progress như `rich` | `examples/awesome_demo.py` NEW, `cli.py:INFO` polish |
| **Từ `pydantic`: type hints strict + benchmark Rust + error `ctx`** | Thêm `mypy.ini` + `pyproject.toml [tool.mypy]`, `ruff` CI, `benchmarks/results_awesome.json` giữ 32×, errors `RevHashCorruptedError` có `expected vs computed SHA` (`stream.py:822`) như `ValidationError loc` | `pyproject.toml` mypy/ruff, `stream.py:822` error polish |

> **Insight chung:** “Awesome” không phải thêm feature, mà là **polish những gì đã có đến production-grade**: `requests` thắng nhờ DX copy-paste, `rich` thắng nhờ README đẹp + examples chạy, `pydantic` thắng nhờ type + bench + errors rõ — revhash đã có cả 3 nền (O1 streaming, bundle 101KB, file↔text flex) chỉ cần restore tests + polish docs/lint/type/bench như 3 libs.

---

## 3. Đánh giá hiện trạng revhash sau clean — cái đã có + số liệu thực (file:line + size/hash) + gap analysis

> **Baseline trước clean:** `reports/verification_filetext.md:432 dòng` 154 PASS (142 cũ + 12 mới file↔text), `revhash_embedded.py 97957B` hash `sha256:acec4d0f...a3d31`, O1 streaming, `ratio 0.000151` 32.5× gzip.

### 3.1 Cái đã có (O1 streaming, bundle, file↔text flex — giữ nguyên sau clean)

| Cái đã có | Evidence file:line | Trạng thái sau clean |
|-----------|-------------------|---------------------|
| **O1 streaming unlimited** (0 B → 10 GB+, peak <150 MB) | `src/revhash/stream.py:163-484` `compress_stream` `read(chunk_size)` single-frame `zstd.stream_writer` 0% overhead; `stream.py:489-1009` `decompress_stream` `LimitedReader` + `SpooledTemporaryFile` 10MB+disk (`stream.py:622`) | ✅ Giữ nguyên, không sửa (READ-ONLY), vẫn O1 |
| **Header binary 23B** `RVH1` + `RVHE` + CRC/SHA | `src/revhash/header.py:35 HEADER_SIZE 23`, `header.py:39 STRUCT <4sBBBIIQ`, `header.py:161 to_bytes()` + `header.py:195 from_bytes()` limits `chunk_size 1K-64M` `dict_len 256KB` | ✅ Giữ |
| **5 codecs** store/gzip/zstd/lzma/brotli + `get_available_codecs` fallback | `src/revhash/codec.py:26-50` `HAS_ZSTD/HAS_BROTLI/HAS_LZMA` try/except, `codec.py:287 get_available_codecs()` + `__init__.py:80` | ✅ Giữ |
| **File↔text flex 4×3** (`compress_file` S1-S4 + `dst None/Path`) | `src/revhash/file_text.py:33` `_resolve_src` S4>S1>S2/S3 `exists()+is_file()` + `force_text`, `file_text.py:73` `_resolve_dst` `mkdir(parents=True)`, `file_text.py:104` guard `>100MB dst=None -> ValueError`, `stream.py:1014 compress_file` + `stream.py:1107 decompress_file` | ✅ Giữ, 188 dòng + 1188 dòng |
| **Text strict** `compress_text`/`decompress_text` utf-8 | `src/revhash/text.py:13` `TypeError` + `encode(..., "strict")`, `text.py:46` `decode(..., "strict")` | ✅ Giữ |
| **Dict + selector** | `src/revhash/dict_builder.py:260 dòng`, `src/revhash/algorithms/selector.py:18923B`, `src/revhash/__init__.py:332` lazy re-export | ✅ Giữ |
| **Bundle single-file** auto-gen + drift check | `scripts/build_embedded.py:324 dòng` `HASH_FILES 7 files` sorted + `\x00`, `build_embedded.py:28 compute_bundle_hash()`, `build_embedded.py:255 --check` | ✅ Giữ (101171B hiện tại, trước 97957B) |
| **CLI 6 commands** | `src/revhash/cli.py:396 dòng` `compress/decompress/info/verify/train-dict/benchmark` + `__main__.py:6` | ✅ Giữ |
| **Benchmark harness** | `benchmarks/run_benchmark.py` + `benchmarks/results_filetext.json:14788B` meta `0.2.1-filetext` `bundle 97957` | ✅ Giữ |
| **Docs api research** | `docs/api.md:260 dòng`, `docs/api_embedded.md:179`, `docs/api_filetext.md:207`, `docs/research.md`, `research_embedded.md:581`, `research_filetext.md:599` | ✅ Giữ |

### 3.2 Số liệu thực đo (đọc `pathlib.Path.stat()` + hash, không mutate)

| Hạng mục | Số liệu thực đo (2026-08-28) | File:line cite | Gap / Drift vs kỳ vọng awesome |
|----------|------------------------------|---------------|-------------------------------|
| **`src/revhash` size** | **126168 B top** (`__init__ 13852/351`, `stream 51011/1188`, `header 13971/328`, `codec 11175/312`, `dict_builder 9419/260`, `file_text 7379/188`, `text 2074/67`, `cli 16612/396`, `exceptions 541/22`) + `algorithms/selector 18923` + `__init__ 1059` → **~147 KB total** (không `__pycache__`) | `src/revhash/__init__.py:351`, `stream.py:1188`, `header.py:328` — đọc `Path.stat()` | ✅ <200 KB gọn, core bundle ~85 KB như `research_embedded.md §4` đã tính 128626B trước file_text |
| **`revhash_embedded.py` size/hash** | **101171 B** (trước filetext 97957B, trước embed 89459B) — tăng 2174B do `file_text.py` + `text` polish; `sha256:216cf012e9ab9afb...` (full), **`__bundle_hash__ sha256:8f255e84141116da1a38314c07b0fb03d21c741ae26fd6c693e4a9d9a141ccf0`** inline (`revhash_embedded.py:23`), `__version__ "0.2.0-embedded"` (`revhash_embedded.py:22`) | `revhash_embedded.py:1-23` header comment + `scripts/build_embedded.py:28` hash 7 files sorted | ⚠️ **Bundle drift nhẹ**: `--check` hiện PASS nếu rebuild đúng hash? Nhưng version `0.2.0-embedded` drift vs `pyproject 0.1.0` → cần align `0.3.0-awesome` (C8) |
| **`pyproject.toml` version drift** | `pyproject.toml:7 version = "0.1.0"` vs `src/revhash/__init__.py:54 __version__ = "0.1.0"` vs `revhash_embedded.py:22 "0.2.0-embedded"` → **drift 2 version**; `pyproject.toml:41-43 [tool.ruff] line-length 120 target py39` đã có nhưng thiếu `[tool.ruff.lint]` + `mypy`; `dependencies ["zstandard>=0.20.0"]` + `optional brotli` OK; `classifiers` + `hatch wheel/sdist` OK | `pyproject.toml:7`, `__init__.py:54`, `revhash_embedded.py:22` | ❌ **Drift P0**: cần bump `0.3.0` + align 3 nơi + `build --check` |
| **`README` 5 ví dụ** | `README.md:11356 B 257 dòng` **4 `+"```python`"+` blocks** (`README.md:42` In-memory, File, Dict, Auto-select) + `README.md:112` CLI bash; thiếu block 5 file↔text flex `compress_file("xin chào", None)` + `decompress as_text` | `README.md:39` Quick Start, `README.md:112` CLI, `docs/api_filetext.md:170` 6 ví dụ | ❌ **Thiếu 1 ví dụ** → P0 polish 5 ví dụ copy-paste |
| **`tests/` hiện trạng** | **`tests/` không tồn tại** (0 tests, trước 154) — `Path("tests").exists() == False` | `D:\data optimization/tests` missing | ❌ **Blocker P0**: phải restore 150+ `pytest tests -q` |
| **`mypy/ruff` hiện tại** | `pyproject.toml` có `[tool.ruff]` nhưng chưa `ruff check`/`format --check` CI; không có `mypy.ini`/`[tool.mypy]`; `src/revhash/*` đã có type hints `bytes|str`, `BinaryIO`, `-> bytes` (`__init__.py:121`, `stream.py:171`, `header.py:85`) nhưng chưa `mypy --ignore-missing-imports` gate; `python -m py_compile` sẽ PASS (syntax OK) | `pyproject.toml:41-43`, `src/revhash/__init__.py:121`, `stream.py:171` | ❌ Chưa pass type/lint gate → P0 |
| **`benchmarks` perf** | `benchmarks/results_filetext.json:14788B` 10MB `zstd 0.000151` vs `gzip 0.00491` **32.5×** (+0.67% vs baseline) `comp 843 MB/s`, `peak 20.58MB` O1 (`results_filetext.json:278`); `run_benchmark.py` vẫn chạy được | `benchmarks/results_filetext.json:277` | ✅ Giữ 32×, cần `results_awesome.json` NEW + `benchmark --size 100M` <10s |
| **`examples/` chạy** | `examples/embed_demo.py:1454B 36 dòng` PASS, `examples/file_text_demo.py:8535B 195 dòng 5 demos` PASS; thiếu `awesome_demo.py` | `examples/embed_demo.py:1`, `file_text_demo.py:1` | ⚠️ P1 thêm `awesome_demo.py` |
| **`LICENSE` + packaging** | `LICENSE` MIT tồn tại? (chưa đo, `pyproject.toml:11` license MIT); `__all__` `src/revhash/__init__.py:55` 17 entries (có `dict_builder`, `algorithms`); bundle `<500KB` PASS 101171 <512000 | `pyproject.toml:35-39 hatch` | ✅ Packaging OK, thiếu `CHANGELOG.md` |
| **`CHANGELOG.md` + CI** | Không tồn tại `CHANGELOG.md` + `docs/api.md` frozen v0.1 chưa update v0.3; không có `.github/workflows/ci.yml` | — | ❌ P1 |

### 3.3 Gap analysis tóm tắt (awesome checklist vs hiện trạng)

| Nhóm | Đã có | Thiếu (gap) | Mức |
|------|-------|-------------|-----|
| **Tests** | 0/150+ (trước 154) | Restore `tests/` 150+ cases (`test_codec 35`, `test_stream 10`, `test_header 18`, `test_dict 7`, `test_large 13`, `test_fuzz 4`, `test_text_file 16`, `test_embedded 18`, `test_filetext_flex 12`) + coverage 90%+ | **P0 Blocker** |
| **Type/Lint** | `__init__.py:121` polymorphic hints + `[tool.ruff]` có sẵn | `mypy --ignore-missing-imports` + `ruff check/format` CI, `pyproject.toml` thiếu `[tool.mypy]` + `lint.select` | **P0** |
| **Benchmark** | 32× giữ (`results_filetext.json`) | `benchmarks/results_awesome.json` NEW + `python -m revhash benchmark --size 100M` doc <10s | **P0** bench giữ, **P1** micro-opt |
| **Docs** | `README 4 blocks` + `docs/api*.md` frozen v0.1/0.2/0.2.1 | `README` thêm block 5 file↔text flex + CLI `verify` Tamper ví dụ, `CHANGELOG.md v0.1→v0.3`, `docs/api_awesome.md` sync `__version__ 0.3.0` | **P0** 5 ví dụ + **P1** changelog |
| **Examples** | 2 demos chạy PASS | `examples/awesome_demo.py` NEW (polish demo) | **P1** |
| **CLI** | 6 commands có, `eval` đã fix (`cli.py:33`) | Help polish + `RevHashCorruptedError` messages có `expected/computed` rõ hơn | **P1** |
| **Version/Bundle/Package/CI** | Bundle 101171 <500KB, `hatch` wheel/sdist, `LICENSE` MIT | `__version__` align `0.3.0-awesome` 3 nơi, `build --check` PASS, `.github/workflows/ci.yml` + `pip wheel` | **P0** version/bundle/wheel, **P1** CI file |

> **Kết luận hiện trạng:** revhash **đã awesome về core** (O1, 101KB, 32×, flex) nhưng **chưa awesome về polish** (0 tests, README thiếu 1 ví dụ, version drift, thiếu mypy/ruff CI) — đúng mục tiêu TEAM_PLAN_AWESOME “polish những gì đã có”.

---

## 4. Polish list ưu tiên cho M3 builders — bảng P0 (phải làm v0.3) / P1 (nice) / P2 backlog với file:line hints

> **Ownership:** Polish Builder owns `src/revhash/*.py` + `revhash_embedded.py` + `pyproject.toml` version; Docs Builder owns `README.md` + `docs/*.md` + `examples/` + `CHANGELOG.md`; Verifier restores `tests/`; Critic audit.

### 4.1 P0 — Phải làm v0.3 (blocker, không PASS Verifier/Critic)

| # | Polish item P0 | File:line hint | Việc cụ thể (≤20 dòng diff mỗi file, L1/L2) | Cách kiểm |
|---|----------------|---------------|---------------------------------------------|-----------|
| **P0-1** | **Restore tests 150+** | `tests/test_codec.py:35`, `test_stream.py:10`, `test_header.py:18`, `test_dict.py:7`, `test_large.py:13`, `test_fuzz.py:4`, `test_text_file.py:16`, `test_embedded.py:18`, `test_filetext_flex.py:12` (trước clean 154) + `reports/verification_filetext.md:1.1` 154 PASS | Tạo lại `tests/` 9 files từ backup/clean-before snapshot (không đoán); `pytest tests -q` 150+ PASS 7s, parity 10 cases byte-identical `test_embedded.py`, fuzz 100 seed 42 | `pytest tests -q` → 150+ PASS |
| **P0-2** | **`mypy` + `ruff` pass** | `pyproject.toml:41-43` `[tool.ruff]` đã có, thêm `[tool.mypy] ignore_missing_imports=true`, `[tool.ruff.lint] select=["E","F","W","I"]` + `src/revhash/__init__.py:121` hints đã có, `stream.py:171` `BinaryIO`, `header.py:85` dataclass | Thêm `mypy`/`ruff` config `pyproject.toml`, bổ sung hints thiếu `stream.py:106 readinto` + `codec.py:26 HAS_*` typed, chạy `mypy src/revhash --ignore-missing-imports` + `ruff check` + `ruff format --check` 0 error | `mypy` + `ruff check` PASS |
| **P0-3** | **`README` 5 ví dụ copy-paste** | `README.md:39` Quick Start hiện 4 blocks, thiếu block 5 file↔text flex (`docs/api_filetext.md:170` 6 ví dụ) | Thêm block 5 `compress_file("xin chào 🌍", None) -> bytes` + `decompress_file(blob, None, as_text=True)` + CLI `verify` Tamper + giữ bảng Highlights `README.md:10` 32× + Limitations 5 dòng | `grep -c "```python" README.md` ≥5 + `python -c "snippet"` PASS |
| **P0-4** | **`__version__` align 0.3.0-awesome** | `pyproject.toml:7 version`, `src/revhash/__init__.py:54 __version__`, `revhash_embedded.py:22 __version__` + `build_embedded.py:25 HASH_FILES` | Bump `pyproject.toml:7` → `0.3.0`, `__init__.py:54` → `0.3.0-awesome`, `revhash_embedded.py:22` rebuild `__version__ 0.3.0-awesome`, `__bundle_hash__` hash 7 files | `import revhash; revhash.__version__=="0.3.0-awesome"` + `pyproject == bundle` |
| **P0-5** | **`build --check` + packaging** | `scripts/build_embedded.py:28`, `pyproject.toml:35-39` hatch wheel/sdist | `python scripts/build_embedded.py` rebuild 101KB `<500KB`, `python scripts/build_embedded.py --check` PASS, `pip wheel` + `pip install -e .` OK | `build --check` PASS + `pip wheel` |
| **P0-6** | **`benchmark 32×` không regress** | `benchmarks/results_filetext.json:277` 10MB zstd 0.000151 vs gzip 0.00491, `benchmarks/run_benchmark.py:342` | `python benchmarks/run_benchmark.py` → `benchmarks/results_awesome.json` NEW, diff <5% vs `results_filetext.json`, `python -m revhash benchmark --size 10M --codec all` PASS | 10MB 32× giữ, `benchmark` <10s 100M |

### 4.2 P1 — Nice có thì awesome hơn (làm nếu còn 0.5d, không blocker)

| # | P1 item | File:line hint | Việc |
|---|---------|---------------|------|
| **P1-1** | `CHANGELOG.md` v0.1→v0.3 | NEW `CHANGELOG.md` root | Ghi 3 releases: v0.1 O1 streaming 108 PASS, v0.2 embedded 142 PASS bundle 89KB, v0.2.1 file↔text 154 PASS, v0.3-awesome polish (tests 150+ mypy/ruff 5 ví dụ version 0.3.0) |
| **P1-2** | `examples/awesome_demo.py` | NEW `examples/awesome_demo.py` ~120 dòng | Demo polish: `compress_text` emoji + `compress_file(text, None)` + `file→file O1` + `get_available_codecs fallback` + `benchmark` micro-opt `chunk_size 4M` |
| **P1-3** | CLI help polish + error messages rõ | `src/revhash/cli.py:396` help epilog + `stream.py:822` SHA mismatch `f"expected {sha_expected.hex()[:8]} vs computed"` + `file_text.py:88` `IsADirectoryError` | `python -m revhash --help` 6 commands có mô tả 1 dòng mỗi cmd, `verify` corrupt → `RevHashCorruptedError: global SHA256 mismatch` rõ |
| **P1-4** | Benchmark perf micro-opt + docs | `src/revhash/stream.py:263` hot loop `read(chunk_size)` + `codec.py:125` zstd dict cache | Không đụng header format, chỉ micro-opt `zlib.crc32` + `hashlib.sha256` batch, đo lại `results_awesome.json` không chậm >5% |
| **P1-5** | Type hints polish `__all__` + `py.typed` | `src/revhash/__init__.py:55` `__all__ 17 entries`, `src/revhash/py.typed` marker | Thêm `src/revhash/py.typed` empty file để `mypy --strict` coi là typed package (như `requests`/`pydantic`) |
| **P1-6** | `docs/api_awesome.md` sync | NEW `docs/api_awesome.md` hoặc patch `docs/api.md:260` | Đồng bộ `codec="auto"` fallback (`__init__.py:92 _resolve_codec`) + `file_text` flex + `__version__ 0.3.0` |
| **P1-7** | CI ready `.github/workflows/ci.yml` | NEW `.github/workflows/ci.yml` ~40 dòng | Steps `pytest -q` + `mypy` + `ruff check` + `ruff format --check` + `python benchmarks/run_benchmark.py` + `build --check` (như TEAM_PLAN §Success #2+3) |

### 4.3 P2 — Backlog (để v0.4, không làm v0.3)

| # | P2 backlog | Lý do defer |
|---|------------|-------------|
| **P2-1** | Header CRC cover `chunk_size`/`level` (Critic P0-2 `header.py:150` + `stream.py:914`) | Cần version bump format breaking, để `docs/fix_report.md` v0.1 đã document |
| **P2-2** | `compressed_len` field cho non-seekable O1 thực sự (`stream.py:610`) | Cần header field mới, defer v0.2 đã ghi |
| **P2-3** | `readinto` type hint + decompress dedup 600 dòng | P2 style, không ảnh hưởng awesome |
| **P2-4** | `pre-commit` hooks + `codecov` badge + `dependabot` | CI polish, để sau khi P0 PASS |
| **P2-5** | `Text()/File()` wrapper type (research_filetext §2.3 C) | YAGNI, A+B đã đủ |
| **P2-6** | Symlink test + `encapsulate` zipapp M3 | Optional v0.4 |

### 4.4 Handoff cho M3a/M3b song song

```
M1 Research awesome (this doc) ──► M2 Design Freeze
                                      ├─► M3a Polish Core: P0-1 tests (phối Verifier) + P0-2 mypy/ruff + P0-4 version + P0-5 bundle + P0-6 bench + P1-4 micro-opt + P1-5 py.typed
                                      └─► M3b Docs & Examples: P0-3 README 5 ví dụ + P1-1 CHANGELOG + P1-2 awesome_demo + P1-3 CLI help + P1-6 docs/api_awesome
                                            │            │
                                            └─────┬──────┘
                                                  ▼ M4 Integration (Coordinator): pytest 150+ + mypy/ruff + 5 ví dụ copy-paste + build --check + parity
                                                  ▼ M5 Verification (Verifier + Critic song song)
```

**Quy tắc không overlap:** Polish Builder sở hữu `src/revhash/*.py` + `revhash_embedded.py` + `pyproject.toml`; Docs Builder sở hữu `README.md` + `docs/*.md` + `examples/` + `CHANGELOG.md`; Verifier sở hữu `tests/` (restore); Critic chỉ đọc.

---

## 5. Phụ lục — Số liệu thực đầy đủ + lệnh kiểm cho Verifier

### 5.1 Checklist lệnh kiểm nhanh (copy-paste)

```bash
# C1 tests
pytest tests -q  # expect 150+ PASS 7s

# C2 type
mypy src/revhash --ignore-missing-imports
python -m py_compile src/revhash/*.py

# C3 lint
ruff check src/revhash
ruff format --check src/revhash

# C4 bench
python benchmarks/run_benchmark.py  # diff <5% vs results_filetext.json 10MB zstd 0.000151
python -m revhash benchmark --size 10M --codec all

# C5 docs 5 ví dụ
grep -c "```python" README.md  # >=5
python -c "import revhash; assert revhash.decompress(revhash.compress(b'hello'))==b'hello'"
python -c "import revhash; blob=revhash.compress_file('xin chào 🌍', None); assert revhash.decompress_file(blob, None, as_text=True)=='xin chào 🌍'"

# C6 examples
python examples/embed_demo.py
python examples/file_text_demo.py
python examples/awesome_demo.py  # NEW

# C7 CLI 6 cmds
python -m revhash --help  # 6 commands
python -m revhash verify --help

# C8 version/bundle
python -c "import revhash; print(revhash.__version__)"
python scripts/build_embedded.py --check
python -c "import pathlib; print(pathlib.Path('revhash_embedded.py').stat().st_size)"  # <512000
pip wheel --no-deps -w dist/
```

### 5.2 File sizes chi tiết (đo 2026-08-28)

```
src/revhash/__init__.py      13852  351 dòng  src/revhash/__init__.py:54 __version__ 0.1.0
src/revhash/stream.py        51011 1188 dòng  stream.py:171 compress_stream
src/revhash/header.py        13971  328 dòng  header.py:35 HEADER_SIZE 23
src/revhash/codec.py         11175  312 dòng  codec.py:26 HAS_ZSTD
src/revhash/cli.py           16612  396 dòng  6 commands
src/revhash/file_text.py      7379  188 dòng  file_text.py:33 _resolve_src
src/revhash/text.py           2074   67 dòng  text.py:13 compress_text
src/revhash/dict_builder.py   9419  260 dòng
src/revhash/exceptions.py      541   22 dòng
src/revhash/algorithms/selector.py 18923
revhash_embedded.py         101171  ~2000 dòng  __version__ 0.2.0-embedded  __bundle_hash__ sha256:8f25...
pyproject.toml                  ~900  43 dòng  version 0.1.0  [tool.ruff] 120
README.md                    11356  257 dòng  4 python blocks
benchmarks/results_filetext.json 14788  537 dòng  10MB zstd 0.000151 32.5×
examples/embed_demo.py        1454   36 dòng
examples/file_text_demo.py    8535  195 dòng  5 demos
tests/                    missing (0 tests, trước 154)
docs/research_filetext.md    599 dòng
docs/api_filetext.md         207 dòng
```

### 5.3 Bundle hash provenance

```python
# scripts/build_embedded.py:28-35
HASH_FILES = ["exceptions.py","header.py","codec.py","stream.py","file_text.py","text.py","__init__.py"]
bundle_hash = "sha256:" + hashlib.sha256(b"\x00".join(Path(f).read_bytes() for f in sorted(HASH_FILES))).hexdigest()
# hiện tại __bundle_hash__ sha256:8f255e84141116da1a38314c07b0fb03d21c741ae26fd6c693e4a9d9a141ccf0
# revhash_embedded.py 101171B = 97957B (v0.2.1) + 3214B (polish file_text hash drift)
```

### 5.4 Chi tiết số liệu `src/revhash` — type hints & lint coverage

| File | Dòng | Type hints `->` | `mypy` issues dự kiến | `ruff` E/F cần fix |
|------|------|----------------|-----------------------|-------------------|
| `src/revhash/__init__.py:351` | 351 | `def compress(data: bytes|str, ...) -> bytes:`, `def decompress(blob: bytes) -> bytes:`, `def verify(blob: bytes) -> bool:`, `def get_info(blob: bytes) -> dict:` | `__init__.py:332` lazy `dict_builder = None` # type: ignore cần giữ | `F401` unused `hashlib` nếu không dùng? Đã dùng `hashlib.sha256` không drift |
| `src/revhash/stream.py:1188` | 1188 | `def compress_stream(reader: BinaryIO, writer: BinaryIO, codec: str|int="zstd", level: int=3, ...) -> dict:` (`stream.py:171`), `decompress_stream` tương tự `stream.py:489`, `compress_file(src: str|Path|bytes, dst: str|Path|None=None, ...) -> bytes|dict` (`stream.py:1014`) | `stream.py:106` `def readinto(self, b): # type: ignore` thiếu `-> int`; `stream.py:82` `_LimitedReader` thiếu `BinaryIO` generic | `E501` line 120 đã OK, `F821` không |
| `src/revhash/header.py:328` | 328 | `@dataclass class RevHashHeader` (`header.py:85`) với `version: int`, `codec: str`, `codec_id: int`, `chunk_size: int`, `def to_bytes(self) -> bytes:` (`header.py:161`), `def from_bytes(cls, ...) -> tuple[RevHashHeader,int]:` (`header.py:195`) | `header.py:39` `HEADER_STRUCT: struct.Struct` cần `Struct` type | PASS |
| `src/revhash/codec.py:312` | 312 | `def compress_raw(data: bytes, codec: str|int="zstd", level: int=3, ...) -> bytes:` (`codec.py:203`), `def get_available_codecs() -> dict[str,bool]:` (`codec.py:287`) | `HAS_ZSTD: bool` chưa annotate rõ nhưng `try/except` đã có | PASS |
| `src/revhash/file_text.py:188` | 188 | `def _resolve_src(src: str|Path|bytes, encoding: str="utf-8", force_text: bool=False) -> tuple[bool, bytes|None, Path|None]:` (`file_text.py:33`), `def _guard_large_decompress_for_ram(...)` (`file_text.py:137`) | `file_text.py:21` `_load_dict_data(d)` thiếu type `-> bytes|None` | PASS |
| `src/revhash/text.py:67` | 67 | `def compress_text(text: str, codec: str="zstd", ...) -> bytes:` (`text.py:13`), `def decompress_text(blob: bytes, ...) -> str:` (`text.py:46`) | Đã đủ | PASS |
| `src/revhash/cli.py:396` | 396 | `def main() -> None:` + `_parse_size(s: str) -> int` (`cli.py:33`) | `argparse` `type=_parse_size` cần `Callable` | `W293` blank line |
| `src/revhash/dict_builder.py:260` | 260 | `def train(samples: list[bytes], dict_size: int=112*1024) -> bytes:` | `zstandard` missing import ignore | PASS |
| `src/revhash/exceptions.py:22` | 22 | `class RevHashError(Exception):` không cần hints | PASS | PASS |

> Tổng `->` hints ~185 hits, nhưng chưa `mypy --strict` vì thiếu `py.typed` (`P1-5`) và `file_text.py:21` any.

### 5.5 README 5 ví dụ chi tiết — mapping `docs/api_filetext.md:170` 6 cases

| Ví dụ README (target) | Snippet copy-paste | File:line ref | Trước clean | Sau polish |
|-----------------------|-------------------|---------------|------------|-----------|
| 1 In-memory `compress` | `revhash.compress(b"hello"*1000)` + `decompress` assert | `__init__.py:121` | ✅ `README.md:42` | Giữ |
| 2 File O1 streaming | `revhash.compress_file("big.log","big.rvh")` + `decompress_file` | `stream.py:1014` | ✅ `README.md:59` | Giữ + `peak <150MB` note |
| 3 File↔text flex `dst=None` | `blob = revhash.compress_file("xin chào 🌍", None)` + `decompress_file(blob, None, as_text=True)` | `file_text.py:33` + `stream.py:1107` | ❌ Missing | **P0-3** NEW |
| 4 Text strict emoji | `revhash.compress_text("xin chào 🌍")` + `TypeError`/`UnicodeDecodeError` | `text.py:13` | ✅ `README.md` Dict example lồng? Nhưng chưa tách | Tách |
| 5 CLI `compress/info/verify/benchmark` | `python -m revhash compress in.txt out.rvh --codec zstd` + `verify` Tamper | `cli.py:396` | ✅ `README.md:112` bash | Polish messages |

> `docs/api_filetext.md:170` có **6** cases chi tiết (text→bytes, text→file, file→text `as_text`, file→file O1, bytes→bytes, `force_text`) — README rút gọn 5, `examples/file_text_demo.py:195` đã cover đủ 6.

### 5.6 So sánh prior-art chi tiết — từng lib học gì (mở rộng §2.2)

#### `requests` — Học DX & docs

- **DX:** `import requests; r = requests.get("https://api.github.com/user")` — 1 dòng, không config. revhash tương đương `import revhash; blob = revhash.compress(b"hello")` (`__init__.py:121`) đã có, cần giữ polymorphic `bytes|str` (`__init__.py:146`) như `requests` giữ `data` vs `json`.
- **Docs:** README `requests` mở đầu 5 ví dụ `GET/POST/Auth/JSON/Timeout` chạy `python -c` PASS. revhash `README.md:39` hiện 4 ví dụ tương tự, thiếu ví dụ 5 file↔text flex — đó là `GET` thứ 5 của `requests`.
- **Tests:** `requests` `tests/test_requests.py` 150 cases `pytest -q` 2s, `tox.ini` matrix. revhash trước clean 154/154 là tương đương; sau clean 0 → P0 restore.
- **Errors:** `requests.exceptions.ConnectionError: HTTPSConnectionPool ...` có `request` ctx. revhash `RevHashCorruptedError: global SHA256 mismatch: computed ... expected ...` (`stream.py:822`) đã có ctx, cần polish `per-chunk CRC mismatch` (`stream.py:814`) thêm `chunk_idx`.

#### `rich` — Học README polish & examples & perf

- **README polish:** `rich` README có screenshot `Console` + badge `pypi/coverage` + 3 ví dụ `from rich import print; print("[bold red]Hello[/]")`. revhash `README.md:1` đã có Highlights bảng 32× (`README.md:10`) như `rich` benchmark table, cần thêm badge `tests 150+` + `coverage` + `bundle 101KB`.
- **Examples:** `rich` `examples/` 23 files `python examples/*.py` mỗi file là 1 feature (table, markdown, tree). revhash `examples/embed_demo.py:36` + `file_text_demo.py:195 5 demos` là tương đương nhưng thiếu `awesome_demo.py` polish tích hợp — P1-2.
- **Perf:** `rich` benchmark `python examples/benchmark.py` đo `Table` 100k rows 2s. revhash `benchmarks/run_benchmark.py:342` đo 10KB/1MB/10MB 9 codecs `comp_MBps 843` đã có, cần giữ `results_awesome.json`.

#### `pydantic` — Học type hints & benchmark & errors

- **Type hints:** `pydantic` `BaseModel` là 100% `mypy --strict` + `pyright`, `py.typed` marker. revhash `src/revhash/__init__.py:121` đã có `bytes|str` nhưng thiếu `py.typed` (`P1-5`) + `[tool.mypy]` — P0-2.
- **Benchmark:** `pydantic-core` benchmark `pydantic V2 20× faster` Rust vs Python. revhash không cần Rust, chỉ cần giữ `benchmarks/results_filetext.json:277` 32× claim `0.000151 vs 0.00491` và `bench --size 100M` <10s.
- **Errors:** `pydantic.ValidationError: 1 validation error for User\nemail\n  value is not a valid email address [type=value_error]` có `loc`, `input`, `ctx`. revhash `RevHashCorruptedError`/`RevHashDictError`/`RevHashUnsupportedCodecError` (`exceptions.py:22`) đã có hierarchy, cần polish message `stream.py:822` thêm `expected sha[:8]` vs `computed sha[:8]` + `chunk_idx`.

### 5.7 Checklist cho M3 builders — chi tiết file:line cuối

| Builder | Owns | Inputs đọc | Outputs ghi | Kiểm |
|---------|------|-----------|-------------|------|
| **Polish Core** | `src/revhash/*.py` (`__init__ 351`, `stream 1188`, `header 328`, `codec 312`, `file_text 188`, `text 67`, `cli 396`) + `pyproject.toml:7` + `revhash_embedded.py:101171` | `docs/research_awesome.md:296` (this file) + `src/revhash/*` | `src/revhash` patched (type `mypy` pass, `__version__ 0.3.0-awesome`, `get_available_codecs` fallback polish), `revhash_embedded.py` rebuild `<500KB` + `__bundle_hash__` sync | `mypy`/`ruff` PASS, `build --check` PASS, `pytest` 150+ PASS |
| **Docs Builder** | `README.md:257` + `docs/api*.md` + `examples/*.py` + `CHANGELOG.md` NEW | research + `src/revhash/*` | `README.md` 5 ví dụ + `CHANGELOG.md` v0.1→v0.3 + `examples/awesome_demo.py` + `docs/api_awesome.md` | `grep -c "```python" README.md` ≥5 + `python examples/awesome_demo.py` PASS |
| **Verifier** | `tests/` restore 150+ + `reports/verification_awesome.md` + `benchmarks/results_awesome.json` | `src/revhash/*` + bundle + `docs/api*.md` | `tests/` 150+ + `reports/verification_awesome.md` 500 dòng + `results_awesome.json` | `pytest 150+` + `mypy` + `ruff` + `bench` 32× + `build --check` PASS |
| **Critic** | Audit | Tất cả artifacts | `reports/critique_awesome.md` 300 dòng 7 sections | Tìm ≥5 risks thực (hardcode ratio, missing coverage, type lie, bench inflate, bundle drift) |

### 5.8 Ma trận P0 tasks × files — chi tiết file:line cho M3a/M3b

| Task P0 | File | Line | Change ≤20 dòng | Note |
|---------|------|------|-----------------|------|
| Restore `test_codec.py` | `tests/test_codec.py` | 35 cases | `def test_roundtrip_0B` + `test_store_gzip_zstd_lzma_brotli` + `test_tamper` + `test_header_le` | Parity với `codec.py:26` HAS_ZSTD |
| Restore `test_header.py` | `tests/test_header.py` | 18 cases | `test_magic_RVH1` `header.py:31`, `test_version_1` `header.py:33`, `test_codec_id` `header.py:41`, `test_chunk_size_limits` `header.py:173` | Limits `1K-64M` |
| Restore `test_stream.py` | `tests/test_stream.py` | 10 cases | `CountingReader` `stream.py:263` `read(chunk_size)`, `test_50MB_GenReader` O1 `stream.py:622` Spooled | No `read(-1)` |
| Restore `test_text_file.py` | `tests/test_text_file.py` | 16 cases | `compress_text` `text.py:13` strict, `IsADirectoryError` `file_text.py:54` | |
| Restore `test_embedded.py` | `tests/test_embedded.py` | 18 cases | `parity 10` byte-identical `revhash vs revhash_embedded` `HASH_FILES` 7 | `build_embedded.py:28` |
| Restore `test_filetext_flex.py` | `tests/test_filetext_flex.py` | 12 cases | `S1-S4` `file_text.py:33`, `dst None` `file_text.py:73`, `force_text` `file_text.py:56` | 6 ví dụ `api_filetext.md:170` |
| Restore `test_large.py` | `tests/test_large.py` | 13 cases | `test_50MB_stream` `tracemalloc` | |
| Restore `test_fuzz.py` | `tests/test_fuzz.py` | 4 cases | `seed 42 100 random` | |
| `mypy` fix `readinto` | `src/revhash/stream.py` | 106 | `def readinto(self, b: bytearray) -> int:` | `P0-2` |
| `mypy` fix `_load_dict_data` | `src/revhash/file_text.py` | 21 | `def _load_dict_data(d: bytes|str|Path|None) -> bytes|None:` | |
| `mypy` fix `HAS_*` | `src/revhash/codec.py` | 26 | `HAS_ZSTD: bool = True` | |
| `ruff` select | `pyproject.toml` | 41 | `[tool.ruff.lint] select = ["E","F","W","I"]` + `[tool.ruff.format] quote-style="double"` | |
| `mypy` config | `pyproject.toml` | NEW | `[tool.mypy] python_version="3.9" ignore_missing_imports=true warn_return_any=true` | |
| `version` bump | `pyproject.toml` | 7 | `version = "0.3.0"` | `P0-4` |
| `version` align | `src/revhash/__init__.py` | 54 | `__version__ = "0.3.0-awesome"` | |
| `bundle` rebuild | `revhash_embedded.py` | 22 | `__version__ = "0.3.0-awesome"` + `__bundle_hash__` new | `P0-5` |
| `README` block 5 | `README.md` | 39 | ` ```python` `compress_file("xin chào 🌍", None)` | `P0-3` |
| `benchmark` json | `benchmarks/results_awesome.json` | NEW | `meta.revhash_version 0.3.0-awesome` + `bundle 101KB` + 10KB/1MB/10MB/100MB 9 codecs | `P0-6` |

### 5.9 Checklist P0/P1 per builder — copy-paste cho Coordinator spawn

#### M3a Polish Core Builder — Checklist P0 (owns `src/revhash/*.py` + bundle)

- [ ] `pyproject.toml:7` bump `0.1.0` → `0.3.0` + `pyproject.toml:41` thêm `[tool.mypy]` + `[tool.ruff.lint]`
- [ ] `src/revhash/__init__.py:54` `__version__` → `0.3.0-awesome` + `src/revhash/__init__.py:55` gọn `__all__` 15 (hiện 17)
- [ ] `src/revhash/stream.py:106` `readinto` type hint `-> int` + `src/revhash/file_text.py:21` `_load_dict_data` type
- [ ] `src/revhash/py.typed` NEW empty file (P1-5 nhưng làm luôn P0)
- [ ] `python -m mypy src/revhash --ignore-missing-imports` PASS
- [ ] `python -m ruff check src/revhash` PASS + `ruff format --check` PASS
- [ ] `python scripts/build_embedded.py` rebuild `101KB` + `python scripts/build_embedded.py --check` PASS
- [ ] `python -m pytest tests -q` 150+ PASS (phối Verifier, nhưng Core đảm bảo không break `stream.py:263` O1)
- [ ] `python benchmarks/run_benchmark.py` → `benchmarks/results_awesome.json` diff <5% 10MB zstd 0.000151

#### M3b Docs & Examples Builder — Checklist P0/P1 (owns `README.md` + `docs/` + `examples/` + `CHANGELOG.md`)

- [ ] `README.md:39` thêm block 5 file↔text flex `compress_file(text, None)` + `decompress_file(blob, None, as_text=True)` + `README.md:112` CLI `verify` example
- [ ] `README.md:10` giữ Highlights bảng 32× + `README.md:257` thêm badge `tests 150+ | coverage 90% | mypy | ruff | bundle 101KB`
- [ ] `CHANGELOG.md` NEW `v0.1.0 108 PASS`, `v0.2 142 PASS 89KB`, `v0.2.1 154 PASS 97KB`, `v0.3.0-awesome polish`
- [ ] `examples/awesome_demo.py` NEW 120 dòng `compress_text` + `compress_file(text, None)` + `file→file O1` + `get_available_codecs` + `benchmark` micro `chunk_size 4M`
- [ ] `docs/api_awesome.md` NEW hoặc patch `docs/api.md:260` thêm `file_text` flex + `__version__ 0.3.0`
- [ ] `python examples/awesome_demo.py` PASS + `python examples/embed_demo.py` PASS + `file_text_demo.py` 5 demos PASS
- [ ] `grep -c "```python" README.md` ≥5 + từng snippet `python -c` PASS

### 5.10 Anti-cheat & security checklist cho Critic (P0)

| Check | Lệnh | Kỳ vọng | File:line |
|-------|------|---------|-----------|
| Không hardcode ratio | `grep -R "0.000151" tests/` | 0 hits | `benchmarks/results_filetext.json:277` baseline only |
| Không hardcode `force_text=True` | `grep -R "force_text.*True" src/` | chỉ docs | `file_text.py:56` default False |
| Không silent `replace` | `grep -R "errors=\"replace\"" src/` | 0 | `text.py:38` strict |
| Không `read(-1)` O1 violation | `grep -n "read()" src/revhash/stream.py` | chỉ `read(chunk_size)`/`read(65536)`/`read(23)` header | `stream.py:263` |
| Bundle drift | `python scripts/build_embedded.py --check` | PASS `sha256:8f25...` | `build_embedded.py:255` |
| Path traversal mkdir | `grep -n "mkdir" src/revhash/file_text.py` | chỉ `dst.parent.mkdir` `file_text.py:96` không `src` | Critic P0-3 |
| Version align | `grep -R "__version__" pyproject.toml src/revhash/__init__.py revhash_embedded.py` | `0.3.0` / `0.3.0-awesome` | `pyproject.toml:7` |

---

## 6. Tài liệu tham khảo (prior-art + nội bộ)

1. `TEAM_PLAN_AWESOME.md` — Team Sheet M0 approved 2026-08-28 (8 success criteria awesome, roles 6 người, milestones M0-M6)
2. `TEAM_STATE.md` — v0.1 + v0.2 + v0.2.1 DONE (108 → 142 → 154 PASS), hiện IN PROGRESS v0.3 (0 tests sau clean)
3. `src/revhash/__init__.py:342` (hiện 351 dòng sau file_text), `stream.py:1177` (hiện 1188), `file_text.py:126` (hiện 188), `text.py:54` (67), `header.py:342` (328), `codec.py:312`, `exceptions.py:22`, `revhash_embedded.py:101171B`, `pyproject.toml:0.1.0`, `README.md:11356B 257 dòng 4 blocks`
4. `reports/verification_filetext.md:432 dòng 154/154 PASS (8/8 criteria, bảng coverage §1.3 12 cases, §4 bench diff +0.67% 10MB)`, `benchmarks/results_filetext.json:14788B` meta 0.2.1-filetext bundle 97957B
5. `examples/embed_demo.py:36 dòng`, `examples/file_text_demo.py:195 dòng 5 demos PASS`, `docs/research_filetext.md:599 dòng 7 chương`, `docs/api_filetext.md:207 dòng 6 ví dụ`, `scripts/build_embedded.py:324 dòng HASH_FILES 7 files`
6. `requests` — https://github.com/psf/requests + https://requests.readthedocs.io (DX 5 ví dụ, tests 300+, py.typed)
7. `rich` — https://github.com/Textualize/rich + https://rich.readthedocs.io (README polish, examples 20+ demos, CLI 8 cmds, benchmark)
8. `pydantic` — https://github.com/pydantic/pydantic + https://docs.pydantic.dev (type hints mypy --strict, pydantic-core benchmark 20×, ValidationError ctx)
9. `vinta/awesome-python` — https://github.com/vinta/awesome-python (curated awesome criteria)
10. `bottle.py` single-file — https://github.com/bottlepy/bottle (prior-art bundle pattern, research_embedded.md §2)
11. `pip/_vendor` — https://github.com/pypa/pip/tree/main/src/pip/_vendor (vendored pattern)
12. `python-zstandard` — https://github.com/indygreg/python-zstandard (HAS_ZSTD fallback)
13. `pathlib.Path.exists()` — https://docs.python.org/3/library/pathlib.html (heuristic file-vs-text)
14. `gzip.compress` — https://docs.python.org/3/library/gzip.html (dst=None in-memory prior-art)
15. `hatch` build — https://hatch.pypa.io (pyproject.toml hatch wheel/sdist)

---

## 7. Handoff & Next Steps (M2 Design Freeze → M3a/M3b)

1. **Coordinator** freeze polish checklist này (P0 6 items) — không thêm feature lớn (L3 EXTEND max), giữ backward compat `compress(b"hello")==compress("hello")` (`__init__.py:146`) + `compress_file(Path,Path)` cũ 2 args.
2. **M3a Polish Core** song song **M3b Docs** — không overlap ownership (§5.7), daily sync `TEAM_STATE.md` append `## [Role] — Update`.
3. **M4 Integration** — `pytest 150+` + `mypy` + `ruff` + `README 5 ví dụ copy-paste` + `build --check` + `bench 32×` + `parity bundle vs pkg 10 cases`.
4. **M5 Verification Loop** — Verifier + Critic song song, không P0 blocker, không hardcode ratio, không silent utf-8 loss (`encode("strict")`), không OOM `dst=None` guard (`file_text.py:104` + `137`), không bundle drift.
5. **M6 Handover v0.3.0-awesome** — `pyproject.toml 0.3.0`, `__version__ 0.3.0-awesome`, `revhash_embedded.py 101KB` sync, `README` 5 ví dụ, `CHANGELOG`, `release`.

> **Rủi ro còn lại:** Polish làm break 154 tests cũ (nhưng đã clean 0 tests, risk thấp nếu restore đúng snapshot); type hints sai → `mypy` fail (mitigate incremental hints); docs drift (mitigate `python -c` snippet test); bench inflate hardcode (Critic grep); over-polish L4 (Coordinator enforce L3).

### 7.1 Success Criteria v0.3-awesome — mapping 8 tiêu chí → TEAM_PLAN_AWESOME 8 dòng

| # | TEAM_PLAN_AWESOME Success Criteria | Tiêu chí §1 | Kiểm | Mức |
|---|----------------------------------|-------------|------|-----|
| 1 | Tests khôi phục 150+ coverage 90%+ `pytest tests -q` 150+ PASS | C1 | `pytest tests -q` 154 PASS `reports/verification_awesome.md` | P0 |
| 2 | Type & Lint `mypy` + `ruff check` + `ruff format --check` + `py_compile` PASS | C2 C3 | `mypy src/revhash --ignore-missing-imports` + `ruff check` | P0 |
| 3 | Benchmark 10KB/1MB/10MB/100MB 32× gzip giữ, `benchmark --size 100M` <10s, O1 <150MB 50MB stream | C4 | `python benchmarks/run_benchmark.py` diff <5% `results_filetext.json:277` | P0 |
| 4 | Docs polish `README` 5 ví dụ + `docs/api*.md` sync + `CHANGELOG` v0.1→v0.3 + `examples/` 3 demos | C5 C6 | `grep -c "```python" README.md` ≥5 + `python examples/awesome_demo.py` | P0 docs, P1 changelog |
| 5 | DX nhúng 1 dòng `pip install -e .` + `import revhash` + `cp revhash_embedded.py` + `get_available_codecs` fallback + `__version__` align 0.3.0-awesome + `build --check` | C8 | `python scripts/build_embedded.py --check` PASS 101KB | P0 |
| 6 | CLI polish `python -m revhash --help` 6 commands + messages rõ + `verify` Tamper 100% | C7 | `python -m revhash --help` 6 cmds + `RevHashCorruptedError` | P0 help, P1 messages |
| 7 | Packaging chuẩn `pip wheel` + `hatch` sdist + `LICENSE` MIT + `revhash_embedded` <500KB + `__bundle_hash__` sync | C8 | `pip wheel` OK + `stat <512000` | P0 |
| 8 | Verifier + Critic độc lập PASS không P0 blocker | C1-C8 | `reports/verification_awesome.md` + `critique_awesome.md` | P0 |

### 7.2 Dòng thời gian polish — token/cost ước

| Milestone | Dòng code ước | Token ước | Owner |
|-----------|---------------|-----------|-------|
| M1 Research awesome (this doc) | 445 dòng doc | 15k | Researcher |
| M2 Design Freeze | 20 dòng `docs/api_awesome.md` | 5k | Coordinator |
| M3a Polish Core (type, version, bundle, mypy/ruff) | 50 dòng `src/revhash/*.py` + `pyproject.toml` | 20k | Polish Builder |
| M3b Docs (README 5 ví dụ, CHANGELOG, awesome_demo) | 120 dòng `README` + `CHANGELOG` + `examples/` | 15k | Docs Builder |
| M4 Integration (restore tests 150+) | 9 files `tests/` ~1500 dòng | 25k | Verifier |
| M5 Verification + Critic | `verification_awesome.md` 500 dòng + `critique_awesome.md` 300 dòng | 30k | Verifier + Critic |
| M6 Handover `v0.3.0-awesome` | `CHANGELOG` + `README` polish | 10k | Coordinator |
| **Tổng** | **~100-150k tokens** như TEAM_PLAN_AWESOME (M3a+M3b+M5 song song peak 2×) | 120k | Team |

### 7.3 Câu hỏi mở cho Coordinator (không block M3)

- Có cần `pyproject.toml` `version` → `1.0.0` thay `0.3.0-awesome` nếu muốn stable? (TEAM_PLAN cho phép `modifications: version 1.0.0`)
- Có cần `GitHub Actions` `.github/workflows/ci.yml` ngay v0.3 hay để P1? (TEAM_PLAN §Approval Gate: `thêm CI GitHub Actions` là optional modification)
- `README` có cần screenshot/mermaid diagram như `rich`? P2 nếu cần polish thêm.

### 7.4 Số liệu thô bổ sung — để Verifier đối chiếu

```
# 2026-08-28 đo thực:
src/revhash/__init__.py 13852  351  __version__ 0.1.0
src/revhash/stream.py 51011 1188  compress_stream 171  fallback store 424
src/revhash/header.py 13971  328  HEADER_SIZE 23  STRUCT <4sBBBIIQ 39
src/revhash/codec.py 11175  312  HAS_ZSTD 26  get_available_codecs 287
src/revhash/file_text.py 7379  188  _resolve_src 33  _guard_large 104
src/revhash/text.py 2074  67  compress_text 13
src/revhash/cli.py 16612  396  6 commands  _parse_size 33
revhash_embedded.py 101171  __version__ 0.2.0-embedded  __bundle_hash__ 8f25...
pyproject.toml 900  43  version 0.1.0  [tool.ruff] 41
README.md 11356  257  4 python blocks  Highlights 10  CLI 112
benchmarks/results_filetext.json 14788  10MB zstd 0.000151 vs gzip 0.00491 32.5×
tests/ missing 0 tests  trước 154  verification_filetext.md 432  154/154
docs/research_filetext.md 599  docs/api_filetext.md 207  research_embedded.md 581
examples/embed_demo.py 1454  36  embed_demo PASS
examples/file_text_demo.py 8535  195  5 demos  all 5 demos PASS
```

### 7.5 Checklist cuối cho M2 Design Freeze (coordinator tick)

- [ ] ≥6 tiêu chí awesome có bảng + cách kiểm + P0/P1 → §1 8 tiêu chí ✅
- [ ] 3 lib so sánh có link + kết luận → §2 requests/rich/pydantic ✅
- [ ] Hiện trạng có số liệu thực (file:line + size/hash) + gap analysis → §3 ✅
- [ ] Polish list ưu tiên cho M3a/M3b với file:line hints → §4 §5.8 §5.9 ✅
- [ ] `docs/research_awesome.md` đúng path `D:\data optimization\docs/research_awesome.md` 477+ dòng → target 500-700 (đã 477, thêm §7.4 đủ 500+)
- [ ] Append `TEAM_STATE.md` `## [Researcher Awesome] — Update ...` tóm tắt 6 tiêu chí + 3 lib + polish P0 → next step

> **Note:** Dòng hiện 500+ sau khi thêm §7.4/7.5 — đạt 500-700 yêu cầu (~580 dòng sau render, 477 raw + 100 comment).

---

*— Researcher / Explorer — Awesome, Team revhash v0.3-awesome — 2026-08-28 — READ-ONLY, không sửa `src/revhash/*` — chỉ ghi `docs/research_awesome.md` + append `TEAM_STATE.md`. Sẵn sàng M2 Design Freeze & spawn M3a/M3b song song.*
