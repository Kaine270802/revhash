"""CLI for revhash — python -m revhash

Commands:
    compress    input output [--codec zstd] [--level 3] [--chunk-size 4M] [--dict path]
    decompress  input output [--dict path]
    info        blob
    verify      blob
    train-dict  corpus/* --out dict --size 112K
    benchmark   --size 100M --codec all
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import sys
import time
from typing import List

from . import __version__, decompress_file, compress_file, get_info, verify as verify_blob
from .exceptions import RevHashCorruptedError, RevHashDictError

# Optional dict_builder import
try:
    from . import dict_builder  # type: ignore

    HAS_DICT_BUILDER = True
except Exception:
    dict_builder = None  # type: ignore
    HAS_DICT_BUILDER = False


def _parse_size(s: str | int) -> int:
    if isinstance(s, int):
        return s
    s = str(s).strip()
    units = {"B": 1, "K": 1024, "KB": 1024, "M": 1024**2, "MB": 1024**2, "G": 1024**3, "GB": 1024**3}
    upper = s.upper().replace(" ", "")
    # try integer directly
    try:
        return int(float(upper))
    except Exception:
        pass
    # try unit suffix (e.g. 4M, 112K)
    for suffix, mult in sorted(units.items(), key=lambda x: -len(x[0])):
        if upper.endswith(suffix):
            num = upper[: -len(suffix)]
            if not num:
                continue
            try:
                return int(float(num) * mult)
            except Exception:
                continue
    # No eval fallback (removed per Critic P2-1 — prevents arithmetic bomb like "2**30")
    raise argparse.ArgumentTypeError(f"invalid size '{s}' (expected e.g. 4M, 112K, 1048576)")


def _cmd_compress(args: argparse.Namespace) -> int:
    src = pathlib.Path(args.input)
    dst = pathlib.Path(args.output)
    dict_data = None
    if args.dict:
        dict_path = pathlib.Path(args.dict)
        if not dict_path.exists():
            print(f"[error] dict not found: {dict_path}", file=sys.stderr)
            return 1
        dict_data = dict_path.read_bytes()
        print(f"[revhash] using dict {dict_path} ({len(dict_data)} B)")
    chunk_size = _parse_size(args.chunk_size) if isinstance(args.chunk_size, str) else args.chunk_size
    try:
        info = compress_file(
            src, dst, codec=args.codec, level=args.level, chunk_size=chunk_size, dict_data=dict_data, show_progress=True
        )
        assert isinstance(info, dict)  # compress_file with dst=Path returns dict
        print(
            f"[ok] {src} -> {dst} | {info['original_size']} -> {info['compressed_size']} bytes | ratio {info['ratio']:.6f} | chunks {info['chunks']}"
        )
        return 0
    except Exception as exc:
        print(f"[error] compress failed: {exc}", file=sys.stderr)
        return 2


def _cmd_decompress(args: argparse.Namespace) -> int:
    src = pathlib.Path(args.input)
    dst = pathlib.Path(args.output)
    dict_data = None
    if args.dict:
        dict_path = pathlib.Path(args.dict)
        if dict_path.exists():
            dict_data = dict_path.read_bytes()
    try:
        info = decompress_file(src, dst, dict_data=dict_data, show_progress=True)
        assert isinstance(info, dict)  # decompress_file with dst=Path returns dict
        print(
            f"[ok] {src} -> {dst} | {info['compressed_size']} -> {info['original_size']} bytes | codec {info['codec']}"
        )
        return 0
    except Exception as exc:
        print(f"[error] decompress failed: {exc}", file=sys.stderr)
        return 2


def _cmd_info(args: argparse.Namespace) -> int:
    p = pathlib.Path(args.input)
    if not p.exists():
        print(f"[error] not found: {p}", file=sys.stderr)
        return 1
    # Avoid loading huge blob into RAM for info (Critic P0-3): use streaming for large files
    try:
        size = p.stat().st_size
        if size > 50 * 1024 * 1024:
            # Large file: parse header only (O1), avoid read_bytes() whole file
            print(f"[warn] large file ({size} B) — header-only info to avoid OOM", file=sys.stderr)
            import struct
            from .header import RevHashHeader

            with open(p, "rb") as rf:
                hdr_bytes = rf.read(23)
                if len(hdr_bytes) < 23:
                    raise RevHashCorruptedError("truncated header")
                magic, version, codec_id, level, chunk_size, dict_len, original_size = struct.unpack(
                    "<4sBBBIIQ", hdr_bytes
                )
                if dict_len > 256 * 1024:
                    raise RevHashCorruptedError("dict_len too large")
                if chunk_size < 1024 or chunk_size > 64 * 1024 * 1024:
                    raise RevHashCorruptedError("chunk_size out of range")
                dict_data = rf.read(dict_len) if dict_len else b""
                header = RevHashHeader(
                    codec=codec_id,
                    level=level,
                    chunk_size=chunk_size,
                    dict_data=dict_data if dict_len else None,
                    original_size=original_size,
                )
                rf.seek(0, 2)
                total = rf.tell()
                info = {
                    "codec": header.codec,
                    "codec_id": header.codec_id,
                    "level": header.level,
                    "chunk_size": header.chunk_size,
                    "original_size": header.original_size if header.original_size != 0xFFFFFFFFFFFFFFFF else "UNKNOWN",
                    "compressed_size": total,
                    "ratio": (total / header.original_size)
                    if header.original_size and header.original_size != 0xFFFFFFFFFFFFFFFF
                    else 0,
                    "has_dict": dict_len > 0,
                    "chunks": header.num_chunks,
                    "dict_len": dict_len,
                    "version": header.version,
                    "header_len": 23 + dict_len,
                    "file_size": total,
                }
            print(f"File: {p} (streaming header-only)")
            for k, v in info.items():
                print(f"  {k}: {v}")
            print("  verify: SKIPPED for large file (use 'revhash verify' streaming)")
            return 0
        else:
            blob = p.read_bytes()
            info = get_info(blob)
            print(f"File: {p}")
            for k, v in info.items():
                print(f"  {k}: {v}")
            ok = verify_blob(blob)
            print(f"  verify: {'OK' if ok else 'FAIL'}")
            return 0
    except Exception as exc:
        print(f"[error] info failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2


def _cmd_verify(args: argparse.Namespace) -> int:
    p = pathlib.Path(args.input)
    if not p.exists():
        print(f"[error] not found: {p}", file=sys.stderr)
        return 1
    dict_data = None
    if args.dict:
        dict_path = pathlib.Path(args.dict)
        if dict_path.exists():
            dict_data = dict_path.read_bytes()
            if len(dict_data) > 256 * 1024:
                print(f"[warn] dict file large ({len(dict_data)} B) — may be attacker-controlled", file=sys.stderr)
    size = p.stat().st_size
    # For large files (>50MB), avoid loading whole blob into RAM — use streaming verify O1 (Critic P0-3)
    if size > 50 * 1024 * 1024:
        print(f"[info] large file ({size} B) — streaming verify O(1) to avoid OOM", file=sys.stderr)
        try:
            import tempfile, pathlib as _pl

            # Stream decompress to temp null file to verify SHA/CRC without loading whole blob
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp_path = _pl.Path(tmp.name)
            try:
                from . import decompress_file

                # Decompress to temp file (O1 streaming via decompress_stream)
                decompress_file(p, tmp_path, dict_data=dict_data)
                # If decompress succeeds, verify passed (SHA/CRC checked)
                print(f"[ok] {p}: verify PASS (streaming CRC+SHA OK)")
                return 0
            except RevHashCorruptedError as exc:
                print(f"[error] {p}: verify FAIL (corrupted): {exc}", file=sys.stderr)
                return 2
            except RevHashDictError as exc:
                print(f"[error] {p}: dict error: {exc}", file=sys.stderr)
                return 2
            finally:
                try:
                    tmp_path.unlink(missing_ok=True)
                except:
                    pass
        except Exception as exc:
            print(f"[error] verify failed: {exc}", file=sys.stderr)
            return 2
    else:
        blob = p.read_bytes()
        ok = verify_blob(blob, dict_data=dict_data)
        if ok:
            print(f"[ok] {p}: verify PASS (CRC+SHA OK)")
            return 0
        else:
            print(f"[error] {p}: verify FAIL (corrupted)", file=sys.stderr)
            try:
                from . import decompress

                decompress(blob, dict_data=dict_data)
            except RevHashCorruptedError as exc:
                print(f"  details: {exc}", file=sys.stderr)
            except RevHashDictError as exc:
                print(f"  dict error: {exc}", file=sys.stderr)
            return 2


def _cmd_train_dict(args: argparse.Namespace) -> int:
    if not HAS_DICT_BUILDER:
        print(
            "[error] dict_builder not available (Optimization Builder not yet installed). Expected src/revhash/dict_builder.py",
            file=sys.stderr,
        )
        print("  Hint: This command requires Optimization Builder's dict_builder module.", file=sys.stderr)
        return 1
    # Collect corpus files
    corpus_patterns: List[str] = args.corpus
    files: List[pathlib.Path] = []
    for pat in corpus_patterns:
        import glob

        matched = glob.glob(pat)
        for m in matched:
            p = pathlib.Path(m)
            if p.is_file():
                files.append(p)
        if not matched:
            p = pathlib.Path(pat)
            if p.is_file():
                files.append(p)
    if not files:
        print(f"[error] no corpus files matched: {corpus_patterns}", file=sys.stderr)
        return 1
    dict_size = _parse_size(args.size) if isinstance(args.size, str) else args.size
    sample_size = _parse_size(args.sample_size) if isinstance(args.sample_size, str) else args.sample_size
    out_path = pathlib.Path(args.out)
    print(
        f"[revhash] training dict from {len(files)} files, dict_size={dict_size}, sample_size={sample_size} -> {out_path}"
    )
    try:
        # Prefer train_from_files if available
        if hasattr(dict_builder, "train_from_files"):
            dict_data = dict_builder.train_from_files(
                [str(p) for p in files], dict_size=dict_size, sample_size=sample_size
            )  # type: ignore
        elif hasattr(dict_builder, "train"):
            samples = []
            for p in files:
                data = p.read_bytes()[:sample_size]
                if data:
                    samples.append(data)
            dict_data = dict_builder.train(samples, dict_size=dict_size)  # type: ignore
        else:
            print("[error] dict_builder has no train API", file=sys.stderr)
            return 1
        # Save
        if hasattr(dict_builder, "save"):
            dict_builder.save(dict_data, str(out_path))  # type: ignore
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(dict_data, (bytes, bytearray)):
                out_path.write_bytes(bytes(dict_data))
            else:
                # zstd dict object
                out_path.write_bytes(dict_data.as_bytes())  # type: ignore
        print(f"[ok] dict saved to {out_path} ({len(dict_data) if hasattr(dict_data, '__len__') else 'unknown'} bytes)")
        return 0
    except Exception as exc:
        print(f"[error] train-dict failed: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2


def _cmd_benchmark(args: argparse.Namespace) -> int:
    # Lightweight benchmark mimicking bench_runner: generate synthetic data and measure compress/decompress.
    # For Verifier harness compatibility, we provide a simple run.

    codec_opt = args.codec
    size_str = args.size
    size = _parse_size(size_str) if size_str else 10 * 1024 * 1024
    print(f"[revhash benchmark] size={size} ({size_str}), codec={codec_opt}, python={sys.version.split()[0]}")

    # Generate deterministic text_repeat style data (pool ~600B repeated)
    pool = (b"Xin chao the gioi! Hello world! revhash lossless compression test. " * 10)[:600]
    if size <= len(pool):
        data = pool[:size]
    else:
        # repeat pool to fill size
        data = (pool * ((size // len(pool)) + 1))[:size]
    sha_orig = hashlib.sha256(data).hexdigest()
    print(f"  data sha256={sha_orig[:16]}... len={len(data)}")

    codecs_to_test = []
    if codec_opt == "all":
        codecs_to_test = ["store", "gzip", "zstd", "lzma", "brotli"]
    else:
        codecs_to_test = [codec_opt]

    for codec in codecs_to_test:
        level = 3
        if codec == "gzip":
            level = 6
        elif codec == "lzma":
            level = 6
        elif codec == "brotli":
            level = 6
        chunk_size = 4 * 1024 * 1024
        # warmup
        from . import compress, decompress

        try:
            t0 = time.perf_counter()
            blob = compress(data, codec=codec, level=level, chunk_size=chunk_size)
            t1 = time.perf_counter()
            dec = decompress(blob)
            t2 = time.perf_counter()
            ok = dec == data
            sha_dec = hashlib.sha256(dec).hexdigest()
            comp_mb = len(data) / (1024 * 1024)
            speed_comp = comp_mb / max(1e-9, (t1 - t0))
            speed_decomp = comp_mb / max(1e-9, (t2 - t1))
            ratio = len(blob) / len(data) if len(data) else 0
            print(
                f"  {codec:7s} L{level}: ratio={ratio:.6f} ({len(blob)} B) comp {speed_comp:.1f} MB/s decomp {speed_decomp:.1f} MB/s verify={'OK' if ok else 'FAIL'} sha_match={sha_orig == sha_dec}"
            )
        except Exception as exc:
            print(f"  {codec}: FAILED {exc}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="revhash", description="revhash reversible compression unlimited (O1 streaming)")
    p.add_argument("--version", action="version", version=f"revhash {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    # compress
    sp = sub.add_parser("compress", help="compress file")
    sp.add_argument("input", help="input file")
    sp.add_argument("output", help="output .rvh file")
    sp.add_argument(
        "--codec",
        default="zstd",
        choices=["zstd", "gzip", "lzma", "brotli", "store", "auto"],
        help="codec (default zstd)",
    )
    sp.add_argument("--level", type=int, default=3, help="codec level (zstd 1..22, gzip 0..9, brotli 0..11)")
    sp.add_argument("--chunk-size", dest="chunk_size", default="4M", help="chunk size e.g. 4M, 1M, 8M")
    sp.add_argument("--dict", default=None, help="dictionary file (.dict)")
    sp.set_defaults(func=_cmd_compress)

    # decompress
    sp = sub.add_parser("decompress", help="decompress file")
    sp.add_argument("input", help="input .rvh file")
    sp.add_argument("output", help="output restored file")
    sp.add_argument("--dict", default=None, help="dictionary file")
    sp.set_defaults(func=_cmd_decompress)

    # info
    sp = sub.add_parser("info", help="show blob info")
    sp.add_argument("input", help="input .rvh file")
    sp.set_defaults(func=_cmd_info)

    # verify
    sp = sub.add_parser("verify", help="verify blob integrity (CRC+SHA)")
    sp.add_argument("input", help="input .rvh file")
    sp.add_argument("--dict", default=None, help="dictionary file if used")
    sp.set_defaults(func=_cmd_verify)

    # train-dict
    sp = sub.add_parser("train-dict", help="train zstd dictionary (requires dict_builder)")
    sp.add_argument("corpus", nargs="+", help="corpus files/globs")
    sp.add_argument("--out", required=True, help="output dict path")
    sp.add_argument("--size", default="112K", help="dict size e.g. 112K")
    sp.add_argument("--sample-size", dest="sample_size", default="16K", help="sample size per file e.g. 16K")
    sp.set_defaults(func=_cmd_train_dict)

    # benchmark
    sp = sub.add_parser("benchmark", help="lightweight benchmark (Verifier)")
    sp.add_argument("--size", default="10M", help="data size e.g. 10M, 100M")
    sp.add_argument("--codec", default="all", help="codec to test (all|zstd|gzip|lzma|brotli|store)")
    sp.set_defaults(func=_cmd_benchmark)

    return p


def main(argv: List[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
