#!/bin/bash
# Test script for identity adoption debugging
# Run with: bash test_identity_adoption.sh

echo "Starting PMM with fresh DB and debug logging..."
echo ""
echo "Instructions:"
echo "1. Select model 11 (gemma3:4b-it-qat)"
echo "2. Type: --@debug on"
echo "3. Type: --@metrics on"
echo "4. Type: Your name is Echo."
echo "5. Check the output for debug logs and SIGNALS section"
echo ""
echo "Press Enter to start..."
read

# Backup existing DB
if [ -f .data/pmm.db ]; then
    echo "Backing up existing DB to .data/pmm.db.backup"
    cp .data/pmm.db .data/pmm.db.backup
fi

# Remove DB for fresh start
rm -f .data/pmm.db

# Start chat
python3 -m pmm.cli.chat
