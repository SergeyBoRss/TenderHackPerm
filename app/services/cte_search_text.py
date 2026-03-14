import json
from typing import Any


class CteSearchTextBuilder:
    @staticmethod
    def normalize_characteristics(characteristics: dict[str, Any] | str | None) -> dict[str, Any]:
        return CteSearchTextBuilder._normalize_characteristics(characteristics)

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
                return CteSearchTextBuilder._parse_characteristics_pairs(text)
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _parse_characteristics_pairs(text: str) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for chunk in text.split(";"):
            part = chunk.strip()
            if not part or ":" not in part:
                continue
            key, value = part.split(":", 1)
            normalized_key = key.strip()
            normalized_value = value.strip()
            if normalized_key and normalized_value:
                result[normalized_key] = normalized_value
        return result
