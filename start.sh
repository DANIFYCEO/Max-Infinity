#!/bin/bash
# Start Flask app in the background
gunicorn app:app --workers 1 --timeout 120 --bind 0.0.0.0:$PORT &

# Start Baileys WhatsApp Bridge in the foreground
cd baileys
export FLASK_URL="http://127.0.0.1:$PORT/message"
# export PHONE_NUMBER=$JOSEPH_NUMBER
node index.js
