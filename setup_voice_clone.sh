#!/bin/bash
# setup_voice_clone.sh — Run once to create all folders

cd /var/POAi/CrewAiFlow/cf2

mkdir -p assets/voices
mkdir -p models/xtts
mkdir -p models/rvc
mkdir -p models/stylettsz
mkdir -p src/cf2/core/services/voice_clone
mkdir -p .runtime/cache/voice_clone

# Create __init__.py files if they don't exist
touch src/cf2/core/services/voice_clone/__init__.py

# Verify
echo "✅ Directory structure created."
ls -R assets/voices models/ .runtime/cache/voice_clone
