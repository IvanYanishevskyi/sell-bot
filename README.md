# Sales Order Bot

Отдельное приложение для загрузки прайса/остатков и формирования черновиков заказов из Telegram.
Файлы, присланные в бота, сохраняются локально в `APP_UPLOAD_DIR` (или можно заменить на S3-адаптер).
Можно включить прием входящих заказов из Viber через webhook: новые сообщения автоматически попадают в Telegram на одобрение.
Менеджерское ревью реализовано через inline-кнопки: `Confirm`, `Cancel`, `Edit Qty`, `Edit Price`, `Remove Item`.

## Слои

- `db`: схема БД + инициализация + query builder
- `repositories`: только SQL-операции
- `services`: транзакционные сценарии
- `parsers`: парсинг файлов в `ParseResult(rows, errors)`
- `llm`: `OrderParser` для JSON-парсинга заказа
- `bot`: тонкий Telegram-слой

## Быстрый старт

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
set -a && source .env && set +a
PYTHONPATH=src python -m order_bot.bot.main
```

## Загрузка прайса, остатков и складов из Telegram

- `/upload_price` -> бот ждёт файл прайса (`.xlsx/.xlsm/.xls/.csv/.docx`)
- `/upload_stock` -> бот ждёт файл остатков (`.xlsx/.xlsm/.xls/.csv`)
- `/upload_warehouses` -> бот ждёт файл довідника складів (`.xlsx/.xlsm/.xls/.csv`)
- `/cancel_upload` -> сброс режима загрузки

После команды просто отправьте документ, подпись `price/stock/warehouse` не обязательна.
Підтримується також `DOCX` з таблицею прайсу.
Кожне нове завантаження `price` і `stock` працює як повна перезапис актуального зрізу.

## Viber -> Telegram одобрение

1. В чате с ботом отправьте `/myid` и возьмите `chat_id`.
2. Укажите его в `.env` как `MANAGER_CHAT_ID`.
3. Включите Viber-ingest и задайте webhook-параметры.
4. Запустите бота.

Пример `.env` для Viber webhook:

```bash
MANAGER_CHAT_ID=123456789
ENABLE_VIBER_INGEST=1
VIBER_HOST=0.0.0.0
VIBER_PORT=8088
VIBER_WEBHOOK_PATH=/webhook/viber
VIBER_AUTH_TOKEN=your_viber_auth_token
```

Webhook endpoint: `http://<your-host>:8088/webhook/viber`.

## LLM провайдер (OpenAI / OpenRouter)

Бот использует единый JSON-адаптер LLM и может работать через `openai` или `openrouter`.

OpenAI:

```bash
LLM_PROVIDER=openai
LLM_MODEL=gpt-4.1-mini
LLM_API_KEY=<your_openai_key>
```

OpenRouter:

```bash
LLM_PROVIDER=openrouter
LLM_MODEL=openai/gpt-4.1-mini
OPENROUTER_API_KEY=<your_openrouter_key>
OPENROUTER_SITE_URL=https://your-domain.example
OPENROUTER_APP_NAME=sales-order-bot
```

`LLM_API_KEY` имеет приоритет. Если он пустой, для `openrouter` будет взят `OPENROUTER_API_KEY`, а для `openai` — `OPENAI_API_KEY`.

## Ревью заказов

- Любой новый заказ (из Telegram текста или из Viber) приходит менеджеру карточкой с кнопками.
- `Confirm`: переводит `draft -> confirmed`.
- `Cancel`: переводит `draft -> cancelled`.
- `Edit Qty` / `Edit Price`: выбор позиции, затем бот ждёт новое значение текстом.
- `Remove Item`: удаляет позицию из активного набора заказа (последнюю удалить нельзя).
- `Bind Client`: ручная привязка клиента к черновику и автоматический перерасчет скидки.
- `Unbind Client`: снимает клиента и пересчитывает итог без клиентской скидки.
- `Bind Warehouse`: ручна прив'язка складу з БД до чернетки.
- `Unbind Warehouse`: зняти склад з чернетки.

## Клиенты и скидки

- LLM больше не определяет клиента.
- Черновик создается без клиента (`Клиент: не привязан`).
- Менеджер добавляет клиентов вручную:
  - `/client_add Название | discount_percent | discount_fixed`
  - `/clients [поиск]`
- После `Bind Client` у заказа пересчитываются:
  - `subtotal_amount`
  - `discount_amount` (процент + фикс, с ограничением не больше подытога)
  - `total_amount`

## Склади

- Додати склад: `/warehouse_add Назва складу`
- Переглянути склади: `/warehouses [пошук]`
- Масове завантаження зі файлу: `/upload_warehouses` (upsert за назвою складу)
- Масове завантаження зі файлу: `/upload_warehouses` (повна заміна активного списку складів)
- Склад підставляється у фінальний підтверджений формат рахунку.

## Классификация входящих сообщений

- Каждое входящее сообщение сначала проходит этап `intent`:
  - `is_order=true` -> запускается парсинг позиций и создание `draft`.
  - `is_order=false` -> сообщение помечается как незаказное и не создаёт заказ.
- При включенном LLM intent определяется моделью.
- Если LLM недоступен, используется эвристика (ключевые слова, строки позиций с количеством, признаки логистики).

## Тесты

```bash
PYTHONPATH=src pytest -q
```

CLI-перевірка завантаження складів без Telegram:

```bash
PYTHONPATH=src python -m order_bot.cli.upload_warehouses --file "/home/azureuser/КомерцСклад 17-04-26.xls"
```
