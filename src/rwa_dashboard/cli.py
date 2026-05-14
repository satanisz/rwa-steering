from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run the Streamlit RWA dashboard from the project console script."""
    parser = argparse.ArgumentParser(description="Run the RWA Streamlit dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Address for Streamlit to bind.")
    parser.add_argument("--port", default=8501, type=int, help="Port for Streamlit to bind.")
    args = parser.parse_args(argv)

    script_path = Path(__file__).with_name("streamlit_app.py")
    sys.argv = [
        "streamlit",
        "run",
        str(script_path),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
        "--server.headless",
        "true",
    ]

    from streamlit.web import cli as streamlit_cli

    return int(streamlit_cli.main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
