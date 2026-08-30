import asyncio
from database import AsyncSessionLocal
from models import User
from security import hash_password

async def create_default_users():
    async with AsyncSessionLocal() as db:
        users = [
            User(
                full_name      = 'System Admin',
                email          = 'admin@charitychain.com',
                hashed_pw      = hash_password('Admin@1234'),
                role           = 'admin',
                kyc_status     = 'verified',
                wallet_balance = 0.0,
            ),
            User(
                full_name      = 'Demo Donor',
                email          = 'donor@charitychain.com',
                hashed_pw      = hash_password('12345678'),
                role           = 'donor',
                kyc_status     = 'verified',
                wallet_balance = 50000.0,
            ),
            User(
                full_name      = 'Demo Needy',
                email          = 'needy@charitychain.com',
                hashed_pw      = hash_password('12345678'),
                role           = 'needy',
                kyc_status     = 'verified',
                wallet_balance = 0.0,
            ),
            User(
                full_name      = 'Demo Trustee',
                email          = 'trustee@charitychain.com',
                hashed_pw      = hash_password('12345678'),
                role           = 'trustee',
                kyc_status     = 'verified',
                wallet_balance = 0.0,
            ),
        ]
        for u in users:
            db.add(u)
        try:
            await db.commit()
            print('✅ Default users created')
        except Exception as e:
            await db.rollback()
            print(f'Users may already exist: {e}')

asyncio.run(create_default_users())
