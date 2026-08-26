# TEAM PLAN — Thư viện Python Tối Ưu Hash Data Có Thể Dịch Ngược (Reversible Compression)

> **Skill:** `teamwork-preview` (Coordinator Workflow) — inspired by Google Antigravity `/teamwork-preview`
> **Ngày:** 25-08-2026
> **Workspace:** `D:\data optimization`
> **Coordinator:** Muse Spark (Hiring Manager / Orchestrator)

---

## 1. Goal Summary (Một câu)

**Xây dựng một thư viện Python mã nguồn mở tên `revhash` / `py-optimash` có khả năng "hash" (nén/encode) dữ liệu văn bản với tỉ lệ nén tối ưu nhất có thể, tiết kiệm dung lượng tối đa nhưng vẫn decode khôi phục 100% byte-identical dữ liệu gốc — hỗ trợ KHÔNG GIỚI HẠN dung lượng (từ vài KB đến nhiều GB, ví dụ 100MB/1GB/10GB+) vẫn hiệu quả tốt nhờ streaming/chunking O(1) memory, API đơn giản và có benchmark chứng minh.**

> **Làm rõ thuật ngữ:** "Hash dịch ngược được" ở đây bản chất là **Reversible Compression / Lossless Encoding**, không phải cryptographic hash (SHA/md5). Thư viện sẽ cung cấp `encode()` / `decode()` (hoặc `compress()` / `decompress()`) với checksum để đảm bảo toàn vẹn.

### Success Criteria Tổng (Top-level) — KHÔNG GIỚI HẠN DUNG LƯỢNG

- [ ] Encode **mọi kích thước** (từ 0B → 100MB → 1GB → 10GB+) → giảm dung lượng đáng kể (mục tiêu: tốt hơn gzip -6, tiệm cận zstd-19 / lzma trên text tiếng Việt/Anh lặp; ratio ổn định không suy giảm khi file lớn)
- [ ] Decode khôi phục **100% byte-identical** với mọi size (SHA256 gốc == SHA256 sau decode), có test tự động
- [ ] **Streaming O(1) memory — cốt lõi cho unlimited:** không bao giờ load toàn bộ file vào RAM; chunk 1-8MB (configurable), memory bounded < 150MB bất kể input 100MB hay 10GB; hỗ trợ file lớn hơn RAM, hỗ trợ `compress_file`/`decompress_file` streaming + `compress_stream`/`decompress_stream` cho pipe/socket
- [ ] Throughput tuyến tính O(n): encode ~80-150 MB/s, decode ~150-250 MB/s (trên backend zstd/lzma), scale tuyến tính khi tăng size; benchmark công khai trên nhiều mốc (10KB, 10MB, 100MB, 1GB)
- [ ] API Python đơn giản: `revhash.compress(data) -> bytes`, `revhash.decompress(blob) -> bytes`, `revhash.compress_file(in, out)`, `decompress_file`, `revhash.compress_stream(reader, writer)`, CLI `python -m revhash` — tất cả đều streaming-aware
- [ ] Tính robust với unlimited: resume-friendly header, checksum per-chunk (CRC32/xxhash) + global SHA256, xử lý file rỗng, file 1 byte, file sparse, file không chia hết chunk
- [ ] Packaging chuẩn: `pyproject.toml`, `pip install -e .`, type hints, docs, 90%+ test coverage
- [ ] Được Verifier + Critic độc lập xác nhận không hardcode, không fake ratio, test thực trên multi-size (không chỉ 100MB)

---

## 2. Roles Table

| Role | Specialty | Owns | Inputs | Outputs | Success Criteria |
|------|-----------|------|--------|---------|------------------|
| **Coordinator / Orchestrator** | Quản lý team, tổng hợp | TEAM_PLAN.md, TEAM_STATE.md, phân công, tích hợp cuối, báo cáo bàn giao | Yêu cầu user + output các role | Team Sheet, milestones, final release | Tất cả stream tích hợp, verification pass, user demo được trên **mọi size (KB → GB+)** với memory bounded |
| **Researcher / Explorer** | Lý thuyết nén, khảo sát prior-art | Khảo sát thuật toán, benchmark thư viện sẵn có | Mục tiêu + dataset mẫu | `docs/research.md`, `benchmarks/baseline_report.md` | So sánh ≥6 thuật toán (Huffman, LZ77/LZ78, LZMA, BWT+MTF, ANS/rANS, Zstd, Brotli, Dictionary), chọn stack tối ưu cho **unlimited streaming** (đánh giá cả ratio, speed, memory, khả năng chunk), có số liệu multi-size (10KB/100MB/1GB), justify bằng tài liệu |
| **Core Engine Builder** | Python Systems / Streaming I/O | Kiến trúc thư viện, core API, streaming chunk O(1) memory, header/checksum, file I/O | Research report + API spec | `src/revhash/` (`codec.py`, `stream.py`, `header.py`, `__init__.py`), `pyproject.toml` | API ổn định, streaming **true O(1) memory** (không load toàn bộ file), encode/decode byte-identical trên **mọi size (0B → 10GB+)**, chunk configurable, có type hints + docstring |
| **Optimization Builder** | Thuật toán nén / Text-specific tuning | Adaptive dictionary, hybrid codec (LZ + Huffman + ANS), pre-processing text, **streaming-adaptive** | Research report + Core Engine interfaces | `src/revhash/algorithms/`, `src/revhash/dict_builder.py`, adaptive tuning | Vượt gzip -6 ≥15% ratio trên text lặp **ở mọi size** (không suy giảm khi scale), tự học dictionary streaming cho file >10MB/1GB, không làm chậm decode >2x, ratio ổn định khi chunk |
| **Verifier / QA** | Testing + Benchmark + Edge cases | Test suite, benchmark harness, **multi-size stress test (0B → 1GB+)** | Toàn bộ code + sample data | `tests/`, `benchmarks/run_benchmark.py`, `reports/verification.md` | 90%+ coverage, fuzz/random bytes, **empty / 1B / 10KB / 10MB / 100MB / 500MB-1GB (streaming)** đều pass byte-identical, benchmark multi-size có số liệu thực thi, memory profile chứng minh O(1), không silent data loss |
| **Critic / Auditor** | Adversarial review, Security, Anti-cheat | Review chéo, anti-pattern scan | Toàn bộ artifacts | `reports/critique.md` | Tìm ≥ top 5 rủi ro thực (hardcode ratio, bỏ qua checksum, memory leak, insecure header, false success), đề xuất fix cụ thể |

> **Team size: 6 (1 Coordinator + 5 Specialists)** — minimal sufficient cho task có 3 workstream song song (Research → Core + Optimization) + 2 verification độc lập. Cảnh báo token/cost: team lớn 5 builders song song ~ tăng 3-4x token so với single-agent; sẽ offload sang subagent/file để giảm bloat context chính.

**Adapted from `references/example-teams.md`:**
- Mẫu #2 Systems Component (Scheduler/Allocator) → áp cho Core Engine + Optimization (2 workers song song trên interfaces chung)
- Mẫu #3 Research+Implementation → Researcher dẫn dắt lựa chọn thuật toán
- Mẫu #4 Data Pipeline Verifier → Verifier đảm bảo lineage byte-identical

---

## 3. Handoff Protocol (Shared Artifacts)

Tất cả roles **không được** giữ context riêng mà phải ghi ra file để Coordinator tích hợp:

| Artifact | Owner ghi | Người đọc | Mô tả |
|----------|-----------|-----------|-------|
| `TEAM_PLAN.md` | Coordinator | All | Kế hoạch này (frozen sau approve) |
| `TEAM_STATE.md` | Coordinator (tổng hợp) | All | Trạng thái milestone, decision log, blockers |
| `docs/research.md` | Researcher | Core, Optimization, Verifier | Khảo sát thuật toán + khuyến nghị stack |
| `benchmarks/baseline_report.md` | Researcher | All | Số liệu baseline gzip/zstd/lzma trên dataset mẫu |
| `src/revhash/**/*` | Core + Optimization | Verifier, Critic | Code thư viện |
| `benchmarks/run_benchmark.py` + `benchmarks/results.json` | Verifier | Coordinator, Critic | Harness đo ratio/speed/memory **multi-size (10KB/100MB/1GB)** thực thi |
| `tests/**/*` | Verifier | All | Test suite (unit, integration, fuzz, **multi-size 0B→1GB+**) |
| `reports/verification.md` | Verifier | Coordinator, Critic | Báo cáo coverage + edge cases |
| `reports/critique.md` | Critic | Coordinator | Adversarial audit |
| `docs/api.md` + `README.md` | Coordinator (tổng hợp) | User | Tài liệu sử dụng cuối |

**Quy tắc:**
- Mỗi subagent nhận **role brief self-contained** (goal, Owns, Inputs, Outputs, Success Criteria + đường dẫn artifact chung) — không giả định subagent thấy conversation này.
- Ghi file xong phải update `TEAM_STATE.md` với `## [Role] — Update YYYY-MM-DD HH:MM`
- Không overlap ownership file (tránh merge conflict): Core sở hữu `codec.py/stream.py`, Optimization sở hữu `algorithms/*`, Verifier sở hữu `tests/*`
- Single responsibility: nếu blocker >30min, respawn role mới với summary.

---

## 4. Milestone Sequence & Parallel Tracks

```
M0: Plan Approval (GATE) ──► M1: Research (1-2 ngày) ──► M2: Design Freeze (API spec)
                                      │                        │
                                      └────────────────────────┼──► M3a: Core Engine Build (song song, O(1) streaming)
                                                               └──► M3b: Optimization Build (song song, streaming-adaptive)
                                                                       │            │
                                                                       └─────┬──────┘
                                                                             ▼
                                                                      M4: Integration & Benchmark UNLIMITED (multi-size: 10KB/100MB/1GB+ streaming, O(1) memory check)
                                                                             │
                                                                             ▼
                                                                      M5: Verification Loop (Verifier + Critic độc lập, non-negotiable, multi-size)
                                                                             │
                                                              ┌──────────────┴──────────────┐
                                                              │ Pass → M6: Synthesis & Handover
                                                              │ Fail → quay lại M3a/M3b với fix list
                                                              └─────────────────────────────┘
```

| Milestone | Tracks chạy song song | Dependencies | Output Gate |
|-----------|------------------------|--------------|-------------|
| **M0** | — | — | User approve TEAM_PLAN.md |
| **M1 Research** | Single track | M0 | `docs/research.md` approved by Coordinator |
| **M2 Design Freeze** | Coordinator + Researcher sync | M1 | API spec (`docs/api.md` draft) frozen |
| **M3a Core** | **Song song với M3b** | M2 | Core API + streaming O(1) pass unit tests cơ bản (test 10GB+ bằng streaming mock) |
| **M3b Optimization** | **Song song với M3a** | M2 | Hybrid codec vượt baseline gzip **và giữ ratio khi streaming chunk** |
| **M4 Integration** | Single track (Coordinator merge) | M3a + M3b | **Multi-size** encode/decode thành công (10KB, 100MB, 500MB-1GB streaming), memory bounded chứng minh, `benchmarks/results.json` có số liệu multi-size |
| **M5 Verification** | Verifier & Critic chạy **song song độc lập** | M4 | `reports/verification.md` + `reports/critique.md` đều pass multi-size (không có critical issue, memory O(1) verified) |
| **M6 Handover** | Coordinator | M5 | Release `v0.1.0`, README (hướng dẫn unlimited), demo script multi-size, TODO/Risks |

**Token/Cost Warning:** M3a+M3b song song tiết kiệm wall-time nhưng tốn peak token 2x. M5 Verifier+Critic song song là bắt buộc để tránh optimism. Ước tính tổng ~ 120k-180k tokens nếu chạy full team với code generation + benchmarks.

---

## 5. Risks & Mitigations

| Risk | Mitigation | Owner |
|------|------------|-------|
| Chọn sai thuật toán → ratio kém, đặc biệt khi streaming chunk làm giảm ratio | Researcher benchmark ≥6 thuật toán **cả ở chế độ streaming chunked vs. whole-file** trên multi-size; chọn thuật toán có dictionary training streaming | Researcher |
| Pure Python quá chậm cho file GB+ | Cho phép dùng `zstd`/`lzma` backend (Rust/C) qua binding + lớp Python wrapper tối ưu; benchmark speed/ratio tradeoff **theo GB** | Core + Optimization |
| Memory blowup khi file > RAM (GB+) | Streaming **true O(1)** + chunk 1-8MB, **không bao giờ** load toàn bộ; test memory profile với `tracemalloc`/`psutil` trên 1GB+ mock, giới hạn <150MB | Core + Verifier |
| Hardcode/mock ratio, chỉ test 100MB | Critic kiểm tra decode thực + SHA256 **trên mọi size**, Verifier chạy fuzz random + test 1GB streaming thực | Critic/Verifier |
| Chunk boundary làm hỏng decode / mất data | Header per-chunk + checksum + global SHA256, test file không chia hết chunk, test power-failure mid-stream | Core + Verifier |
| Over-engineering library | Coordinator enforce minimal API, YAGNI, release v0.1 trước, nhưng vẫn đảm bảo unlimited contract | Coordinator |

---

## 6. Approval Gate (BẮT BUỘC)

> **Bạn có Approve Team Plan này không?**
> - Reply `yes` / `approve` / `go` để Coordinator launch team ngay.
> - Hoặc ghi `modifications: ...` để điều chỉnh (ví dụ: đổi team size, thêm target ratio, đổi tên lib, yêu cầu hỗ trợ binary/file ảnh ngoài text, v.v.)

**Không proceed cho đến khi có explicit approval.**

---

## 7. Sau Approval — Cách Launch

- Coordinator sẽ spawn subagents qua `Task` tool (hoặc simulate sequential focused sessions nếu host không support parallel).
- Mỗi subagent nhận role brief self-contained + artifact paths.
- Tiến độ cập nhật liên tục vào `TEAM_STATE.md`.
- Verification Loop là **non-negotiable** trước khi bàn giao cuối.

