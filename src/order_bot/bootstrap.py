# order_bot/bootstrap.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from order_bot.config import AppConfig
from order_bot.db import Database, init_db
from order_bot.ingest import ViberConfig, ViberIngestServer
from order_bot.llm.order_parser import OrderParser
from order_bot.llm.client import JSONLLMClient, LLMClientConfig
from order_bot.parsers.llm_file_parser import LLMFileParser
from order_bot.services import MatchingService, OrderService, PriceService, StockService, WarehouseService


@dataclass
class ServiceContainer:
    price_service: PriceService
    stock_service: StockService
    warehouse_service: WarehouseService
    order_service: OrderService
    file_parser: LLMFileParser
    order_parser: OrderParser
    upload_dir: Path


def build_services(config: AppConfig) -> ServiceContainer:
    db_path = Path(config.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    upload_dir = Path(config.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    db = Database(db_path)
    init_db(db_path)
    matching_service = MatchingService()

    # один клиент — используется и для file_parser и для order_parser
    
    llm_client = JSONLLMClient(
        LLMClientConfig(
            provider=config.llm_provider,
            api_key=config.llm_api_key,
            model=config.llm_model,
            base_url=config.llm_base_url,
            openrouter_site_url=config.openrouter_site_url,
            openrouter_app_name=config.openrouter_app_name,
        )
    )   
    print("LLM Config Debug:", {                    # ← тимчасовий дебаг
        "provider": config.llm_provider,
        "model": config.llm_model,
        "api_key_set": bool(config.llm_api_key),
        "enabled": llm_client.enabled,
    })
        # === DEBUG: який OrderParser реально використовується ===
    print("=== DEBUG OrderParser ===")
    print("Module path:", OrderParser.__module__)
    print("File path:", getattr(OrderParser, '__file__', 'No __file__'))
    print("Has parse method?", hasattr(OrderParser, 'parse'))
    print("Methods:", [m for m in dir(OrderParser) if not m.startswith('_')])
    # ====================================================

    order_parser=OrderParser(llm=llm_client),

    return ServiceContainer(
        price_service=PriceService(db),
        stock_service=StockService(db),
        warehouse_service=WarehouseService(db),
        order_service=OrderService(db, matching_service),
        file_parser=LLMFileParser(llm=llm_client),
        order_parser=OrderParser(llm=llm_client),
        upload_dir=upload_dir,
    )


def build_viber_ingest(config: AppConfig, services: ServiceContainer) -> ViberIngestServer | None:
    if not config.enable_viber_ingest:
        return None
    return ViberIngestServer(
        config=ViberConfig(
            enabled=True,
            host=config.viber_host,
            port=config.viber_port,
            path=config.viber_webhook_path,
            auth_token=config.viber_auth_token,
            manager_chat_id=config.manager_chat_id,
        ),
        services=services,
    )