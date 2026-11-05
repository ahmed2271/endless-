"""OpenMPI is filled in automatically on start-up when Settings leave it empty."""
import os


def test_autofill_openmpi(studio, tmp_path, monkeypatch):
    from orca_studio import config, tools
    d = tmp_path / "openmpi-4.1.6" / "bin"
    d.mkdir(parents=True)
    m = d / "mpirun"
    m.write_text("#!/bin/sh\necho 'mpirun (Open MPI) 4.1.6'\n")
    m.chmod(0o755)
    monkeypatch.setenv("PATH", f"{d}:{os.environ['PATH']}")
    assert config.load_settings()["programs"]["openmpi_bin"] == ""
    assert tools.autofill_openmpi() == str(d)
    assert config.load_settings()["programs"]["openmpi_bin"] == str(d)
    assert tools.autofill_openmpi() is None            # never overwrites a value that is set
    env = tools.build_env()
    assert env["PATH"].startswith(str(d)) and str(tmp_path / "openmpi-4.1.6" / "lib") in env["LD_LIBRARY_PATH"]
