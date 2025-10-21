# v1.0.0 Ship Checklist

## Pre-Release ✅

- [x] Version bump to 1.0.0 in `pyproject.toml`
- [x] README.md updated with:
  - [x] Hash verification clarification (opt-in, not "on every read")
  - [x] Context-aware bandit status (infra complete, partial wiring)
  - [x] Safety defaults section (autonomous naming, bounded traits)
  - [x] Data integrity section
  - [x] Documentation references
- [x] Implementation docs created:
  - [x] `IMPLEMENTATION-SUMMARY.md` (Phase 1 fixes)
  - [x] `BULLSHIT-ANALYSIS.md` (gap analysis)
  - [x] `CONTEXT-BANDIT-IMPLEMENTATION.md` (tracking)
  - [x] `PHASE-2-COMPLETE.md` (context-aware bandit)

## Testing

```bash
# Activate venv
source .venv/bin/activate

# Run full test suite
pytest -q

# Run bandit-specific tests
pytest tests/test_reflection_bandit.py \
       tests/test_stage_policy_arm_wiring.py \
       tests/test_contextual_bandit_learning.py -v

# Quick smoke test
python -m pmm.cli.chat --@metrics on
# Type a few messages, verify metrics update
# Type --@reflect to force reflection
# Ctrl+C to exit
```

## Release

```bash
# Commit all changes
git add -A
git commit -m "Release v1.0.0: Context-aware bandit + Phase 1-2 complete"

# Tag release
git tag -a v1.0.0 -m "v1.0.0: Self-evolving AI identity with context-aware learning"

# Push (if using remote)
git push origin main
git push origin v1.0.0
```

## Post-Release

- [ ] Monitor autonomy loop stability
- [ ] Check event log for stage metadata in rewards
- [ ] Verify guidance bias applying (check arm selection patterns)
- [ ] Collect feedback on trait evolution conservativeness

## What You're Shipping

### Core Features ✅
- Persistent, ledger-defined identity
- Autonomous evolution loop (reflections, policies, traits)
- Self-modification with audit trail
- Commitment lifecycle and prioritization
- Context-aware reflection bandit (infrastructure complete)
- Full observability (metrics, traces, UI/API)

### Intentional Gaps (Documented)
- Autonomous naming disabled by default (safety)
- Context-aware bandit partially wired (infra done, full wiring next)
- Trait drift conservative and bounded (safety)

### Test Coverage
- 13/13 bandit tests passing
- Full pytest suite clean
- Integration tests for context-aware learning

## Next 10% (Optional, 1-2 days)

If you want to complete the context-aware wiring:

1. **Wire stage everywhere** (1 day)
   - Pass `stage` to `choose_arm()` in all reflection paths
   - Verify `arm_source="bandit_contextual"` in events
   - Test: Different arms chosen in different stages

2. **Enable identity proposer** (1 day)
   - Emit `identity_propose` from reflections with confidence threshold
   - Add cooldown and flip-flop guards
   - Auto-adopt when safe (confidence > 0.9, stable window)

3. **Expand trait signals** (optional)
   - Add more semantic drivers to `TraitDriftManager`
   - Keep deltas small (±0.05 max)
   - Maintain strict invariants

## Support

- **Issues**: Open GitHub issue or check existing docs
- **Questions**: See `CONTRIBUTING.md` for development guidelines
- **Feedback**: Tag issues with `v1.0-feedback`

---

**Ready to ship!** 🚀
