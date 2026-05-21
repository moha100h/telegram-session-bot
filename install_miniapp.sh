#!/bin/bash
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  TSB MiniApp — Install Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd /opt/telegram-session-bot

# 1. pull latest
echo "[1/5] Pulling latest code..."
git pull origin main

# 2. بررسی پورت 9012
echo "[2/5] Checking port 9012..."
if ss -tlnp | grep -q ':9012'; then
  echo "  ⚠️  Port 9012 in use — stopping old container..."
  docker stop tsb_miniapp_web 2>/dev/null || true
  docker rm tsb_miniapp_web 2>/dev/null || true
fi

# 3. build
echo "[3/5] Building miniapp containers..."
docker compose build --no-cache miniapp_api miniapp_web

# 4. start
echo "[4/5] Starting miniapp containers..."
docker compose up -d miniapp_api miniapp_web

# 5. health check
echo "[5/5] Health check..."
sleep 6
STATUS=$(docker inspect --format='{{.State.Status}}' tsb_miniapp_api 2>/dev/null || echo "not found")
WEB_STATUS=$(docker inspect --format='{{.State.Status}}' tsb_miniapp_web 2>/dev/null || echo "not found")

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  API container:  $STATUS"
echo "  Web container:  $WEB_STATUS"
echo ""

if [ "$STATUS" = "running" ] && [ "$WEB_STATUS" = "running" ]; then
  IP=$(curl -s ifconfig.me 2>/dev/null || echo "YOUR_IP")
  echo "  ✅ MiniApp is LIVE!"
  echo ""
  echo "  🌐 URL: http://$IP:9012"
  echo ""
  echo "  Next step — set WebApp URL in BotFather:"
  echo "  /newapp → URL: http://$IP:9012"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
else
  echo "  ❌ Something went wrong. Logs:"
  docker logs tsb_miniapp_api --tail=20 2>/dev/null || true
  docker logs tsb_miniapp_web --tail=10 2>/dev/null || true
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  exit 1
fi
