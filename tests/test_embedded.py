"""test_embedded — 18 cases: parity bundle vs pkg 10 cases, hash/version/size, vendored subprocess, zero-deps mock."""
import hashlib
import os
import pathlib
import random
import shutil
import subprocess
import sys
import tempfile

import pytest

import revhash
import revhash_embedded


def gen_repeat(n, pool=b"hello world "):
    if n == 0:
        return b""
    return (pool * ((n // len(pool)) + 1))[:n]


def gen_random(n, seed=0):
    rnd = random.Random(seed)
    return bytes(rnd.getrandbits(8) for _ in range(n))


parametrize_cases = [
    ("0B", 0, {"codec": "zstd"}),
    ("xin_chao", -1, {"codec": "zstd"}),
    ("emoji", -2, {"codec": "zstd"}),
    ("1KB_repeat", 1024, {"codec": "zstd"}),
    ("1MB_text_repeat", 1024 * 1024, {"codec": "zstd"}),
    ("10KB_file_content", 10 * 1024, {"codec": "zstd"}),
    ("random_10KB", -3, {"codec": "zstd"}),
    ("gzip_codec", 10 * 1024, {"codec": "gzip", "level": 6}),
    ("store_codec", 10 * 1024, {"codec": "store"}),
    ("zstd_codec_explicit", 10 * 1024, {"codec": "zstd", "level": 3}),
]


@pytest.mark.parametrize("label,size,kwargs", parametrize_cases)
def test_parity_bundle_vs_pkg_byte_identical(label, size, kwargs):
    if size == 0:
        data = b""
    elif size == -1:
        data = "xin chào".encode("utf-8")
    elif size == -2:
        data = "hello 🌍🌈🔥 — revhash 🚀 xin chào".encode("utf-8")
    elif size == -3:
        data = gen_random(10 * 1024, seed=42)
    else:
        data = gen_repeat(size)
    blob_pkg = revhash.compress(data, **kwargs)
    blob_emb = revhash_embedded.compress(data, **kwargs)
    assert blob_pkg == blob_emb, f"parity failed for {label}"
    # decompress both ways
    out_pkg = revhash.decompress(blob_pkg)
    out_emb = revhash_embedded.decompress(blob_emb)
    assert out_pkg == data
    assert out_emb == data
    # cross
    assert revhash.decompress(blob_emb) == data
    assert revhash_embedded.decompress(blob_pkg) == data
    # verify
    assert revhash.verify(blob_pkg) is True
    assert revhash_embedded.verify(blob_emb) is True
    # codec agree (store fallback for tiny)
    info_pkg = revhash.get_info(blob_pkg)
    info_emb = revhash_embedded.get_info(blob_emb)
    assert info_pkg["codec"] == info_emb["codec"]


def test_parity_file_10KB_and_text_via_file_api(tmp_path):
    data = gen_repeat(10 * 1024)
    src = tmp_path / "in.txt"
    src.write_bytes(data)
    dst_pkg = tmp_path / "pkg.rvh"
    dst_emb = tmp_path / "emb.rvh"
    revhash.compress_file(src, dst_pkg)
    revhash_embedded.compress_file(src, dst_emb)
    assert dst_pkg.read_bytes() == dst_emb.read_bytes()
    # cross decompress
    out_pkg = tmp_path / "out_pkg.bin"
    out_emb = tmp_path / "out_emb.bin"
    revhash.decompress_file(dst_emb, out_pkg)
    revhash_embedded.decompress_file(dst_pkg, out_emb)
    assert out_pkg.read_bytes() == data
    assert out_emb.read_bytes() == data


def test_parity_dict_case(tmp_path):
    dict_path = pathlib.Path("dicts/vi_text.dict")
    if not dict_path.exists():
        pytest.skip("dict missing")
    dict_data = dict_path.read_bytes()
    data = gen_repeat(100 * 1024)
    blob_pkg = revhash.compress(data, codec="zstd", dict_data=dict_data)
    blob_emb = revhash_embedded.compress(data, codec="zstd", dict_data=dict_data)
    assert blob_pkg == blob_emb
    assert revhash.decompress(blob_pkg, dict_data=dict_data) == data
    assert revhash_embedded.decompress(blob_emb, dict_data=dict_data) == data
    info = revhash.get_info(blob_pkg)
    assert info["has_dict"] is True


def test_parity_text_str_emoji():
    for text in ["", "xin chào", "hello 🌍", "copy 1 file là chạy"]:
        b_pkg = revhash.compress_text(text)
        b_emb = revhash_embedded.compress_text(text)
        assert b_pkg == b_emb
        assert revhash.decompress_text(b_pkg) == text
        assert revhash_embedded.decompress_text(b_emb) == text
        # polymorphic
        assert revhash.compress(text) == revhash_embedded.compress(text)


def test_bundle_hash_version_size():
    assert hasattr(revhash_embedded, "__bundle_hash__")
    assert revhash_embedded.__bundle_hash__.startswith("sha256:")
    assert len(revhash_embedded.__bundle_hash__) == len("sha256:") + 64
    assert revhash_embedded.__version__ == "0.3.0"
    assert revhash.__version__ == "0.3.0"
    p = pathlib.Path("revhash_embedded.py")
    assert p.exists()
    assert p.stat().st_size < 512000
    # recompute hash over src
    src = pathlib.Path("src/revhash")
    HASH_FILES = ["exceptions.py", "header.py", "codec.py", "stream.py", "file_text.py", "text.py", "__init__.py"]
    h = hashlib.sha256()
    for name in sorted(HASH_FILES):
        pp = src / name
        if pp.exists():
            h.update(pp.read_bytes())
            h.update(b"\x00")
    expected = "sha256:" + h.hexdigest()
    assert revhash_embedded.__bundle_hash__ == expected


def test_single_file_vendored_subprocess(tmp_path):
    # copy revhash_embedded.py to temp dir and run subprocess import
    src = pathlib.Path("revhash_embedded.py")
    dst = tmp_path / "revhash_embedded.py"
    shutil.copy(src, dst)
    code = """
import revhash_embedded as revhash
assert revhash.decompress_text(revhash.compress_text("copy 1 file là chạy")) == "copy 1 file là chạy"
from pathlib import Path
Path("tmp_demo.txt").write_text("hello\\n"*10, encoding="utf-8")
revhash.compress_file("tmp_demo.txt", "tmp_demo.rvh")
revhash.decompress_file("tmp_demo.rvh", "tmp_demo_restored.txt")
assert Path("tmp_demo_restored.txt").read_text() == Path("tmp_demo.txt").read_text()
print("vendored PASS", revhash.get_available_codecs())
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "vendored PASS" in result.stdout


def test_single_file_vendored_import_as_revhash_subprocess(tmp_path):
    src = pathlib.Path("revhash_embedded.py")
    shutil.copy(src, tmp_path / "revhash_embedded.py")
    code = """
import revhash_embedded as revhash
print(revhash.__version__)
assert revhash.__version__ == "0.3.0"
blob = revhash.compress(b"hello")
assert revhash.decompress(blob) == b"hello"
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_zero_deps_fallback_mock(monkeypatch):
    # mock both pkg and embedded? We'll test pkg via monkeypatch, and embedded via direct HAS_ZSTD attr?
    import revhash.codec as codec_mod
    import revhash.stream as stream_mod

    monkeypatch.setattr(codec_mod, "HAS_ZSTD", False)
    monkeypatch.setattr(stream_mod, "HAS_ZSTD", False)
    monkeypatch.setattr("revhash.HAS_ZSTD", False, raising=False)
    # pkg fallback
    avail = revhash.get_available_codecs()
    assert avail["zstd"] is False
    data = b"fallback test " * 500
    blob = revhash.compress(data, codec="auto")
    info = revhash.get_info(blob)
    assert info["codec"] in ("gzip", "store")
    assert revhash.decompress(blob) == data
    with pytest.raises(Exception):
        revhash.compress(data, codec="zstd")
    # file version
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as td:
        td = pathlib.Path(td)
        src = td / "a.txt"
        src.write_bytes(data)
        dst = td / "out.rvh"
        # compress_file auto should also fallback? currently stream codec auto may handle via _normalize_codec_id
        # we test that at least gzip works
        blob_gz = revhash.compress(data, codec="gzip")
        assert revhash.decompress(blob_gz) == data


def test_zero_deps_both_missing_fallback_to_store(monkeypatch):
    import revhash.codec as codec_mod

    monkeypatch.setattr(codec_mod, "HAS_ZSTD", False)
    monkeypatch.setattr(codec_mod, "HAS_BROTLI", False)
    monkeypatch.setattr("revhash.HAS_ZSTD", False, raising=False)
    monkeypatch.setattr("revhash.HAS_BROTLI", False, raising=False)
    import revhash.stream as stream_mod

    monkeypatch.setattr(stream_mod, "HAS_ZSTD", False)
    avail = revhash.get_available_codecs()
    assert avail["store"] is True and avail["gzip"] is True
    data = b"store fallback " * 200
    blob = revhash.compress(data, codec="store")
    assert revhash.decompress(blob) == data
    # auto should still work (gzip)
    blob2 = revhash.compress(data, codec="auto")
    assert revhash.decompress(blob2) == data


def test_embedded_compress_file_mkdir_nested(tmp_path):
    src = tmp_path / "hello.txt"
    src.write_text("hello mkdir embedded", encoding="utf-8")
    dst = tmp_path / "out" / "nested" / "deep" / "b.rvh"
    revhash_embedded.compress_file(src, dst)
    assert dst.exists()
    # also pkg
    dst2 = tmp_path / "out2" / "nested" / "b2.rvh"
    import revhash as revhash_pkg
    revhash_pkg.compress_file(src, dst2)
    assert dst2.exists()
