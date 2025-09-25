#!/bin/bash

# PMM Companion Startup Script
# Starts both the backend API server and frontend UI server

echo "🚀 Starting PMM Companion..."
echo "================================"

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down PMM Companion..."
    kill $API_PID $UI_PID 2>/dev/null
    wait $API_PID $UI_PID 2>/dev/null
    echo "✅ Shutdown complete"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Start the backend API server
echo "📡 Starting backend API server on http://localhost:8001..."
cd "$SCRIPT_DIR"
python3 -m pmm.api.companion &
API_PID=$!

# Wait a moment for API to start
sleep 3

# Start the frontend UI server
echo "🎨 Starting frontend UI server on http://localhost:3000..."
cd "$SCRIPT_DIR/ui"
npm run dev &
UI_PID=$!

# Wait a moment for UI to start
sleep 3

echo ""
echo "✅ PMM Companion is now running!"
echo "================================"
echo "🌐 Frontend UI:  http://localhost:3000"
echo "📡 Backend API:  http://localhost:8001"
echo "📚 API Docs:     http://localhost:8001/docs"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes to finish
wait $API_PID $UI_PID
