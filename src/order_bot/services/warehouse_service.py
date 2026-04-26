from __future__ import annotations

from order_bot.db.connection import Database
from order_bot.repositories.warehouse import WarehouseRepository


class WarehouseService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upload_warehouses(
        self,
        rows: list[dict[str, object]],
        source_filename: str,
        uploaded_by: str | None = None,
    ) -> dict[str, int]:
        _ = source_filename
        _ = uploaded_by

        unique_names: dict[str, str] = {}
        for row in rows:
            raw_name = str(row.get("name", "")).strip()
            if not raw_name:
                continue
            normalized = WarehouseRepository._normalize(raw_name)
            if normalized not in unique_names:
                unique_names[normalized] = raw_name

        if not unique_names:
            raise ValueError("Файл складів не містить валідних назв")

        created = 0
        updated = 0
        with self.db.transaction() as conn:
            repo = WarehouseRepository(conn)
            # File contains full актуальный список складов: делаем replace.
            repo.deactivate_all_active()
            for normalized, name in unique_names.items():
                existing = repo.get_by_normalized_name(normalized)
                repo.upsert_warehouse(name)
                if existing is None:
                    created += 1
                else:
                    updated += 1

        return {
            "rows_total": len(unique_names),
            "created": created,
            "updated": updated,
        }
