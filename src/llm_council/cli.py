"""CLI entry point with graceful degradation for MCP dependencies."""

import sys


def main():
    """Run the LLM Council MCP server.

    This entry point gracefully handles missing MCP dependencies,
    guiding users to install with the [mcp] extra if needed.
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
