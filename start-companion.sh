#!/bin/bash

# PMM Companion Startup Script
# Starts both the backend API server and frontend UI server

echo "🚀 Starting PMM Companion..."
echo "================================"

# Kill any existing PMM processes
echo "🧹 Cleaning up any existing processes..."
pkill -f "pmm.api.companion" 2>/dev/null
pkill -f "next dev" 2>/dev/null
pkill -f "node.*next" 2>/dev/null

# Clear Next.js cache to prevent port detection issues
rm -rf ui/.next 2>/dev/null

sleep 1

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo "🛑 Shutting down PMM Companion..."
    
    # Kill the API server
    if [ ! -z "$API_PID" ]; then
        kill $API_PID 2>/dev/null
    fi
    
    # Kill the UI server and all its children (Next.js spawns multiple processes)
    if [ ! -z "$UI_PID" ]; then
        # Kill the entire process group
        pkill -P $UI_PID 2>/dev/null
        kill $UI_PID 2>/dev/null
    fi
    
    # Also kill any lingering Next.js processes
    pkill -f "next dev" 2>/dev/null
    
    # Wait for processes to terminate
    wait $API_PID $UI_PID 2>/dev/null
    
    echo "✅ Shutdown complete"
    exit 0
}

# Trap Ctrl+C and call cleanup
trap cleanup SIGINT SIGTERM

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if virtual environment exists, if not create it
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    echo "📥 Installing Python dependencies..."
    "$SCRIPT_DIR/.venv/bin/pip" install -q -r "$SCRIPT_DIR/requirements.txt"
fi

# Start the backend API server
echo "📡 Starting backend API server on http://localhost:8001..."
cd "$SCRIPT_DIR"
"$SCRIPT_DIR/.venv/bin/python" -m pmm.api.companion &
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
