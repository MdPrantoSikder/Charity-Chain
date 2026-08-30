import hashlib
import os


IPFS_MOCK = os.getenv("IPFS_MOCK", "true").lower() == "true"


def generate_mock_cid(content: str) -> str:
    sha = hashlib.sha256(content.encode()).digest()
    import base64
    encoded = base64.b32encode(sha).decode().lower().rstrip("=")
    return "Qm" + encoded[:44]


async def pin_to_ipfs(content: str, filename: str = "document") -> str:
    if IPFS_MOCK:
        return generate_mock_cid(f"{filename}:{content}")
    raise NotImplementedError("Real IPFS not configured.")


def ipfs_url(cid: str) -> str:
    return f"https://ipfs.io/ipfs/{cid}"