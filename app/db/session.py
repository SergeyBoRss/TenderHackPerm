import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import asyncpg
from asyncpg.pool import Pool

from app.core.config import settings


class AsyncDatabase:
    def __init__(
        self,
        db_name: str,
        user: str,
        password: str,
        host: str,
        port: int,
        min_size: int,
        max_size: int,
        ssl_mode: str = "disable",
    ):
        self.db_name = db_name
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.min_size = min_size
        self.max_size = max_size
        self.ssl_mode = ssl_mode
        self.pool: Pool | None = None

    def _make_ssl_param(self) -> ssl.SSLContext | bool | None:
        if not self.ssl_mode or self.ssl_mode == "disable":
            return None
        if self.ssl_mode == "require":
            return True
        if self.ssl_mode in ("verify-ca", "verify-full"):
            ctx = ssl.create_default_context()
            if self.ssl_mode == "verify-ca":
                ctx.check_hostname = False
            return ctx
        raise ValueError(f"Unknown ssl_mode: {self.ssl_mode}")

    async def connect(self) -> None:
        ssl_param = self._make_ssl_param()
        self.pool = await asyncpg.create_pool(
            database=self.db_name,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            min_size=self.min_size,
            max_size=self.max_size,
            ssl=ssl_param,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _require_pool(self) -> Pool:
        if not self.pool:
            raise RuntimeError("DB pool is not initialized. Did you call connect()?")
        return self.pool

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[asyncpg.Connection]:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args: Any) -> str:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any, column: int = 0) -> Any:
        pool = self._require_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args, column=column)


db = AsyncDatabase(
    db_name=settings.postgres_db,
    user=settings.postgres_user,
    password=settings.postgres_password,
    host=settings.postgres_host,
    port=settings.postgres_port,
    min_size=settings.postgres_min_pool_size,
    max_size=settings.postgres_max_pool_size,
    ssl_mode=settings.postgres_ssl_mode,
)
