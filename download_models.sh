#!/usr/bin/env bash
set -e

echo "============================================================"
echo " ADAS Model Provisioner (Ollama)"
echo "============================================================"

# Ensure ollama is present
if ! command -v ollama &> /dev/null; then
    echo "Error: 'ollama' command not found. Please install Ollama from https://ollama.com"
    exit 1
fi

# Ensure ollama daemon is running
if ! curl -s http://127.0.0.1:11434/api/tags &> /dev/null; then
    echo "Notice: Ollama service does not appear to be running."
    echo "Starting Ollama service or please run 'ollama serve' in another terminal."
fi

# Specialized Model Assignments:
# 1. Architect: Planning, technical decomposition, clear specifications
ARCHITECT_MODEL="${ARCHITECT_MODEL:-qwen2.5:7b}"

# 2. Forge: Code synthesis, repo layout, multi-file generation
FORGE_MODEL="${FORGE_MODEL:-qwen2.5-coder:14b}"

# 3. Sentry: Deep reasoning, critical QA, test analysis, bug finding
SENTRY_MODEL="${SENTRY_MODEL:-deepseek-r1:8b}"

echo ""
echo "Target Models:"
echo "  - Architect (Planning & Specs): $ARCHITECT_MODEL"
echo "  - Forge     (Code Synthesis)   : $FORGE_MODEL"
echo "  - Sentry    (QA & Verification): $SENTRY_MODEL"
echo ""

echo ">>> [1/3] Pulling Architect model: $ARCHITECT_MODEL..."
ollama pull "$ARCHITECT_MODEL"

echo ""
echo ">>> [2/3] Pulling Forge model: $FORGE_MODEL..."
ollama pull "$FORGE_MODEL"

echo ""
echo ">>> [3/3] Pulling Sentry model: $SENTRY_MODEL..."
ollama pull "$SENTRY_MODEL"

echo ""
echo "============================================================"
echo " All ADAS models are ready!"
echo "============================================================"
echo "Run the nodes across 4 terminals:"
echo "  Terminal 1: ./nexus.py"
echo "  Terminal 2: ./architect.py"
echo "  Terminal 3: ./forge.py"
echo "  Terminal 4: ./sentry.py"
