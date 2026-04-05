# Implementation Plan: LLM Council Setup and Execution

To help you get **LLM Council** up and running, we'll follow these steps based on the project's requirements:

## 1. Prerequisites
- **Python 3.10+** (You have 3.14.2)
- [**uv**](https://github.com/astral-sh/uv) (Recommended for easiest dependency management)

## 2. Setup Environment
We'll use `uv` to sync dependencies as specified in the `Makefile`.
1.  Install `uv` (if not already installed).
2.  Clone the repository (already done).
3.  Run `uv sync --all-extras` to create a virtual environment (`.venv`) and install all necessary packages.

## 3. Configuration
LLM Council requires API keys to function.
1.  **OpenRouter** is the easiest gateway to set up.
2.  Create a `.env` file from the example: `cp .env.example .env`.
3.  Add your `OPENROUTER_API_KEY` to the `.env` file.

## 4. Verification
1.  Run `uv run llm-council health-check` to verify the setup.
2.  Run a test query: `uv run llm-council "What are the trade-offs of microservices?"`.

## 5. Integration (Optional)
- Add the council as an MCP server to Claude Desktop or Claude Code.

---

### Step-by-Step Instructions

#### 1. Install uv
If you don't have `uv`, install it via PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### 2. Sync Dependencies
```bash
uv sync --all-extras
```

#### 3. Configure API Keys
Edit your `.env` file:
```bash
cp .env.example .env
# Edit .env and add:
# OPENROUTER_API_KEY=sk-or-v1-...
```

#### 4. Run the Council
```bash
uv run llm-council "Tell me about the history of artificial intelligence."
```
