#!/usr/bin/env python3
"""
Step 1 — Holo Edge / BroNode GUI smoke checks (no GUI).

Usage (from windows-gui/):
  python packaging/smoke_step1.py
"""
from __future__ import annotations

import importlib.util
import os
import sys


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    gui_root = os.path.dirname(here)
    if gui_root not in sys.path:
        sys.path.insert(0, gui_root)

    app_path = os.path.join(gui_root, "app.py")
    spec = importlib.util.spec_from_file_location("bronode_app", app_path)
    if spec is None or spec.loader is None:
        print("FAIL: could not load app.py")
        return 1
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Core Holo Edge constants
    for name, expected in (
        ("APP_NAME", "BroNode"),
        ("DEFAULT_IMAGE", "ghcr.io/holo-host/edgenode"),
        ("CONTAINER_NAME", "edgenode"),
        ("CONTAINER_USER", "nonroot"),
        ("DEFAULT_VOLUME", "holo-data"),
    ):
        got = getattr(mod, name, None)
        if got != expected:
            print(f"FAIL: {name} expected {expected!r}, got {got!r}")
            return 1

    root = mod._resource_root()
    mascot = mod.MASCOT_SVG
    print("APP_VERSION", getattr(mod, "APP_VERSION", "?"))
    print("_resource_root()", root)
    print("MASCOT_SVG", mascot)

    if not os.path.isdir(os.path.join(root, "assets")):
        print("FAIL: assets/ missing under resource root")
        return 1
    if not os.path.isfile(mascot):
        print("FAIL: mascot SVG missing:", mascot)
        return 1

    try:
        import tkinter as tk  # noqa: F401
    except ImportError as e:
        print("FAIL: tkinter required for BroNode:", e)
        return 1

    # Dev-only: default happ_config path helper (empty if frozen or binary missing)
    dft = mod._default_happ_config_tool_path()
    print("_default_happ_config_tool_path()", repr(dft))
    if not mod._is_frozen() and dft and not os.path.isfile(dft):
        print("WARN: Rust happ_config_file not built yet (optional):", dft)

    dbg = mod._debug_log_file_path()
    print("_debug_log_file_path()", repr(dbg), "(set BRONODE_DEBUG_LOG=1 to enable)")

    code, _, _ = mod.run_command(["docker", "version", "--format", "{{.Client.Version}}"], timeout=8)
    if code != 0:
        print("WARN: docker CLI not responding (install/start Docker for full Step 1 runtime check)")
    else:
        print("OK: docker CLI reachable")

    print("OK - Step 1 smoke passed (dev tree).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
