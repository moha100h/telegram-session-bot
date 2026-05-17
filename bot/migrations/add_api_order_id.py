"""Add api_order_id to orders table."""
import asyncio
from db.database import engine

async def migrate():
    async with engine.begin() as conn:
        try:
            await conn.execute(
                __import__("sqlalchemy").text(
                    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS api_order_id VARCHAR(64)"
                )
            )
            await conn.execute(
                __import__("sqlalchemy").text(
                    "CREATE INDEX IF NOT EXISTS ix_orders_api_order_id ON orders(api_order_id)"
                )
            )
            print("✅ api_order_id column added")
        except Exception as e:
            print(f"⚠️ {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
