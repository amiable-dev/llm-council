# Streaming Deliberation

A council deliberation takes 30–600s. Instead of a spinner, stream it live
(ADR-046) — on HTTP via SSE, and on MCP via progress notifications.

## SSE (HTTP)

```bash
curl -N "http://localhost:8000/v1/council/stream?prompt=What+is+AI"
```

Every event carries the v1 envelope: `v`, `session_id`, `ts`, and a
monotonic `seq`. Schema changes are additive-only within `v: 1`.

| Event | Payload | When |
|---|---|---|
| `council.deliberation_start` | `prompt` (truncated) | start |
| `stage1.response` | `model`, `response`, `latency_ms`, `usage` | each model's answer, as it lands |
| `council.stage1.complete` | counts | stage 1 done |
| `stage2.review` | `reviewer`, `ranking`, `parse_ok` | each peer review, as it lands |
| `consensus.early_termination` | ADR-044 payload | early consensus (flag-on) |
| `council.stage2.complete` | counts | stage 2 done |
| `stage3.start` | `chairman` | synthesis begins |
| `synthesis.delta` | `text` | chairman tokens (opt-in) |
| `council.complete` / `council.error` | full result / error | terminal |

## Chairman token streaming (opt-in)

```bash
curl -N "http://localhost:8000/v1/council/stream?prompt=...&stream_tokens=true"
```

`synthesis.delta` events carry the chairman's tokens as generated. The
streamed path assembles the **same synthesis text and result structure** as
the non-streamed path (equality-tested); transport failure silently falls
back to the regular call. One deliberate difference: the SSE wire protocol
carries no usage data, so a token-streamed stage 3 reports its usage as
*unknown* (`cost_known: false`) rather than fabricating a number — ADR-011
semantics. If you need exact stage-3 cost accounting, run without
`stream_tokens`.

## MCP progress

`consult_council` and `verify` emit MCP progress notifications through the
stages — per-model in stage 1 ("✓ gpt-5.4 (2/4)"), per-reviewer in stage 2
("claude reviewed (3/4)"), then synthesis. Clients that render progress
(Claude Code, Cursor) show these live; clients that ignore progress lose
nothing.

## Guarantees

- Non-streaming responses are **byte-identical** — streaming wiring only
  activates when a stream consumer is attached (test-pinned).
- Client disconnect cancels the deliberation promptly (no wasted spend).
