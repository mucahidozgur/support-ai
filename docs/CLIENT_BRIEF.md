
### 3) `docs/CLIENT_BRIEF.md`

```markdown
# Client Brief — SupportHub AI Assistant

**Client:** SupportHub
**Industry:** B2B SaaS, customer support platform
**Engagement:** Hourly, 1-3 months, ongoing
**Rate:** $30-50/hr, 30+ hrs/week

---

## The problem

SupportHub's enterprise customers submit support tickets through their
platform. Support agents answer by searching a knowledge base of 5,000+
articles — manually. This takes 30% of their time.

Current attempts at AI chatbots fail in two ways:
1. They **hallucinate** answers not backed by the KB
2. They don't show **which document** the answer came from

For enterprise customers, a wrong answer means lost revenue. So SupportHub
needs an AI assistant that is either **correct with proof**, or **silent**.

---

## Required features

### 1. RAG chat with citations
- Agent asks: "How do I configure SSO for enterprise?"
- AI retrieves top-k chunks from KB
- **Every claim cites:** document ID + chunk ID + similarity score
- If no chunk above confidence threshold: "Bu bilgi knowledge base'de
  bulunmuyor. İlgili dokümanı arayın veya uzmana danışın."

### 2. Ticket summarization
- Agent pastes 20-message ticket → 3-bullet summary
- Must cite which messages were summarized

### 3. Suggested response generation
- Agent drafts a reply to customer
- AI suggests improvements based on KB
- Each suggestion links to source article

### 4. Evaluation dashboard
- RAGAS metrics: faithfulness, answer relevance, context precision, recall
- Sample size: 50 synthetic Q&A pairs
- Tracked per release

### 5. Observability
- Every retrieval call traced
- Every LLM call logged (prompt, response, tokens, latency)
- Langfuse dashboard for debugging

---

## Non-negotiables

| Rule | Rationale |
|------|-----------|
| **Citation required** | Every answer cites source (document + chunk) |
| **No hallucination** | If below threshold, say "not found" |
| **Self-critique** | RAG answer → critic check → final (if critic rejects, retry or "not found") |
| **Traceable** | Every retrieval/LLM call in Langfuse |
| **Measurable** | RAGAS score tracked per release, minimum 0.85 faithfulness |

---

## Success criteria (client-defined)

- Faithfulness (RAGAS) ≥ 0.85
- Context precision ≥ 0.75
- Answer relevance ≥ 0.80
- Zero hallucinated citations in 50-question audit
- p95 latency ≤ 3 seconds (SSE streaming)

---

## Timeline

Week 1-2: Base infrastructure + hybrid search + reranking
Week 3-4: Evaluation + observability + self-critique agent
Week 5-6: Admin dashboard + docs + handoff

---

## Billing

- Hourly: $30-50/hr
- Minimum: 30 hrs/week
- Payment: weekly, through Upwork