import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# 1. Force environment loading before any downstream imports read the configuration
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from web3 import Web3

from routes.payment import router as payment_router

from database import Base, engine
from routes import admin, auth, blockchain, cases, donations
from scheduler import start_scheduler, stop_scheduler

# Configure logging framework
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CharityChain")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize relational database layers asynchronously
    logger.info("Initializing PostgreSQL database schema...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ PostgreSQL database tables confirmed.")

    # Fire up the CB-BFT background node-activity simulation
    logger.info("Activating CB-BFT consensus scheduling heartbeat...")
    start_scheduler()
    logger.info("✅ CB-BFT Background simulation cycle running.")

    yield

    # Clean shutdown handling
    logger.info("Deactivating background threads and pool assets...")
    stop_scheduler()
    await engine.dispose()
    logger.info("✅ Core systems cleanly offline.")


# Instantiate the unified core FastAPI application
app = FastAPI(
    title="CharityChain API",
    description="CB-BFT Cluster-Based Byzantine Fault Tolerant Blockchain Charity Framework",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure open CORS policies to handle frontend requests from VS Code Live Server (127.0.0.1:5500)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bind structural core modular routes
app.include_router(auth.router)
app.include_router(cases.router)
app.include_router(donations.router)
app.include_router(blockchain.router)
app.include_router(admin.router)
app.include_router(payment_router)

@app.get("/")
async def root():
    return {
        "system": "CharityChain",
        "version": "1.0.0",
        "status": "running",
        "consensus": "CB-BFT (CRITIC + Adaptive Clustering)",
        "researcher": "Pranto Shikder (ULAB)",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/blockchain/status")
async def check_besu_network_link():
    """System Diagnostic Route: Verifies the FastAPI platform can successfully interact

    with the active Hyperledger Besu core running over the cross-OS WSL layer.
    """
    # Read config the same way blockchain_client.py does. There is no settings
    # object in this project -- referencing one raised NameError on every call.
    blockchain_enabled = os.getenv("BLOCKCHAIN_ENABLED", "false").lower() == "true"
    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", "http://127.0.0.1:8545")
    contract_address = os.getenv("CONTRACT_ADDRESS", "")

    if not blockchain_enabled:
        return {
            "status": "Disabled",
            "message": "On-chain core operations set to mock mode.",
        }

    try:
        # Connect natively using the specific virtual switch URL from your .env file
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        if w3.is_connected():
            return {
                "status": "Connected",
                "layer_1_client": "Hyperledger Besu (Private Network)",
                "current_block_height": w3.eth.block_number,
                "chain_id": w3.eth.chain_id,
                "active_smart_contract": contract_address,
                "deployer_address": "0xfe3b557e8fb62b89f4916b721be55ceb828dbd73",
            }
        else:
            return {
                "status": "Connection Failed",
                "error": f"Could not complete RPC handshake with {rpc_url}",
            }
    except Exception as e:
        return {"status": "Network Error Exception", "detail": str(e)}