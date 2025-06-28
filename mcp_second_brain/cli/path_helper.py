import json
from pathlib import Path
import typer

app = typer.Typer(help="Utility to expand paths for MCP parameters")

@app.command()
def expand(paths: list[str]):
    """Print absolute versions of the given paths as a JSON array."""
    expanded = [str(Path(p).expanduser().resolve()) for p in paths]
    typer.echo(json.dumps(expanded, indent=2))


def main():
    app()


if __name__ == "__main__":
    main()

