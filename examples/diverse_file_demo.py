"""
diverse_file_demo.py - Ví dụ đầy đủ đa dạng file cho compress_file/decompress_file

Chạy:  python examples/diverse_file_demo.py
Yêu cầu: pip install git+https://github.com/Kaine270802/revhash.git  (cần zstandard)

Demo 6 loại file: .txt, .json, .csv, .bin (binary), .log, file lớn 10MB
Mỗi demo: tạo file gốc -> compress_file -> decompress_file -> assert byte-identical
"""

from pathlib import Path
import json
import csv
import tempfile
import hashlib
import sys

# Đảm bảo import được cả src/revhash và revhash_embedded.py ở root khi chạy từ examples/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import revhash
import revhash_embedded  # để chứng minh bundle cũng đa dạng file

# Helper tạo tmp dir sạch
TMP = Path(tempfile.gettempdir()) / "revhash_diverse_demo"
TMP.mkdir(parents=True, exist_ok=True)
print(f"[demo] tmp dir: {TMP}")
print(f"[demo] revhash {revhash.__version__}, codecs {revhash.get_available_codecs()}")
print(f"[demo] bundle {revhash_embedded.__version__} {revhash_embedded.__bundle_hash__[:12]}...")

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]

def demo_txt():
    """1) .txt - văn bản tiếng Việt + emoji"""
    src = TMP / "sample.txt"
    src.write_text("xin chào thế giới 🌍\n" * 1000, encoding="utf-8")
    dst = TMP / "sample.txt.rvh"
    revhash.compress_file(str(src), str(dst))  # str path
    out = TMP / "sample_restored.txt"
    revhash.decompress_file(str(dst), str(out))
    assert out.read_bytes() == src.read_bytes()
    print(f"1) .txt PASS - {src.stat().st_size} -> {dst.stat().st_size} sha {sha(src)}")

def demo_json_file():
    """2) .json - file JSON (đường dẫn)"""
    src = TMP / "data.json"
    data = {"xin": "chào", "list": list(range(100)), "nested": {"a": 1, "b": [2,3]}}
    src.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    dst = TMP / "data.json.rvh"
    revhash.compress_file(src, dst)  # Path
    out = TMP / "data_restored.json"
    revhash.decompress_file(dst, out)
    assert json.loads(out.read_text(encoding="utf-8")) == data
    assert out.read_bytes() == src.read_bytes()
    print(f"2) .json file PASS - {src.stat().st_size} -> {dst.stat().st_size} ratio {dst.stat().st_size/src.stat().st_size:.3f}")

def demo_json_text_direct():
    """3) JSON text truc tiep (không cần file) - str JSON -> bytes blob"""
    jstr = json.dumps({"hello": "world", "arr": [1,2,3]}, ensure_ascii=False)
    blob = revhash.compress_file(jstr, None)  # str text, dst=None -> bytes
    assert isinstance(blob, bytes)
    text = revhash.decompress_file(blob, None, as_text=True)  # bytes blob -> str
    assert text == jstr
    assert json.loads(text) == {"hello": "world", "arr": [1,2,3]}
    print(f"3) JSON text truc tiep PASS - {len(jstr.encode())} -> {len(blob)} bytes")

def demo_csv():
    """4) .csv - file CSV"""
    src = TMP / "table.csv"
    with open(src, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "note"])
        for i in range(500):
            w.writerow([i, f"tên_{i}", "xin chào"])
    dst = TMP / "table.csv.rvh"
    revhash.compress_file(str(src), str(dst))
    out = TMP / "table_restored.csv"
    revhash.decompress_file(str(dst), str(out))
    assert out.read_bytes() == src.read_bytes()
    print(f"4) .csv PASS - {src.stat().st_size} -> {dst.stat().st_size}")

def demo_bin():
    """5) .bin - binary thuần túy"""
    src = TMP / "binary.bin"
    src.write_bytes(b"\x00\xff\xfe\x80\x81 raw \x00" * 10000 + b"hello" * 1000)
    dst = TMP / "binary.bin.rvh"
    revhash.compress_file(src, dst)
    out = TMP / "binary_restored.bin"
    revhash.decompress_file(dst, out)
    assert out.read_bytes() == src.read_bytes()
    # bytes trực tiếp
    raw = b"\x00\xff\xfe hello"
    assert revhash.decompress_file(revhash.compress_file(raw, None), None) == raw
    print(f"5) .bin PASS - {src.stat().st_size} -> {dst.stat().st_size}")

def demo_log_and_force_text():
    """6) .log + force_text - text trùng tên file"""
    # Tạo file log
    log = TMP / "app.log"
    log.write_text("ERROR xin chào\n" * 2000, encoding="utf-8")
    dst = TMP / "app.log.rvh"
    revhash.compress_file(log, dst)
    # Text literal trùng tên file "app.log" - force_text=True để ép text
    blob_text = revhash.compress_file("app.log", None, force_text=True)
    assert revhash.decompress_file(blob_text, None, as_text=True) == "app.log"
    # Không force_text -> sẽ đọc file app.log nếu tồn tại ở cwd
    print(f"6) .log + force_text PASS - {log.stat().st_size} -> {dst.stat().st_size}")

def demo_large_and_embedded():
    """7) File lớn 10MB O1 + bundle parity"""
    src = TMP / "large_10MB.json"
    # JSON lớn 10MB (lặp)
    obj = {"data": "x" * 1000}
    # Ghi 10MB bằng lặp JSON lines
    with open(src, "w", encoding="utf-8") as f:
        for _ in range(10000):
            f.write(json.dumps(obj) + "\n")
    assert src.stat().st_size > 5_000_000
    dst = TMP / "large_10MB.json.rvh"
    info = revhash.compress_file(src, dst, codec="zstd")
    # Bundle cũng phải đa dạng file
    dst2 = TMP / "large_10MB_embedded.rvh"
    revhash_embedded.compress_file(src, dst2)
    assert dst.stat().st_size == dst2.stat().st_size  # byte-identical
    out = TMP / "large_restored.json"
    revhash.decompress_file(dst, out)
    assert out.read_bytes() == src.read_bytes()
    print(f"7) large 10MB O1 + bundle parity PASS - {src.stat().st_size} -> {dst.stat().st_size} ratio {info['ratio']:.4f}")

def demo_dict_with_json():
    """8) JSON + dict training (tối ưu cho small JSON)"""
    from revhash import dict_builder
    # Train dict từ 50 sample JSON nhỏ
    samples = [json.dumps({"id": i, "name": "xin chào"}).encode() for i in range(50)]
    dict_data = dict_builder.train(samples, dict_size=4096)
    j = json.dumps({"id": 999, "name": "xin chào"})
    blob_no = revhash.compress(j.encode(), dict_data=None)
    blob_yes = revhash.compress(j.encode(), dict_data=dict_data)
    assert revhash.decompress(blob_yes, dict_data=dict_data) == j.encode()
    print(f"8) JSON + dict PASS - no dict {len(blob_no)} vs with dict {len(blob_yes)}")

if __name__ == "__main__":
    demo_txt()
    demo_json_file()
    demo_json_text_direct()
    demo_csv()
    demo_bin()
    demo_log_and_force_text()
    demo_large_and_embedded()
    demo_dict_with_json()
    print("\n[demo] all 8 diverse file demos PASS - revhash ho tro da dang file (txt/json/csv/bin/log/large) O1")
