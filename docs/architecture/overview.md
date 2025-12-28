# Architecture Overview

LLM Council uses a multi-stage deliberation process inspired by academic peer review.

## High-Level Flow

```
User Query
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 1: Independent Responses              │
│ • All council models queried in parallel    │
│ • No knowledge of other responses           │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 2: Anonymous Peer Review              │
│ • Responses labeled A, B, C (randomized)    │
│ • Each model ranks all responses            │
│ • Self-votes excluded from aggregation      │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ STAGE 3: Chairman Synthesis                 │
│ • Receives all responses + rankings         │
│ • Produces final synthesized answer         │
└─────────────────────────────────────────────┘
    ↓
Final Response + Metadata
```

## Layer Architecture (ADR-024)

| Layer | Responsibility |
|-------|----------------|
| L1: Tier Selection | Choose confidence tier |
| L2: Query Triage | Classify and optimize query |
| L3: Orchestration | Coordinate council stages |
| L4: Gateway | Route to LLM providers |

## Key Design Decisions

### Anonymization

Models review responses labeled "Response A", "Response B", etc. This prevents:

- Self-preference bias
- Provider loyalty
- Model recognition

### Peer Review

Each model evaluates all responses independently, providing:

- Rankings (ordered preference)
- Scores (numeric ratings)
- Justifications

### Graceful Degradation

If some models fail:

- Continue with successful responses
- Note excluded models in metadata
- Never fail entire request for single model failure

## Configuration Layers

```
YAML File
    ↓
Environment Variables (override)
    ↓
Runtime Parameters (override)
```

See [ADRs](adrs.md) for detailed design decisions.
