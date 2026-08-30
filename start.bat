@echo off
echo.
echo  ==========================================
echo   CharityChain — Starting Backend Server
echo  ==========================================
echo.

cd /d "%~dp0backend"

echo  [1/3] Activating virtual environment...
call venv\Scripts\activate.bat

echo  [2/3] Starting FastAPI server...
echo.
echo  Backend: http://127.0.0.1:8000
echo  API Docs: http://127.0.0.1:8000/docs
echo  Frontend: Open frontend/index.html with Live Server
echo.
echo  Press CTRL+C to stop the server
echo.

uvicorn main:app --reload --port 8000
Email: admin@charitychain.com
Password: Admin@1234
cd blockchain
npx hardhat run scripts/deploy.js --network localhost
wsl

cd ~/charitychain-besu && snap run geth --datadir geth-data --networkid 1337 --rpc --rpcaddr 0.0.0.0 --rpcport 8545 --rpcapi eth,net,web3,clique --mine --minerthreads 1 --etherbase 0x0e6fd4541c3e3600abc49f15be661629ede07cb0 --nodiscover --unlock 0x0e6fd4541c3e3600abc49f15be661629ede07cb0 --password password.txt --allow-insecure-unlock


cd C:\Users\User\OneDrive\Desktop\abpc-charity\backend
venv\Scripts\activate
python -m uvicorn main:app --reload


wsl hostname -I

Backend: http://127.0.0.1:8000/docs
Frontend: http://127.0.0.1:5500
Geth RPC: http://172.19.4.195:8545

Every time you sit down to work:
Step 1 — Open WSL and run:
bash~/charitychain_start.sh
Wait for it to finish. It will say "Besu is running!"
Step 2 — Open PowerShell and run:
powershellcd "C:\Users\User\OneDrive\Desktop\abpc-charity - Copy\backend"
venv\Scripts\activate
python -m uvicorn main:app --reload
Step 3 — Open VS Code Live Server on any frontend page.
That's it. Three steps, system is fully running.
To stop at end of day:
Step 1 — Ctrl+C in the PowerShell uvicorn terminal
Step 2 — WSL:
bash~/charitychain_stop.sh
Done.
pkill -f besu

cd ~/cbbft-net
docker compose -p cbbft down



cat > ~/stop-all.sh <<'EOF'
#!/usr/bin/env bash
echo "stopping cbbft test network..."
cd ~/cbbft-net 2>/dev/null && docker compose -p cbbft down

echo "stopping any other containers..."
docker stop $(docker ps -q) 2>/dev/null

echo "stopping docker..."
sudo service docker stop

echo "done. run 'wsl --shutdown' in PowerShell to close WSL too."
docker ps 2>/dev/null || echo "docker is down"
EOF
chmod +x ~/stop-all.sh
~/stop-all.sh



wsl --shutdown