#!/usr/bin/env python3
"""Start the PMM Companion API server."""

import os
import sys

import uvicorn

# Add the project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

if __name__ == "__main__":
    print("Starting PMM Companion API server...")
    print("API docs available at: http://localhost:8001/docs")
    print("WebSocket endpoint: ws://localhost:8001/stream")

    uvicorn.run(
        "pmm.api.companion:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
