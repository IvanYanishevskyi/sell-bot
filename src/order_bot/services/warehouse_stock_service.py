"""Service for importing warehouse-specific stock levels"""
from __future__ import annotations

from typing import Any
from order_bot.db.connection import Database
from order_bot.repositories.warehouse import WarehouseRepository


class WarehouseStockService:
    """Handles per-warehouse inventory imports"""

    def __init__(self, db: Database) -> None:
        self.db = db

    def _split_warehouse_rows(
        self, rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Split rows by warehouse sections.
        Format: Warehouse name as header row, then product rows with inventory data.
        """
        warehouse_data = []
        current_warehouse = None
        row_num = 0

        for row in rows:
            row_num += 1
            # Check if this is a warehouse header row (contains underscores)
            first_col = str(list(row.values())[0] if row else "").strip()
            if "______________________________" in first_col:
                # Extract warehouse name
                warehouse_name = first_col.split("___")[0].strip()
                if warehouse_name and warehouse_name != "nan":
                    current_warehouse = warehouse_name
                continue

            # Skip if no warehouse set
            if not current_warehouse:
                continue

            # Skip header rows
            if "Номенклатура" in first_col:
                continue

            # Process product row
            try:
                # Find product name column (usually second column)
                product_name = None
                for col_name in ["Номенклатура", "name", "product", "sku"]:
                    if col_name in row:
                        product_name = str(row[col_name]).strip()
                        break

                if not product_name or product_name == "nan" or not product_name:
                    continue

                # Find quantity columns
                total_stock = 0.0
                reserved = 0.0
                available = 0.0

                # Look for quantity fields
                for key, value in row.items():
                    if isinstance(value, (int, float)) or (
                        isinstance(value, str) and value.replace(".", "").replace(",", "").replace(" ", "").isdigit()
                    ):
                        qty = float(str(value).replace(" ", "").replace(",", "."))
                        if "_1" in str(key).lower() or "total" in str(key).lower():
                            total_stock = qty
                        elif "_2" in str(key).lower() or "reserved" in str(key).lower():
                            reserved = qty
                        elif "_3" in str(key).lower() or "available" in str(key).lower():
                            available = qty

                # If we only have one quantity, assume it's available
                if total_stock == 0 and available > 0:
                    total_stock = available + reserved

                warehouse_data.append({
                    "warehouse_name": current_warehouse,
                    "product_name": product_name,
                    "total_stock": total_stock,
                    "reserved": reserved,
                    "available": available,
                    "row_num": row_num
                })

            except Exception as e:
                print(f"Error parsing row {row_num}: {e}")
                continue

        return warehouse_data

    def import_inventory(
        self,
        rows: list[dict[str, Any]],
        source_filename: str,
        uploaded_by: str | None = None,
    ) -> dict[str, int]:
        """
        Import inventory levels per warehouse.
        Format: Warehouse header rows followed by product inventory data.
        """
        if not rows:
            raise ValueError("Inventory data is empty")

        # Parse warehouse sections
        warehouse_data = self._split_warehouse_rows(rows)

        if not warehouse_data:
            raise ValueError("No valid warehouse data found")

        processed = 0
        errors = []

        with self.db.transaction() as conn:
            warehouse_repo = WarehouseRepository(conn)

            # Group by warehouse
            warehouse_groups = {}
            for item in warehouse_data:
                wh_name = item["warehouse_name"]
                if wh_name not in warehouse_groups:
                    warehouse_groups[wh_name] = []
                warehouse_groups[wh_name].append(item)

            # Process each warehouse
            for warehouse_name, items in warehouse_groups.items():
                try:
                    # Get or create warehouse
                    warehouse = warehouse_repo.get_by_normalized_name(
                        WarehouseRepository._normalize(warehouse_name)
                    )

                    if not warehouse:
                        warehouse_id = warehouse_repo.upsert_warehouse(warehouse_name)
                    else:
                        warehouse_id = warehouse["id"]

                    # Clear existing stock for this warehouse
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        DELETE FROM stock_current
                        WHERE warehouse_id = ?
                        """,
                        (warehouse_id,)
                    )

                    # Insert new stock levels
                    insert_data = [
                        (warehouse_id, item["product_name"], item["available"])
                        for item in items
                        if item["product_name"] and item["available"] > 0
                    ]

                    if insert_data:
                        cursor.executemany(
                            """
                            INSERT OR REPLACE INTO stock_current
                            (warehouse_id, product_name, quantity, updated_at)
                            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                            """,
                            insert_data
                        )

                    processed += len(insert_data)

                except Exception as e:
                    errors.append(f"Error processing warehouse {warehouse_name}: {e}")

        return {
            "processed": processed,
            "warehouses": len(warehouse_groups),
            "errors_count": len(errors),
            "errors": errors if errors else None
        }
