"""CLI entry point with graceful degradation for optional dependencies (ADR-009).

Usage:
    llm-council               # Start MCP server (default)
    llm-council serve         # Start HTTP server
    llm-council serve --port 9000 --host 127.0.0.1
    llm-council setup-key     # Store API key in system keychain (ADR-013)
    llm-council bias-report   # Cross-session bias analysis (ADR-018)
"""

import argparse
import sys

from llm_council import __version__

# Optional keyring import - may not be installed
keyring = None
try:
    import keyring as _keyring_module

    keyring = _keyring_module
except ImportError:
    pass  # keyring not installed - this is fine


def _is_fail_backend() -> bool:
    """Check if keyring has a fail backend (headless/Docker)."""
    if keyring is None:
        return True
    try:
        from keyring.backends import fail

        return isinstance(keyring.get_keyring(), fail.Keyring)
    except Exception:
        return True


def main():
    """Main CLI entry point - dispatches to MCP or HTTP server."""
    parser = argparse.ArgumentParser(
        prog="llm-council",
        description="LLM Council - Multi-model deliberation system",
    )
    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
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

    # Setup key command (ADR-013)
    setup_key_parser = subparsers.add_parser(
        "setup-key",
        help="Securely store API key in system keychain",
    )
    setup_key_parser.add_argument(
        "--stdin",
        action="store_true",
        dest="from_stdin",
        help="Read API key from stdin (for CI/CD automation)",
    )

    # Bias report command (ADR-018)
    bias_parser = subparsers.add_parser(
        "bias-report",
        help="Analyze cross-session bias metrics",
    )
    bias_parser.add_argument(
        "--input",
        type=str,
        dest="input_path",
        help="Path to JSONL store (default: ~/.llm-council/bias_metrics.jsonl)",
    )
    bias_parser.add_argument(
        "--sessions",
        type=int,
        dest="max_sessions",
        help="Limit to last N sessions",
    )
    bias_parser.add_argument(
        "--days",
        type=int,
        dest="max_days",
        help="Limit to last N days",
    )
    bias_parser.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        dest="output_format",
        help="Output format (default: text)",
    )
    bias_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include detailed reviewer profiles",
    )

    args = parser.parse_args()

    if args.command == "serve":
        serve_http(host=args.host, port=args.port)
    elif args.command == "setup-key":
        setup_key(from_stdin=args.from_stdin)
    elif args.command == "bias-report":
        bias_report(
            input_path=args.input_path,
            max_sessions=args.max_sessions,
            max_days=args.max_days,
            output_format=args.output_format,
            verbose=args.verbose,
        )
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


def setup_key(from_stdin: bool = False):
    """Securely store API key in system keychain (ADR-013).

    Args:
        from_stdin: If True, read key from stdin (for CI/CD automation).
                   If False, prompt interactively using getpass.
    """
    # Check if keyring is available
    if keyring is None:
        print("Error: keyring package not installed.", file=sys.stderr)
        print("\nInstall with: pip install 'llm-council-core[secure]'", file=sys.stderr)
        sys.exit(1)

    # Check for fail backend (headless/Docker)
    if _is_fail_backend():
        print("Error: No keychain backend available.", file=sys.stderr)
        print("On headless servers, use environment variables instead.", file=sys.stderr)
        print("\nSet OPENROUTER_API_KEY in your environment or .env file.", file=sys.stderr)
        sys.exit(1)

    import getpass

    # Get the key
    if from_stdin:
        key = sys.stdin.read().strip()
    else:
        key = getpass.getpass("Enter your OpenRouter API key: ")

    if not key:
        print("Error: No key provided.", file=sys.stderr)
        sys.exit(1)

    # Validate format (warning only, not blocking)
    if not key.startswith("sk-or-"):
        print("Warning: Key doesn't look like an OpenRouter key (expected sk-or-...)")
        if not from_stdin:
            confirm = input("Store anyway? [y/N]: ")
            if confirm.lower() != "y":
                print("Aborted.")
                sys.exit(1)

    # Store the key
    try:
        keyring.set_password("llm-council", "openrouter_api_key", key)
        print("API key stored securely in system keychain.")
    except Exception as e:
        print(f"Error storing key: {e}", file=sys.stderr)
        sys.exit(1)


def bias_report(
    input_path: str = None,
    max_sessions: int = None,
    max_days: int = None,
    output_format: str = "text",
    verbose: bool = False,
):
    """Generate cross-session bias analysis report (ADR-018).

    Args:
        input_path: Path to JSONL store (default: ~/.llm-council/bias_metrics.jsonl)
        max_sessions: Limit to last N sessions
        max_days: Limit to last N days
        output_format: 'text' or 'json'
        verbose: Include detailed reviewer profiles
    """
    from pathlib import Path

    from llm_council.bias_aggregation import (
        generate_bias_report_text,
        generate_bias_report_json,
        generate_bias_report_csv,
    )

    store_path = Path(input_path) if input_path else None

    if output_format == "json":
        output = generate_bias_report_json(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
        )
    elif output_format == "csv":
        output = generate_bias_report_csv(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
        )
    else:
        output = generate_bias_report_text(
            store_path=store_path,
            max_sessions=max_sessions,
            max_days=max_days,
            verbose=verbose,
        )

    print(output)


if __name__ == "__main__":
    main()
