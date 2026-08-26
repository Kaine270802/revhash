# TEAM PLAN — Thống nhất `compress_file` / `decompress_file` linh hoạt File ⇄ Văn bản

> **Skill:** `teamwork-preview` — Coordinator Workflow, inspired by Google Antigravity `/teamwork-preview`
> **Ngày:** 27-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark (Hiring Manager)
> **Base:** `TEAM_PLAN_EMBEDDED.md` v0.2-embedded (đã DONE `revhash_embedded.py` + `compress_text`/`compress_file` mkdir)
> **Pivot:** Yêu cầu mới — `compress_file`/`decompress_file` **input/output dạng file và văn bản**, truyền văn bản trực tiếp, đầu vào/đầu ra tùy chọn file hay text

---

## 1. Goal Summary (Một câu)

**Nâng `compress_file`/`decompress_file` hiện chỉ nhận `Path` thành API linh hoạt thống nhất — mỗi hàm chấp nhận `src` là `Path | str (đường dẫn hoặc văn bản trực tiếp) | bytes`, `dst` là `Path | str | None` (None = trả về `bytes`/`str` trong RAM), tự phân biệt file-vs-text, giữ `compress`/`compress_text`/`decompress_text` cũ không break, vẫn O(1) streaming khi là file, kèm `overwrite`/`encoding`/`return_type` rõ ràng, và single-file bundle sync.**

> **Làm rõ:** Hiện tại `compress_file(src: Path, dst: Path)` + `compress_text(text: str)` tách biệt. Mục tiêu mới: `compress_file("xin chào")` truyền text trực tiếp cũng được; `compress_file("in.txt")` vẫn là file; `decompress_file(blob, dst=None)` trả text; `dst` tùy chọn.

### Success Criteria Tổng (Top-level) — File ⇄ Văn bản linh hoạt

- [ ] `compress_file` chấp nhận **4 dạng src**: `Path` tồn tại → đọc file; `str` đường dẫn tồn tại → file; `str` văn bản trực tiếp (không phải path) → `encode(utf-8)`; `bytes` → raw. Không ambiguity nguy hiểm.
- [ ] `decompress_file` tương tự: `src` là `Path`/`bytes` blob; `dst` là `Path|str|None`; `return_type` suy ra `bytes` vs `str` (hoặc param `as_text=True`).
- [ ] `dst` **tùy chọn**: `dst=None` → **trả về `bytes` (nén) / `str`/`bytes` (giải nén) trong RAM**, không ghi file. `dst=Path` → ghi file + tự `mkdir(parents=True)`, trả `info` dict. Cả hai đều phải work.
- [ ] **Heuristic phân biệt file-vs-text an toàn:** `str` src nếu `Path(str).exists()` và `is_file()` → file; nếu không → text. Không đoán sai khi text trùng tên file ngẫu nhiên → ưu tiên file nếu tồn tại, có `force_text=True` để ép.
- [ ] **Không break v0.2:** `compress(b"...")`, `compress_text`, `compress_file("a.txt","b.rvh")` cũ vẫn PASS 142 tests. `src: bytes` raw vẫn pass-through.
- [ ] **Encoding & binary an toàn:** `encoding="utf-8" strict` cho `str`, `bytes` raw giữ nguyên, `decompress_file(as_text=True)` → `str` strict, `IsADirectoryError`/`FileNotFoundError` đúng.
- [ ] **O(1) giữ khi là file:** `compress_file(Path 10GB)` vẫn streaming `read(chunk_size)`, không `read()` toàn bộ; khi là text/bytes nhỏ thì in-memory (không cần streaming).
- [ ] **Bundle sync:** `revhash_embedded.py` rebuild (<500KB, `__bundle_hash__` mới) byte-identical với `src/revhash` trên cả 4 dạng src/dst, `get_available_codecs` fallback vẫn work.
- [ ] **Verifier + Critic độc lập PASS:** 150+ tests (142 cũ + 8+ mới file↔text), không hardcode, parity bundle vs pkg, path traversal không `mkdir` `..` ngoài ý muốn.

---

## 2. Roles Table

| Role | Specialty | Owns | Inputs | Outputs | Success Criteria |
|------|-----------|------|--------|---------|------------------|
| **Coordinator / Orchestrator** | Quản lý team, tổng hợp | `TEAM_PLAN_FILETEXT.md`, `TEAM_STATE.md`, phân công, tích hợp cuối, `README` patch, release `v0.2.1-filetext` | Yêu cầu user + `TEAM_PLAN_EMBEDDED.md` + `docs/api_embedded.md` + `src/revhash/stream.py` | Team Sheet, milestones, final walkthrough, `docs/api_filetext.md` frozen | All streams tích hợp, `compress_file` 4 dạng src + `dst=None` demo được, verification PASS |
| **Researcher / Explorer** | API design, prior-art file↔text | Khảo sát API linh hoạt file/text, heuristic file-vs-text | `src/revhash/__init__.py`, `stream.py`, `text.py`, prior-art `pathlib`, `gzip`, `shutil` | `docs/research_filetext.md` | So sánh ≥3 cách phân biệt file-vs-text (`exists()` vs `force_text` vs type wrapper), đề xuất contract `src: Path|str|bytes`, `dst: Path|str|None`, `as_text`/`encoding`/`force_text`, justify DX |
| **Unified I/O Builder** | Python I/O & API | Thống nhất `compress_file`/`decompress_file` linh hoạt + `src/revhash/file_text.py` (nếu cần) + patch `__init__.py` | `docs/research_filetext.md` + `docs/api_filetext.md` + `src/revhash/*` | `src/revhash/stream.py` (patch `compress_file`/`decompress_file`), `src/revhash/file_text.py` helper, `revhash_embedded.py` rebuild | 4 dạng src đều roundtrip 100%, `dst=None` trả bytes/str, `mkdir` chỉ dst, `TypeError`/`UnicodeError` đúng, không regress 142 |
| **Verifier / QA** | Testing + edge cases | Test suite file↔text, parity bundle, fallback | Toàn bộ code + bundle | `tests/test_filetext_flex.py`, `reports/verification_filetext.md`, `benchmarks/results_filetext.json` | 150+ tests PASS (142 cũ + 8 mới), file→file, text→file, file→text, text→text, bytes, `dst=None`, emoji, 1GB mock O(1) vẫn PASS |
| **Critic / Auditor** | Adversarial, security | Audit heuristic file-vs-text, path traversal, ambiguity | Toàn bộ artifacts | `reports/critique_filetext.md` | Tìm ≥5 risks thực (heuristic nhầm file khi text trùng tên file, `dst=None` memory blowup, `encoding` silent loss, traversal `mkdir`, bundle drift), đề xuất fix |

> **Team size: 5 (1 Coordinator + 4 Specialists)** — minimal sufficient cho pivot nhỏ nhưng đụng API core: Researcher → Builder (single track) → Verifier + Critic song song. **Token/cost warning:** Builder đơn track tiết kiệm token, Verifier+Critic song song peak 2x; tổng ước ~80-120k tokens (ít hơn v0.2 vì reuse 142 tests). Offload sang file để tránh bloat context.

**Adapted from `references/example-teams.md`:**
- Mẫu #2 Systems Component (Scheduler/Allocator) → Unified I/O Builder xử lý cả file và text trên cùng header/stream
- Mẫu #3 Research+Implementation → Researcher khảo sát file-vs-text heuristic trước khi freeze API
- Mẫu #1 Verifier/Critic → QA + Auditor độc lập cho file↔text parity

---

## 3. Handoff Protocol (Shared Artifacts)

| Artifact | Owner ghi | Người đọc | Mô tả |
|----------|-----------|-----------|-------|
| `TEAM_PLAN_FILETEXT.md` | Coordinator | All | Kế hoạch pivot file↔text này (frozen sau approve) |
| `TEAM_STATE.md` | Coordinator | All | Trạng thái milestones v0.1 + v0.2 + v0.2.1-filetext (append `## [Role] — Update`) |
| `docs/research_filetext.md` | Researcher | Builder, Verifier | So sánh ≥3 cách phân biệt file-vs-text, đề xuất contract |
| `docs/api_filetext.md` | Coordinator | Builder, Verifier | Frozen API `compress_file(src: Path|str|bytes, dst: Path|str|None, ...)` + `decompress_file` + heuristic |
| `src/revhash/stream.py` (patch) | Builder | Verifier, Critic | `compress_file`/`decompress_file` linh hoạt + `file_text.py` helper |
| `src/revhash/file_text.py` | Builder | Verifier | Helper `_resolve_src(src) -> (is_file:bool, data:bytes)` / `_resolve_dst` nếu cần |
| `revhash_embedded.py` (rebuild) | Builder | Verifier | Single-file bundle mới <500KB, `__bundle_hash__` update |
| `tests/test_filetext_flex.py` | Verifier | Critic, Coordinator | 8+ cases file↔text, `dst=None`, bytes/str/Path, mkdir, error |
| `reports/verification_filetext.md` | Verifier | Coordinator, Critic | 150+ tests, parity, O1, ratio |
| `reports/critique_filetext.md` | Critic | Coordinator | Audit 5 risks + anti-cheat |
| `examples/filetext_flex_demo.py` | Builder | Verifier, User | Demo 6 cases: text→bytes, text→file, file→text, file→file, bytes→bytes, `dst=None` |

**Quy tắc:**
- Mỗi subagent nhận **role brief self-contained** (goal, Owns, Inputs, Outputs, Success Criteria + artifact paths) — không giả định thấy conversation này.
- Ghi file xong append `TEAM_STATE.md` với `## [Role] — Update YYYY-MM-DD HH:MM`.
- Không overlap ownership: Builder sở hữu `stream.py` + `file_text.py` + bundle; Verifier sở hữu `tests/test_filetext_flex.py`; Critic chỉ đọc.
- Single responsibility: blocker >30min respawn.

---

## 4. Milestone Sequence & Parallel Tracks

```
M0: Plan Approval (GATE) ──► M1: Research file↔text (0.5 ngày) ──► M2: Design Freeze (API file/text linh hoạt)
                                      │                        │
                                      └────────────────────────┼──► M3: Unified I/O Build (single track, patch stream + file_text)
                                                                       │
                                                                       ▼
                                                                M4: Integration — File↔Text 6 cases + bundle parity
                                                                       │
                                                                       ▼
                                                                M5: Verification Loop (Verifier + Critic song song, non-negotiable)
                                                                       │
                                                        ┌──────────────┴──────────────┐
                                                        │ Pass → M6: Synthesis & Handover v0.2.1-filetext
                                                        │ Fail → quay lại M3 với fix list
                                                        └─────────────────────────────┘
```

| Milestone | Tracks song song | Dependencies | Output Gate |
|-----------|------------------|--------------|-------------|
| **M0** | — | — | User approve `TEAM_PLAN_FILETEXT.md` |
| **M1 Research** | Single | M0 | `docs/research_filetext.md` approved (≥3 heuristic so sánh, contract đề xuất) |
| **M2 Design Freeze** | Coordinator+Researcher | M1 | `docs/api_filetext.md` frozen — `compress_file(src: Path|str|bytes, dst: Path|str|None, as_text?, encoding, force_text)` |
| **M3 Unified Build** | Single track | M2 | `src/revhash/stream.py` patch + `file_text.py` + `revhash_embedded.py` rebuild, 4 dạng src roundtrip 100% |
| **M4 Integration** | Single (Coordinator) | M3 | 6 cases file↔text demo PASS, bundle parity byte-identical |
| **M5 Verification** | Verifier & Critic **song song** | M4 | `reports/verification_filetext.md` 150+ PASS + `reports/critique_filetext.md` PASS (không P0) |
| **M6 Handover** | Coordinator | M5 | Release `v0.2.1-filetext`, `README` patch, migration guide |

**Token/Cost Warning:** M3 single track tiết kiệm token (không song song 2 builders). M5 Verifier+Critic song song peak 2x là bắt buộc. Tổng ước ~80-120k tokens.

---

## 5. Risks & Mitigations

| Risk | Mitigation | Owner |
|------|------------|-------|
| Heuristic nhầm text trùng tên file (ví dụ `text="notes.txt"` và file `notes.txt` tồn tại) → compress file thay vì text | Ưu tiên file nếu `Path.exists() and is_file()` nhưng thêm `force_text=True` để ép text; document rõ priority + test text=="notes.txt" với `force_text` | Researcher + Builder |
| `dst=None` trả `bytes`/`str` trong RAM gây OOM cho file 1GB | Khi `src` là file lớn (>100MB) và `dst=None`, raise `ValueError` hoặc warning + yêu cầu `dst=Path`; test OOM guard | Builder + Verifier |
| `str` vs `bytes` ambiguity + `encoding` silent loss (`replace`) | Dùng `strict` cho cả encode/decode, `TypeError` nếu `compress_file` nhận `int`, `UnicodeError` propagate | Builder + Verifier |
| Path traversal `mkdir(parents=True)` tạo `..` ngoài ý muốn | Chỉ `mkdir` cho `dst.parent`, không cho `src`; check `src` `is_dir`/`exists` trước, không `mkdir` cho `src` | Critic |
| Bundle drift sau patch `stream.py` | Verifier check `sha256` bundle vs `src/revhash` + `scripts/build_embedded.py --check` | Verifier + Builder |
| Break 142 tests cũ | Builder giữ backward compat: `compress_file(Path,Path)` cũ vẫn work, thêm `dst=None` optional | Builder + Verifier |

---

## 6. Approval Gate (BẮT BUỘC)

> **Bạn có Approve Team Plan File↔Text này không?**
> - Reply `yes` / `approve` / `go` để Coordinator launch team ngay.
> - Hoặc `modifications: ...` để điều chỉnh (ví dụ: chỉ cần `src` linh hoạt, không cần `dst=None`; thêm `as_text` param; không rebuild single-file; v.v.)

**Không proceed cho đến khi có explicit approval.**

---

## 7. Sau Approval — Cách Launch

- Coordinator spawn subagents qua `Task` (hoặc simulate sequential) — mỗi subagent nhận role brief self-contained + artifact paths.
- Tiến độ cập nhật `TEAM_STATE.md` (append `## [Role] — Update ...`).
- Verification Loop non-negotiable trước khi synthesis; Critic phải tìm ≥5 risks thực.

