"""Algorithms package for revhash — Optimization Builder (M3b).

Exports ``selector`` and re-exposes ``dict_builder`` for convenience.

- ``revhash.algorithms.selector``: auto codec/level/chunk selector
- ``revhash.dict_builder``: dictionary training (also available as ``revhash.algorithms.dict_builder``)

Usage:
    from revhash.algorithms import selector
    from revhash.algorithms.selector import auto_select, choose_best_chunk
    import revhash.dict_builder
"""

from __future__ import annotations

from . import selector  # noqa: F401

# Re-export dict_builder at algorithms namespace for convenience (task §6 layout)
try:
    from .. import dict_builder  # type: ignore  # noqa: F401

    __all__ = ["selector", "dict_builder"]
except Exception:  # pragma: no cover
    # Fallback if dict_builder not yet importable (e.g., during partial install)
    dict_builder = None  # type: ignore
    __all__ = ["selector"]

# Also expose submodules for `from revhash.algorithms import selector`
# and allow `import revhash.algorithms.selector` naturally.
