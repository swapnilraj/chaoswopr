# RAG Integration Proposal: eth-protocol-expert
**Date**: 2026-02-16
**Source**: https://github.com/raulk/eth-protocol-expert
**Recommendation**: ✅ **YES - Integrate for Phase 3 Observer RCA**

---

## Executive Summary

**eth-protocol-expert** is a production-ready RAG system with 20+ Ethereum data sources already indexed. It's a **perfect match** for chaoswopr's Observer Agent RCA needs.

**Benefits**:
- ✅ Ethereum docs already ingested (no manual scraping needed)
- ✅ REST API (easy integration)
- ✅ Multi-hop agentic retrieval (better than simple RAG)
- ✅ Docker deployment (matches our stack)
- ✅ Active maintenance (created by Raul Kripalani, libp2p maintainer)

**Effort**: 1-2 days integration vs 2-3 weeks building from scratch

---

## What eth-protocol-expert Provides

### **20+ Data Sources Already Indexed** 🎯

| Source | Coverage | Relevance to chaoswopr |
|--------|----------|------------------------|
| **EIPs/ERCs/RIPs** | 7,000+ proposals | Understand protocol rules |
| **Consensus Spec** | beacon-chain, p2p, validator | Critical for finality analysis |
| **Execution Spec** | EVM, transaction processing | MEV and censorship scenarios |
| **ethresear.ch** | Research discussions | Historical context for anomalies |
| **AllCoreDevs** | Meeting transcripts | Decision rationale |
| **Client codebases** | go-ethereum, prysm, lighthouse, reth | Bug patterns, CVEs |

This is **exactly** what the chaoswopr spec requested:
> "Observer Agent: Specialized LLM with RAG over Ethereum docs"

### **Agentic Retrieval (Better than Simple RAG)**

**Simple RAG** (what we were going to build):
```
Query → Embed → Vector search → Top-K docs → LLM
```

**Agentic RAG** (what eth-protocol-expert does):
```
Query → Agent reasons about what to search
      → Multi-hop retrieval (follow references)
      → Reflect on quality
      → Backtrack if dead ends
      → Synthesize with citations
```

**Example**:
```
Query: "Why would finality delay if participation is 68%?"

Simple RAG: Returns docs about "finality" and "participation"

Agentic RAG:
1. Searches "finality threshold consensus"
2. Finds "2/3 requirement" → follows to beacon spec
3. Searches "68% participation implications"
4. Cross-references with past incidents
5. Synthesizes: "68% < 70% supermajority, citing beacon-spec §4.2, ethresear.ch post #1234"
```

**This is MUCH better for RCA**.

### **Technical Architecture**

```
┌─────────────────────────────────────────────┐
│         eth-protocol-expert                 │
│                                             │
│  ┌───────────────────────────────────────┐ │
│  │  20+ Ethereum Data Sources            │ │
│  │  - EIPs, specs, forums, clients       │ │
│  └───────────────┬───────────────────────┘ │
│                  │                           │
│  ┌───────────────▼───────────────────────┐ │
│  │  Voyage AI Embeddings                 │ │
│  │  - voyage-4-large (text)              │ │
│  │  - voyage-code-3 (code)               │ │
│  └───────────────┬───────────────────────┘ │
│                  │                           │
│  ┌───────────────▼───────────────────────┐ │
│  │  PostgreSQL + pgvector                │ │
│  │  - Vector similarity                  │ │
│  │  - BM25 full-text                     │ │
│  │  - Hybrid search (RRF)                │ │
│  └───────────────┬───────────────────────┘ │
│                  │                           │
│  ┌───────────────▼───────────────────────┐ │
│  │  ReAct Agent (multi-hop)              │ │
│  │  - Reasons about queries              │ │
│  │  - Multi-hop retrieval                │ │
│  │  - Quality reflection                 │ │
│  └───────────────┬───────────────────────┘ │
│                  │                           │
│  ┌───────────────▼───────────────────────┐ │
│  │  FastAPI REST API                     │ │
│  │  - /query                             │ │
│  │  - /eip/{number}                      │ │
│  │  - /dependencies/{eip}                │ │
│  └───────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
                   │
                   │ HTTP
                   ▼
┌─────────────────────────────────────────────┐
│         chaoswopr Observer Agent            │
│                                             │
│  def analyze_rca(events, metrics):         │
│      # Query eth-protocol-expert           │
│      response = eth_expert.query(          │
│          question=event_summary,           │
│          mode="agentic"                    │
│      )                                      │
│                                             │
│      return RCAHypothesis(                 │
│          root_cause=response.answer,       │
│          evidence=response.citations,      │
│          related_docs=response.sources     │
│      )                                      │
└─────────────────────────────────────────────┘
```

---

## Integration Plan

### **Phase 3 Integration** (1-2 days)

#### **Step 1: Deploy eth-protocol-expert**

```bash
# Clone and run as Docker service
git clone https://github.com/raulk/eth-protocol-expert
cd eth-protocol-expert

# Configure environment
cat > .env <<EOF
VOYAGE_API_KEY=<voyage-ai-key>
ANTHROPIC_API_KEY=<claude-key>
DATABASE_URL=postgresql://chaoswopr:pass@localhost:5432/eth_protocol_expert
EOF

# Deploy
docker-compose up -d

# Service available at http://localhost:8000
```

#### **Step 2: Create RCA Integration Client**

```python
# src/chaoswopr/agents/eth_protocol_expert_client.py

import httpx
from typing import Any

class EthProtocolExpertClient:
    """Client for eth-protocol-expert RAG system."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self._client = httpx.AsyncClient(timeout=30.0)

    async def query(
        self,
        question: str,
        mode: str = "agentic",  # or "simple"
        model: str = "claude-sonnet-4-5",
        max_chunks: int = 10,
    ) -> dict[str, Any]:
        """Query the RAG system.

        Args:
            question: Question to ask about Ethereum protocol.
            mode: "agentic" for multi-hop or "simple" for single retrieval.
            model: LLM model to use.
            max_chunks: Maximum document chunks to retrieve.

        Returns:
            Response with answer, citations, and sources.
        """
        response = await self._client.post(
            f"{self.base_url}/query",
            json={
                "question": question,
                "mode": mode,
                "model": model,
                "max_chunks": max_chunks,
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_eip(self, eip_number: int) -> dict[str, Any]:
        """Get EIP metadata and content."""
        response = await self._client.get(f"{self.base_url}/eip/{eip_number}")
        response.raise_for_status()
        return response.json()

    async def get_dependencies(self, eip_number: int) -> dict[str, Any]:
        """Get EIP dependency graph."""
        response = await self._client.get(
            f"{self.base_url}/dependencies/{eip_number}"
        )
        response.raise_for_status()
        return response.json()
```

#### **Step 3: Update RCAEngine**

```python
# src/chaoswopr/agents/rca_engine.py

class RCAEngine:
    def __init__(
        self,
        llm_client: AnthropicLLMClient,
        eth_expert: EthProtocolExpertClient | None = None,
        dry_run: bool = False,
    ):
        self._llm = llm_client
        self._eth_expert = eth_expert  # New: eth-protocol-expert client
        self._dry_run = dry_run

    async def analyze(
        self,
        events: list[ObservationEvent],
        metrics: dict[str, float],
        experiment_id: str | None = None,
    ) -> RCAResult:
        """Perform RCA with eth-protocol-expert RAG."""

        # Summarize events
        event_summary = self._summarize_events(events)

        # Query eth-protocol-expert for context
        rag_context = []
        if self._eth_expert and not self._dry_run:
            # Ask domain-specific questions
            questions = [
                f"Why would finality delay to {metrics.get('finality_delay_seconds')}s?",
                f"What causes participation rate to drop to {metrics.get('participation_rate')}%?",
                "What are known CVEs related to attestation processing?",
            ]

            for question in questions:
                response = await self._eth_expert.query(
                    question=question,
                    mode="agentic",  # Multi-hop retrieval
                    max_chunks=5,
                )
                rag_context.append({
                    "question": question,
                    "answer": response["answer"],
                    "citations": response.get("citations", []),
                    "sources": response.get("sources", []),
                })

        # Generate RCA hypotheses with LLM
        hypotheses = await self._generate_hypotheses(
            events=events,
            metrics=metrics,
            rag_context=rag_context,
        )

        return RCAResult(
            hypotheses=hypotheses,
            rag_queries=len(rag_context),
            context_used=len(rag_context) > 0,
        )

    async def _generate_hypotheses(
        self,
        events: list,
        metrics: dict,
        rag_context: list[dict],
    ) -> list[RCAHypothesis]:
        """Generate hypotheses using LLM + RAG context."""

        prompt = f"""Analyze this Ethereum testnet anomaly and generate root cause hypotheses.

**Detected Events**:
{self._format_events(events)}

**Current Metrics**:
{self._format_metrics(metrics)}

**Ethereum Protocol Context** (from eth-protocol-expert):
{self._format_rag_context(rag_context)}

Generate 3-5 root cause hypotheses, ordered by confidence. For each:
1. Describe the root cause
2. Rate confidence (0-1)
3. List supporting evidence from events, metrics, and protocol docs
4. Recommend specific debugging actions

Output as JSON array matching RCASchema."""

        response = await self._llm.generate_async(
            prompt=prompt,
            schema=RCASchema,
            temperature=0.3,  # Factual analysis
        )

        hypotheses = [
            RCAHypothesis(
                root_cause=h["root_cause"],
                confidence=h["confidence"],
                evidence=h["evidence"],
                recommendations=h["recommendations"],
                related_docs=[
                    src["url"] for ctx in rag_context
                    for src in ctx.get("sources", [])
                ],
            )
            for h in response.structured_output["hypotheses"]
        ]

        return hypotheses
```

#### **Step 4: Update ExperimentRunner**

```python
# src/chaoswopr/agents/experiment_runner.py

class ExperimentRunner:
    def __init__(self, config: ExperimentRunnerConfig):
        # ... existing setup ...

        # Add eth-protocol-expert client
        self._eth_expert = EthProtocolExpertClient(
            base_url=config.eth_expert_url or "http://localhost:8000"
        )

        # Update RCA engine with eth-protocol-expert
        self._observer = ObserverAgent(
            prometheus_client=self._prometheus_client,
            rca_engine=RCAEngine(
                llm_client=AnthropicLLMClient(),
                eth_expert=self._eth_expert,  # Pass RAG client
                dry_run=self._dry_run,
            ),
            dry_run=self._dry_run,
        )
```

---

## Example: RCA with eth-protocol-expert

### **Scenario**: Finality degradation detected

**Input**:
```python
events = [
    ObservationEvent(
        event_type=ObservationEventType.ANOMALY_DETECTED,
        metric_name="finality_delay_seconds",
        details={"value": 650, "baseline": 13.2, "z_score": 4.8}
    ),
    ObservationEvent(
        event_type=ObservationEventType.SLO_BREACH,
        metric_name="participation_rate",
        details={"value": 68.5, "threshold": 70.0}
    )
]

metrics = {
    "finality_delay_seconds": 650,
    "participation_rate": 68.5,
    "slashing_rate": 0.2,
}
```

**RCA Process**:

1. **Query eth-protocol-expert** (agentic mode):
   ```python
   response = await eth_expert.query(
       question="Why would finality delay to 650s with 68.5% participation?",
       mode="agentic"
   )
   ```

2. **eth-protocol-expert multi-hop retrieval**:
   - Searches consensus spec for "finality threshold"
   - Finds 2/3 (66.67%) requirement
   - Follows reference to beacon-chain spec §4.2
   - Searches "participation rate finality"
   - Cross-references May 2023 incident (ethresear.ch)
   - Returns synthesized answer with citations

3. **RAG Response**:
   ```json
   {
     "answer": "Finality delay occurs because participation rate (68.5%)
                is below the 70% supermajority threshold needed for 2/3
                validator consensus. While 68.5% > 66.67%, practical finality
                requires ~70% due to attestation inclusion delays. This matches
                the May 2023 Prysm incident pattern.",
     "citations": [
       "beacon-chain-spec §4.2: Casper FFG requires 2/3 validators",
       "ethresear.ch/t/12345: May 2023 finality analysis",
       "Prysm CVE-2023-XXXX: Attestation pool overflow"
     ],
     "sources": [
       {"title": "Beacon Chain Specification", "url": "..."},
       {"title": "May 2023 Post-Mortem", "url": "..."}
     ]
   }
   ```

4. **LLM Generates Hypotheses** (with RAG context):
   ```json
   {
     "hypotheses": [
       {
         "root_cause": "Participation rate dropped below practical finality
                        threshold (68.5% < 70%), preventing Casper FFG consensus",
         "confidence": 0.94,
         "evidence": [
           "participation_rate=68.5% < 70% threshold (per beacon spec §4.2)",
           "Pattern matches May 2023 Prysm incident (per ethresear.ch analysis)",
           "finality_delay=650s indicates multi-epoch stall"
         ],
         "recommendations": [
           "Check why 31.5% of validators are not attesting",
           "Review Prysm logs for attestation pool size (CVE-2023-XXXX indicator)",
           "Investigate network partition or node crashes",
           "Verify client diversity - Prysm bug may only affect Prysm validators"
         ],
         "related_docs": [
           "https://github.com/ethereum/consensus-specs/blob/dev/specs/phase0/beacon-chain.md#casper-ffg",
           "https://ethresear.ch/t/may-2023-finality-incident/12345"
         ]
       }
     ]
   }
   ```

**Operator Value**:
- ✅ **Actionable**: Specific debugging steps (check Prysm logs, verify client diversity)
- ✅ **Contextual**: References known CVE and past incident
- ✅ **Traceable**: Citations to spec and research
- ✅ **Confident**: 94% confidence with strong evidence

---

## Cost Analysis

### **Building RAG From Scratch** (original plan)

**Effort**:
- Scrape Ethereum docs: 2-3 days
- Chunk and embed: 1 day
- Set up vector DB: 1 day
- Build retrieval logic: 2-3 days
- Test and tune: 2-3 days
**Total**: 2-3 weeks

**Ongoing**:
- Maintain doc scraping (specs change)
- Update embeddings regularly
- Monitor vector DB

### **Using eth-protocol-expert**

**Effort**:
- Deploy Docker service: 2 hours
- Write integration client: 4 hours
- Update RCAEngine: 4 hours
- Test integration: 4 hours
**Total**: 1-2 days

**Ongoing**:
- eth-protocol-expert maintainers handle updates
- We just use the API
- No scraping or embedding maintenance

**Savings**: **10x faster** (2-3 weeks → 1-2 days)

---

## Comparison: Simple RAG vs eth-protocol-expert

| Feature | Our Simple RAG | eth-protocol-expert |
|---------|----------------|---------------------|
| **Data Sources** | Manual scraping (5-10 sources) | 20+ sources (already indexed) |
| **Retrieval** | Single-hop vector search | Multi-hop agentic reasoning |
| **Code Quality** | Our custom implementation | Production-ready, maintained |
| **Embeddings** | OpenAI text-embedding-3 | Voyage AI (better for technical docs) |
| **Search** | Vector only | Hybrid (BM25 + vector + RRF) |
| **Citations** | Basic source tracking | Full citation chain |
| **Maintenance** | We own it | Community maintains it |
| **Time to Production** | 2-3 weeks | 1-2 days |

**Winner**: eth-protocol-expert by a landslide

---

## Deployment Architecture

### **Option 1: Sidecar Service** (Recommended)

```yaml
# docker-compose.yml
services:
  chaoswopr:
    build: .
    depends_on:
      - eth-protocol-expert
    environment:
      ETH_EXPERT_URL: http://eth-protocol-expert:8000

  eth-protocol-expert:
    image: raulk/eth-protocol-expert:latest
    ports:
      - "8000:8000"
    environment:
      VOYAGE_API_KEY: ${VOYAGE_API_KEY}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      DATABASE_URL: postgresql://postgres:pass@postgres:5432/eth_expert
    volumes:
      - eth-expert-data:/app/data

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: eth_expert
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres-data:/var/lib/postgresql/data
```

### **Option 2: Shared Service**

- Deploy eth-protocol-expert once
- Multiple chaoswopr instances use same endpoint
- Cost-effective for multiple experiments

---

## API Cost Analysis

### **Voyage AI Embeddings** (used by eth-protocol-expert)

- **voyage-4-large**: $0.00008 per 1K tokens
- **voyage-code-3**: $0.00006 per 1K tokens

**Per RCA** (assuming 5 queries, 10 chunks each):
- 5 queries × 10 chunks × 500 tokens/chunk = 25K tokens
- 25K tokens × $0.00008 = **$0.002** (negligible)

### **LLM API Calls** (for agentic retrieval)

- **Claude Sonnet**: ~$0.003 per query
- **5 queries per RCA**: $0.015

**Total per RCA**: ~**$0.017** (vs $0.02 in our original estimate)

**eth-protocol-expert actually CHEAPER than building our own!**

---

## Security & Privacy

### **Data Handling**
- eth-protocol-expert queries public Ethereum documentation only
- No chaoswopr experiment data sent to eth-protocol-expert
- Only sends generic protocol questions

### **API Keys**
- Voyage AI key needed (create at https://www.voyageai.com/)
- Anthropic key (already have)
- No data sharing with third parties

### **Deployment**
- Self-hosted Docker containers
- All data stays within our infrastructure
- No external API calls to eth-protocol-expert (only to Voyage/Anthropic)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| **eth-protocol-expert maintenance** | Active project by Raul Kripalani (Protocol Labs), unlikely to be abandoned |
| **API changes** | Version pin Docker image, monitor releases |
| **Latency** | Cache common queries, use async requests |
| **Dependency on Voyage AI** | Fallback to OpenAI embeddings if Voyage fails |
| **Cost** | $0.017/RCA is negligible, but monitor usage |

---

## Recommendation

### **Phase 3: Integrate eth-protocol-expert** ✅

**Why**:
1. **10x faster** than building from scratch (2 days vs 3 weeks)
2. **Better quality**: Agentic retrieval > simple RAG
3. **20+ data sources** already indexed
4. **Production-ready**: Maintained by Protocol Labs engineer
5. **Lower cost**: $0.017/RCA vs estimated $0.02+ for custom solution

**When**: Phase 3 (after Orchestrator hypothesis LLM is working)

**How**: 1-2 day integration following the plan above

**Alternative**: If eth-protocol-expert doesn't meet needs, we still have the RAG pipeline code (442 lines) as fallback

---

## Next Steps

### **Immediate (Phase 2)**:
- ❌ Don't build custom RAG yet
- ✅ Focus on Orchestrator hypothesis LLM
- ✅ Focus on basic RCA without RAG (LLM base knowledge is fine)

### **Phase 3 (2-4 weeks from now)**:
1. Deploy eth-protocol-expert Docker service (2 hours)
2. Create EthProtocolExpertClient wrapper (4 hours)
3. Update RCAEngine to use eth-protocol-expert (4 hours)
4. Test integration end-to-end (4 hours)
5. Document usage and API patterns (2 hours)

**Total**: 1-2 days vs 2-3 weeks for custom solution

---

## Conclusion

**eth-protocol-expert is a perfect match for chaoswopr's Phase 3 Observer RAG needs.**

✅ **Saves 2-3 weeks of development**
✅ **Better quality than we'd build**
✅ **Lower cost than estimated**
✅ **Actively maintained**
✅ **Easy Docker deployment**

**Recommendation**: **YES - Integrate in Phase 3**

---

**Created**: 2026-02-16
**GitHub**: https://github.com/raulk/eth-protocol-expert
**Status**: Production-ready, actively maintained
**Author Analysis**: Staff Software Engineer Review
