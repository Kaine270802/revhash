"""Exception hierarchy for revhash — frozen M2 contract.

See docs/api.md §4.
"""

from __future__ import annotations


class RevHashError(Exception):
    """Base class for all revhash errors."""


class RevHashCorruptedError(RevHashError):
    """Raised when blob is corrupted (CRC / SHA mismatch, bad magic)."""


class RevHashDictError(RevHashError):
    """Raised when dictionary is missing or mismatched."""


class RevHashUnsupportedCodecError(RevHashError):
    """Raised when codec id/name is unknown or backend not available."""
