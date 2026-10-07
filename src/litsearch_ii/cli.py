"""Command line: run the MCP server, or try the tools from a terminal."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
from typing import Any

from . import __version__, service
from .http import Http
from .models import LitSearchError
from .sources import SEARCHABLE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="litsearch-ii",
        description="Keyless literature search: an MCP server plus a few terminal commands.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="run the MCP server (stdio by default)")
    serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    search = sub.add_parser("search", help="search all sources and print JSON")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--source", action="append", choices=SEARCHABLE, help="repeatable")
    search.add_argument("--from", dest="year_from", type=int)
    search.add_argument("--to", dest="year_to", type=int)
    search.add_argument("--open-access", action="store_true")
    search.add_argument("--country", help="two-letter code, e.g. NG (OpenAlex only)")

    details = sub.add_parser("details", help="show one paper (DOI, PMID, PMCID, arXiv id)")
    details.add_argument("identifier")

    verify = sub.add_parser("verify", help="check that a citation is real")
    verify.add_argument("--doi")
    verify.add_argument("--title")
    verify.add_argument("--year", type=int)
    verify.add_argument("--author", action="append")

    sub.add_parser("doctor", help="check which sources are reachable right now")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    http = Http()
    try:
        if args.command == "search":
            return await service.search_literature(
                http,
                args.query,
                args.limit,
                args.source,
                args.year_from,
                args.year_to,
                args.open_access,
                args.country,
            )
        if args.command == "details":
            return await service.paper_details(http, args.identifier)
        if args.command == "verify":
            return await service.verify_citation(http, args.doi, args.title, args.author, args.year)
        return await service.doctor(http)
    finally:
        await http.aclose()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    if args.command in (None, "serve"):
        from .server import create_server

        server = create_server()
        transport = getattr(args, "transport", "stdio")
        if transport == "stdio":
            server.run("stdio")
        else:
            print(
                f"LitSearch II on http://{args.host}:{args.port}/mcp (read-only, no keys)",
                file=sys.stderr,
            )
            server.run("streamable-http", host=args.host, port=args.port)
        return 0
    try:
        result = asyncio.run(_run(args))
    except LitSearchError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
