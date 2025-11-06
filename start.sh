#!/bin/bash

# Nostr AI Swarm - Startup Script

echo "Starting Nostr AI Swarm..."
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

echo "Python found: $(python3 --version)"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "WARNING: Ollama doesn't seem to be running on http://localhost:11434"
    echo "   Please start Ollama: https://ollama.ai"
    echo ""
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install/upgrade dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo "Setup complete!"
echo ""
echo "Starting web server on http://localhost:8000"
echo "   Press Ctrl+C to stop"
echo ""

# Start the server
python backend.py
