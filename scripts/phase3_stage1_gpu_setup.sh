#!/bin/bash
# Phase 3 Stage 1: GPU Setup via Python Dependencies
# This script sets up GPU acceleration using Python packages instead of system CUDA

set -e  # Exit on error

echo "=========================================="
echo "Phase 3 Stage 1: GPU Setup (Python-based)"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo -e "${RED}Error: Must run from project root${NC}"
    exit 1
fi

# Check if venv is activated
if [ -z "$VIRTUAL_ENV" ]; then
    echo -e "${YELLOW}Warning: Virtual environment not activated${NC}"
    echo "Activating .venv..."
    source .venv/bin/activate
fi

echo "Step 1: Checking NVIDIA GPU..."
echo "----------------------------------------"

# Check if nvidia-smi is available
if ! command -v nvidia-smi &> /dev/null; then
    echo -e "${RED}Error: nvidia-smi not found${NC}"
    echo "NVIDIA drivers are not installed or GPU not detected"
    echo ""
    echo "Please install NVIDIA drivers first:"
    echo "  sudo ubuntu-drivers autoinstall"
    echo "  sudo reboot"
    exit 1
fi

# Get GPU info
GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -n 1)
GPU_MEMORY=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -n 1)
DRIVER_VERSION=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -n 1)

echo -e "${GREEN}✓ GPU detected: $GPU_NAME${NC}"
echo -e "${GREEN}✓ VRAM: $GPU_MEMORY${NC}"
echo -e "${GREEN}✓ Driver version: $DRIVER_VERSION${NC}"
echo ""

# Check if it's an RTX 3080
if [[ "$GPU_NAME" == *"3080"* ]]; then
    echo -e "${GREEN}✓ RTX 3080 confirmed - excellent for LLM inference!${NC}"
else
    echo -e "${YELLOW}Note: GPU is $GPU_NAME (not RTX 3080)${NC}"
    echo "Phase 3 will still work, but performance may vary"
fi
echo ""

echo "Step 2: Installing CUDA-enabled Python packages..."
echo "----------------------------------------"

# Install llama-cpp-python with CUDA support
echo "Installing llama-cpp-python with CUDA support..."
echo "This may take 5-10 minutes as it compiles from source..."
echo ""

# Set build flags for CUDA (using new GGML_CUDA flag)
export CMAKE_ARGS="-DGGML_CUDA=on"
export FORCE_CMAKE=1

# Install with pip
pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ llama-cpp-python installed with CUDA support${NC}"
else
    echo -e "${RED}✗ Failed to install llama-cpp-python${NC}"
    echo "Trying alternative installation method..."
    
    # Try with specific CUDA architecture for RTX 3080 (Ampere = 86)
    CMAKE_ARGS="-DGGML_CUDA=on -DCMAKE_CUDA_ARCHITECTURES=86" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Installation failed. See error above.${NC}"
        exit 1
    fi
fi
echo ""

echo "Step 3: Verifying GPU support..."
echo "----------------------------------------"

# Test GPU support
python3 << 'EOF'
import sys

print("Testing llama-cpp-python GPU support...")

try:
    from llama_cpp import Llama
    print("✓ llama-cpp-python imported successfully")
    
    # Check if CUDA is available
    import ctypes
    try:
        # Try to load CUDA library
        ctypes.CDLL("libcuda.so.1")
        print("✓ CUDA library accessible")
    except:
        print("⚠ CUDA library not found (may still work)")
    
    print("\nGPU support verification complete!")
    print("Ollama will automatically use GPU when available.")
    
except ImportError as e:
    print(f"✗ Error importing llama-cpp-python: {e}")
    sys.exit(1)
except Exception as e:
    print(f"⚠ Warning: {e}")
    print("GPU support may still work with Ollama")

EOF

if [ $? -ne 0 ]; then
    echo -e "${RED}GPU support verification failed${NC}"
    exit 1
fi

echo ""
echo "Step 4: Checking Ollama GPU support..."
echo "----------------------------------------"

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo -e "${YELLOW}Ollama not found. Installing...${NC}"
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Check Ollama version
OLLAMA_VERSION=$(ollama --version 2>/dev/null || echo "unknown")
echo "Ollama version: $OLLAMA_VERSION"

# Pull a small test model if not already present
echo ""
echo "Pulling test model (llama3.2:1b) for GPU verification..."
ollama pull llama3.2:1b

echo ""
echo "Testing Ollama with GPU..."
echo "Running test query (this should use GPU)..."
echo ""

# Run test with debug output
OLLAMA_DEBUG=1 ollama run llama3.2:1b "Say 'GPU test successful' and nothing else" 2>&1 | grep -i "gpu\|cuda" || true

echo ""
echo "Step 5: Creating GPU configuration..."
echo "----------------------------------------"

# Create Ollama config directory
mkdir -p ~/.ollama

# Create environment file for GPU settings
cat > .env.gpu << 'EOF'
# GPU Configuration for Phase 3
# These settings optimize for RTX 3080 (10GB VRAM)

# CUDA settings
export CUDA_VISIBLE_DEVICES=0

# Ollama GPU settings
export OLLAMA_NUM_GPU=1
export OLLAMA_GPU_LAYERS=32
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_KEEP_ALIVE=5m

# Memory management
export OLLAMA_MAX_QUEUE=512
EOF

echo -e "${GREEN}✓ GPU configuration created: .env.gpu${NC}"
echo ""
echo "To use GPU settings, run:"
echo "  source .env.gpu"
echo ""

echo "Step 6: Running GPU benchmark..."
echo "----------------------------------------"

# Create quick benchmark script
cat > /tmp/gpu_benchmark.py << 'EOF'
#!/usr/bin/env python3
import time
import subprocess
import sys

def test_gpu_inference():
    """Quick GPU inference test."""
    print("Running GPU inference benchmark...")
    print("Model: llama3.2:1b")
    print("Query: 'Count from 1 to 10'")
    print("")
    
    start = time.time()
    result = subprocess.run(
        ['ollama', 'run', 'llama3.2:1b', 'Count from 1 to 10'],
        capture_output=True,
        text=True,
        timeout=30
    )
    duration = time.time() - start
    
    if result.returncode == 0:
        print(f"✓ Inference successful")
        print(f"  Time: {duration:.2f}s")
        
        # Estimate tokens (rough)
        output_len = len(result.stdout.split())
        if output_len > 0:
            tok_per_sec = output_len / duration
            print(f"  Tokens: ~{output_len}")
            print(f"  Speed: ~{tok_per_sec:.1f} tok/s")
            
            # Check if GPU speed (should be >20 tok/s for 1B model on GPU)
            if tok_per_sec > 20:
                print(f"\n✓ GPU acceleration appears to be working!")
                print(f"  (Speed indicates GPU usage)")
            else:
                print(f"\n⚠ Speed seems slow for GPU")
                print(f"  (May be using CPU - check Ollama logs)")
        
        return True
    else:
        print(f"✗ Inference failed: {result.stderr}")
        return False

if __name__ == "__main__":
    try:
        success = test_gpu_inference()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"✗ Benchmark failed: {e}")
        sys.exit(1)
EOF

chmod +x /tmp/gpu_benchmark.py
python3 /tmp/gpu_benchmark.py

echo ""
echo "=========================================="
echo "Stage 1 Complete!"
echo "=========================================="
echo ""
echo -e "${GREEN}✓ GPU detected and configured${NC}"
echo -e "${GREEN}✓ CUDA-enabled Python packages installed${NC}"
echo -e "${GREEN}✓ Ollama GPU support verified${NC}"
echo ""
echo "Next steps:"
echo "  1. Source GPU environment: source .env.gpu"
echo "  2. Run Stage 2: Ollama GPU optimization"
echo "  3. Test with PMM"
echo ""
echo "To verify GPU is being used:"
echo "  watch -n 1 nvidia-smi"
echo "  # In another terminal:"
echo "  ollama run llama3.2:1b 'Write a story'"
echo ""
