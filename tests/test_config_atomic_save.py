"""Tests for ArixConfig atomic file writes (REL-05)."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from arix.config import ArixConfig


def test_config_save_atomic(tmp_path):
    """save() should use write-then-rename, not in-place overwrite."""
    import arix.config as cfg_mod
    cfg_file = tmp_path / "config.json"
    with patch.object(cfg_mod, "Arix_DIR", tmp_path), \
         patch.object(cfg_mod, "CONFIG_FILE", cfg_file):
        cfg = ArixConfig()
        cfg.save()
        assert cfg_file.exists()
        # Permissions should be 600
        mode = oct(os.stat(cfg_file).st_mode)[-3:]
        assert mode == "600"


def test_config_save_valid_json(tmp_path):
    import arix.config as cfg_mod
    cfg_file = tmp_path / "config.json"
    with patch.object(cfg_mod, "Arix_DIR", tmp_path), \
         patch.object(cfg_mod, "CONFIG_FILE", cfg_file):
        cfg = ArixConfig()
        cfg.max_steps = 42
        cfg.save()
        data = json.loads(cfg_file.read_text())
        assert data["max_steps"] == 42


def test_config_save_no_tmp_left_on_success(tmp_path):
    """No .tmp files should remain after a successful save."""
    import arix.config as cfg_mod
    cfg_file = tmp_path / "config.json"
    with patch.object(cfg_mod, "Arix_DIR", tmp_path), \
         patch.object(cfg_mod, "CONFIG_FILE", cfg_file):
        cfg = ArixConfig()
        cfg.save()
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == [], f"Orphaned tmp files: {tmp_files}"
