import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FAKE_BIN = ROOT / "tests" / "fake_bin"
DATA = ROOT / "tests" / "data"


@pytest.fixture()
def studio(tmp_path, monkeypatch):
    """A fresh studio folder whose settings point at the fake ORCA."""
    home = tmp_path / "studio"
    monkeypatch.setenv("ORCA_STUDIO_HOME", str(home))
    monkeypatch.setenv("FAKE_ORCA_SLEEP", os.environ.get("FAKE_ORCA_SLEEP", "0.3"))
    from orca_studio import config, db, store
    config._cache.clear()
    db.reset_connection()
    store._lib_cache.clear()
    store.seed()
    s = config.load_settings()
    s["programs"]["orca"] = str(FAKE_BIN / "orca")
    s["programs"]["python"] = sys.executable
    s["folders"]["calculations_root"] = str(tmp_path / "calcs")
    s["resources"]["total_cores"] = 4
    s["resources"]["nice"] = 0
    config.save_settings(s)
    db.init()
    yield home
    db.reset_connection()


def wait_for(pred, timeout=60, step=0.2):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(step)
    return False
