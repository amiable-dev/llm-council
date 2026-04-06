# Implementation Plan - Claude Desktop Integration (Issue #4)

## 1. Problem Statement
Windows users of Claude Desktop (installed via the Microsoft Store) often encounter silent failures when trying to launch MCP servers using standard `uv run` commands due to restricted execution environments and path resolution issues.

## 2. Solution Summary
- **Wrapper Script**: Document the use of `run_mcp.bat` to bridge the gap between Claude's environment and the project's virtual environment.
- **MCP Guide**: Create a user-facing markdown guide explaining the `claude_desktop_config.json` configuration and the specific paths required for Windows.
- **Verification**: Document how to use the terminal to verify the MCP bridge before launching the UI.

## 3. Implementation Details
- `run_mcp.bat`: A lightweight bridge script for Windows process management.
- `docs/how_to_use_llm_council_with_claude_desktop.md`: The definitive guide for Windows integration.

## 4. Verification Strategy
- **Terminal Verification**: Run the `.bat` file directly to confirm the MCP initialization string appears as expected.
- **UI Verification**: Confirm the Claude Desktop "Hammer" icon appears and the `consult_council` tool is available.
