# debug_stage_advancement.py

from pmm.storage.eventlog import EventLog
from pmm.runtime.stage_manager import StageManager

print("🔍 Debugging Stage Advancement Criteria")
print("=" * 50)

eventlog = EventLog(".data/pmm.db")
sm = StageManager(eventlog)

events = eventlog.read_all()
refs = [e for e in events if e.get("kind") == "reflection"]
evols = [e for e in events if e.get("kind") == "evolution"]
introspections = [e for e in events if e.get("kind") == "introspection_query"]
adoptions = [e for e in events if e.get("kind") == "identity_adopt"]
metrics = [e for e in events if e.get("kind") == "metrics"]

latest_metrics = metrics[-1]["meta"] if metrics else {}
ias = latest_metrics.get("IAS", 0.0)
gas = latest_metrics.get("GAS", 0.0)

print(f"Current stage: {sm.current_stage()}")
print(f"Reflections: {len(refs)}")
print(f"Evolutions: {len(evols)}")
print(f"Introspection queries: {len(introspections)}")
print(f"Identity adoptions: {len(adoptions)}")
print(f"IAS: {ias:.3f}, GAS: {gas:.3f}")

print("\nCriteria thresholds:")
print(" S0→S1: ≥2 refs + ≥1 evol, IAS≥0.60, GAS≥0.20")
print("         or ≥2 refs + ≥2 introspections + ≥2 adoptions")
print(" S1→S2: ≥5 refs + ≥4 evol, IAS≥0.70, GAS≥0.35")
print(" S2→S3: ≥8 refs + ≥6 evol, IAS≥0.80, GAS≥0.50")
print(" S3→S4: ≥12 refs + ≥8 evol, IAS≥0.85, GAS≥0.75")
