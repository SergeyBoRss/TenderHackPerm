import json
from typing import Any


class CteSearchTextBuilder:
    @staticmethod
    def build(
        name: str,
        category_name: str | None,
        manufacturer_name: str | None,
        characteristics: dict[str, Any] | str | None,
    ) -> str:
        parts = [f"Наименование: {name.strip()}"]
        if category_name:
            parts.append(f"Категория: {category_name.strip()}")
        if manufacturer_name:
            parts.append(f"Производитель: {manufacturer_name.strip()}")
        normalized_characteristics = CteSearchTextBuilder._normalize_characteristics(characteristics)
        if normalized_characteristics:
            serialized = ", ".join(
                f"{key.strip()}: {str(value).strip()}"
                for key, value in sorted(normalized_characteristics.items(), key=lambda item: item[0].lower())
                if key and str(value).strip()
            )
            if serialized:
                parts.append(f"Характеристики: {serialized}")
        return ". ".join(parts)

    @staticmethod
    def _normalize_characteristics(characteristics: dict[str, Any] | str | None) -> dict[str, Any]:
        if characteristics is None:
            return {}
        if isinstance(characteristics, dict):
            return characteristics
        if isinstance(characteristics, str):
            text = characteristics.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}
