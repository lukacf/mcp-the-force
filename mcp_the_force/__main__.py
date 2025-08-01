"""Allow running `python -m mcp_the_force`"""

from __future__ import annotations
import sys
import textwrap
from importlib.metadata import version
from .server import main


def _print_help() -> None:
    print(
        textwrap.dedent(
            """\
            mcp-the-force – Model-Context-Protocol server
            Usage:
              python -m mcp_the_force [--host HOST] [--port PORT] [--log-level LEVEL]
              python -m mcp_the_force --help
              python -m mcp_the_force --version
            """
        )
    )


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        _print_help()
        sys.exit(0)
    if "--version" in sys.argv or "-V" in sys.argv:
        print(version("mcp_the_force"))
        sys.exit(0)

    # Check for invalid arguments
    valid_args = ["--help", "-h", "--version", "-V", "--host", "--port", "--log-level"]
    for i, arg in enumerate(sys.argv[1:], 1):  # Skip script name
        if arg.startswith("-") and not any(
            arg.startswith(valid) for valid in valid_args
        ):
            print(f"Error: Unknown option: {arg}", file=sys.stderr)
            print(
                "Try 'python -m mcp_the_force --help' for more information.",
                file=sys.stderr,
            )
            sys.exit(2)

    # Fall through → run server
    main()
