"""PMM Companion API Server - FastAPI implementation for UI backend."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pmm.api import probe
from pmm.runtime.metrics import compute_ias_gas
from pmm.storage.eventlog import EventLog
from pmm.storage.projection import build_self_model

logger = logging.getLogger(__name__)

API_VERSION = "1.0.0"

app = FastAPI(title="PMM Companion API", version=API_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _get_evlog(db: str | None) -> EventLog:
    return EventLog(db) if db else EventLog()


@app.get("/events")
@app.get("/snapshot")
async def get_snapshot(db: str | None = Query(None)):
    """Get a comprehensive snapshot of PMM state including identity, events, and directives."""
    try:
        evlog = _get_evlog(db)

        # Get the main snapshot from probe
        snapshot_data = probe.snapshot(evlog)

        # Add directives to the snapshot
        directives = probe.snapshot_directives(evlog)
        snapshot_data["directives"] = directives

        return {"version": API_VERSION, **snapshot_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_events(
    db: str | None = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    after_id: int | None = Query(None),
    kind: str | None = Query(None),
):
    """Get paginated events."""
    try:
        evlog = _get_evlog(db)

        if after_id is not None:
            snapshot_data = probe.snapshot_paged(evlog, limit=limit, after_id=after_id)
        else:
            snapshot_data = probe.snapshot(evlog, limit=limit)

        events = snapshot_data["events"]

        if kind:
            events = [e for e in events if e.get("kind") == kind]

        return {
            "version": API_VERSION,
            "events": events,
            "pagination": {
                "limit": limit,
                "count": len(events),
                "next_after_id": snapshot_data.get("next_after_id"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
async def get_metrics(db: str | None = Query(None)):
    """Get current metrics (IAS, GAS, OCEAN traits, stage)."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        model = build_self_model(events)
        identity = model.get("identity", {})
        traits = identity.get("traits", {})

        try:
            ias, gas = compute_ias_gas(events)
        except Exception:
            ias, gas = 0.0, 0.0

        # Determine current stage from events
        current_stage = "S0"
        for event in reversed(events):
            if event.get("kind") == "stage_progress":
                stage_from_event = event.get("meta", {}).get("stage")
                if stage_from_event:
                    current_stage = str(stage_from_event)
                    break

        return {
            "version": API_VERSION,
            "metrics": {
                "ias": float(ias),
                "gas": float(gas),
                "traits": traits,
                "stage": {"current": current_stage},
                "last_updated": datetime.now().isoformat(),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/consciousness")
async def get_consciousness(db: str | None = Query(None)):
    """Get PMM's current consciousness state for the living mind dashboard."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        # Get current identity and metrics
        model = build_self_model(events)
        identity = model.get("identity", {})
        traits = identity.get("traits", {})

        try:
            ias, gas = compute_ias_gas(events)
        except Exception:
            ias, gas = 0.0, 0.0

        # Determine current stage
        current_stage = "S0"
        for event in reversed(events):
            if event.get("kind") == "stage_progress":
                stage_from_event = event.get("meta", {}).get("stage")
                if stage_from_event:
                    current_stage = str(stage_from_event)
                    break

        # Get evolution metrics
        total_events = len(events)
        first_event = events[0] if events else None
        birth_timestamp = first_event.get("ts") if first_event else None

        # Calculate days alive
        days_alive = 0
        if birth_timestamp:
            from datetime import datetime

            try:
                birth_date = datetime.fromisoformat(
                    birth_timestamp.replace("Z", "+00:00")
                )
                days_alive = (datetime.now(birth_date.tzinfo) - birth_date).days
            except Exception:
                days_alive = 0

        # Count reflections and commitments
        reflection_count = sum(
            1 for e in events if e.get("kind") in ["reflection", "meta_reflection"]
        )
        commitment_count = sum(
            1
            for e in events
            if e.get("kind") in ["commitment_open", "commitment_close"]
        )

        # Find latest identity-related reflection
        latest_identity_reflection = None
        for event in reversed(events):
            if event.get("kind") in ["reflection", "meta_reflection"]:
                content = str(event.get("content", "")).lower()
                if any(
                    keyword in content
                    for keyword in [
                        "identity",
                        "stage",
                        "evolve",
                        "self",
                        "conscious",
                        "autonom",
                    ]
                ):
                    latest_identity_reflection = {
                        "content": event.get("content", ""),
                        "timestamp": event.get("ts"),
                        "kind": event.get("kind"),
                    }
                    break

        # Calculate consciousness indicators
        autonomy_level = min(1.0, (ias + gas) / 2.0)  # 0-1 scale
        self_awareness = min(
            1.0, reflection_count / 100.0
        )  # Based on reflection volume
        evolution_progress = {
            "S0": 0,
            "S1": 0.25,
            "S2": 0.5,
            "S3": 0.75,
            "S4": 1.0,
        }.get(current_stage, 0)

        return {
            "version": API_VERSION,
            "consciousness": {
                "identity": {
                    "name": identity.get("name", "Unnamed"),
                    "stage": current_stage,
                    "stage_progress": evolution_progress,
                    "birth_timestamp": birth_timestamp,
                    "days_alive": days_alive,
                },
                "vital_signs": {
                    "ias": float(ias),
                    "gas": float(gas),
                    "autonomy_level": autonomy_level,
                    "self_awareness": self_awareness,
                },
                "personality": {
                    "traits": {
                        "openness": float(traits.get("openness", 0.0)),
                        "conscientiousness": float(
                            traits.get("conscientiousness", 0.0)
                        ),
                        "extraversion": float(traits.get("extraversion", 0.0)),
                        "agreeableness": float(traits.get("agreeableness", 0.0)),
                        "neuroticism": float(traits.get("neuroticism", 0.0)),
                    }
                },
                "evolution_metrics": {
                    "total_events": total_events,
                    "reflection_count": reflection_count,
                    "commitment_count": commitment_count,
                    "stage_reached": current_stage,
                },
                "latest_insight": latest_identity_reflection,
                "consciousness_state": {
                    "is_self_aware": self_awareness > 0.3,
                    "is_autonomous": autonomy_level > 0.5,
                    "is_evolving": evolution_progress > 0.1,
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/reflections")
async def get_reflections(
    db: str | None = Query(None), limit: int = Query(20, ge=1, le=500)
):
    """Get reflection events."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        reflections = []
        for event in reversed(events):
            if event.get("kind") in ["reflection", "meta_reflection"]:
                reflections.append(event)
                if len(reflections) >= limit:
                    break

        return {
            "version": API_VERSION,
            "reflections": reflections,
            "count": len(reflections),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/commitments")
async def get_commitments(
    db: str | None = Query(None),
    status: str = Query("all"),
    limit: int = Query(50, ge=1, le=500),
):
    """Get commitments."""
    try:
        evlog = _get_evlog(db)

        if status == "open":
            commitments = probe.snapshot_commitments_open(evlog, limit=limit)
        else:
            # Get all commitment events
            events = evlog.read_all()
            commitments = []
            for event in reversed(events):
                if event.get("kind") in ["commitment_open", "commitment_close"]:
                    commitments.append(event)
                    if len(commitments) >= limit:
                        break

        return {
            "version": API_VERSION,
            "commitments": commitments,
            "count": len(commitments),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/traces")
async def get_traces(
    db: str | None = Query(None),
    limit: int = Query(20, ge=1, le=500),
    query_filter: str | None = Query(None, description="Filter by query text"),
):
    """Get reasoning trace summaries."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        traces = []
        for event in reversed(events):
            if event.get("kind") == "reasoning_trace_summary":
                meta = event.get("meta", {})

                # Apply query filter if provided
                if query_filter:
                    query_text = meta.get("query", "").lower()
                    if query_filter.lower() not in query_text:
                        continue

                traces.append(
                    {
                        "id": event.get("id"),
                        "timestamp": event.get("ts"),
                        "session_id": meta.get("session_id"),
                        "query": meta.get("query"),
                        "total_nodes_visited": meta.get("total_nodes_visited", 0),
                        "node_type_distribution": meta.get(
                            "node_type_distribution", {}
                        ),
                        "high_confidence_count": meta.get("high_confidence_count", 0),
                        "high_confidence_paths": meta.get("high_confidence_paths", []),
                        "sampled_count": meta.get("sampled_count", 0),
                        "reasoning_steps": meta.get("reasoning_steps", []),
                        "duration_ms": meta.get("duration_ms", 0),
                    }
                )

                if len(traces) >= limit:
                    break

        return {
            "version": API_VERSION,
            "traces": traces,
            "count": len(traces),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/traces/{session_id}")
async def get_trace_details(
    session_id: str,
    db: str | None = Query(None),
):
    """Get detailed trace information for a specific session."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        # Find summary
        summary = None
        samples = []

        for event in events:
            kind = event.get("kind")
            meta = event.get("meta", {})

            if (
                kind == "reasoning_trace_summary"
                and meta.get("session_id") == session_id
            ):
                summary = {
                    "id": event.get("id"),
                    "timestamp": event.get("ts"),
                    "session_id": meta.get("session_id"),
                    "query": meta.get("query"),
                    "total_nodes_visited": meta.get("total_nodes_visited", 0),
                    "node_type_distribution": meta.get("node_type_distribution", {}),
                    "high_confidence_count": meta.get("high_confidence_count", 0),
                    "high_confidence_paths": meta.get("high_confidence_paths", []),
                    "sampled_count": meta.get("sampled_count", 0),
                    "reasoning_steps": meta.get("reasoning_steps", []),
                    "duration_ms": meta.get("duration_ms", 0),
                    "start_time_ms": meta.get("start_time_ms"),
                    "end_time_ms": meta.get("end_time_ms"),
                }
            elif (
                kind == "reasoning_trace_sample"
                and meta.get("session_id") == session_id
            ):
                samples.append(
                    {
                        "id": event.get("id"),
                        "timestamp": event.get("ts"),
                        "node_digest": meta.get("node_digest"),
                        "node_type": meta.get("node_type"),
                        "context_query": meta.get("context_query"),
                        "traversal_depth": meta.get("traversal_depth", 0),
                        "confidence": meta.get("confidence", 0.0),
                        "edge_label": meta.get("edge_label"),
                        "reasoning_step": meta.get("reasoning_step"),
                    }
                )

        if not summary:
            raise HTTPException(
                status_code=404, detail=f"Trace session {session_id} not found"
            )

        return {
            "version": API_VERSION,
            "summary": summary,
            "samples": samples,
            "sample_count": len(samples),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/traces/stats/overview")
async def get_trace_stats(
    db: str | None = Query(None),
):
    """Get aggregate statistics about reasoning traces."""
    try:
        evlog = _get_evlog(db)
        events = evlog.read_all()

        total_traces = 0
        total_nodes_visited = 0
        avg_duration_ms = 0
        node_type_totals = {}

        trace_summaries = []

        for event in events:
            if event.get("kind") == "reasoning_trace_summary":
                meta = event.get("meta", {})
                total_traces += 1
                total_nodes_visited += meta.get("total_nodes_visited", 0)
                avg_duration_ms += meta.get("duration_ms", 0)

                # Aggregate node types
                dist = meta.get("node_type_distribution", {})
                for node_type, count in dist.items():
                    node_type_totals[node_type] = (
                        node_type_totals.get(node_type, 0) + count
                    )

                trace_summaries.append(meta)

        if total_traces > 0:
            avg_duration_ms = avg_duration_ms / total_traces
            avg_nodes_per_trace = total_nodes_visited / total_traces
        else:
            avg_nodes_per_trace = 0

        return {
            "version": API_VERSION,
            "stats": {
                "total_traces": total_traces,
                "total_nodes_visited": total_nodes_visited,
                "avg_nodes_per_trace": round(avg_nodes_per_trace, 1),
                "avg_duration_ms": round(avg_duration_ms, 1),
                "node_type_distribution": node_type_totals,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/events/sql")
async def execute_sql(
    request: dict[str, Any],
    db: str | None = Query(None, description="Path to SQLite database"),
) -> JSONResponse:
    """Execute SQL query against the events table (read-only)."""
    try:
        import time

        start_time = time.time()

        query = request.get("query", "").strip()
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Basic security checks
        if not query.upper().startswith("SELECT"):
            raise HTTPException(
                status_code=400, detail="Only SELECT queries are allowed"
            )

        # Block dangerous operations
        forbidden_words = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "ALTER",
            "CREATE",
            "TRUNCATE",
        ]
        query_upper = query.upper()
        for word in forbidden_words:
            if word in query_upper:
                raise HTTPException(
                    status_code=400,
                    detail=f"Query contains forbidden operation: {word}",
                )

        evlog = _get_evlog(db)

        # Execute the query

        conn = evlog._conn  # Direct access to SQLite connection
        cursor = conn.cursor()

        cursor.execute(query)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()

        # Convert to dict format
        results = []
        for row in rows:
            result_dict = {}
            for i, col in enumerate(columns):
                value = row[i]
                # Convert bytes to string for JSON serialization
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="replace")
                result_dict[col] = value
            results.append(result_dict)

        execution_time = int((time.time() - start_time) * 1000)  # ms

        response = {
            "version": API_VERSION,
            "query": query,
            "results": results,
            "count": len(results),
            "execution_time_ms": execution_time,
        }

        return JSONResponse(content=response)

    except Exception as e:
        logger.error(f"SQL query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
