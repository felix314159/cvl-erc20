#!/usr/bin/env python3
"""Run Halmos with the local committed-event recorder (no installed files changed)."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys


def main():
    if importlib.util.find_spec("halmos") is None:
        tool_dir = Path(subprocess.check_output(["uv", "tool", "dir"], text=True).strip())
        python = tool_dir / "halmos/bin/python"
        if not python.exists():
            raise SystemExit("Install Halmos with uv before running this script")
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    from log_adapter import install
    from halmos.__main__ import main as halmos_main
    install()
    return halmos_main()


if __name__ == "__main__":
    raise SystemExit(main())
