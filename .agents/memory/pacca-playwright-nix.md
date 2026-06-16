---
name: Arix Playwright Nix Setup
description: How browser tools are wired to the Nix-provided Chromium in Replit, bypassing version mismatch between pip playwright and nix playwright-browsers.
---

## Problem
- Replit `.replit` has `playwright-driver` in nix packages → installs `playwright-browsers-1.55.0-with-cjk` (chromium-1187) in nix store
- pip `playwright==1.49.1` expects `chromium-1148` at `~/.cache/ms-playwright/chromium-1148/`
- Running `playwright install chromium` downloads 1148 but it fails to launch (missing Ubuntu system libs in NixOS container)
- The nix chromium-1187 works fine because all its dependencies are baked into the nix store

## Solution
`pacca/tools/browser_tools.py` has `_find_nix_chromium()` that:
1. Checks the known hardcoded path for the nix chromium
2. Falls back to a subprocess `ls /nix/store/*playwright-browsers*/chromium-*/chrome-linux/chrome` (slow, but only if primary fails)
3. Stores result in `_NIX_CHROMIUM` module-level constant

`BrowserController.start()` passes `executable_path=_NIX_CHROMIUM` to `chromium.launch()` when `_NIX_CHROMIUM` is set, bypassing playwright's own browser resolution entirely.

**Why:** The version mismatch (pip 1.49.1 vs nix 1.55.0 browsers) can't be resolved without either upgrading pip playwright or symlinking — the executable_path override is cleaner and more resilient.

**How to apply:** If playwright breaks after a nix package update (different hash), update the hardcoded path in `_find_nix_chromium()`. The subprocess fallback should handle it automatically if the hash changes.

## Known nix chromium path (as of June 2026)
`/nix/store/kcvsxrmgwp3ffz5jijyy7wn9fcsjl4hz-playwright-browsers-1.55.0-with-cjk/chromium-1187/chrome-linux/chrome`
Chromium version: 140.0.7339.16
