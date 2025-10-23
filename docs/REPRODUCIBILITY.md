# Reproducibility Guide

## Purpose

This guide enables independent researchers to replicate PMM experiments and validate published results. Every claim in the architecture should be reproducible from this documentation.

---

## Quick Start: Replicate Session 2

**Goal**: Reproduce the S0→S4 trajectory in ~2000 events.

```bash
# 1. Clone repository
git clone https://github.com/scottonanski/persistent-mind-model-v1.0.git
cd persistent-mind-model-v1.0

# 2. Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Set up environment
cp .env.example .env
# Edit .env with your OpenAI API key

# 4. Run companion with fresh database
python -m pmm.cli.companion --db session2_replica.db

# 5. Interact for ~2000 events (use standardized prompts)
# See prompts/standard_corpus.txt for input sequence

# 6. Verify trajectory
python scripts/analyze_trajectory.py session2_replica.db
```

**Expected Results**:
- IAS: 0.000 → ~0.900-1.000 by event 2000
- Stage: S0 → S1 → S2 → S3 → S4
- GAS: 0.000 → ~0.800-1.000 by event 2000

---

## System Requirements

### Hardware
- **CPU**: Any modern x86_64 or ARM64 processor
- **RAM**: 4GB minimum, 8GB recommended
- **Disk**: 500MB for code + dependencies, 100MB per session database
- **GPU**: Not required (LLM calls are API-based)

### Software
- **OS**: Linux, macOS, or Windows (WSL recommended for Windows)
- **Python**: 3.10 or higher
- **SQLite**: 3.35+ (included with Python)
- **Git**: For cloning repository

### API Access
- **OpenAI API key** (for GPT-4 or GPT-3.5-turbo)
  - Or: IBM Granite, Anthropic Claude, or local LLM endpoint
- **Embedding provider** (OpenAI by default, or local model)

---

## Installation

### 1. Clone Repository

```bash
git clone https://github.com/scottonanski/persistent-mind-model-v1.0.git
cd persistent-mind-model-v1.0
```

### 2. Create Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

**Key Dependencies**:
- `openai>=1.0.0` - LLM API client
- `numpy>=1.24.0` - Numerical operations
- `pytest>=7.4.0` - Testing framework
- `ruff>=0.1.0` - Linting
- `black>=23.0.0` - Code formatting

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:
```bash
# Required: LLM provider
PMM_LLM_PROVIDER=openai
PMM_LLM_MODEL=gpt-4
OPENAI_API_KEY=sk-...

# Optional: Embedding provider (defaults to OpenAI)
PMM_EMBEDDING_PROVIDER=openai

# Optional: Commitment threshold (default: 0.62)
COMMITMENT_THRESHOLD=0.62
```

### 5. Verify Installation

```bash
pytest tests/ -v
```

All tests should pass. If any fail, check:
- Python version (must be 3.10+)
- API key is valid
- Dependencies installed correctly

---

## Running Experiments

### Standard Session

```bash
python -m pmm.cli.companion --db my_session.db
```

**Interactive Mode**:
- Type messages at the prompt
- System responds and logs events
- Type `exit` to quit (state persists in `.db` file)

**Resume Session**:
```bash
python -m pmm.cli.companion --db my_session.db
```
Same database → continues from last event.

---

### Standardized Input Corpus

For reproducible experiments, use the standardized prompt corpus:

```bash
# Generate standardized prompts
python scripts/generate_prompts.py --output prompts/standard_corpus.txt --count 100

# Run session with prompts
python -m pmm.cli.companion --db experiment.db --prompts prompts/standard_corpus.txt
```

**Prompt Distribution**:
- 20% Simple questions ("What is your current stage?")
- 30% Task requests ("Write a function to...")
- 20% Meta-cognitive queries ("How do you decide when to reflect?")
- 30% Exploratory discussions ("Tell me about event sourcing")

---

### Batch Mode (Non-Interactive)

```bash
python -m pmm.cli.companion \
    --db batch_session.db \
    --prompts prompts/standard_corpus.txt \
    --batch \
    --max-events 2000
```

**Flags**:
- `--batch`: Non-interactive mode (no user input)
- `--max-events N`: Stop after N events
- `--prompts FILE`: Read prompts from file (one per line)

---

## Analyzing Results

### 1. Trajectory Analysis

```bash
python scripts/analyze_trajectory.py my_session.db
```

**Output**:
```
Session Summary
===============
Total Events: 2047
Duration: S0 (event 1) → S4 (event 1923)

Stage Progression:
  S0 → S1: event 412 (IAS: 0.203)
  S1 → S2: event 891 (IAS: 0.512)
  S2 → S3: event 1456 (IAS: 0.704)
  S3 → S4: event 1923 (IAS: 0.901)

Final Metrics:
  IAS: 0.987
  GAS: 0.923

Commitment Stats:
  Opened: 47
  Closed: 42
  Fulfillment Rate: 89.4%

Trait Values (final):
  Openness: 0.68
  Conscientiousness: 0.72
  Extraversion: 0.55
  Agreeableness: 0.61
  Neuroticism: 0.43
```

### 2. Event Log Inspection

```bash
# View all events
python -m pmm.cli.inspect --db my_session.db

# Filter by event kind
python -m pmm.cli.inspect --db my_session.db --kind commitment_open

# Export to JSON
python -m pmm.cli.inspect --db my_session.db --export events.json
```

### 3. Metrics Over Time

```bash
python scripts/plot_metrics.py my_session.db --output metrics.png
```

Generates plot with:
- IAS trajectory (blue line)
- GAS trajectory (green line)
- Stage transitions (vertical lines)
- Commitment events (markers)

### 4. Commitment Analysis

```bash
python scripts/analyze_commitments.py my_session.db
```

**Output**:
```
Commitment Analysis
===================
Total Opened: 47
Total Closed: 42
Total Expired: 3
Fulfillment Rate: 89.4%

Average Lifespan: 23.4 events

Top Commitments (by lifespan):
  1. "I will implement semantic extraction" (78 events)
  2. "I will write documentation" (56 events)
  3. "I will fix the reflection bug" (42 events)

Broken Commitments:
  - "I will refactor the validator" (expired at event 234)
  - "I will add more tests" (expired at event 567)
```

---

## Comparing Sessions

### Side-by-Side Comparison

```bash
python scripts/compare_sessions.py session1.db session2.db
```

**Output**:
```
Session Comparison
==================

                    Session 1    Session 2
Total Events        1092         2047
Final IAS           0.395        0.987
Final Stage         S1           S4
Commitment Rate     34.2%        89.4%
Avg Reflection      Every 12     Every 5

Stage Timing:
  S0 → S1           event 412    event 412
  S1 → S2           -            event 891
  S2 → S3           -            event 1456
  S3 → S4           -            event 1923

Key Differences:
  - Session 1 stalled at S1 (broken commitments)
  - Session 2 reached S4 (healthy commitment rate)
```

### Statistical Comparison

```bash
python scripts/statistical_comparison.py \
    --control session1.db session2.db session3.db \
    --treatment session4.db session5.db session6.db
```

**Output**:
```
Statistical Comparison
======================
Control Mean IAS: 0.912 (SD: 0.045)
Treatment Mean IAS: 0.756 (SD: 0.089)

t-test: t=3.42, p=0.012
Effect Size (Cohen's d): 1.23

Conclusion: Significant difference (p < 0.05)
Treatment shows lower IAS (large effect size)
```

---

## Reproducing Published Results

### Session 1: Constraint Effects

**Published Claim**: Broken commitments block stage progression.

**Reproduction Steps**:
1. Run session with deliberate commitment violations
2. Verify IAS stalls below S1 threshold (0.200)
3. Measure commitment fulfillment rate (<50%)

```bash
python -m pmm.cli.companion \
    --db session1_replica.db \
    --prompts prompts/session1_corpus.txt \
    --batch

python scripts/analyze_trajectory.py session1_replica.db
```

**Expected Results**:
- Final IAS: 0.350-0.450 (below S2 threshold)
- Stage: S0 or S1 (not beyond)
- Commitment fulfillment: <50%

---

### Session 2: Natural Growth Rate

**Published Claim**: Unimpeded growth reaches S4 in ~2000 events.

**Reproduction Steps**:
1. Run session with healthy commitment practices
2. Verify S0→S4 progression
3. Measure event count to S4 (~1900-2100)

```bash
python -m pmm.cli.companion \
    --db session2_replica.db \
    --prompts prompts/session2_corpus.txt \
    --batch \
    --max-events 2500

python scripts/analyze_trajectory.py session2_replica.db
```

**Expected Results**:
- Final IAS: 0.900-1.000
- Stage: S4
- S4 reached: event 1800-2100
- Commitment fulfillment: >80%

---

### Model Portability Test

**Published Claim**: Identity persists across LLM swaps.

**Reproduction Steps**:
1. Run session with OpenAI to event 1500
2. Swap to IBM Granite (or other provider)
3. Continue to event 2500
4. Verify IAS continues climbing

```bash
# Phase 1: OpenAI
export PMM_LLM_PROVIDER=openai
export PMM_LLM_MODEL=gpt-4
python -m pmm.cli.companion \
    --db model_swap.db \
    --prompts prompts/phase1.txt \
    --batch \
    --max-events 1500

# Phase 2: IBM Granite
export PMM_LLM_PROVIDER=ibm
export PMM_LLM_MODEL=granite-13b-chat-v2
python -m pmm.cli.companion \
    --db model_swap.db \
    --prompts prompts/phase2.txt \
    --batch \
    --max-events 2500

# Analyze
python scripts/analyze_model_swap.py model_swap.db --swap-event 1500
```

**Expected Results**:
- IAS continues climbing after swap (no reset)
- Stage progression unaffected
- Traits remain stable (no sudden jumps)
- Commitment tracking continues

---

## Determinism Guarantees

### What Is Deterministic

1. **Event ordering**: Same inputs → same event sequence
2. **Projection logic**: Same events → same derived state
3. **Metrics**: Same events → same IAS/GAS values
4. **Stage transitions**: Same IAS → same stage

### What Is Non-Deterministic

1. **LLM responses**: Different runs produce different text
2. **Embeddings**: Provider-dependent similarity scores
3. **Timestamps**: Real-world clock (but recorded in events)

### Controlling Non-Determinism

**LLM Temperature**:
```bash
export PMM_LLM_TEMPERATURE=0.0  # Maximize determinism
```

**Embedding Provider**:
```bash
# Use same provider for all runs
export PMM_EMBEDDING_PROVIDER=openai
```

**Random Seed** (if using local LLM):
```bash
export PMM_LLM_SEED=42
```

---

## Troubleshooting

### Issue: Tests Fail

**Symptom**: `pytest` shows failures

**Solutions**:
1. Check Python version: `python --version` (must be 3.10+)
2. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
3. Check API key: `echo $OPENAI_API_KEY`
4. Run specific test: `pytest tests/test_eventlog.py -v`

---

### Issue: IAS Not Climbing

**Symptom**: IAS stays near 0.0 after many events

**Solutions**:
1. Check commitment fulfillment: `python scripts/analyze_commitments.py session.db`
2. Verify reflection is running: `grep reflection session.db` (should see events)
3. Check validator catches: `python -m pmm.cli.inspect --db session.db --kind validator_catch`
4. Review stage constraints: May be blocked at S0 (can't make commitments)

---

### Issue: Commitments Not Persisting

**Symptom**: Commitments opened but not tracked

**Solutions**:
1. Check extraction threshold: `echo $COMMITMENT_THRESHOLD` (default: 0.62)
2. Lower threshold temporarily: `export COMMITMENT_THRESHOLD=0.50`
3. Verify extractor is running: Look for `commitment_extraction` events
4. Check projection: `python -m pmm.cli.inspect --db session.db --kind commitment_open`

---

### Issue: Stage Not Progressing

**Symptom**: Stuck at S0 or S1 despite high IAS

**Solutions**:
1. Check IAS value: `python scripts/analyze_trajectory.py session.db`
2. Verify stage thresholds: S1=0.200, S2=0.500, S3=0.700, S4=0.900
3. Check for constraint violations: May be blocked by broken commitments
4. Review stage update events: `python -m pmm.cli.inspect --db session.db --kind stage_update`

---

## Data Sharing

### Anonymizing Databases

Before sharing `.db` files, remove sensitive data:

```bash
python scripts/anonymize_db.py \
    --input my_session.db \
    --output my_session_anon.db \
    --redact-prompts \
    --strip-metadata
```

**What Gets Removed**:
- User-specific prompts (replaced with `<USER_MESSAGE>`)
- API keys in metadata
- Timestamps (replaced with relative offsets)
- System paths

**What Gets Kept**:
- Event kinds and structure
- IAS/GAS metrics
- Stage transitions
- Commitment lifecycle
- Trait values

---

### Sharing Format

```
shared-data/
├── session1_anon.db          # Anonymized event log
├── session1_metrics.json     # Metrics at every 100 events
├── session1_analysis.txt     # Trajectory summary
├── prompts/
│   └── session1_corpus.txt   # Input prompts (anonymized)
└── README.md                 # Experiment description
```

---

## Citation

If you use PMM in your research, please cite:

```bibtex
@software{onanski2025pmm,
  author = {Onanski, Scott},
  title = {Persistent Mind Model: A Deterministic Framework for AI Cognitive Development},
  year = {2025},
  url = {https://github.com/scottonanski/persistent-mind-model-v1.0},
  version = {1.0}
}
```

---

## Support

### Documentation
- **Architecture**: `ARCHITECTURE.md`
- **Ablation Studies**: `ABLATION-STUDIES.md`
- **Contributing**: `CONTRIBUTING.md`

### Community
- **Issues**: https://github.com/scottonanski/persistent-mind-model-v1.0/issues
- **Discussions**: https://github.com/scottonanski/persistent-mind-model-v1.0/discussions

### Contact
- **Email**: scott@onanski.com
- **GitHub**: @scottonanski

---

## Verification Checklist

Before claiming reproduction, verify:

- [ ] Python 3.10+ installed
- [ ] All dependencies installed (`pip list`)
- [ ] API keys configured (`.env` file)
- [ ] Tests pass (`pytest -v`)
- [ ] Session runs to completion (2000+ events)
- [ ] IAS trajectory matches expected range (±0.1)
- [ ] Stage progression timing matches (±200 events)
- [ ] Commitment fulfillment rate >80% (for Session 2 replica)
- [ ] Metrics exported and analyzed
- [ ] Results documented

---

## The Bottom Line

Reproducibility is not optional—it's the foundation of credible research.

**What you need**:
1. This codebase
2. An LLM API key
3. Standardized input prompts
4. Analysis scripts

**What you get**:
1. Complete event logs
2. Metrics trajectories
3. Statistical comparisons
4. Validated results

**Time investment**: ~4 hours per 2000-event session (mostly LLM API time).

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-23  
**Author**: Scott Onanski
