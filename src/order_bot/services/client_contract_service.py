"""Service for importing and managing client contracts with warehouse assignments"""
from __future__ import annotations

from typing import Any
import sqlite3
from order_bot.db.connection import Database
from order_bot.repositories.client import ClientRepository
from order_bot.repositories.warehouse import WarehouseRepository


class ClientContractService:
    """Handles client contract imports with warehouse and price level assignments"""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _normalize_price_level(self, level_str: str) -> str:
        """Convert Ukrainian price level names to internal format"""
        level_str = str(level_str).strip().lower()

        # Check for explicit amounts
        if any(word in level_str for word in ["200 тис", "200000", "2000000"]):
            return "200k"
        if any(word in level_str for word in ["150 тис", "150000"]):
            return "150k"
        if any(word in level_str for word in ["100 тис", "100000"]):
            return "100k"
        if any(word in level_str for word in ["базов", "базовий", "base"]):
            return "base"

        # Check for sales targets in millions
        if "4,000,000" in level_str or "4000000" in level_str:
            return "200k"  # 4M = high volume
        if "2,000,000" in level_str or "2000000" in level_str:
            return "150k"  # 2M = medium volume

        return "base"  # Default

    def _parse_contract_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single contract row into structured data"""
        try:
            # Skip empty rows
            if not any(str(v).strip() for v in row.values()):
                return None

            # Extract fields based on the structure
            client_name = (
                row.get("Покупець")
                or row.get("name")
                or row.get("client")
                or row.get("customer")
            )

            if not client_name or str(client_name).strip() == "nan":
                return None

            # Sales targets
            sales_target_2026 = float(
                str(row.get("Plan продажів 2026 грн", 0) or 0)
                .replace(" ", "")
                .replace(",", ".")
            )

            sales_2025 = float(
                str(row.get("Вартість продажу (грн) 2025", 0) or 0)
                .replace(" ", "")
                .replace(",", ".")
            )

            # Determine price level from contract or sales target
            price_level_raw = (
                row.get("Покупець контракт")
                or row.get("price_level")
                or row.get("contract_type")
                or ""
            )

            # If no explicit level, infer from sales target
            if not price_level_raw and sales_target_2026 > 0:
                if sales_target_2026 >= 4000000:
                    price_level_raw = "4,000,000"
                elif sales_target_2026 >= 2000000:
                    price_level_raw = "2,000,000"
                else:
                    price_level_raw = "базовий"

            price_level = self._normalize_price_level(price_level_raw)

            # Warehouse assignment
            warehouse_name = (
                row.get("Склад відгрузки")
                or row.get("warehouse")
                or "БОЯРКА"  # Default warehouse
            )

            # Manager info
            manager_name = (
                row.get("Керівник")
                or row.get("manager")
                or ""
            )

            manager_phone = (
                row.get("Телефон")
                or row.get("phone")
                or ""
            )

            # Location
            location = (
                row.get("Місцезнаходження та де представлені")
                or row.get("location")
                or ""
            )

            return {
                "name": str(client_name).strip(),
                "sales_target_2026": sales_target_2026,
                "sales_2025": sales_2025,
                "price_level": price_level,
                "warehouse_name": str(warehouse_name).strip(),
                "manager_name": str(manager_name).strip(),
                "manager_phone": str(manager_phone).strip(),
                "location": str(location).strip(),
            }

        except Exception as e:
            print(f"Error parsing contract row: {e}, row: {row}")
            return None

    def import_contracts(
        self,
        rows: list[dict[str, Any]],
        source_filename: str,
        uploaded_by: str | None = None,
    ) -> dict[str, int | list[str]]:
        """Import client contracts from Excel/CSV data"""
        if not rows:
            raise ValueError("Contract data is empty")

        processed = 0
        errors: list[str] = []
        warehouse_cache = {}

        with self.db.transaction() as conn:
            client_repo = ClientRepository(conn)
            warehouse_repo = WarehouseRepository(conn)

            for row in rows:
                parsed = self._parse_contract_row(row)
                if not parsed:
                    continue

                try:
                    # Get or create warehouse
                    warehouse_name = parsed["warehouse_name"]
                    if warehouse_name not in warehouse_cache:
                        warehouse = warehouse_repo.get_by_normalized_name(
                            WarehouseRepository._normalize(warehouse_name)
                        )
                        if not warehouse:
                            # Create new warehouse
                            warehouse_id = warehouse_repo.upsert_warehouse(warehouse_name)
                            warehouse_cache[warehouse_name] = {"id": warehouse_id}
                        else:
                            warehouse_cache[warehouse_name] = warehouse

                    warehouse_id = warehouse_cache[warehouse_name]["id"]

                    # Prepare client data with contract info
                    client_data = {
                        "name": parsed["name"],
                        "sales_target_2026": parsed["sales_target_2026"],
                        "sales_2025": parsed["sales_2025"],
                        "price_level": parsed["price_level"],
                        "warehouse_id": warehouse_id,
                        "manager_name": parsed["manager_name"],
                        "manager_phone": parsed["manager_phone"],
                        "location": parsed["location"],
                    }

                    # Create or update client
                    client_repo.upsert_with_contract_info(client_data)
                    processed += 1

                except sqlite3.IntegrityError as e:
                    errors.append(f"Error processing client {parsed.get('name', 'unknown')}: {e}")
                except Exception as e:
                    errors.append(f"Unexpected error: {e}")

        return {
            "processed": processed,
            "errors_count": len(errors),
            "errors": errors if errors else []
        }

    def get_contract_summary(self) -> dict[str, Any]:
        """Get summary of all contracts"""
        with self.db.connect() as conn:
            cursor = conn.cursor()

            # Count by price level
            cursor.execute("""
                SELECT price_level, COUNT(*) as count, SUM(sales_target_2026) as total_target
                FROM clients
                WHERE is_active = 1
                GROUP BY price_level
                ORDER BY price_level
            """)
            levels = [dict(row) for row in cursor.fetchall()]

            # Count by warehouse
            cursor.execute("""
                SELECT w.name, COUNT(c.id) as count
                FROM warehouses w
                LEFT JOIN clients c ON w.id = c.warehouse_id AND c.is_active = 1
                WHERE w.is_active = 1
                GROUP BY w.id, w.name
                ORDER BY count DESC
            """)
            warehouses = [dict(row) for row in cursor.fetchall()]

            return {
                "total_clients": sum(l["count"] for l in levels),
                "price_levels": levels,
                "warehouse_distribution": warehouses
            }
