import argparse
import asyncio
import logging
import os
import ssl
from pathlib import Path
from time import perf_counter

import asyncpg
from openpyxl import Workbook

DEFAULT_FILE_PATH = Path("data/imports/cte_embeddings_for_postgres.xlsx")
HEADERS = (
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
    parser = argparse.ArgumentParser(description="Standalone export of cte_embeddings from PostgreSQL to xlsx")
    parser.add_argument("--file-path", default=str(DEFAULT_FILE_PATH), help="Path to output xlsx file")
    parser.add_argument("--batch-size", type=int, default=5000, help="Rows fetched per batch")
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


async def export_embeddings(args: argparse.Namespace) -> None:
    file_path = Path(args.file_path)
    if args.batch_size <= 0:
        raise ValueError("batch_size must be positive")

    file_path.parent.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(
        database=args.db_name,
        user=args.db_user,
        password=args.db_password,
        host=args.db_host,
        port=args.db_port,
        ssl=make_ssl_param(args.ssl_mode),
    )

    workbook = Workbook(write_only=True)
    worksheet = workbook.create_sheet(title="cte_embeddings")
    worksheet.append(list(HEADERS))

    started_at = perf_counter()
    exported = 0
    last_id = 0

    try:
        while True:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    cte_id,
                    model_name,
                    embedding_dimensions,
                    input_text,
                    input_hash,
                    embedding::text AS embedding,
                    created_at,
                    updated_at
                FROM cte_embeddings
                WHERE id > $1
                ORDER BY id
                LIMIT $2
                """,
                last_id,
                args.batch_size,
            )
            if not rows:
                break

            for row in rows:
                worksheet.append(
                    [
                        int(row["cte_id"]),
                        str(row["model_name"]),
                        int(row["embedding_dimensions"]),
                        str(row["input_text"]),
                        str(row["input_hash"]),
                        str(row["embedding"]),
                        row["created_at"].isoformat() if row["created_at"] else None,
                        row["updated_at"].isoformat() if row["updated_at"] else None,
                    ]
                )

            exported += len(rows)
            last_id = int(rows[-1]["id"])
            logging.info("Exported %s embeddings", exported)

        workbook.save(file_path)
        elapsed = perf_counter() - started_at
        logging.info("Finished embeddings export: exported=%s file=%s elapsed=%.1fs", exported, file_path, elapsed)
    finally:
        await conn.close()


def main() -> None:
    configure_logging()
    args = parse_args()
    asyncio.run(export_embeddings(args))


if __name__ == "__main__":
    main()
