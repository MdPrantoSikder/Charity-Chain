import asyncio
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

async def fix():
    pwd = CryptContext(schemes=['bcrypt'])
    h = pwd.hash('12345678')
    print('Hash:', h)
    engine = create_async_engine('postgresql+asyncpg://postgres:4422322321@localhost:5432/charitychain')
    async with engine.begin() as conn:
        await conn.execute(text("UPDATE users SET hashed_pw = :h"), {"h": h})
    print('Done - all passwords reset to 12345678')

asyncio.run(fix())
