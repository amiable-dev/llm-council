<div class="hero" markdown>
  <img src="img/logo.svg" alt="llm-council">
  <h1>llm-council</h1>
  <p>Don't ship on one model's guess. Multiple LLMs debate, anonymously peer-review each answer, and a chairman synthesizes the result — so you get an answer you can trust, or a machine-actionable <strong>pass / fail / unclear</strong> verdict with calibrated confidence for your CI.</p>
  <div class="hero-buttons">
    <a href="getting-started/quickstart/" class="primary">Get Started →</a>
    <a href="https://github.com/amiable-dev/llm-council" class="secondary">★ Star on GitHub</a>
  </div>
</div>

<p align="center">
<a href="https://pypi.org/project/llm-council-core/"><img src="https://img.shields.io/pypi/v/llm-council-core.svg?label=pypi" alt="PyPI version"></a>
<a href="https://pypi.org/project/llm-council-core/"><img src="https://img.shields.io/pypi/dm/llm-council-core.svg?color=blue" alt="Downloads"></a>
<a href="https://pypi.org/project/llm-council-core/"><img src="https://img.shields.io/pypi/pyversions/llm-council-core.svg" alt="Python versions"></a>
<a href="https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml"><img src="https://github.com/amiable-dev/llm-council/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
<a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/pypi/l/llm-council-core.svg?color=green" alt="License: MIT"></a>
<a href="https://discord.gg/y467DGHF"><img src="https://img.shields.io/badge/Discord-join-7289da?logo=discord&logoColor=white" alt="Discord"></a>
</p>

## Start in 60 seconds

=== "Claude Code / Cursor (MCP)"

    ```bash
    pip install "llm-council-core[mcp,secure]"
    export OPENROUTER_API_KEY="sk-or-v1-..."
    claude mcp add llm-council --scope user -- llm-council
    ```

    Then just ask your agent:

    > *Consult the council on whether this database migration is safe to ship.*

    Your agent gets a synthesized, peer-reviewed answer instead of one model's hot take.

=== "Python"

    ```python
    from llm_council import consult_council

    result = await consult_council(
        "What's the most robust way to make retries idempotent?",
        confidence="balanced",
    )

    print(result.synthesis)    # the chairman's synthesized answer
    print(result.confidence)   # calibrated 0.0–1.0
    ```

=== "CI gate"

    ```bash
    pip install "llm-council-core[secure]"
    llm-council gate --snapshot HEAD --file-paths src/ --tier balanced
    # exit 0 = pass · 1 = fail · 2 = unclear  →  drop straight into your pipeline
    ```

## See it decide

`verify` doesn't hand you prose to parse — it returns a verdict your pipeline can act on, with the exact findings that produced it:

```text
$ llm-council gate --snapshot HEAD --file-paths src/auth.py --tier balanced

Council Verification: FAIL ❌   (exit code 1)
  Verdict       fail
  Confidence    0.82   (calibrated)
  Findings      3 critical · 1 major

  ✗ critical   src/auth.py:14   SQL injection — user input concatenated into the query
  ✗ critical   src/auth.py:22   Command injection via os.system on unsanitized host
  ✗ critical   src/auth.py:31   Hardcoded AWS secret committed to source

  → Verdict is computed mechanically: any critical finding ⇒ fail.
    The verdict can't disagree with the evidence, because it's derived from it.
```

The same result is available as JSON (verdict, `blocking_issues`, calibrated confidence, `unclear_reason`) over the [MCP tool](guides/mcp.md) and the [HTTP API](guides/http-api.md) — see the [verification guide](guides/verify.md).

## Pick your path

<div class="grid cards" markdown>

-   🤖 __I use an AI coding agent__

    ---

    Add a trustworthy second opinion to Claude Code, Cursor, or any MCP client — no code required.

    [MCP setup →](guides/mcp.md)

-   🐍 __I'm building an app__

    ---

    Call the council from Python or a stateless HTTP API, with streaming and full cost accounting.

    [Python library →](guides/python.md) · [HTTP API →](guides/http-api.md)

-   ✅ __I want to gate CI__

    ---

    Turn "does this change look right?" into an exit code — pass / fail / unclear with calibrated confidence.

    [Verification & CI gating →](guides/verify.md)

</div>

## Why llm-council

- **Anonymized peer review** — in Stage 2, models rank "Response A / B / C…", never each other by name, so they can't play favorites. Bias is the failure mode of naive ensembling; this is the fix.
- **A verdict you can gate on** — `verify` returns `pass` / `fail` / `unclear` with an exit code, `blocking_issues`, and calibrated confidence — machine-actionable, not prose to regex.
- **Calibrated confidence** — an isotonic fit against real human dispositions, so a 0.8 means 0.8. Every response also reports the raw value.
- **Cost transparency** — real per-model and per-stage token + USD accounting on every response, with provider ground-truth where available.
- **Runs where you work** — one package, four surfaces: MCP server, HTTP API, Python library, and CLI.
- **Any model, any router** — GPT, Claude, Gemini, Grok, DeepSeek, or local Ollama, via OpenRouter, Requesty, or direct provider APIs.

## How it works

Three stages, fully parallel wherever possible:

1. **Deliberate** — your question goes to several frontier LLMs at once.
2. **Peer-review (anonymized)** — each model evaluates and ranks the others' responses, blind to who wrote them. Rankings are aggregated with Borda counting.
3. **Synthesize** — a Chairman model composes the final answer from the full, ranked context — and for `verify`, host code computes the verdict *mechanically* from the findings.

Choose a **confidence tier** — `quick`, `balanced`, `high`, or `reasoning` — to trade latency and cost for depth. [How it works in depth →](architecture/overview.md)

## Community

- **[Discord](https://discord.gg/y467DGHF)** — real-time chat and support
- **[GitHub Discussions](https://github.com/amiable-dev/llm-council/discussions)** — Q&A and ideas
- **[Contributing Guide](contributing.md)** — help improve llm-council

## Next steps

- [Installation](getting-started/installation.md) — extras, keys, and the keychain-secured setup
- [Quick Start](getting-started/quickstart.md) — your first verdict in five minutes
- [Verification & CI Gating](guides/verify.md) — the machine-actionable verdict contract
- [Configuration](getting-started/configuration.md) — models, tiers, and `llm_council.yaml`
