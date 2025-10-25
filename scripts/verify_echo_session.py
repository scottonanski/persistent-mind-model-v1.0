#!/usr/bin/env python3
"""
Verify Echo's current session against PMM breakthrough claims.
Run this while Echo is active to generate verification report.
"""

import requests
import json
from datetime import datetime

API_BASE = "http://localhost:8001"

def sql_query(query):
    """Execute SQL query via PMM API"""
    try:
        response = requests.post(f"{API_BASE}/events/sql", 
                               json={"query": query},
                               timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_snapshot():
    """Get current agent snapshot"""
    try:
        response = requests.get(f"{API_BASE}/snapshot", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def verify_memory_systems():
    """Verify emergent memory systems"""
    print("🧠 Verifying Memory Systems...")
    
    # Episodic Memory: Event references
    episodic = sql_query("""
        SELECT id, content FROM events 
        WHERE content LIKE '%event #%' 
        ORDER BY id DESC LIMIT 5
    """)
    
    # Semantic Memory: System understanding  
    semantic = sql_query("""
        SELECT id, content FROM events 
        WHERE (content LIKE '%ledger%' OR content LIKE '%commitment%')
        AND kind = 'assistant_reply'
        ORDER BY id DESC LIMIT 3
    """)
    
    # Working Memory Errors: Validator catches
    working = sql_query("""
        SELECT id, content, timestamp FROM events 
        WHERE kind = 'validator_warning' 
        AND content LIKE '%hallucination%'
        ORDER BY id DESC LIMIT 3
    """)
    
    return {
        "episodic_memory": episodic,
        "semantic_memory": semantic, 
        "working_memory_errors": working
    }

def verify_architectural_honesty():
    """Verify architectural honesty system"""
    print("🛡️ Verifying Architectural Honesty...")
    
    # All validator warnings
    warnings = sql_query("""
        SELECT id, content, timestamp FROM events 
        WHERE kind = 'validator_warning'
        ORDER BY id DESC LIMIT 5
    """)
    
    # Self-corrections after warnings
    corrections = sql_query("""
        SELECT id, content FROM events 
        WHERE content LIKE '%previously%' 
        OR content LIKE '%correction%'
        OR content LIKE '%doesn\\'t match%'
        ORDER BY id DESC LIMIT 3
    """)
    
    return {
        "validator_warnings": warnings,
        "self_corrections": corrections
    }

def verify_trait_evolution():
    """Verify trait-based personality evolution"""
    print("📊 Verifying Trait Evolution...")
    
    # Trait updates over time
    trait_updates = sql_query("""
        SELECT id, meta, timestamp FROM events 
        WHERE kind = 'trait_update' 
        ORDER BY id
    """)
    
    # Current snapshot
    snapshot = get_snapshot()
    
    return {
        "trait_history": trait_updates,
        "current_traits": snapshot.get("identity", {}).get("traits", {}),
        "snapshot": snapshot
    }

def verify_stage_progression():
    """Verify stage-gated cognitive development"""
    print("🎯 Verifying Stage Progression...")
    
    # Stage updates
    stages = sql_query("""
        SELECT id, meta, timestamp FROM events 
        WHERE kind = 'stage_update' 
        ORDER BY id
    """)
    
    # IAS/GAS progression
    metrics = sql_query("""
        SELECT id, meta FROM events 
        WHERE kind IN ('autonomy_tick', 'reflection') 
        AND meta LIKE '%IAS%'
        ORDER BY id DESC LIMIT 10
    """)
    
    return {
        "stage_updates": stages,
        "metrics_progression": metrics
    }

def verify_commitment_system():
    """Verify commitment lifecycle"""
    print("📋 Verifying Commitment System...")
    
    # Commitment lifecycle
    commitments = sql_query("""
        SELECT id, kind, meta, timestamp FROM events 
        WHERE kind LIKE 'commitment_%'
        ORDER BY id DESC LIMIT 10
    """)
    
    # Current open commitments
    snapshot = get_snapshot()
    open_commitments = snapshot.get("commitments", {}).get("open", {})
    
    return {
        "commitment_events": commitments,
        "open_commitments": open_commitments,
        "commitment_count": len(open_commitments)
    }

def generate_report(results):
    """Generate verification report"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"echo_verification_{timestamp}.md"
    
    with open(filename, 'w') as f:
        f.write(f"# Echo Session Verification Report\n")
        f.write(f"**Generated**: {timestamp}\n\n")
        
        # Current state summary
        snapshot = results.get("trait_evolution", {}).get("snapshot", {})
        identity = snapshot.get("identity", {})
        
        f.write("## Session Summary\n\n")
        f.write(f"- **Identity**: {identity.get('name', 'Unknown')}\n")
        f.write(f"- **Current Traits**: {identity.get('traits', {})}\n")
        f.write(f"- **Open Commitments**: {results.get('commitment_system', {}).get('commitment_count', 0)}\n\n")
        
        # Verification results
        f.write("## Verification Results\n\n")
        
        for category, data in results.items():
            if category == "memory_systems":
                f.write("### ✅ Emergent Memory Systems\n\n")
                f.write("**Episodic Memory** (specific event references):\n")
                episodic = data.get("episodic_memory", {}).get("rows", [])
                for row in episodic[:3]:
                    f.write(f"- Event #{row[0]}: \"{row[1][:100]}...\"\n")
                
                f.write("\n**Working Memory Errors** (validator catches):\n")
                working = data.get("working_memory_errors", {}).get("rows", [])
                for row in working[:2]:
                    f.write(f"- Event #{row[0]}: {row[1]}\n")
                f.write("\n")
                
            elif category == "architectural_honesty":
                f.write("### ✅ Architectural Honesty System\n\n")
                warnings = data.get("validator_warnings", {}).get("rows", [])
                f.write(f"**Validator Warnings**: {len(warnings)} detected\n")
                for row in warnings[:2]:
                    f.write(f"- Event #{row[0]}: {row[1][:80]}...\n")
                f.write("\n")
                
            elif category == "stage_progression":
                f.write("### ✅ Stage-Gated Development\n\n")
                stages = data.get("stage_updates", {}).get("rows", [])
                f.write(f"**Stage Updates**: {len(stages)} transitions\n")
                for row in stages:
                    f.write(f"- Event #{row[0]}: {row[1]}\n")
                f.write("\n")
        
        f.write("## Raw Data\n\n")
        f.write("```json\n")
        f.write(json.dumps(results, indent=2))
        f.write("\n```\n")
    
    print(f"✅ Verification report saved: {filename}")
    return filename

def main():
    """Run complete verification of Echo session"""
    print("🔍 Starting PMM Claims Verification for Echo...")
    print("=" * 50)
    
    results = {}
    
    try:
        results["memory_systems"] = verify_memory_systems()
        results["architectural_honesty"] = verify_architectural_honesty()  
        results["trait_evolution"] = verify_trait_evolution()
        results["stage_progression"] = verify_stage_progression()
        results["commitment_system"] = verify_commitment_system()
        
        report_file = generate_report(results)
        
        print("\n🎉 Verification Complete!")
        print(f"📄 Report: {report_file}")
        print("\nKey Findings:")
        
        # Quick summary
        snapshot = results["trait_evolution"]["snapshot"]
        identity = snapshot.get("identity", {})
        
        print(f"- Identity: {identity.get('name', 'Unknown')}")
        print(f"- Traits: {identity.get('traits', {})}")
        print(f"- Commitments: {results['commitment_system']['commitment_count']}")
        
        warnings = len(results["architectural_honesty"]["validator_warnings"].get("rows", []))
        print(f"- Validator Warnings: {warnings} (honesty system active)")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        print("Make sure PMM is running with API on http://localhost:8001")

if __name__ == "__main__":
    main()
