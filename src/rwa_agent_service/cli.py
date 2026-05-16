from __future__ import annotations

import argparse


def main() -> None:
    """Run the RWA agent FastAPI application from the console script entry point."""
    parser = argparse.ArgumentParser(description="RWA agent service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8060)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        "rwa_agent_service.fastapi_app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
