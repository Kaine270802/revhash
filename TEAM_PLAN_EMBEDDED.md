# TEAM PLAN — Thư viện nhúng revhash (Embedded) — File + Text trực tiếp

> **Skill:** `teamwork-preview` (Coordinator Workflow) — Google Antigravity style
> **Ngày:** 26-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark
> **Phiên bản:** v0.2-embedded (pivot từ v0.1.0-rc unlimited)
> **Tham chiếu:** `references/example-teams.md` — đã đọc, adapt không copy blindly

---

## 1. Goal Summary (Một câu)

**Biến `revhash` hiện có thành thư viện nhúng (embedded) sử dụng trực tiếp — chỉ `import revhash` hoặc copy 1 file là chạy, hỗ trợ thống nhất cả `str`/`bytes` (text) và `file`/`đường dẫn` với cùng một API đơn giản, zero-copy embed, không đòi hỏi cài đặt phức tạp, vẫn giữ O(1) streaming unlimited nhưng đóng gói để nhúng thẳng vào dự án khác (vendored) — bao gồm single-file bundle `revhash_embedded.py` và package chuẩn `pip install -e .`.**

> **Embedded =** copy 1 file hoặc 1 folder vào repo khác là chạy; không service, không server; API trực tiếp cho text (`str`) và file (path). Khác v0.1-rc (tập trung benchmark unlimited) — v0.2 này tập trung **trải nghiệm nhúng**.

### Success Criteria Tổng (Top-level) — Embedded

- [ ] **Nhúng 1 dòng:** `import revhash` sau khi `pip install -e .` HOẶC `copy revhash_embedded.py` vào dự án khác → chạy ngay, không config
- [ ] **Text trực tiếp:** `revhash.compress_text("xin chào") -> bytes` / `decompress_text(blob) -> str` (tự handle `str<->utf-8`, `bytes` vẫn hỗ trợ `compress`/`decompress`)
- [ ] **File trực tiếp:** `revhash.compress_file("in.txt","out.rvh")` / `decompress_file` chấp nhận `str|Path`, tự tạo parent dirs, trả `info` dict; cũng hỗ trợ `compress_path` alias cho DX
- [ ] **Single-file bundle:** `revhash_embedded.py` (~1 file, <500KB) chứa toàn bộ core (header+codec+stream) + fallback stdlib nếu thiếu `zstandard` → vẫn chạy (downgrade sang `gzip`/`store`), `sha256` verify bundle
- [ ] **Zero-deps graceful:** Nếu `zstandard`/`brotli` không có, không crash import; `get_available_codecs()` báo, `compress(..., codec="zstd")` raise `Unsupported` rõ ràng, auto fallback sang `gzip` khi `codec="auto"`
- [ ] **DX nhúng:** `__all__` gọn, type hints, docstring ví dụ copy-paste, `examples/embed_demo.py` chạy được sau khi copy 1 file
- [ ] **Không regress:** O(1) streaming, 108 tests vẫn PASS, ratio 32× gzip giữ nguyên, benchmark không chậm hơn 5%
- [ ] **Verifier + Critic độc lập:** PASS với tiêu chí nhúng (không hardcode, single-file byte-identical với package)

---

## 2. Roles Table

| Role | Specialty | Owns | Inputs | Outputs | Success Criteria |
|------|-----------|------|--------|---------|------------------|
| **Coordinator / Orchestrator** | Quản lý team, tổng hợp | TEAM_PLAN_EMBEDDED.md, TEAM_STATE.md, phân công, tích hợp cuối, release `v0.2-embedded` | Yêu cầu user + `TEAM_PLAN.md` v0.1 + Critic fixes | Team Sheet, milestones, final walkthrough, `README_EMBEDDED.md` | All streams tích hợp, single-file + package đều demo được `text` + `file`, verification PASS |
| **Researcher / Explorer** | Embedded patterns, DX, prior-art | Khảo sát cách nhúng Python lib (single-file bundle, vendored, zero-deps fallback) | `src/revhash/*` hiện tại, `references/example-teams.md`, mẫu `requests`/`bottle` single-file | `docs/research_embedded.md` | So sánh ≥4 pattern nhúng (single-file, vendored pkg, stdlib-only fallback, import hook), đề xuất bundle strategy + API `compress_text`/`compress_file` hợp nhất, justify DX |
| **Core Embed Builder** | Python Packaging / Single-file bundle | Bundle `revhash_embedded.py`, lazy deps, `__init__.py` nhúng, `compress_text`/`decompress_text` | `docs/research_embedded.md` + `src/revhash/*` v0.1 | `revhash_embedded.py`, `src/revhash/__init__.py` (patch), `src/revhash/text.py` | `import revhash` chạy khi thiếu zstd (fallback), `compress_text(str)->bytes` và `compress(data: bytes|str)` thống nhất, bundle `sha256` khớp với pkg |
| **API DX Builder** | DX / File + Text API | Thống nhất API file+text, path handling, examples | `docs/research_embedded.md` + Core Embed interfaces | `src/revhash/text.py`, `src/revhash/file_api.py` (hoặc patch `stream.py`), `examples/embed_demo.py`, `examples/file_text_demo.py` | `compress_file("a.txt","a.rvh")` tự tạo dirs, `compress_text`/`decompress_text` str roundtrip 100%, 5 ví dụ copy-paste trong `README_EMBEDDED.md` chạy được |
| **Verifier / QA** | Testing + edge cases + embed | Test suite embed, single-file parity, fallback | Toàn bộ code + bundle | `tests/test_embedded.py`, `tests/test_text_file.py`, `reports/verification_embedded.md` | 120+ tests PASS (108 cũ + 12 mới embed), bundle vs pkg byte-identical trên 10 cases, thiếu zstd vẫn PASS fallback, `pytest tests -q` 0 fail |
| **Critic / Auditor** | Adversarial, anti-cheat, security | Review chéo embed + DX | Toàn bộ artifacts | `reports/critique_embedded.md` | Tìm ≥5 risks thực (hardcode bundle, silent utf-8 loss, path traversal, import side-effect, bundle drift), đề xuất fix |

> **Team size: 6 (1 Coordinator + 5 Specialists)** — minimal sufficient cho pivot nhúng: Researcher dẫn dắt pattern → 2 builders song song (Core Embed + API DX) → 2 verification độc lập. Cảnh báo token/cost: song song 2 builders + 2 verifiers ~ 3-4x token so với single-agent (~100-150k tokens); offload sang file để tránh bloat context chính. Nếu cần tiết kiệm, có thể gộp Core+API thành 1 builder (giảm xuống 5 người).

**Adapted from `references/example-teams.md`:**

- Mẫu #2 Systems Component (Scheduler/Allocator) → Core Embed + API DX song song trên interface chung (`docs/api.md` + `research_embedded.md`)
- Mẫu #3 Research+Implementation → Researcher khảo sát embedded patterns trước khi bundle
- Mẫu #1 Full-Stack Verifier/Critic → Verifier + Critic độc lập cho embed parity

---

## 3. Handoff Protocol (Shared Artifacts)

| Artifact | Owner ghi | Người đọc | Mô tả |
|----------|-----------|-----------|-------|
| `TEAM_PLAN_EMBEDDED.md` | Coordinator | All | Kế hoạch pivot nhúng này (frozen sau approve) |
| `TEAM_STATE.md` | Coordinator | All | Trạng thái milestones, decision log (append `## [Role] — Update`) |
| `docs/research_embedded.md` | Researcher | Core, API, Verifier | Khảo sát 4+ pattern nhúng + đề xuất API text/file thống nhất |
| `revhash_embedded.py` (root) | Core Embed | Verifier, Critic | Single-file bundle (<500KB, hash) |
| `src/revhash/text.py` | API DX / Core Embed | Verifier | `compress_text`/`decompress_text` (str<->bytes) |
| `src/revhash/__init__.py` (patch) | Core Embed | All | Lazy deps, `get_available_codecs()`, thống nhất `compress(bytes|str)` |
| `examples/embed_demo.py` + `file_text_demo.py` | API DX | Verifier, User | Demo copy-1-file nhúng + file+text |
| `tests/test_embedded.py` + `test_text_file.py` | Verifier | Critic, Coordinator | Parity bundle vs pkg + fallback |
| `reports/verification_embedded.md` | Verifier | Coordinator, Critic | Báo cáo 120+ tests, bundle hash, fallback |
| `reports/critique_embedded.md` | Critic | Coordinator | Audit anti-cheat + risks |
| `README_EMBEDDED.md` + `README.md` update | Coordinator | User | Hướng dẫn nhúng 1 dòng + file+text |

**Quy tắc:**

- Mỗi subagent nhận **role brief self-contained** (goal, Owns, Inputs, Outputs, Success Criteria + artifact paths) — không giả định thấy conversation này.
- Ghi file xong append `TEAM_STATE.md` với `## [Role] — Update ...`
- Không overlap ownership: Core sở hữu `revhash_embedded.py` + `__init__.py`, API DX sở hữu `text.py` + `examples/*`, Verifier sở hữu `tests/test_embed*`
- Respawn nếu blocker >30min.

---

## 4. Milestone Sequence & Parallel Tracks

```
M0: Plan Approval (GATE) ──► M1: Research Embedded (1 ngày) ──► M2: Design Freeze (API text/file + bundle spec)
                                      │                        │
                                      └────────────────────────┼──► M3a: Core Embed Build (single-file + lazy deps)
                                                               └──► M3b: API DX Build (text+file thống nhất + examples)
                                                                       │            │
                                                                       └─────┬──────┘
                                                                             ▼
                                                                      M4: Integration — Bundle parity + File+Text demo (single-file vs pkg byte-identical)
                                                                             │
                                                                             ▼
                                                                      M5: Verification Loop (Verifier + Critic song song, non-negotiable)
                                                                             │
                                                              ┌──────────────┴──────────────┐
                                                              │ Pass → M6: Synthesis & Handover v0.2-embedded
                                                              │ Fail → quay lại M3a/M3b với fix list
                                                              └─────────────────────────────┘
```

| Milestone | Tracks song song | Dependencies | Output Gate |
|-----------|------------------|--------------|-------------|
| **M0** | — | — | User approve `TEAM_PLAN_EMBEDDED.md` |
| **M1 Research** | Single | M0 | `docs/research_embedded.md` approved |
| **M2 Design Freeze** | Coordinator+Researcher | M1 | API `compress_text`/`compress_file` + bundle spec frozen |
| **M3a Core Embed** | **Song song M3b** | M2 | `revhash_embedded.py` import được khi thiếu zstd, `compress_text` ok |
| **M3b API DX** | **Song song M3a** | M2 | `text.py` + 5 ví dụ `examples/*` chạy được |
| **M4 Integration** | Single (Coordinator) | M3a+M3b | Bundle vs pkg parity 10 cases byte-identical, file+text demo OK |
| **M5 Verification** | Verifier & Critic **song song** | M4 | `reports/verification_embedded.md` + `critique_embedded.md` PASS (không P0) |
| **M6 Handover** | Coordinator | M5 | Release `v0.2-embedded`, `README_EMBEDDED.md`, migration guide v0.1→v0.2 |

**Token/Cost Warning:** M3a+M3b song song + M5 Verifier+Critic song song là bắt buộc nhưng tốn peak 2x token. Tổng ước ~100-150k tokens cho pivot nhúng (ít hơn v0.1 vì reuse code). Offload aggressively sang file.

---

## 5. Risks & Mitigations

| Risk | Mitigation | Owner |
|------|------------|-------|
| Single-file bundle drift so với pkg (không sync) | Verifier test parity byte-identical 10 cases + `sha256` bundle vs pkg; CI check hash | Core + Verifier |
| Zero-deps fallback làm ratio kém, user tưởng lỗi | `get_available_codecs()` + warning khi fallback sang gzip/store; docs nêu rõ | Core + API |
| `str` vs `bytes` silent loss (utf-8) | `compress_text` ép `str→utf-8` + `decompress_text` `utf-8` strict, test emoji/tiếng Việt; `compress(bytes|str)` detect type | API + Verifier |
| Path traversal / auto mkdir side-effect | `compress_file` `Path.mkdir(parents=True, exist_ok=True)` chỉ cho output, không cho input `..`; check `dict_len` limit đã có | Critic |
| Over-engineering embed (quá nhiều API) | Coordinator enforce `compress`/`decompress`/`compress_text`/`compress_file` 4 hàm chính, YAGNI | Coordinator |

---

## 6. Approval Gate (BẮT BUỘC)

> **Bạn có Approve Team Plan Embedded này không?**
> - Reply `yes` / `approve` / `go` để Coordinator launch team ngay.
> - Hoặc `modifications: ...` để điều chỉnh (ví dụ: không cần single-file, chỉ cần `pip` nhúng; thêm hỗ trợ `async`; đổi tên bundle; v.v.)

**Không proceed cho đến khi có explicit approval.**

---

## 7. Sau Approval — Cách Launch

- Coordinator spawn subagents qua `Task` (hoặc simulate sequential) — mỗi subagent nhận role brief self-contained + artifact paths.
- Tiến độ cập nhật `TEAM_STATE.md`.
- Verification Loop non-negotiable trước khi synthesis.

