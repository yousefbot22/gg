
#!/bin/bash

cd /home/container || exit 1

export TZ="${TZ:-UTC}"

# Get internal IP
if command -v ip >/dev/null 2>&1; then
    INTERNAL_IP=$(ip route get 1 | awk '{for(i=1;i<NF;i++) if($i=="src"){print $(i+1);exit}}')
    export INTERNAL_IP
fi

# Parse Pterodactyl startup variables
PARSED=$(echo "${STARTUP}" | \
    sed -e 's/{{/${/g' -e 's/}}/}/g' | \
    eval echo "$(cat -)")

echo "=================================="
echo " QUREO BOT - CUSTOM DOCKER IMAGE"
echo "=================================="

echo "Checking Playwright Chromium..."

python -c 'from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True, args=["--no-sandbox"]); print("CHROMIUM_OK"); b.close(); p.stop()' || exit 1

echo "Starting application..."

printf '%s\n' "$PARSED"

exec bash -c "$PARSED"
