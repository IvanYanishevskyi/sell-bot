from __future__ import annotations

import unittest

from order_bot.db import Database, init_db
from order_bot.parsers import FileParser
from order_bot.repositories.price import PriceRepository
from order_bot.repositories.stock import StockRepository
from order_bot.repositories.warehouse import WarehouseRepository
from order_bot.services.price_service import PriceService
from order_bot.services.stock_service import StockService
from order_bot.services.warehouse_service import WarehouseService
from tests.fake_llm import FakeLLMClient


def _make_csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(item) for item in row))
    return "\n".join(lines).encode("utf-8")


class PriceStockUploadTests(unittest.TestCase):
    def setUp(self) -> None:
        from tempfile import TemporaryDirectory

        self._tmpdir = TemporaryDirectory()
        self.db_path = f"{self._tmpdir.name}/app.db"
        init_db(self.db_path)
        self.db = Database(self.db_path)
        self.parser = FileParser(llm=FakeLLMClient())

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_price_upload_activates_new_version(self) -> None:
        price_service = PriceService(self.db)

        first_price_file = _make_csv_bytes(
            ["SKU", "Name", "Price"],
            [["A-1", "Apple", 100], ["B-2", "Banana", 50]],
        )
        first = self.parser.parse(first_price_file, "price_v1.csv", forced_type="price")
        self.assertFalse(first.errors)
        first_version_id = price_service.upload_new_price(first.rows, "price_v1.csv", created_by="tester")

        second_price_file = _make_csv_bytes(
            ["SKU", "Name", "Price"],
            [["A-1", "Apple", 120], ["C-3", "Cherry", 80]],
        )
        second = self.parser.parse(second_price_file, "price_v2.csv", forced_type="price")
        self.assertFalse(second.errors)
        second_version_id = price_service.upload_new_price(second.rows, "price_v2.csv", created_by="tester")
        self.assertGreater(second_version_id, first_version_id)

        with self.db.connect() as conn:
            repo = PriceRepository(conn)
            active = repo.get_active()

        self.assertIsNotNone(active)
        self.assertEqual(active["version"]["id"], second_version_id)
        self.assertEqual({item["sku"] for item in active["items"]}, {"A-1", "C-3"})

    def test_price_parse_without_sku_header(self) -> None:
        price_service = PriceService(self.db)
        file_bytes = _make_csv_bytes(
            ["№", "Назва препарату", "Базова ціна, у.о без ПДВ"],
            [["1", "ГЕФЕСТ ПРО", "3.8"], ["2", "ЛІКОРІС", "13.3"]],
        )
        parsed = self.parser.parse(file_bytes, "price_ua.csv", forced_type="price")
        self.assertFalse(parsed.errors)
        self.assertEqual(len(parsed.rows), 2)
        self.assertTrue(parsed.rows[0]["sku"])
        version_id = price_service.upload_new_price(parsed.rows, "price_ua.csv", created_by="tester")
        self.assertGreater(version_id, 0)

    def test_stock_upload_upserts_current_snapshot(self) -> None:
        stock_service = StockService(self.db)

        first_stock_file = _make_csv_bytes(
            ["SKU", "Quantity"],
            [["A-1", 10], ["B-2", 5]],
        )
        first = self.parser.parse(first_stock_file, "stock_v1.csv", forced_type="stock")
        self.assertFalse(first.errors)
        stock_service.upload_stock(first.rows, "stock_v1.csv", uploaded_by="tester")

        second_stock_file = _make_csv_bytes(
            ["SKU", "Quantity"],
            [["A-1", 2], ["C-3", 9]],
        )
        second = self.parser.parse(second_stock_file, "stock_v2.csv", forced_type="stock")
        self.assertFalse(second.errors)
        stock_service.upload_stock(second.rows, "stock_v2.csv", uploaded_by="tester")

        with self.db.connect() as conn:
            repo = StockRepository(conn)
            a1 = repo.get_by_sku("A-1")
            b2 = repo.get_by_sku("B-2")
            c3 = repo.get_by_sku("C-3")

        self.assertIsNotNone(a1)
        self.assertIsNone(b2)
        self.assertIsNotNone(c3)
        self.assertEqual(a1["quantity"], 2)
        self.assertEqual(c3["quantity"], 9)

    def test_warehouse_upload_upserts_reference_table(self) -> None:
        warehouse_service = WarehouseService(self.db)

        warehouse_file = _make_csv_bytes(
            ["Склад"],
            [["ВЗ Кропивницький 6"], ["Вінницькі хутори"], ["ВЗ Кропивницький 6"]],
        )
        parsed = self.parser.parse(warehouse_file, "warehouses.csv", forced_type="warehouse")
        self.assertFalse(parsed.errors)
        result = warehouse_service.upload_warehouses(parsed.rows, "warehouses.csv", uploaded_by="tester")
        self.assertEqual(result["rows_total"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)

        warehouse_file_2 = _make_csv_bytes(
            ["Склад"],
            [["ВЗ Кропивницький 6"], ["Нове місто"]],
        )
        parsed_2 = self.parser.parse(warehouse_file_2, "warehouses2.csv", forced_type="warehouse")
        self.assertFalse(parsed_2.errors)
        result_2 = warehouse_service.upload_warehouses(parsed_2.rows, "warehouses2.csv", uploaded_by="tester")
        self.assertEqual(result_2["rows_total"], 2)
        self.assertEqual(result_2["created"], 1)
        self.assertEqual(result_2["updated"], 1)

        with self.db.connect() as conn:
            repo = WarehouseRepository(conn)
            warehouses = repo.list_active(limit=10)

        names = {row["name"] for row in warehouses}
        self.assertEqual(names, {"ВЗ Кропивницький 6", "Нове місто"})


if __name__ == "__main__":
    unittest.main()
