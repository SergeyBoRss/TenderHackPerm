from app.db.session import AsyncDatabase, db


async def get_db() -> AsyncDatabase:
    return db
