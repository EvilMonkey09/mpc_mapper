"""Entry point for the macOS app bundle built by build_mac.command.

PyInstaller needs a script file; ``python -m mpc_mapper`` is not one, so this
just calls the same main() function.
"""
import sys

from mpc_mapper.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
