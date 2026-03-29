#!/bin/bash
while true; do
    echo "$(date) — checking..."
    result=$(cd ~/tamago-max && python3 src/bounty_scanner.py 2>/dev/null | grep "ACTIVE")
    if ! echo "$result" | grep -q "ACTIVE (0)"; then
        echo "🚨 NEW CONTEST FOUND!"
        echo "$result"
    fi
    sleep 3600  # ogni ora
done
