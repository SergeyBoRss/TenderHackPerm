from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.db.session import AsyncDatabase
from app.repositories.procurement_imports import ProcurementImportRepository
from app.services.import_models import ContractRow, CteRow, ImportSummary


class ImportValidationError(ValueError):
    pass


class ExcelImportReader:
    CTE_HEADERS = {
        "идентификатор": "cte_id",
        "идентификатор сте": "cte_id",
        "наименование": "name",
        "наименование сте": "name",
        "категории": "category_name",
        "категория": "category_name",
        "производитель": "manufacturer_name",
        "характеристики": "characteristics",
        "характеристики сте": "characteristics",
    }

    CONTRACT_HEADERS = {
        "наименование закупки": "purchase_name",
        "кол-во": "quantity",
        "колво": "quantity",
        "количество": "quantity",
        "единица измерения": "unit_value",
        "идентификатор": "contract_id",
        "идентификатор контракта": "contract_id",
        "способ закупки": "procurement_method",
        "начальная стоимость": "initial_price",
        "начальная стоимость контракта": "initial_price",
        "стоимость закупки": "final_price",
        "стоимость контракта": "final_price",
        "стоимость контракта после заключения": "final_price",
        "% снижения": "reduction_percent",
        "ставка ндс": "vat_rate",
        "дата заключеия": "signed_at",
        "дата заключения": "signed_at",
        "дата заключения контракта": "signed_at",
        "инн заказчика": "customer_inn",
        "регион заказчика": "customer_region",
        "инн поставщика": "supplier_inn",
        "регион поставщика": "supplier_region",
        "идентификатор товара": "cte_id",
        "идентификатор сте по контракту": "cte_id",
        "наименование позиции": "position_name",
        "наименование позиции сте": "position_name",
        "цена за единицу": "unit_price",
    }

    def __init__(self, cte_path: Path, contracts_path: Path):
        self.cte_path = cte_path
        self.contracts_path = contracts_path

    def _read_cte_rows(self) -> list[CteRow]:
        rows = self._read_sheet_rows(self.cte_path, self.CTE_HEADERS)
        result: list[CteRow] = []
        for row_number, row in rows:
            cte_id = self._require_int(row.get("cte_id"), f"cte.xlsx row {row_number}: invalid identifier")
            name = self._require_text(row.get("name"), f"cte.xlsx row {row_number}: empty name")
            category_name = self._require_text(
                row.get("category_name"),
                f"cte.xlsx row {row_number}: empty category",
            )
            manufacturer_name = self._optional_text(row.get("manufacturer_name"))
            characteristics = self._parse_characteristics(row.get("characteristics"))
            result.append(
                CteRow(
                    cte_id=cte_id,
                    name=name,
                    category_name=category_name,
                    manufacturer_name=manufacturer_name,
                    characteristics=characteristics,
                )
            )
        return result

    def _read_contract_rows(self) -> list[ContractRow]:
        rows = self._read_sheet_rows(self.contracts_path, self.CONTRACT_HEADERS)
        result: list[ContractRow] = []
        for row_number, row in rows:
            result.append(
                ContractRow(
                    contract_id=self._require_int(
                        row.get("contract_id"),
                        f"contracts.xlsx row {row_number}: invalid contract identifier",
                    ),
                    purchase_name=self._require_text(
                        row.get("purchase_name"),
                        f"contracts.xlsx row {row_number}: empty purchase name",
                    ),
                    quantity=self._require_decimal(
                        row.get("quantity"),
                        f"contracts.xlsx row {row_number}: invalid quantity",
                    ),
                    unit_value=self._require_text(
                        row.get("unit_value"),
                        f"contracts.xlsx row {row_number}: empty unit",
                    ),
                    procurement_method=self._require_text(
                        row.get("procurement_method"),
                        f"contracts.xlsx row {row_number}: empty procurement method",
                    ),
                    initial_price=self._require_decimal(
                        row.get("initial_price"),
                        f"contracts.xlsx row {row_number}: invalid initial price",
                    ),
                    final_price=self._require_decimal(
                        row.get("final_price"),
                        f"contracts.xlsx row {row_number}: invalid final price",
                    ),
                    reduction_percent=self._require_decimal(
                        row.get("reduction_percent"),
                        f"contracts.xlsx row {row_number}: invalid reduction percent",
                    ),
                    vat_rate=self._require_decimal(
                        row.get("vat_rate"),
                        f"contracts.xlsx row {row_number}: invalid VAT rate",
                    ),
                    signed_at=self._require_date(
                        row.get("signed_at"),
                        f"contracts.xlsx row {row_number}: invalid signed date",
                    ),
                    customer_inn=self._require_text(
                        row.get("customer_inn"),
                        f"contracts.xlsx row {row_number}: empty customer INN",
                    ),
                    customer_region=self._optional_text(row.get("customer_region")),
                    supplier_inn=self._require_text(
                        row.get("supplier_inn"),
                        f"contracts.xlsx row {row_number}: empty supplier INN",
                    ),
                    supplier_region=self._optional_text(row.get("supplier_region")),
                    cte_id=self._require_int(
                        row.get("cte_id"),
                        f"contracts.xlsx row {row_number}: invalid CTE identifier",
                    ),
                    unit_price=self._require_decimal(
                        row.get("unit_price"),
                        f"contracts.xlsx row {row_number}: invalid unit price",
                    ),
                )
            )
        return result

    def read(self) -> tuple[list[CteRow], list[ContractRow]]:
        return self._read_cte_rows(), self._read_contract_rows()

    def _read_sheet_rows(self, path: Path, expected_headers: dict[str, str]) -> list[tuple[int, dict[str, Any]]]:
        if not path.exists():
            raise FileNotFoundError(f"Import file not found: {path}")

        try:
            from openpyxl import load_workbook
        except ModuleNotFoundError as exc:
            raise ImportValidationError(
                "openpyxl is not installed. Run `pip install -r requirements.txt` or rebuild the Docker image."
            ) from exc

        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows_iter = sheet.iter_rows(values_only=True)
            raw_headers = next(rows_iter, None)
            if raw_headers is None:
                raise ImportValidationError(f"{path.name}: file is empty")

            header_indexes: dict[str, int] = {}
            for index, value in enumerate(raw_headers):
                normalized = self._normalize_header(value)
                if normalized in expected_headers:
                    header_indexes[expected_headers[normalized]] = index

            missing = sorted(set(expected_headers.values()) - set(header_indexes.keys()))
            required_missing = [header for header in missing if header != "position_name"]
            if required_missing:
                raise ImportValidationError(
                    f"{path.name}: missing required columns {', '.join(required_missing)}"
                )

            result: list[tuple[int, dict[str, Any]]] = []
            for row_number, values in enumerate(rows_iter, start=2):
                if self._row_is_empty(values):
                    continue
                parsed_row = {
                    field_name: values[index] if index < len(values) else None
                    for field_name, index in header_indexes.items()
                }
                result.append((row_number, parsed_row))
            return result
        finally:
            workbook.close()

    @staticmethod
    def _normalize_header(value: Any) -> str:
        text = str(value or "").strip().lower().replace("ё", "е")
        return " ".join(text.split())

    @staticmethod
    def _row_is_empty(values: tuple[Any, ...]) -> bool:
        return all(value is None or str(value).strip() == "" for value in values)

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _require_text(self, value: Any, error_message: str) -> str:
        text = self._optional_text(value)
        if text is None:
            raise ImportValidationError(error_message)
        return text

    @staticmethod
    def _require_int(value: Any, error_message: str) -> int:
        if value is None or str(value).strip() == "":
            raise ImportValidationError(error_message)
        try:
            if isinstance(value, float):
                return int(value)
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise ImportValidationError(error_message) from exc

    @staticmethod
    def _require_decimal(value: Any, error_message: str) -> Decimal:
        if value is None or str(value).strip() == "":
            raise ImportValidationError(error_message)
        try:
            normalized = str(value).strip().lower()
            if normalized in {"без ндс", "ндс не облагается", "не облагается ндс"}:
                return Decimal("0")
            normalized = normalized.replace(" ", "").replace("%", "").replace(",", ".")
            return Decimal(normalized)
        except (InvalidOperation, ValueError) as exc:
            raise ImportValidationError(error_message) from exc

    @staticmethod
    def _require_date(value: Any, error_message: str) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None or str(value).strip() == "":
            raise ImportValidationError(error_message)

        raw = str(value).strip()
        for fmt in (
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%d-%m-%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        raise ImportValidationError(error_message)

    @staticmethod
    def _parse_characteristics(value: Any) -> dict[str, str]:
        text = str(value or "").strip()
        if not text:
            return {}

        result: dict[str, str] = {}
        for chunk in text.split(";"):
            part = chunk.strip().strip('"')
            if not part or ":" not in part:
                continue
            key, raw_value = part.split(":", 1)
            clean_key = key.strip()
            clean_value = raw_value.strip().strip('"')
            if clean_key:
                result[clean_key] = clean_value
        return result


class ProcurementImportService:
    def __init__(self, db: AsyncDatabase):
        self.db = db
        self.import_dir = Path(settings.import_data_dir)
        self.cte_path = self.import_dir / settings.import_cte_filename
        self.contracts_path = self.import_dir / settings.import_contracts_filename
        self.reader = ExcelImportReader(self.cte_path, self.contracts_path)
        self.repository = ProcurementImportRepository(db)

    async def clear_all(self) -> None:
        await self.repository.clear_all()

    async def load(self, refresh: bool = False) -> ImportSummary:
        cte_rows, contract_rows = self.reader.read()

        async with self.db.transaction() as conn:
            if refresh:
                await self.repository.clear_all_with_conn(conn)

            await self.repository.upsert_cte_data(conn, cte_rows)
            contracts_upserted, contract_items_inserted = await self.repository.upsert_contract_data(
                conn,
                contract_rows,
            )

        return ImportSummary(
            mode="refresh" if refresh else "load",
            cte_file=str(self.cte_path),
            contracts_file=str(self.contracts_path),
            cte_rows_processed=len(cte_rows),
            contracts_rows_processed=len(contract_rows),
            contracts_upserted=contracts_upserted,
            contract_items_inserted=contract_items_inserted,
        )
