# Path: pmm/runtime/bindings.py
"""Execution binding router for runtime dispatch."""

from __future__ import annotations

import json
from typing import Dict, Iterable, Optional, Tuple

from pmm.core.event_log import EventLog
from pmm.runtime.executors import IdleMonitorExecutor


class ExecBindRouter:
    """Materialize exec_bind configurations into runtime executors."""

    def __init__(self, eventlog: EventLog) -> None:
        self.eventlog = eventlog
        self.executors: Dict[str, IdleMonitorExecutor] = {}
        self.eventlog.register_listener(self._on_event)
        self._load_active_binds()

    def _load_active_binds(self) -> None:
        for exec_type, cid, params in self._iter_exec_binds(self.eventlog.read_all()):
            self._ensure_executor(exec_type, cid, params)

    def tick(self) -> None:
        for executor in self.executors.values():
            executor.tick()

    def _on_event(self, event: Dict) -> None:
        if event.get("kind") != "config":
            return
        parsed = self._parse_exec_bind(event)
        if parsed:
            exec_type, cid, params = parsed
            self._ensure_executor(exec_type, cid, params)

    def _ensure_executor(
        self, exec_type: str, cid: Optional[str], params: Dict[str, object]
    ) -> None:
        if exec_type != "idle_monitor" or not cid:
            return
        if cid not in self.executors:
            self.executors[cid] = IdleMonitorExecutor(self.eventlog, cid, params)

    def _iter_exec_binds(
        self, events: Iterable[Dict]
    ) -> Iterable[Tuple[str, Optional[str], Dict[str, object]]]:
        for event in events:
            parsed = self._parse_exec_bind(event)
            if parsed:
                yield parsed

    def _parse_exec_bind(
        self, event: Dict
    ) -> Optional[Tuple[str, Optional[str], Dict[str, object]]]:
        if event.get("kind") != "config":
            return None
        content_raw = event.get("content") or ""
        try:
            data = json.loads(content_raw)
        except (TypeError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        if data.get("type") != "exec_bind":
            return None
        exec_type = data.get("exec")
        cid = data.get("cid")
        params = data.get("params") if isinstance(data.get("params"), dict) else {}
        if not isinstance(exec_type, str):
            return None
        if cid is not None and not isinstance(cid, str):
            return None
        return exec_type, cid, params
