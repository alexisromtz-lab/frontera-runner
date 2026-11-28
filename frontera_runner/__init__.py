"""Composite frontier runner: four instruments, one receipt, one PR check.

The runner measures; it does not re-implement. Every instrument is invoked as a subprocess,
in its own repository, and identified in the receipt by version, commit and a digest of the
code that actually ran.
"""

__version__ = "0.2.2"
__all__ = ["__version__"]
