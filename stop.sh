#!/usr/bin/env bash
pkill -f uvicorn 2>/dev/null || true
docker compose -p cbbft down 2>/dev/null || true
docker rm -f charitychain-db 2>/dev/null || true
echo "CharityChain stopped"
