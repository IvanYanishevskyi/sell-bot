PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    telegram_user_id INTEGER,
    phone TEXT,
    discount_percent NUMERIC NOT NULL DEFAULT 0,
    discount_fixed NUMERIC NOT NULL DEFAULT 0,
    price_level TEXT DEFAULT 'base' CHECK (price_level IN ('base', '200k', '150k', '100k')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name_normalized)
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    name_normalized TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(name_normalized)
);

CREATE TABLE IF NOT EXISTS price_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_label TEXT NOT NULL,
    source_filename TEXT,
    items_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS price_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    price_version_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    base_price NUMERIC NOT NULL,
    price_200k NUMERIC NOT NULL,
    discount_200k_percent NUMERIC DEFAULT 0,
    price_150k NUMERIC NOT NULL,
    discount_150k_percent NUMERIC DEFAULT 0,
    price_100k NUMERIC NOT NULL,
    discount_100k_percent NUMERIC DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (price_version_id) REFERENCES price_versions(id) ON DELETE CASCADE,
    UNIQUE(price_version_id, sku)
);

CREATE TABLE IF NOT EXISTS stock_uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_filename TEXT,
    rows_count INTEGER NOT NULL DEFAULT 0,
    uploaded_by TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS stock_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_upload_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_upload_id) REFERENCES stock_uploads(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stock_current (
    sku TEXT PRIMARY KEY,
    stock_upload_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (stock_upload_id) REFERENCES stock_uploads(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id INTEGER,
    warehouse_id INTEGER,
    status TEXT NOT NULL CHECK (status IN ('draft', 'confirmed', 'cancelled', 'parse_error')),
    subtotal_amount NUMERIC NOT NULL DEFAULT 0,
    discount_amount NUMERIC NOT NULL DEFAULT 0,
    total_amount NUMERIC NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    name TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK (qty > 0),
    price_at_order NUMERIC NOT NULL,
    line_total NUMERIC NOT NULL,
    match_confidence REAL,
    needs_review INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    available_qty INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS order_raw_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    source_text TEXT NOT NULL,
    llm_payload TEXT,
    parse_status TEXT NOT NULL DEFAULT 'ok' CHECK (parse_status IN ('ok', 'parse_error')),
    error_message TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_is_active ON clients(is_active);
CREATE INDEX IF NOT EXISTS idx_clients_updated_at ON clients(updated_at);
CREATE INDEX IF NOT EXISTS idx_clients_name_normalized ON clients(name_normalized);

CREATE INDEX IF NOT EXISTS idx_warehouses_is_active ON warehouses(is_active);
CREATE INDEX IF NOT EXISTS idx_warehouses_updated_at ON warehouses(updated_at);
CREATE INDEX IF NOT EXISTS idx_warehouses_name_normalized ON warehouses(name_normalized);

CREATE INDEX IF NOT EXISTS idx_price_versions_is_active ON price_versions(is_active);
CREATE INDEX IF NOT EXISTS idx_price_versions_updated_at ON price_versions(updated_at);

CREATE INDEX IF NOT EXISTS idx_price_items_sku ON price_items(sku);
CREATE INDEX IF NOT EXISTS idx_price_items_is_active ON price_items(is_active);
CREATE INDEX IF NOT EXISTS idx_price_items_updated_at ON price_items(updated_at);
CREATE INDEX IF NOT EXISTS idx_price_items_version_id ON price_items(price_version_id);

CREATE INDEX IF NOT EXISTS idx_stock_uploads_is_active ON stock_uploads(is_active);
CREATE INDEX IF NOT EXISTS idx_stock_uploads_updated_at ON stock_uploads(updated_at);

CREATE INDEX IF NOT EXISTS idx_stock_items_sku ON stock_items(sku);
CREATE INDEX IF NOT EXISTS idx_stock_items_is_active ON stock_items(is_active);
CREATE INDEX IF NOT EXISTS idx_stock_items_updated_at ON stock_items(updated_at);
CREATE INDEX IF NOT EXISTS idx_stock_items_upload_id ON stock_items(stock_upload_id);

CREATE INDEX IF NOT EXISTS idx_stock_current_is_active ON stock_current(is_active);
CREATE INDEX IF NOT EXISTS idx_stock_current_updated_at ON stock_current(updated_at);

CREATE INDEX IF NOT EXISTS idx_orders_is_active ON orders(is_active);
CREATE INDEX IF NOT EXISTS idx_orders_updated_at ON orders(updated_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_client_id ON orders(client_id);
CREATE INDEX IF NOT EXISTS idx_orders_warehouse_id ON orders(warehouse_id);

CREATE INDEX IF NOT EXISTS idx_order_items_sku ON order_items(sku);
CREATE INDEX IF NOT EXISTS idx_order_items_is_active ON order_items(is_active);
CREATE INDEX IF NOT EXISTS idx_order_items_updated_at ON order_items(updated_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);

CREATE INDEX IF NOT EXISTS idx_order_raw_log_is_active ON order_raw_log(is_active);
CREATE INDEX IF NOT EXISTS idx_order_raw_log_updated_at ON order_raw_log(updated_at);
CREATE INDEX IF NOT EXISTS idx_order_raw_log_order_id ON order_raw_log(order_id);

CREATE TRIGGER IF NOT EXISTS trg_clients_updated_at
AFTER UPDATE ON clients
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE clients SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_warehouses_updated_at
AFTER UPDATE ON warehouses
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE warehouses SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_price_versions_updated_at
AFTER UPDATE ON price_versions
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE price_versions SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_price_items_updated_at
AFTER UPDATE ON price_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE price_items SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_stock_uploads_updated_at
AFTER UPDATE ON stock_uploads
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE stock_uploads SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_stock_items_updated_at
AFTER UPDATE ON stock_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE stock_items SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_stock_current_updated_at
AFTER UPDATE ON stock_current
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE stock_current SET updated_at = CURRENT_TIMESTAMP WHERE sku = OLD.sku;
END;

CREATE TRIGGER IF NOT EXISTS trg_orders_updated_at
AFTER UPDATE ON orders
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE orders SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_order_items_updated_at
AFTER UPDATE ON order_items
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE order_items SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS trg_order_raw_log_updated_at
AFTER UPDATE ON order_raw_log
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE order_raw_log SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
