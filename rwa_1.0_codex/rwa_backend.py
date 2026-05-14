from __future__ import annotations

import argparse
from pathlib import Path

from rwa_calculator.calculator import dumps_json
from rwa_calculator.server import build_server, calculate_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Restricted-environment Basel/RWA backend")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Run the HTTP API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--nccr", default="nccr_mapping.csv")
    serve.add_argument("--country", default="preprod_country_info.csv")

    serve_fastapi = subparsers.add_parser("serve-fastapi", help="Run the FastAPI microservice")
    serve_fastapi.add_argument("--host", default="127.0.0.1")
    serve_fastapi.add_argument("--port", type=int, default=8000)
    serve_fastapi.add_argument("--nccr", default="nccr_mapping.csv")
    serve_fastapi.add_argument("--country", default="preprod_country_info.csv")
    serve_fastapi.add_argument("--reference-data", default="reference_data")
    serve_fastapi.add_argument("--reload", action="store_true")

    calculate = subparsers.add_parser("calculate", help="Calculate RWA for a CSV batch")
    calculate.add_argument("--core", default="preprod_core_info_1000.csv")
    calculate.add_argument("--country", default="preprod_country_info.csv")
    calculate.add_argument("--nccr", default="nccr_mapping.csv")
    calculate.add_argument("--out")
    calculate.add_argument("--trace", action="store_true")
    calculate.add_argument("--projection-date")

    args = parser.parse_args()
    if args.command in {None, "serve"}:
        server = build_server(args.host, args.port, args.nccr, args.country)
        print(f"RWA backend listening on http://{args.host}:{args.port}")
        server.serve_forever()
        return

    if args.command == "serve-fastapi":
        import uvicorn

        from rwa_calculator.fastapi_app import ServiceSettings, create_app

        app = create_app(
            ServiceSettings(
                nccr_mapping_path=args.nccr,
                country_info_path=args.country,
                reference_data_root=args.reference_data,
            )
        )
        uvicorn.run(app, host=args.host, port=args.port, reload=args.reload)
        return

    if args.command == "calculate":
        payload = calculate_file(
            args.core,
            args.country,
            args.nccr,
            include_trace=args.trace,
            projection_date=args.projection_date,
        )
        text = dumps_json(payload)
        if args.out:
            Path(args.out).write_text(text + "\n", encoding="utf-8")
        else:
            print(text)


if __name__ == "__main__":
    main()
