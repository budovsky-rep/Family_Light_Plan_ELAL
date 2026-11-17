#!/usr/bin/env bash
set -e

SERVER_URL="${1:-http://34.165.250.15:8080}"
TARGET_DIR="$HOME/elal_chrome_extension"

mkdir -p "$TARGET_DIR"
curl -sL "$SERVER_URL/chrome_extension/manifest.json" -o "$TARGET_DIR/manifest.json"
curl -sL "$SERVER_URL/chrome_extension/background.js" -o "$TARGET_DIR/background.js"
curl -sL "$SERVER_URL/chrome_extension/content.js" -o "$TARGET_DIR/content.js"

echo "✅ תוסף הכרום הורד בהצלחה אל: $TARGET_DIR"
echo "כעת פתח ב-Chrome את הכתובת: chrome://extensions"
echo "1. הפעל בפינה העליונה את 'Developer mode' (מצב פיתוח)"
echo "2. לחץ על 'Load unpacked' (טעינת פריט שלא נארז)"
echo "3. בחר את התיקייה: $TARGET_DIR"
