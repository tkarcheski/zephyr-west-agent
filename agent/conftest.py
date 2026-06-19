"""Ensure the in-tree package is importable without an editable install.

pytest loads this top-level conftest first and prepends its directory (the
``agent/`` package root) to ``sys.path``, so ``import zephyr_agent`` resolves
when running the suite straight from a checkout.
"""
