import json

from asyncpg import Connection

from app.db.session import AsyncDatabase
from app.services.import_models import ContractRow, CteRow


class ProcurementImportRepository:
    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def clear_all(self) -> None:
        async with self.db.transaction() as conn:
            await self.clear_all_with_conn(conn)

    async def clear_all_with_conn(self, conn: Connection) -> None:
        await conn.execute(
            """
            TRUNCATE TABLE
                contract_items,
                contracts,
                cte,
                purchase_names,
                procurement_methods,
                units,]
                counterparties,
                manufacturers,
                categories
            RESTART IDENTITY CASCADE
            """
        )

    async def upsert_cte_data(self, conn: Connection, rows: list[CteRow]) -> None:
        category_names = sorted({row.category_name for row in rows})
        manufacturer_names = sorted({row.manufacturer_name for row in rows if row.manufacturer_name})

        await self._insert_unique_values(conn, "categories", "name", category_names)
        await self._insert_unique_values(conn, "manufacturers", "name", manufacturer_names)

        category_map = await self._fetch_id_map(conn, "categories", "name", category_names)
        manufacturer_map = await self._fetch_id_map(conn, "manufacturers", "name", manufacturer_names)

        for row in rows:
            await conn.execute(
                """
                INSERT INTO cte (id, name, category_id, manufacturer_id, characteristics)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (id) DO UPDATE
                SET
                    name = EXCLUDED.name,
                    category_id = EXCLUDED.category_id,
                    manufacturer_id = EXCLUDED.manufacturer_id,
                    characteristics = EXCLUDED.characteristics,
                    updated_at = NOW()
                """,
                row.cte_id,
                row.name,
                category_map[row.category_name],
                manufacturer_map.get(row.manufacturer_name) if row.manufacturer_name else None,
                json.dumps(row.characteristics, ensure_ascii=False),
            )

    async def upsert_contract_data(self, conn: Connection, rows: list[ContractRow]) -> tuple[int, int]:
        purchase_names = sorted({row.purchase_name for row in rows})
        procurement_methods = sorted({row.procurement_method for row in rows})
        units = sorted({row.unit_value for row in rows})

        customer_inns = {row.customer_inn: row.customer_region for row in rows}
        supplier_inns = {row.supplier_inn: row.supplier_region for row in rows}
        counterparties = {**customer_inns, **supplier_inns}

        await self._insert_unique_values(conn, "purchase_names", "name", purchase_names)
        await self._insert_unique_values(conn, "procurement_methods", "name", procurement_methods)
        await self._insert_unique_values(conn, "units", "value", units)

        for inn, region in counterparties.items():
            await conn.execute(
                """
                INSERT INTO counterparties (inn, region)
                VALUES ($1, $2)
                ON CONFLICT (inn) WHERE inn IS NOT NULL DO UPDATE
                SET
                    region = COALESCE(EXCLUDED.region, counterparties.region),
                    updated_at = NOW()
                """,
                inn,
                region,
            )

        purchase_name_map = await self._fetch_id_map(conn, "purchase_names", "name", purchase_names)
        procurement_method_map = await self._fetch_id_map(conn, "procurement_methods", "name", procurement_methods)
        unit_map = await self._fetch_id_map(conn, "units", "value", units)
        counterparty_map = await self._fetch_id_map(conn, "counterparties", "inn", list(counterparties.keys()))

        contracts_by_id: dict[int, ContractRow] = {}
        for row in rows:
            contracts_by_id[row.contract_id] = row

        contract_ids = sorted(contracts_by_id.keys())
        if contract_ids:
            await conn.execute("DELETE FROM contract_items WHERE contract_id = ANY($1::bigint[])", contract_ids)

        for contract_id, row in contracts_by_id.items():
            await conn.execute(
                """
                INSERT INTO contracts (
                    id,
                    purchase_name_id,
                    procurement_method_id,
                    initial_price,
                    final_price,
                    reduction_percent,
                    vat_rate,
                    signed_at,
                    customer_id,
                    supplier_id
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (id) DO UPDATE
                SET
                    purchase_name_id = EXCLUDED.purchase_name_id,
                    procurement_method_id = EXCLUDED.procurement_method_id,
                    initial_price = EXCLUDED.initial_price,
                    final_price = EXCLUDED.final_price,
                    reduction_percent = EXCLUDED.reduction_percent,
                    vat_rate = EXCLUDED.vat_rate,
                    signed_at = EXCLUDED.signed_at,
                    customer_id = EXCLUDED.customer_id,
                    supplier_id = EXCLUDED.supplier_id,
                    updated_at = NOW()
                """,
                contract_id,
                purchase_name_map[row.purchase_name],
                procurement_method_map[row.procurement_method],
                row.initial_price,
                row.final_price,
                row.reduction_percent,
                row.vat_rate,
                row.signed_at,
                counterparty_map[row.customer_inn],
                counterparty_map[row.supplier_inn],
            )

        for row in rows:
            await conn.execute(
                """
                INSERT INTO contract_items (contract_id, cte_id, quantity, unit_id, unit_price)
                VALUES ($1, $2, $3, $4, $5)
                """,
                row.contract_id,
                row.cte_id,
                row.quantity,
                unit_map[row.unit_value],
                row.unit_price,
            )

        return len(contracts_by_id), len(rows)

    async def _insert_unique_values(
        self,
        conn: Connection,
        table_name: str,
        column_name: str,
        values: list[str],
    ) -> None:
        for value in values:
            await conn.execute(
                f"""
                INSERT INTO {table_name} ({column_name})
                VALUES ($1)
                ON CONFLICT ({column_name}) DO NOTHING
                """,
                value,
            )

    async def _fetch_id_map(
        self,
        conn: Connection,
        table_name: str,
        key_column: str,
        keys: list[str],
    ) -> dict[str, int]:
        if not keys:
            return {}
        rows = await conn.fetch(
            f"""
            SELECT id, {key_column}
            FROM {table_name}
            WHERE {key_column} = ANY($1::text[])
            """,
            keys,
        )
        return {str(row[key_column]): int(row["id"]) for row in rows}
