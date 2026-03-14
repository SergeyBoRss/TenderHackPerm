from asyncpg import Connection

from app.db.session import AsyncDatabase


class ProcurementAnalysisRepository:
    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def count_cte(self) -> int:
        return await self.db.fetchval("SELECT COUNT(*) FROM cte")

    async def fetch_cte_embedding_backfill_batch(
        self,
        conn: Connection,
        after_cte_id: int,
        limit: int,
    ) -> list[dict]:
        rows = await conn.fetch(
            """
            SELECT
                c.id,
                c.name,
                c.characteristics,
                c.category_id,
                c.manufacturer_id,
                categories.name AS category_name,
                manufacturers.name AS manufacturer_name,
                cte_embeddings.input_hash
            FROM cte AS c
            JOIN categories ON categories.id = c.category_id
            LEFT JOIN manufacturers ON manufacturers.id = c.manufacturer_id
            LEFT JOIN cte_embeddings ON cte_embeddings.cte_id = c.id
            WHERE c.id > $1
            ORDER BY c.id
            LIMIT $2
            """,
            after_cte_id,
            limit,
        )
        return [dict(row) for row in rows]

    async def upsert_cte_embedding(
        self,
        conn: Connection,
        cte_id: int,
        model_name: str,
        embedding_dimensions: int,
        input_text: str,
        input_hash: str,
        embedding_literal: str,
    ) -> None:
        await conn.execute(
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
            cte_id,
            model_name,
            embedding_dimensions,
            input_text,
            input_hash,
            embedding_literal,
        )

    async def upsert_cte_embeddings_batch(
        self,
        conn: Connection,
        rows: list[tuple[int, str, int, str, str, str]],
    ) -> None:
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

    async def fetch_target_cte_context(self, cte_id: int) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT
                c.id,
                c.name,
                c.category_id,
                c.manufacturer_id,
                categories.name AS category_name,
                manufacturers.name AS manufacturer_name,
                c.characteristics,
                cte_embeddings.embedding::text AS embedding_text
            FROM cte AS c
            JOIN categories ON categories.id = c.category_id
            LEFT JOIN manufacturers ON manufacturers.id = c.manufacturer_id
            LEFT JOIN cte_embeddings ON cte_embeddings.cte_id = c.id
            WHERE c.id = $1
            """,
            cte_id,
        )
        return dict(row) if row else None

    async def fetch_exact_candidates(
        self,
        target_category_id: int,
        target_manufacturer_id: int | None,
        target_embedding_text: str | None,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT
                contract_items.id AS contract_item_id,
                contract_items.cte_id,
                contract_items.unit_price,
                contracts.signed_at,
                counterparties.region AS customer_region,
                cte.category_id,
                cte.manufacturer_id,
                CASE
                    WHEN $3::text IS NULL OR cte_embeddings.embedding IS NULL THEN NULL
                    ELSE 1 - (cte_embeddings.embedding <=> $3::vector)
                END AS embedding_similarity
            FROM contract_items
            JOIN contracts ON contracts.id = contract_items.contract_id
            JOIN counterparties ON counterparties.id = contracts.customer_id
            JOIN cte ON cte.id = contract_items.cte_id
            LEFT JOIN cte_embeddings ON cte_embeddings.cte_id = cte.id
            WHERE cte.category_id = $1
               OR ($2::bigint IS NOT NULL AND cte.manufacturer_id = $2)
            """,
            target_category_id,
            target_manufacturer_id,
            target_embedding_text,
        )
        return [dict(row) for row in rows]

    async def fetch_name_exact_candidates(
        self,
        query_name: str,
        target_embedding_text: str | None,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT
                contract_items.id AS contract_item_id,
                contract_items.cte_id,
                contract_items.unit_price,
                contracts.signed_at,
                counterparties.region AS customer_region,
                cte.category_id,
                cte.manufacturer_id,
                TRUE AS name_exact_match,
                CASE
                    WHEN $2::text IS NULL OR cte_embeddings.embedding IS NULL THEN NULL
                    ELSE 1 - (cte_embeddings.embedding <=> $2::vector)
                END AS embedding_similarity
            FROM contract_items
            JOIN contracts ON contracts.id = contract_items.contract_id
            JOIN counterparties ON counterparties.id = contracts.customer_id
            JOIN cte ON cte.id = contract_items.cte_id
            LEFT JOIN cte_embeddings ON cte_embeddings.cte_id = cte.id
            WHERE lower(btrim(cte.name)) = lower(btrim($1))
            """,
            query_name,
            target_embedding_text,
        )
        return [dict(row) for row in rows]

    async def fetch_cte_name_exact_matches(
        self,
        query_name: str,
        limit: int,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT
                c.id AS cte_id,
                c.name,
                c.characteristics,
                c.category_id,
                categories.name AS category_name,
                c.manufacturer_id,
                manufacturers.name AS manufacturer_name,
                TRUE AS exact_name_match,
                NULL::double precision AS embedding_similarity
            FROM cte AS c
            JOIN categories ON categories.id = c.category_id
            LEFT JOIN manufacturers ON manufacturers.id = c.manufacturer_id
            WHERE lower(btrim(c.name)) = lower(btrim($1))
            ORDER BY c.id
            LIMIT $2
            """,
            query_name,
            limit,
        )
        return [dict(row) for row in rows]

    async def fetch_cte_vector_matches(
        self,
        target_embedding_text: str,
        limit: int,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT
                c.id AS cte_id,
                c.name,
                c.characteristics,
                c.category_id,
                categories.name AS category_name,
                c.manufacturer_id,
                manufacturers.name AS manufacturer_name,
                FALSE AS exact_name_match,
                1 - (cte_embeddings.embedding <=> $1::vector) AS embedding_similarity
            FROM cte_embeddings
            JOIN cte AS c ON c.id = cte_embeddings.cte_id
            JOIN categories ON categories.id = c.category_id
            LEFT JOIN manufacturers ON manufacturers.id = c.manufacturer_id
            ORDER BY cte_embeddings.embedding <=> $1::vector
            LIMIT $2
            """,
            target_embedding_text,
            limit,
        )
        return [dict(row) for row in rows]

    async def fetch_vector_candidates(
        self,
        target_embedding_text: str,
        limit: int,
    ) -> list[dict]:
        rows = await self.db.fetch(
            """
            SELECT
                contract_items.id AS contract_item_id,
                contract_items.cte_id,
                contract_items.unit_price,
                contracts.signed_at,
                counterparties.region AS customer_region,
                cte.category_id,
                cte.manufacturer_id,
                1 - (cte_embeddings.embedding <=> $1::vector) AS embedding_similarity
            FROM cte_embeddings
            JOIN cte ON cte.id = cte_embeddings.cte_id
            JOIN contract_items ON contract_items.cte_id = cte.id
            JOIN contracts ON contracts.id = contract_items.contract_id
            JOIN counterparties ON counterparties.id = contracts.customer_id
            ORDER BY cte_embeddings.embedding <=> $1::vector
            LIMIT $2
            """,
            target_embedding_text,
            limit,
        )
        return [dict(row) for row in rows]

    async def fetch_region_geo(self, region: str) -> dict | None:
        row = await self.db.fetchrow(
            """
            SELECT region, latitude, longitude, geocoder_source
            FROM region_geo_cache
            WHERE region = $1
            """,
            region,
        )
        return dict(row) if row else None

    async def upsert_region_geo(self, region: str, latitude: float, longitude: float, geocoder_source: str) -> None:
        await self.db.execute(
            """
            INSERT INTO region_geo_cache (region, latitude, longitude, geocoder_source)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (region) DO UPDATE
            SET
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                geocoder_source = EXCLUDED.geocoder_source,
                updated_at = NOW()
            """,
            region,
            latitude,
            longitude,
            geocoder_source,
        )
