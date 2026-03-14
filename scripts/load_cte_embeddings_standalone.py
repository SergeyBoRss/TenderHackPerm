import argparse
import asyncio
import logging
import os
import ssl
from pathlib import Path
from time import perf_counter

import asyncpg
from openpyxl import load_workbook

DEFAULT_FILE_PATH = Path("data/imports/cte_embeddings_for_postgres.xlsx")
EXPECTED_HEADERS = (
    "cte_id",
    "model_name",
    "embedding_dimensions",
    "input_text",
    "input_hash",
    "embedding",
    "created_at",
    "updated_at",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone import of cte_embeddings from xlsx into PostgreSQL")
    parser.add_argument("--file-path", default=str(DEFAULT_FILE_PATH), help="Path to xlsx file")
    parser.add_argument("--batch-size", type=int, default=1000, help="Rows per transaction")
    parser.add_argument("--truncate", action="store_true", help="Truncate cte_embeddings before import")
    parser.add_argument("--db-name", default=os.getenv("POSTGRES_DB", "tenderhackperm"))
    parser.add_argument("--db-user", default=os.getenv("POSTGRES_USER", "postgres"))
    parser.add_argument("--db-password", default=os.getenv("POSTGRES_PASSWORD", "postgres"))
    parser.add_argument("--db-host", default=os.getenv("POSTGRES_HOST", "localhost"))
    parser.add_argument("--db-port", type=int, default=int(os.getenv("POSTGRES_PORT", "5432")))
    parser.add_argument("--ssl-mode", default=os.getenv("POSTGRES_SSL_MODE", "disable"))
    return parser.parse_args()


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def make_ssl_param(ssl_mode: str) -> ssl.SSLContext | bool | None:
    if not ssl_mode or ssl_mode == "disable":
        return None
    if ssl_mode == "require":
        return True
    if ssl_mode in ("verify-ca", "verify-full"):
        ctx = ssl.create_default_context()
        if ssl_mode == "verify-ca":
            ctx.check_hostname = False
        return ctx
    raise ValueError(f"Unknown ssl_mode: {ssl_mode}")


def iter_embedding_rows(file_path: Path):
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    worksheet = workbook.active
    rows = worksheet.iter_rows(values_only=True)

    try:
        headers = next(rows)
    except StopIteration as exc:
        workbook.close()
        raise ValueError("Embeddings xlsx is empty") from exc

    if tuple(headers) != EXPECTED_HEADERS:
        workbook.close()
        raise ValueError(f"Unexpected headers: {headers}")

    try:
        for row_number, row in enumerate(rows, start=2):
            if row is None or all(value is None for value in row):
                continue

            cte_id, model_name, embedding_dimensions, input_text, input_hash, embedding, *_ = row
            if None in (cte_id, model_name, embedding_dimensions, input_text, input_hash, embedding):
                raise ValueError(f"Row {row_number}: required columns contain null values")

            yield (
                int(cte_id),
                str(model_name),
                int(embedding_dimensions),
                str(input_text),
                str(input_hash),
                str(embedding),
            )
    finally:
        workbook.close()


async def upsert_batch(conn: asyncpg.Connection, rows: list[tuple[int, str, int, str, str, str]]) -> None:
    await conn.executemany(
        """
        INSERT INTO cte_embeddings (
            cte_id,
            model_name,
            embedding_dimensions,
            input_text,
            input_hash,
            embedding
        )
        VALUES ($1, $2, $3, $4, $5, $6::vector)
        ON CONFLICT (cte_id) DO UPDATE
        SET
            model_name = EXCLUDED.model_name,
            embedding_dimensions = EXCLUDED.embedding_dimensions,
            input_text = EXCLUDED.input_text,
            input_hash = EXCLUDED.input_hash,
            embedding = EXCLUDED.embedding,
            updated_at = NOW()
        """,
        rows,
    )


async def import_embeddings(args: argparse.Namespace) -> None:
    file_path = Path(args.file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if args.batch_size <= 0:
        raise ValueError("batch_size must be positive")

    conn = await asyncpg.connect(
        database=args.db_name,
        user=args.db_user,
        password=args.db_password,
        host=args.db_host,
        port=args.db_port,
        ssl=make_ssl_param(args.ssl_mode),
    )

    started_at = perf_counter()
    imported = 0
    batch: list[tuple[int, str, int, str, str, str]] = []

    try:
        if args.truncate:
            await conn.execute("TRUNCATE TABLE cte_embeddings RESTART IDENTITY")
            logging.info("Truncated cte_embeddings table before import")

        for row in iter_embedding_rows(file_path):
            batch.append(row)
            if len(batch) < args.batch_size:
                continue

            async with conn.transaction():
                await upsert_batch(conn, batch)
            imported += len(batch)
            logging.info("Imported %s embeddings", imported)
            batch.clear()

        if batch:
            async with conn.transaction():
                await upsert_batch(conn, batch)
            imported += len(batch)
            logging.info("Imported %s embeddings", imported)

        elapsed = perf_counter() - started_at
        logging.info("Finished embeddings import: imported=%s elapsed=%.1fs", imported, elapsed)
    finally:
        await conn.close()


def main() -> None:
    configure_logging()
    args = parse_args()
    asyncio.run(import_embeddings(args))


if __name__ == "__main__":
    main()
