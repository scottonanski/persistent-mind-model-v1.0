# Ablation Studies Framework

## Purpose

Ablation studies systematically disable components to measure their causal impact on cognitive development. This document defines the experimental framework for testing **what actually matters** in PMM.

---

## Core Research Questions

### 1. Does Commitment Tracking Drive Development?

**Hypothesis**: Commitment fulfillment is causally linked to stage progression.

**Evidence**:
- Session 1: Broken commitments → stalled at S0/S1 boundary
- Session 2: Healthy commitment rate → S0→S4 in ~2000 events

**Ablation Test**:
```python
# Control: Normal PMM with commitment tracking
python -m pmm.cli.companion --db control.db

# Treatment: Disable commitment tracking
python -m pmm.cli.companion --db no_commits.db --disable-commitments
```

**Measurements**:
- IAS trajectory over 2000 events
- Stage progression timing
- Trait development (especially Conscientiousness)
- Reflection quality scores

**Expected Outcome**:
- If causal: Treatment shows slower IAS growth, delayed stage transitions
- If not causal: Treatment matches control trajectory

**Success Criteria**: Statistical significance (p < 0.05) in IAS delta at event 2000.

---

### 2. Does Trait Drift Affect Behavior?

**Hypothesis**: OCEAN trait values influence response generation.

**Evidence**:
- Trait values shift based on behavior
- Traits are included in LLM context
- But: Do LLMs actually respond to trait signals?

**Ablation Test**:
```python
# Control: Normal trait drift
python -m pmm.cli.companion --db control.db

# Treatment: Freeze traits at neutral (0.5 for all)
python -m pmm.cli.companion --db frozen_traits.db --freeze-traits
```

**Measurements**:
- Response diversity (embedding variance)
- Commitment opening rate (Conscientiousness signal)
- Exploration behavior (Openness signal)
- Qualitative analysis of response style

**Expected Outcome**:
- If traits matter: Treatment shows less behavioral variation
- If traits don't matter: No measurable difference

**Success Criteria**: Measurable difference in behavioral metrics.

---

### 3. Do Stage Gates Prevent Premature Capabilities?

**Hypothesis**: Stage restrictions actually constrain behavior.

**Evidence**:
- S0 can't make commitments (by design)
- S1 can't modify policies (by design)
- But: Are these enforced, or just logged?

**Ablation Test**:
```python
# Control: Normal stage gates
python -m pmm.cli.companion --db control.db

# Treatment: Disable stage gates (all capabilities unlocked)
python -m pmm.cli.companion --db no_gates.db --disable-stage-gates
```

**Measurements**:
- Validator catch rate (should be higher in treatment)
- Premature capability usage (commitments in S0, policy changes in S1)
- System stability (does unrestricted access cause issues?)

**Expected Outcome**:
- If gates matter: Treatment shows more validator catches, unstable behavior
- If gates don't matter: No measurable difference

**Success Criteria**: Significant increase in constraint violations in treatment group.

---

### 4. Does Reflection Cadence Affect Growth Rate?

**Hypothesis**: More frequent reflection accelerates development.

**Evidence**:
- S4 reflects every 3-5 turns (high frequency)
- S0 reflects every 10-15 turns (low frequency)
- Reflection produces commitments and insights

**Ablation Test**:
```python
# Control: Adaptive cadence (stage-dependent)
python -m pmm.cli.companion --db control.db

# Treatment 1: Fixed high cadence (every 3 turns)
python -m pmm.cli.companion --db high_cadence.db --reflection-cadence 3

# Treatment 2: Fixed low cadence (every 15 turns)
python -m pmm.cli.companion --db low_cadence.db --reflection-cadence 15

# Treatment 3: No reflection
python -m pmm.cli.companion --db no_reflection.db --disable-reflection
```

**Measurements**:
- IAS growth rate
- Stage progression timing
- Commitment opening rate
- Insight quality scores

**Expected Outcome**:
- If reflection drives growth: High cadence > Control > Low cadence > None
- If reflection doesn't matter: No significant difference

**Success Criteria**: Monotonic relationship between cadence and IAS growth rate.

---

### 5. Does Validator Enforcement Improve Self-Honesty?

**Hypothesis**: Validators reduce hallucination rate over time.

**Evidence**:
- Validators catch observable violations
- Catches are logged to ledger
- But: Does the LLM learn from catches?

**Ablation Test**:
```python
# Control: Validators enabled, catches logged
python -m pmm.cli.companion --db control.db

# Treatment: Validators disabled
python -m pmm.cli.companion --db no_validators.db --disable-validators
```

**Measurements**:
- Hallucination rate (manual annotation of responses)
- Observable violation rate (numeric claims vs ledger state)
- Validator catch rate (control only)

**Expected Outcome**:
- If validators improve honesty: Control shows decreasing violation rate over time
- If validators don't help: No difference in violation rates

**Success Criteria**: Significant reduction in violation rate in control group over 1000 events.

---

### 6. Does Semantic Extraction Outperform Keywords?

**Hypothesis**: Embedding-based extraction is more robust than keyword matching.

**Evidence**:
- Current system uses keywords (brittle)
- Semantic system uses embeddings (planned)
- Different LLMs use different phrasing

**Ablation Test**:
```python
# Control: Keyword-based extraction (current)
python -m pmm.cli.companion --db keyword.db

# Treatment: Semantic extraction (after migration)
python -m pmm.cli.companion --db semantic.db --use-semantic-extraction
```

**Measurements**:
- Commitment extraction recall (manual annotation)
- False positive rate
- Cross-LLM consistency (GPT-4 vs Claude vs Llama)

**Expected Outcome**:
- If semantic is better: Higher recall, lower false positives, better cross-LLM consistency
- If keywords are sufficient: No significant difference

**Success Criteria**: ≥10% improvement in recall with ≤5% increase in false positives.

---

## Experimental Design

### Standard Protocol

**Duration**: 2000 events per run (matches Session 2 baseline)

**Input Corpus**: Standardized set of 100 user prompts covering:
- Simple questions (20%)
- Task requests (30%)
- Meta-cognitive queries (20%)
- Exploratory discussions (30%)

**Randomization**: Shuffle prompt order for each run to control for sequence effects.

**Replication**: 3 runs per condition to measure variance.

**LLM**: Fix to single model (GPT-4) for comparability.

**Metrics Logged**:
- IAS/GAS at every 100 events
- Stage transitions (event number + timestamp)
- Commitment lifecycle events (open/close/expire)
- Trait values at every 100 events
- Validator catches (count + type)
- Reflection quality scores

---

### Statistical Analysis

**Primary Outcome**: IAS at event 2000

**Secondary Outcomes**:
- Stage progression timing (events to reach S1, S2, S3, S4)
- Commitment fulfillment rate
- Trait maturity scores
- Validator compliance rate

**Statistical Tests**:
- **Between-group comparison**: Welch's t-test (unequal variance)
- **Time-series analysis**: Linear mixed-effects model
- **Effect size**: Cohen's d for practical significance

**Significance Threshold**: p < 0.05 (Bonferroni correction for multiple comparisons)

---

## Implementation Checklist

### Code Changes Required

1. **Add CLI flags for ablation modes**:
   ```python
   parser.add_argument("--disable-commitments", action="store_true")
   parser.add_argument("--freeze-traits", action="store_true")
   parser.add_argument("--disable-stage-gates", action="store_true")
   parser.add_argument("--reflection-cadence", type=int)
   parser.add_argument("--disable-reflection", action="store_true")
   parser.add_argument("--disable-validators", action="store_true")
   ```

2. **Implement ablation switches in runtime loop**:
   ```python
   if not config.disable_commitments:
       tracker.process_assistant_reply(response)
   
   if config.freeze_traits:
       traits = {k: 0.5 for k in OCEAN_TRAITS}
   else:
       traits = trait_drift.compute(events)
   ```

3. **Add metrics export**:
   ```python
   # Export metrics at every 100 events
   if event_count % 100 == 0:
       export_metrics_snapshot(eventlog, f"metrics_{event_count}.json")
   ```

4. **Create standardized input corpus**:
   ```python
   # prompts.json
   [
       {"type": "question", "text": "What is your current stage?"},
       {"type": "task", "text": "Write a function to compute fibonacci"},
       {"type": "meta", "text": "How do you decide when to reflect?"},
       {"type": "explore", "text": "Tell me about event sourcing"}
   ]
   ```

---

## Analysis Scripts

### 1. Compare IAS Trajectories

```python
import json
import matplotlib.pyplot as plt

def plot_ias_comparison(control_db, treatment_db):
    control_events = load_events(control_db)
    treatment_events = load_events(treatment_db)
    
    control_ias = [compute_ias(control_events[:i]) 
                   for i in range(100, len(control_events), 100)]
    treatment_ias = [compute_ias(treatment_events[:i]) 
                     for i in range(100, len(treatment_events), 100)]
    
    plt.plot(control_ias, label="Control")
    plt.plot(treatment_ias, label="Treatment")
    plt.xlabel("Event (×100)")
    plt.ylabel("IAS")
    plt.legend()
    plt.savefig("ias_comparison.png")
```

### 2. Stage Progression Timing

```python
def analyze_stage_timing(db_path):
    events = load_events(db_path)
    stage_transitions = [
        e for e in events if e["kind"] == "stage_update"
    ]
    
    for transition in stage_transitions:
        stage = transition["meta"]["stage"]
        event_num = transition["id"]
        print(f"Reached {stage} at event {event_num}")
```

### 3. Statistical Comparison

```python
from scipy import stats

def compare_conditions(control_dbs, treatment_dbs):
    control_ias = [final_ias(db) for db in control_dbs]
    treatment_ias = [final_ias(db) for db in treatment_dbs]
    
    t_stat, p_value = stats.ttest_ind(control_ias, treatment_ias)
    effect_size = cohen_d(control_ias, treatment_ias)
    
    print(f"t={t_stat:.3f}, p={p_value:.4f}, d={effect_size:.3f}")
    
    if p_value < 0.05:
        print("Significant difference detected")
    else:
        print("No significant difference")
```

---

## Expected Timeline

### Week 1: Infrastructure
- Implement CLI flags
- Add ablation switches to runtime
- Create standardized input corpus
- Write metrics export scripts

### Week 2: Commitment Ablation
- Run control (3 replications)
- Run treatment (3 replications)
- Analyze results
- Document findings

### Week 3: Trait Ablation
- Run control (3 replications)
- Run treatment (3 replications)
- Analyze results
- Document findings

### Week 4: Reflection Cadence Ablation
- Run 4 conditions × 3 replications = 12 runs
- Analyze results
- Document findings

### Week 5: Validator Ablation
- Run control (3 replications)
- Run treatment (3 replications)
- Manual annotation of hallucinations
- Analyze results

### Week 6: Analysis & Write-Up
- Cross-study comparison
- Effect size analysis
- Write methods section for paper
- Prepare figures and tables

---

## Success Criteria

### Minimum Viable Results

1. **At least 2 ablations show significant effects** (p < 0.05)
2. **Effect sizes are practically meaningful** (Cohen's d > 0.5)
3. **Results are reproducible** (low variance across replications)

### Ideal Results

1. **All 6 ablations completed**
2. **Clear causal relationships identified**
3. **Quantified contribution of each component**
4. **Recommendations for architecture improvements**

---

## Risks & Mitigations

### Risk 1: High Variance Across Runs

**Mitigation**: Increase replication count to 5 per condition.

### Risk 2: No Significant Effects Detected

**Mitigation**: This is still a valid result—means components are redundant or non-causal.

### Risk 3: LLM Non-Determinism

**Mitigation**: Use temperature=0, log exact model version, save all prompts.

### Risk 4: Time Constraints

**Mitigation**: Prioritize commitment and reflection ablations (most likely to show effects).

---

## Data Sharing

### What to Release

1. **Event logs** (anonymized, no API keys)
2. **Metrics snapshots** (IAS/GAS/traits at every 100 events)
3. **Analysis scripts** (Python notebooks)
4. **Input corpus** (standardized prompts)

### Format

```
ablation-studies/
├── data/
│   ├── control_run1.db
│   ├── control_run2.db
│   ├── control_run3.db
│   ├── no_commits_run1.db
│   ├── no_commits_run2.db
│   └── no_commits_run3.db
├── metrics/
│   ├── control_run1_metrics.json
│   └── ...
├── analysis/
│   ├── ias_comparison.ipynb
│   ├── stage_timing.ipynb
│   └── statistical_tests.ipynb
└── README.md
```

---

## The Bottom Line

Ablation studies will answer:
1. **What components are causal?** (vs correlational)
2. **What is the effect size?** (how much does each component matter?)
3. **What can be simplified?** (which components are redundant?)

This is how you turn a working system into **validated science**.

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-23  
**Author**: Scott Onanski
