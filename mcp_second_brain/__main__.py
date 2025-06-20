"""Allow running `python -m mcp_second_brain`"""
from __future__ import annotations
import sys
import textwrap
from importlib.metadata import version
from .server import main

def _print_help() -> None:
    print(
        textwrap.dedent(
            """\
            mcp-second-brain – Model-Context-Protocol server
            Usage:
              python -m mcp_second_brain [--host HOST] [--port PORT] [--log-level LEVEL]
              python -m mcp_second_brain --help
              python -m mcp_second_brain --version
            """
        )
    )

if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        _print_help()
        sys.exit(0)
    if "--version" in sys.argv or "-V" in sys.argv:
        print(version("mcp_second_brain"))
        sys.exit(0)

    # Fall through → run server
    main()