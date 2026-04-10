"""Pytest configuration for py-mgipsim test suite.

Adds the repo root to sys.path so that `pymgipsim` is importable as a
top-level package without triggering the broken relative imports in the
root __init__.py.
"""
import sys
import os

# Ensure the py-mgipsim directory is on sys.path so `import pymgipsim` works
sys.path.insert(0, os.path.dirname(__file__))
