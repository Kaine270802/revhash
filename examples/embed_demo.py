"""embed_demo — copy-1-file demo with revhash_embedded (M3b API DX).

Usage (M2 single-file vendored):
    cp revhash_embedded.py ./myproject/
    python examples/embed_demo.py  # or python myproject/embed_demo.py

Spec: docs/api_embedded.md §2.3 + TEAM_PLAN_EMBEDDED.md, research_embedded.md §3.4 Demo 5
Requires only revhash_embedded.py — no pip install needed.
"""
import sys
from pathlib import Path

# Ensure workspace root on sys.path when running as `python examples/embed_demo.py`
# (Python adds script dir `examples/` to sys.path, not workspace root)
if str(Path(__file__).resolve().parents[1]) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import revhash_embedded as revhash

# Demo: text roundtrip (Vietnamese + emoji, utf-8 strict)
assert revhash.decompress_text(revhash.compress_text("xin chào 🌍")) == "xin chào 🌍"

# Demo: file roundtrip via single-file bundle
Path("tmp_demo.txt").write_text("hello\n" * 100, encoding="utf-8")
revhash.compress_file("tmp_demo.txt", "tmp_demo.rvh")
revhash.decompress_file("tmp_demo.rvh", "tmp_demo_restored.txt")
assert Path("tmp_demo_restored.txt").read_text(encoding="utf-8") == Path("tmp_demo.txt").read_text(encoding="utf-8")

print("embed_demo PASS", revhash.get_available_codecs())

# cleanup (optional)
for p in ["tmp_demo.txt", "tmp_demo.rvh", "tmp_demo_restored.txt"]:
    try:
        Path(p).unlink()
    except FileNotFoundError:
        pass
