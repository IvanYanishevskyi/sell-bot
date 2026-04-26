from __future__ import annotations

import argparse
import os
from pathlib import Path

from order_bot.db import init_db
from order_bot.parsers import FileParser
from order_bot.services.price_service import PriceService
from order_bot.db.connection import Database


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload price file directly into DB")
    parser.add_argument("--file", required=True, help="Path to .xlsx/.xlsm/.csv file")
    parser.add_argument("--created-by", default="cli", help="Author label")
    args = parser.parse_args()

    db_path = Path(os.getenv("APP_DB_PATH", "data/app.db"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    init_db(db_path)

    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File not found: {file_path}")

    data = file_path.read_bytes()
    parsed = FileParser().parse(data, file_path.name, forced_type="price")
    if parsed.errors:
        print("Parse errors:")
        for err in parsed.errors[:30]:
            print(f"- row={err.row} field={err.field}: {err.message}")
        raise SystemExit(1)

    service = PriceService(Database(db_path))
    version_id = service.upload_new_price(parsed.rows, source_filename=str(file_path), created_by=args.created_by)
    print(f"OK: activated price version #{version_id}, rows={len(parsed.rows)}")


if __name__ == "__main__":
    main()
