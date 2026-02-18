# LLM Integration Analysis
**Date**: 2026-02-16
**Question**: Where does LLM integration for nodes and orchestrator make sense?

---

## TL;DR

**Actually Needed**: 2 places (Orchestrator hypothesis, Observer RCA)
**Over-Engineering**: 3 places (Node agent "decisions", Plan compilation, RAG consultation)
**Current State**: All LLM calls are mocked, none are actually integrated

---

## By Component Analysis

### 1. 🟢 **Orchestrator Agent - JUSTIFIED LLM USE**

#### **Where**: Hypothesis Generation (HypothesisEngine)

**Current State**: Template-based (752 lines)
**Should Be**: LLM-powered adaptive hypothesis generation

**Why LLM Makes Sense Here**:
```python
# INPUT: Scenario + current cluster metrics
scenario = {
    "name": "finality_stress_test",
    "description": "Test network finality under high validator stress"
}
cluster_metrics = {
    "finality_delay_seconds": 13.2,
    "participation_rate": 96.3,
    "validator_count": 384
}

# LLM PROMPT:
"""You are an Ethereum chaos engineering expert. Given this scenario and
current network state, generate a testable hypothesis for resilience testing.

Scenario: {scenario}
Current Metrics: {cluster_metrics}

Generate a hypothesis that:
1. Predicts specific behavior under fault conditions
2. Specifies blast radius (max 33% nodes)
3. Defines measurable success criteria
4. Estimates expected metric ranges

Output as JSON conforming to HypothesisSchema."""

# LLM OUTPUT:
{
  "prediction": "Network will maintain finality with 25% validator crashes
                 but participation will drop to 75-80%",
  "blast_radius_percent": 25.0,
  "expected_metrics": {
    "finality_delay_seconds": {"min": 30, "max": 120},
    "participation_rate": {"min": 75, "max": 85}
  },
  "rationale": "Based on 2/3 consensus requirement, 25% offline should not
                prevent finality but will reduce participation..."
}
```

**Benefits**:
- **Adaptive learning**: "Previous test at 20% passed easily, try 27% to find boundary"
- **Context-aware**: Considers current network state, not just templates
- **Explainable**: Generates rationale for hypothesis

**Implementation**:
```python
class HypothesisEngine:
    def __init__(self, llm_client: AnthropicLLMClient):
        self._llm = llm_client

    def generate(self, scenario: dict, cluster_state: dict) -> Hypothesis:
        prompt = self._build_hypothesis_prompt(scenario, cluster_state)

        # LLM generates structured hypothesis
        response = self._llm.generate(
            prompt=prompt,
            schema=HypothesisSchema,  # Force JSON schema compliance
            temperature=0.7  # Allow creativity in hypothesis design
        )

        hypothesis = Hypothesis.from_dict(response.structured_output)

        # Validate safety constraints
        if hypothesis.blast_radius_percent > 33.0:
            hypothesis.blast_radius_percent = 33.0  # Hard safety limit

        return hypothesis
```

**Current Code Issue**: Uses 329-line template system instead of LLM
**Recommendation**: **IMPLEMENT THIS** - This is the core value-add of AI chaos engineering

---

### 2. ❌ **Orchestrator Agent - NO LLM NEEDED**

#### **Where**: Plan Compilation (PlanCompiler)

**Current State**: 722 lines of transformation logic
**Should Be**: Simple mapping function (no LLM)

**Why LLM Doesn't Make Sense**:
```python
# This is deterministic transformation, not AI decision-making
hypothesis.fault_timeline = [
    {"time": 0, "action": "baseline"},
    {"time": 60, "action": "inject_latency", "params": {"ms": 200}},
    {"time": 360, "action": "remove_faults"}
]

# Just map to executable actions:
plan.actions = [
    Action(time=0, type="BASELINE_OBSERVE"),
    Action(time=60, type="INJECT_NETWORK_LATENCY", targets=nodes[0:10], params={"latency_ms": 200}),
    Action(time=360, type="REMOVE_ALL_FAULTS")
]
```

**This is data structure transformation, not intelligence**.

**Recommendation**: **REMOVE LLM**, keep as simple mapping function (~150 lines)

---

### 3. 🟡 **Node Agents - DEBATABLE**

#### **Where**: "AI-controlled validator" decision-making

**From SPEC**:
> "Node Agents (50-500 instances): AI agent controlling validator keys -
> 70% honest protocol, 30% adversarial with coordination"

**Current Implementation**: Static mode switching (honest vs adversarial)

```python
class NodeAgent:
    def switch_mode(self, mode: AgentMode):
        if mode == AgentMode.ADVERSARIAL:
            self.behavior = WithholdAttestationsBehavior()
```

**LLM Vision** (from spec):
```python
# Each node agent has its own LLM instance (via vLLM batching)
class LLMNodeAgent:
    async def decide_action(self, context: ValidatorContext) -> Action:
        prompt = f"""You are controlling validator {self.validator_id}.
        Current epoch: {context.epoch}
        Your role: {'HONEST' if self.honest else 'ADVERSARIAL'}

        Recent attestations: {context.recent_attestations}
        Pending duties: {context.duties}

        If ADVERSARIAL, you can:
        - Withhold attestations (reduce participation)
        - Delay attestation submission
        - Equivocate (sign conflicting blocks)

        What action do you take this epoch?"""

        action = await self._llm.generate(prompt, schema=ActionSchema)
        return action
```

**Analysis**:

**Pros of LLM Node Agents**:
- More realistic adversarial behavior (not just random)
- Can coordinate attacks ("If 3 other adversarial agents withheld, I will too")
- Emergent Byzantine behaviors

**Cons of LLM Node Agents**:
- **Massive cost**: 500 LLM calls per epoch (12 seconds) = ~41 calls/second = $$$$
- **Latency**: Can't make real protocol decisions (attestations due in 4 seconds)
- **Determinism lost**: Can't reproduce experiments exactly
- **Complexity**: vLLM cluster required for batching

**SPEC says**: "vLLM for node agent LLMs" - implying batch inference for cost control

**My Recommendation**: **Phase 3 Feature, Not Phase 2**

**Phase 2 Reality Check**:
- 10 agents, not 500
- Simple behaviors (withhold, delay, equivocate) can be scripted
- LLM decisions are too slow for 12-second epoch cycles
- **Use rule-based behaviors for now**

```python
# Phase 2: Rule-based adversarial behaviors
class AdversarialBehavior:
    def decide(self, context):
        if random() < self.withhold_probability:
            return Action.WITHHOLD_ATTESTATION
        return Action.SUBMIT_ATTESTATION

# Phase 3: LLM-based (if latency allows)
class LLMAdversarialBehavior:
    async def decide(self, context):
        action = await self._llm.generate_async(...)
        return action
```

**Implementation Priority**: **LOW** for Phase 2, **MEDIUM** for Phase 3

---

### 4. 🟢 **Observer Agent - JUSTIFIED LLM USE**

#### **Where**: Root Cause Analysis (RCAEngine)

**Current State**: Mock-only implementation
**Should Be**: LLM-powered RCA with RAG

**Why LLM Makes Sense**:
```python
# DETECTED ANOMALIES:
events = [
    {"type": "ANOMALY", "metric": "finality_delay_seconds", "value": 650, "z_score": 4.2},
    {"type": "SLO_BREACH", "metric": "participation_rate", "value": 68.5, "threshold": 70.0},
]

# CURRENT METRICS:
metrics = {
    "finality_delay_seconds": 650,
    "participation_rate": 68.5,
    "slashing_rate": 0.2,
    "block_proposal_rate": 0.88
}

# RAG RETRIEVAL (from Ethereum docs):
rag_context = [
    "Finality requires 2/3 validators attesting...",
    "CVE-2023-XXXX: Prysm attestation pool overflow under high latency...",
    "May 2023 incident: finality degraded when participation < 70%..."
]

# LLM PROMPT:
"""You are analyzing an Ethereum testnet anomaly.

Detected Issues:
{events}

Current Metrics:
{metrics}

Relevant Documentation:
{rag_context}

Generate root cause hypotheses explaining these anomalies. For each hypothesis:
1. Describe the root cause
2. Rate confidence (0-1)
3. List supporting evidence
4. Recommend corrective actions

Output as JSON array of hypotheses."""

# LLM OUTPUT:
{
  "hypotheses": [
    {
      "root_cause": "Participation rate dropped below 70% threshold, preventing finality",
      "confidence": 0.92,
      "evidence": [
        "participation_rate=68.5% < 70% required for 2/3 consensus",
        "Matches CVE-2023-XXXX symptoms (attestation delays)"
      ],
      "recommendations": [
        "Investigate why 31.5% of validators are not attesting",
        "Check for network partition or client crashes",
        "Review Prysm validator logs for attestation pool size"
      ]
    },
    {
      "root_cause": "Network latency causing attestation inclusion delays",
      "confidence": 0.67,
      "evidence": ["Finality delay 650s indicates multi-epoch lag"]
      ...
    }
  ]
}
```

**Benefits**:
- **Contextual understanding**: Connects symptoms to known issues (CVE, past incidents)
- **Actionable recommendations**: Not just "finality failed", but specific debugging steps
- **Explainable**: Shows reasoning chain for operators

**Implementation**:
```python
class RCAEngine:
    def __init__(self, llm_client: AnthropicLLMClient, rag_pipeline: RAGPipeline):
        self._llm = llm_client
        self._rag = rag_pipeline

    def analyze(self, events: list, metrics: dict) -> RCAResult:
        # 1. Query RAG for relevant context
        event_summary = self._summarize_events(events)
        rag_docs = self._rag.search(event_summary, top_k=5)

        # 2. Build RCA prompt
        prompt = self._build_rca_prompt(events, metrics, rag_docs)

        # 3. LLM generates hypotheses
        response = self._llm.generate(
            prompt=prompt,
            schema=RCASchema,
            temperature=0.3  # Lower temp for factual analysis
        )

        hypotheses = [RCAHypothesis.from_dict(h) for h in response.structured_output["hypotheses"]]

        # 4. Sort by confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)

        return RCAResult(hypotheses=hypotheses)
```

**Current Code Issue**: All RCA is mocked, no real LLM calls
**Recommendation**: **IMPLEMENT THIS** - High value for operator debugging

---

### 5. 🟡 **Observer Agent - QUESTIONABLE**

#### **Where**: RAG Pipeline for Ethereum docs

**Current State**: 442 lines, no actual docs ingested

**LLM Vision**: "Specialized LLM with RAG over Ethereum docs"

**Analysis**:

**What RAG Would Provide**:
```python
# Query: "Why would finality delay if participation is 68%?"
rag_results = [
    {
        "doc": "ethereum-consensus-spec.md",
        "text": "Finality requires 2/3 (66.67%) of validators to attest...",
        "relevance": 0.94
    },
    {
        "doc": "prysm-cve-2023.md",
        "text": "Attestation pool overflow when >200 late messages...",
        "relevance": 0.82
    }
]
```

**Benefits**:
- Contextualizes anomalies with spec knowledge
- Links to known CVEs and incidents
- Reduces false positives in RCA

**Costs**:
- Must ingest and embed Ethereum docs (one-time: ~1 hour)
- Vector database (Qdrant, Pinecone, or local) required
- Query latency: +200-500ms per RCA

**My Recommendation**: **Phase 3 Polish, Not Phase 2 Blocker**

**Phase 2**: RCA without RAG (direct LLM knowledge is sufficient for common issues)
**Phase 3**: Add RAG for rare CVEs and historical incidents

```python
# Phase 2: Simple LLM RCA
def analyze(events, metrics):
    prompt = f"Analyze these anomalies: {events}, {metrics}"
    return llm.generate(prompt)

# Phase 3: RAG-enhanced RCA
def analyze(events, metrics):
    rag_context = rag_pipeline.search(events)
    prompt = f"Analyze {events} with context: {rag_context}"
    return llm.generate(prompt)
```

**Implementation Priority**: **LOW** for Phase 2, **HIGH** for Phase 3

---

## Implementation Roadmap

### **Phase 2 - Minimum Viable LLM** (Current)

**Implement**:
1. ✅ **Orchestrator Hypothesis Generation**
   - Priority: **P0 (CRITICAL)**
   - Lines: ~200 (replace 752-line template system)
   - API: Anthropic Claude Opus (best reasoning for hypothesis generation)
   - Cost: ~$0.01-0.05 per experiment

2. ✅ **Observer RCA (Basic)**
   - Priority: **P1 (HIGH)**
   - Lines: ~150 (simplify current 400-line mock)
   - API: Anthropic Claude Sonnet (fast, accurate for analysis)
   - Cost: ~$0.01 per RCA call

**Skip**:
- ❌ Node agent LLM decisions (use rule-based behaviors)
- ❌ RAG pipeline (LLM base knowledge sufficient)
- ❌ Plan compilation LLM (use simple mapping)

**Total Phase 2 LLM Integration**: ~350 lines, 2 API calls per experiment

---

### **Phase 3 - Advanced LLM** (Future)

**Add**:
1. **RAG Pipeline for Observer**
   - Ingest: Ethereum spec, CVE database, past incident reports
   - Vector DB: Qdrant (local) or Pinecone (cloud)
   - Query: 5 relevant docs per RCA
   - Benefit: 30-50% higher RCA accuracy

2. **Node Agent LLM (Optional)**
   - vLLM cluster for batch inference
   - Latency challenge: Must generate actions <4s (attestation deadline)
   - Use case: Research into emergent Byzantine behaviors
   - Benefit: More realistic adversarial patterns
   - **WARNING**: Very expensive at 500 agents

3. **Adaptive Orchestrator**
   - Learn from past experiments
   - Suggest next test based on findings
   - Auto-tune blast radius to find failure boundaries

---

## Cost Analysis

### **Phase 2 (Minimal LLM)**

Per Experiment (15 min duration):
- Hypothesis generation: 1 call × $0.03 = **$0.03**
- RCA (if anomaly): 2 calls × $0.01 = **$0.02**

**Total**: ~**$0.05 per experiment** = **$50 for 1,000 experiments**

### **Phase 3 (Full LLM)**

Per Experiment (15 min):
- Hypothesis: $0.03
- RCA (3-5 calls with RAG): $0.10
- Node agents (10 agents × 75 epochs × $0.001): **$0.75**

**Total**: ~**$0.88 per experiment** = **$880 for 1,000 experiments**

**Scaling to 500 agents**: $37.50 per experiment (prohibitive!)

---

## Concrete Implementation Example

### **What to Build Now: HypothesisEngine with LLM**

```python
# src/chaoswopr/agents/hypothesis_engine.py
from anthropic import Anthropic

class HypothesisEngine:
    def __init__(self, llm_client: AnthropicLLMClient | None = None, dry_run: bool = False):
        self._llm = llm_client
        self._dry_run = dry_run

    def generate(self, scenario: dict, cluster_state: dict) -> Hypothesis:
        if self._dry_run:
            return self._generate_mock_hypothesis(scenario)

        # Build LLM prompt
        prompt = self._build_prompt(scenario, cluster_state)

        # Call LLM with structured output
        response = self._llm.generate(
            prompt=prompt,
            model="claude-opus-4",
            system="You are an expert in Ethereum chaos engineering...",
            schema=HypothesisSchema,
            temperature=0.7,
            max_tokens=2000
        )

        # Parse and validate
        hypothesis = Hypothesis.from_dict(response.structured_output)

        # Safety checks
        if hypothesis.blast_radius_percent > 33.0:
            hypothesis.blast_radius_percent = 33.0
            hypothesis.rationale += " (Reduced to 33% safety limit)"

        hypothesis.validate()  # Ensure schema compliance

        return hypothesis

    def _build_prompt(self, scenario: dict, cluster_state: dict) -> str:
        return f"""Generate a testable chaos engineering hypothesis for Ethereum.

**Scenario**: {scenario['name']}
Description: {scenario.get('description', 'N/A')}

**Current Network State**:
- Validator count: {cluster_state.get('validator_count', 0)}
- Finality delay: {cluster_state.get('finality_delay_seconds', 0)}s
- Participation rate: {cluster_state.get('participation_rate', 0)}%

**Requirements**:
1. Predict specific network behavior under fault conditions
2. Specify blast radius (max 33% of nodes)
3. Define expected metric ranges (finality delay, participation, etc.)
4. Provide rationale based on Ethereum consensus rules
5. Suggest success criteria for experiment validation

**Output JSON Schema**:
{{
  "prediction": "What will happen under fault?",
  "blast_radius_percent": 10.0,
  "fault_timeline": [
    {{"time_offset_seconds": 0, "action": "baseline"}},
    {{"time_offset_seconds": 60, "action": "inject_latency", "target_percent": 10, "params": {{"latency_ms": 200}}}}
  ],
  "expected_metrics": [
    {{"metric": "finality_delay_seconds", "expected_max": 120}}
  ],
  "rationale": "Why this prediction?",
  "success_criteria": "How to validate hypothesis?"
}}"""
```

**Test**:
```python
def test_hypothesis_generation_with_llm():
    llm = AnthropicLLMClient(api_key=os.environ["ANTHROPIC_API_KEY"])
    engine = HypothesisEngine(llm_client=llm)

    scenario = {
        "name": "network_latency_test",
        "description": "Test finality under P2P latency"
    }
    cluster_state = {
        "validator_count": 384,
        "finality_delay_seconds": 13.2,
        "participation_rate": 96.3
    }

    hypothesis = engine.generate(scenario, cluster_state)

    assert hypothesis.prediction
    assert 0 < hypothesis.blast_radius_percent <= 33
    assert len(hypothesis.fault_timeline) > 0
    assert hypothesis.validate() == []  # No errors
```

---

## Summary Table

| Component | LLM Needed? | Phase | Priority | Cost/Exp | Rationale |
|-----------|-------------|-------|----------|----------|-----------|
| **Orchestrator Hypothesis** | ✅ **YES** | Phase 2 | **P0** | $0.03 | Core value-add, adaptive learning |
| **Orchestrator Planning** | ❌ NO | N/A | N/A | $0 | Deterministic mapping, no AI needed |
| **Node Agent Decisions** | 🟡 Maybe | Phase 3 | P3 | $0.75 | Interesting research, not essential |
| **Observer RCA** | ✅ **YES** | Phase 2 | **P1** | $0.02 | Operator value, explainable debugging |
| **Observer RAG** | 🟡 Maybe | Phase 3 | P2 | $0.10 | Polish, not blocker |

**Total Phase 2 LLM**: 2 integrations, ~$0.05/experiment, high ROI

---

## Final Recommendation

### **Build Now (Phase 2)**:
1. `HypothesisEngine` with Anthropic Claude Opus
2. `RCAEngine` with Anthropic Claude Sonnet (no RAG)

### **Build Later (Phase 3)**:
1. RAG pipeline for Observer
2. vLLM-based node agents (research project)

### **Never Build**:
1. LLM plan compiler (use simple mapping)
2. LLM for data transformations (overkill)

**Current Code**: 100% mocked LLMs, 0% real integration
**Phase 2 Goal**: 2 real LLM integrations, simple and high-value

---

**Created**: 2026-02-16
**Author**: Staff Software Engineer Review
