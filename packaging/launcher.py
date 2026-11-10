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
for _a in list(sys.argv[1:]):           # also accept --selftest=<log file>
    if _a.startswith("--selftest="):
        SELFTEST_LOG = _a.split("=", 1)[1]
        os.environ["MPC_MAPPER_SELFTEST"] = SELFTEST_LOG
        sys.argv.remove(_a)

if not getattr(sys, "frozen", False):
    # running from source: make the package next to this folder importable
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _log(text: str) -> None:
    if SELFTEST_LOG:
        with open(SELFTEST_LOG, "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")


def _fail(code: int) -> None:
    _log("FAILED:\n" + traceback.format_exc())
    os._exit(code)


_log(f"launcher started (frozen={getattr(sys, 'frozen', False)}, name={__name__})")

if __name__ == "__main__":
    try:
        from mpc_mapper.__main__ import main
    except Exception:
        if SELFTEST_LOG:
            _fail(3)
        raise
    _log("imports ok, starting main()")
    try:
        rc = main()
    except Exception:
        if SELFTEST_LOG:
            _fail(4)
        raise
    _log(f"ok (exit code {rc})")
    sys.exit(rc)
