"""Entry point for the packaged app (macOS .app / Windows .exe).

PyInstaller needs a script file; ``python -m mpc_mapper`` is not one, so this
just calls the same main() function.

Self-test (used by the CI build): with MPC_MAPPER_SELFTEST=<log file> set,
the app opens its window, closes it again after a few seconds and exits with
0 on success. Any error is written to the log file and gives a non-zero exit
code instead of an error dialog, so the build can detect a broken package.
"""
import os
import sys
import traceback

SELFTEST_LOG = os.environ.get("MPC_MAPPER_SELFTEST")

if not getattr(sys, "frozen", False):
    # running from source: make the package next to this folder importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _fail(code: int) -> None:
    with open(SELFTEST_LOG, "w", encoding="utf-8") as f:
        traceback.print_exc(file=f)
    os._exit(code)


if __name__ == "__main__":
    try:
        from mpc_mapper.__main__ import main
    except Exception:
        if SELFTEST_LOG:
            _fail(3)
        raise
    try:
        rc = main()
    except Exception:
        if SELFTEST_LOG:
            _fail(4)
        raise
    if SELFTEST_LOG:
        with open(SELFTEST_LOG, "w", encoding="utf-8") as f:
            f.write(f"ok (exit code {rc})\n")
    sys.exit(rc)
