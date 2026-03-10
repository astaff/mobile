"""Smoke tests: CLI and SDK happy paths from the README."""

import subprocess
import sys
import tempfile
from pathlib import Path

from mbl import Mobile


def test_cli_default():
    """CLI generates output with default shape."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hello.3mf"
        r = subprocess.run(
            [sys.executable, "-m", "mbl.cli", "HI", "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert out.exists() and out.stat().st_size > 0


def test_cli_shape():
    """CLI works with a non-default built-in shape."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hi-heart.3mf"
        r = subprocess.run(
            [sys.executable, "-m", "mbl.cli", "HI", "--shape", "heart", "--output", str(out)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, r.stderr
        assert out.exists() and out.stat().st_size > 0


def test_sdk_from_word():
    """SDK Mobile.from_word() produces a file."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hi.3mf"
        Mobile.from_word("HI").to_file(out)
        assert out.exists() and out.stat().st_size > 0


def test_sdk_shape_burst():
    """SDK with shape= kwarg."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "hi-burst.3mf"
        Mobile.from_word("HI", shape="burst").to_file(out)
        assert out.exists() and out.stat().st_size > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(f"{name} ... ", end="", flush=True)
            fn()
            print("ok")
    print("All tests passed.")
