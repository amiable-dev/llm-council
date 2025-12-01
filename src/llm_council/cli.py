"""CLI entry point with graceful degradation for optional dependencies (ADR-009).

Usage:
    llm-council           # Start MCP server (default)
    llm-council serve     # Start HTTP server
    llm-council serve --port 9000 --host 127.0.0.1
"""

import argparse
import sys


def main():
    """Main CLI entry point - dispatches to MCP or HTTP server."""
    parser = argparse.ArgumentParser(
        prog="llm-council",
        description="LLM Council - Multi-model deliberation system",
    )
    subparsers = parser.add_subparsers(dest="command")

    # HTTP serve command
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start HTTP server for REST API access",
    )
    serve_parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )

    args = parser.parse_args()

    if args.command == "serve":
        serve_http(host=args.host, port=args.port)
    else:
        # Default: MCP server
        serve_mcp()


def serve_http(host: str = "0.0.0.0", port: int = 8000):
    """Start the HTTP server.

    Requires the [http] extra: pip install 'llm-council[http]'
    """
    try:
        from llm_council.http_server import app

        import uvicorn
    except ImportError:
        print("Error: HTTP dependencies not installed.", file=sys.stderr)
        print("\nTo use the HTTP server, install with:", file=sys.stderr)
        print("    pip install 'llm-council[http]'", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(app, host=host, port=port)


def serve_mcp():
    """Start the MCP server.

    Requires the [mcp] extra: pip install 'llm-council[mcp]'
    """
    try:
        from llm_council.mcp_server import mcp
    except ImportError:
        print("Error: MCP dependencies not installed.", file=sys.stderr)
        print("\nTo use the MCP server, install with:", file=sys.stderr)
        print("    pip install 'llm-council[mcp]'", file=sys.stderr)
        print("\nFor library-only usage, import directly:", file=sys.stderr)
        print("    from llm_council import run_full_council", file=sys.stderr)
        sys.exit(1)

    mcp.run()


if __name__ == "__main__":
    main()
