# ADR-019: AI-Powered Outlook Email Analysis for ITIL Operations Insights

**Status:** Proposed
**Date:** 2025-12-18
**Decision Makers:** Engineering, IT Operations
**Council Review:** Full council (GPT-5.1, Claude Opus 4.5, Gemini 3 Pro, Grok-4)

---

## Context

IT Operations teams receive large volumes of unstructured support emails via shared Outlook mailboxes. These emails contain valuable operational intelligence but lack the structure of formal ITSM ticketing systems:

### Current Challenges

| Challenge | Impact |
|-----------|--------|
| Unstructured data | Cannot query "top issues" or "worst apps" |
| Reply chain noise | Signatures, disclaimers, "thank you" messages pollute analysis |
| No ITIL mapping | Emails don't classify as Incident/Problem/Change/Request |
| Pattern blindness | Recurring issues go undetected until major outages |
| Tribal knowledge | Solutions exist in email threads but aren't discoverable |

### Desired Outcomes

1. **Most frequent issues** ranked by volume and severity
2. **Effective solutions** extracted and catalogued
3. **Worst offending applications** identified for remediation
4. **Avoidance strategies** generated proactively
5. **Trend detection** for emerging problems

---

## Decision

Implement a **Hybrid AI Architecture** combining traditional NLP for preprocessing with LLM-based extraction for ITIL insights, using a "Filter-Cluster-Extract" pattern.

### Council Consensus

The LLM Council unanimously agreed on three critical architectural decisions:

1. **Graph API + Pre-processing Layer** (not IMAP/SMTP)
2. **Vector Database + Temporal Aggregation** for pattern detection
3. **Structured JSON Output** constrained to ITIL taxonomy

---

## Architecture

### High-Level Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 1: INGESTION                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Microsoft Graph API                                                         │
│  ├── OAuth 2.0 (Client Credentials Flow)                                    │
│  ├── Delta Queries for incremental sync                                     │
│  ├── Target: Shared mailboxes (support@, helpdesk@)                         │
│  └── Batch: Every 15-60 minutes via orchestrator                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 2: PRE-PROCESSING                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  2a. PII Redaction (MUST be first)                                          │
│      └── Microsoft Presidio: names, emails, IPs, passwords → <REDACTED>     │
│                                                                              │
│  2b. Thread Reconstruction                                                   │
│      └── Group by conversationId, extract First (problem) + Last (solution) │
│                                                                              │
│  2c. Noise Removal                                                           │
│      ├── Signatures: regex for "Best regards", "--", phone patterns         │
│      ├── Disclaimers: keyword match "confidential", "do not reply"          │
│      ├── Reply headers: "On [date] wrote:", "From:", "Sent:"                │
│      └── Transactional: discard <50 words or "thank you" sentiment          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 3: AI PROCESSING                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  3a. Vectorization (Low-cost, high-volume)                                  │
│      ├── Model: text-embedding-3-small or all-MiniLM-L6-v2                  │
│      └── Output: 384-1536 dim vectors per email thread                      │
│                                                                              │
│  3b. Semantic Clustering                                                     │
│      ├── Algorithm: HDBSCAN (density-based, handles noise)                  │
│      └── Result: 1000 emails → ~50 distinct issue clusters                  │
│                                                                              │
│  3c. LLM Extraction (High-cost, cluster centroids only)                     │
│      ├── Model: GPT-4o or Llama-3-70b                                       │
│      ├── Input: Representative emails from each cluster                     │
│      └── Output: Structured JSON (see ITIL Schema below)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 4: STORAGE                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Bronze Layer (Raw)                                                          │
│  └── Azure Blob / S3: Full JSON from Graph API (enables replay)             │
│                                                                              │
│  Vector Store                                                                │
│  └── Pinecone / pgvector / FAISS: Embeddings + metadata                     │
│                                                                              │
│  Silver Layer (Structured)                                                   │
│  └── PostgreSQL: Extracted ITIL records for analytics                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LAYER 5: ANALYTICS                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│  Dashboards: Power BI / Grafana                                              │
│  Reports: Automated weekly PDF via Azure Functions                           │
│  Alerts: Cluster drift detection → Teams/Slack notification                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ITIL Classification Schema

The LLM must output structured JSON conforming to this schema (enforced via Pydantic or JSON mode):

```json
{
  "thread_id": "AAMkAGI2...",
  "timestamp": "2025-12-18T10:30:00Z",

  "classification": {
    "itil_type": "Incident | Problem | Service Request | Change Request | Noise",
    "category": "Hardware | Software | Network | Identity | Security",
    "subcategory": "VPN | Email | ERP | CRM | Endpoint | Other",
    "severity": "Critical | High | Medium | Low",
    "sentiment": "Frustrated | Neutral | Satisfied"
  },

  "extraction": {
    "issue_summary": "One sentence description of the problem",
    "affected_ci": "Application or system name (from approved CI list)",
    "error_message": "Extracted error code or message if present",
    "root_cause": "Identified cause or 'Unknown'",
    "resolution_summary": "How it was resolved or 'Unresolved'",
    "resolution_type": "Restart | Access Grant | Patch | Workaround | Escalation | User Training | Self-Healed"
  },

  "metadata": {
    "thread_length": 5,
    "time_to_resolution_hours": 2.5,
    "participants": ["support@company.com", "<REDACTED>"]
  }
}
```

### Constrained Generation

To prevent hallucination of application names, provide the LLM with an enumerated list of valid Configuration Items:

```python
VALID_CIS = [
    "Microsoft Outlook", "Microsoft Teams", "SAP ERP", "Salesforce CRM",
    "GlobalProtect VPN", "Okta SSO", "ServiceNow", "Jira", "Confluence",
    "Active Directory", "Azure AD", "Office 365", "Other"
]
```

The LLM must select from this list or output "Other" with a free-text description.

---

## Analytics Outputs

### 1. Frequent Issues Report

| Rank | Issue Cluster | Volume | Severity | Top Solution |
|------|---------------|--------|----------|--------------|
| 1 | VPN Connection Failures | 234 | High | Token resync via self-service |
| 2 | Password Reset Requests | 189 | Low | AD self-service portal |
| 3 | Outlook Freezing | 156 | Medium | Clear OST cache |

### 2. Worst Offending Applications

Scoring: `Score = Volume × Severity_Weight × (1 + Negative_Sentiment_Ratio)`

| Application | Incidents | Avg Severity | Frustration Score | Trend |
|-------------|-----------|--------------|-------------------|-------|
| SAP ERP | 89 | High | 0.72 | ↑ 23% |
| GlobalProtect VPN | 234 | Medium | 0.45 | ↓ 12% |
| Microsoft Teams | 67 | Low | 0.31 | → Stable |

### 3. Avoidance Matrix

```
                    HIGH COMPLEXITY (Long threads, escalations)
                              │
     PROBLEM MANAGEMENT       │      ROOT CAUSE ANALYSIS
     (Systemic fixes needed)  │      (Deep investigation)
                              │
    ──────────────────────────┼──────────────────────────────
                              │
     AUTOMATION CANDIDATE     │      TRAINING / DOCUMENTATION
     (Chatbot, self-service)  │      (User education)
                              │
                    LOW COMPLEXITY (Quick resolution)

    LOW FREQUENCY ────────────┼──────────────── HIGH FREQUENCY
```

### 4. Proactive Recommendations

LLM-generated from top clusters:

> "Based on 234 VPN connection failures in the past 30 days, recommend:
> 1. Implement automatic RSA token refresh before expiration
> 2. Create self-service portal for token resync
> 3. Add monitoring alert for certificate expiration"

---

## Privacy & Security

| Concern | Mitigation |
|---------|------------|
| **PII in emails** | Microsoft Presidio redaction BEFORE any AI processing |
| **Credentials in text** | TruffleHog scanner for leaked passwords/API keys |
| **Data residency** | Same-region Azure OpenAI (GDPR/HIPAA compliance) |
| **Access control** | Row-level security by email folder/department |
| **Retention** | Auto-delete raw data after 90 days per policy |
| **LLM data usage** | Zero Data Retention agreement with API provider |

---

## Alternatives Considered

### Alternative 1: Pure LLM Approach (All emails through GPT-4)

**Rejected**: Cost-prohibitive at scale. Processing 10,000 emails/day at $0.01/email = $3,000/month. Hybrid approach reduces LLM calls by 90%+ via clustering.

### Alternative 2: Pure Traditional NLP (No LLM)

**Rejected**: Cannot extract nuanced insights like root causes or generate avoidance recommendations. Keyword-based classification misses semantic similarity ("frozen" vs "hangs" vs "unresponsive").

### Alternative 3: Fine-tuned Domain Model

**Deferred**: Requires 5,000+ labeled examples. Start with few-shot prompting; fine-tune later if accuracy <85% on validation set.

### Alternative 4: Direct IMAP/SMTP Access

**Rejected**: Security concerns (storing credentials), no OAuth support, limited metadata. Graph API provides conversationId, threading, and enterprise-grade auth.

---

## Implementation Phases

### Phase 1: Foundation (Weeks 1-4)
- [ ] Azure AD app registration with Graph API permissions
- [ ] Delta query ingestion pipeline (Azure Functions)
- [ ] PII redaction with Presidio
- [ ] Bronze layer storage (Blob)

### Phase 2: Intelligence (Weeks 5-8)
- [ ] Thread reconstruction and noise filtering
- [ ] Embedding generation pipeline
- [ ] Vector store setup (pgvector or Pinecone)
- [ ] HDBSCAN clustering job

### Phase 3: Extraction (Weeks 9-12)
- [ ] LLM extraction prompts with JSON schema
- [ ] ITIL classification validation
- [ ] Silver layer database schema
- [ ] CI enumeration and constraint logic

### Phase 4: Analytics (Weeks 13-16)
- [ ] Power BI dashboard integration
- [ ] Automated weekly reports
- [ ] Cluster drift alerting
- [ ] Avoidance recommendation generation

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Thread fragmentation** (10 replies = 10 incidents) | High | High | Strict conversationId aggregation |
| **Signature hallucination** (LLM reads signature as issue) | Medium | Medium | Aggressive regex truncation before LLM |
| **Topic drift in reply chains** (new issue in old thread) | Medium | Medium | LLM prompt: "Is this semantically related?" |
| **"Thank you" pollution** | High | Low | Filter messages <50 words + positive sentiment |
| **Cost overruns** | Medium | High | Cluster-first approach; LLM only for centroids |
| **Compliance breach** (PII to external LLM) | Low | Critical | Presidio redaction as FIRST step, not optional |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Issue classification accuracy | >85% F1 | Manual validation of 200 samples |
| Pattern detection coverage | >90% of issues in clusters | Noise cluster <10% |
| Time to insight | <24 hours | Ingestion to dashboard latency |
| Cost per email | <$0.001 | Total monthly cost / emails processed |
| Actionable recommendations | 5+ per week | Auto-generated avoidance strategies |

---

## Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| Ingestion | MS Graph API + Azure Functions | Native O365 integration, serverless scale |
| Orchestration | Apache Airflow | Complex DAG support, monitoring |
| PII Redaction | Microsoft Presidio | Open source, runs locally |
| Embeddings | text-embedding-3-small | Cost-effective, good quality |
| Vector Store | pgvector (PostgreSQL) | Single database, familiar SQL |
| Clustering | HDBSCAN (scikit-learn) | Handles noise, variable density |
| LLM | Azure OpenAI GPT-4o | Enterprise compliance, JSON mode |
| Structured Output | Pydantic + Instructor | Schema enforcement |
| Analytics | Power BI | Enterprise standard, Graph integration |
| Alerting | Azure Logic Apps | Low-code, Teams/Slack integration |

---

## References

- [Microsoft Graph API Mail Documentation](https://learn.microsoft.com/en-us/graph/api/resources/mail-api-overview)
- [Microsoft Presidio](https://microsoft.github.io/presidio/)
- [ITIL 4 Foundation](https://www.axelos.com/certifications/itil-service-management/itil-4-foundation)
- [HDBSCAN Clustering](https://hdbscan.readthedocs.io/)
- [OpenAI JSON Mode](https://platform.openai.com/docs/guides/structured-outputs)

---

## Council Review Summary

**Reviewed by**: GPT-5.1, Claude Opus 4.5, Gemini 3 Pro, Grok-4

**Council Rankings**:
1. Claude Opus 4.5 (0.667) - Hybrid embeddings + LLM approach
2. GPT-5.1 (0.500) - Feedback loop emphasis
3. Gemini 3 Pro (0.333) - PII-first architecture
4. Grok-4 (0.000) - Cloud-native scaling

**Key Council Insights**:
- PII redaction must be architectural prerequisite, not afterthought
- Vector clustering before LLM extraction reduces costs 90%+
- Structured JSON output prevents ITIL taxonomy drift
- Time-windowed aggregation distinguishes chronic vs acute issues
