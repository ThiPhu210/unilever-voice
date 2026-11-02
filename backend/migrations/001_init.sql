-- Unilever Voice Coach — schema PostgreSQL

CREATE TABLE coaches (
    id    SERIAL PRIMARY KEY,
    name  TEXT NOT NULL UNIQUE
);

CREATE TABLE stores (
    code      TEXT PRIMARY KEY,               -- ESS STORE CODE, vd STR-AEON-00459
    name      TEXT NOT NULL,
    customer  TEXT,                            -- AEON, Co.opmart...
    ka        TEXT,                            -- HYPER / ...
    region    TEXT,
    province  TEXT,
    coach_id  INT REFERENCES coaches(id)
);
CREATE INDEX idx_stores_coach ON stores(coach_id);

-- SA/BA. Chỉ lưu thông tin vận hành; KHÔNG lưu CCCD, ngày sinh, địa chỉ, SĐT, lương...
CREATE TABLE staff (
    code        TEXT PRIMARY KEY,              -- BA CODE: SA0247 / BA0587
    ess_code    TEXT,
    name        TEXT NOT NULL,
    position    TEXT,                          -- SA BPC, SA ORAL, BA ECOM...
    bu          TEXT,
    category    TEXT,
    store_code  TEXT REFERENCES stores(code),
    coach_id    INT REFERENCES coaches(id),
    active      BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX idx_staff_coach ON staff(coach_id);
CREATE INDEX idx_staff_store ON staff(store_code);

CREATE TABLE skus (
    sku_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    brand       TEXT,
    unit        TEXT,
    list_price  INTEGER CHECK (list_price IS NULL OR list_price >= 0),  -- đồng, tham khảo
    aliases     TEXT[] NOT NULL DEFAULT '{}',  -- cách đọc/nghe sai thường gặp, dùng cho matcher
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sessions (
    id               TEXT PRIMARY KEY,
    client_id        TEXT UNIQUE,              -- app tự sinh: upload lại không bị trùng
    staff_code       TEXT NOT NULL REFERENCES staff(code),
    store_code       TEXT REFERENCES stores(code),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    audio_path       TEXT,
    duration         REAL,
    status           TEXT NOT NULL CHECK (status IN ('queued','processing','done','error')),
    error            TEXT,
    transcript_text  TEXT,
    segments         JSONB NOT NULL DEFAULT '[]'
);
CREATE INDEX idx_sessions_created ON sessions(created_at DESC);
CREATE INDEX idx_sessions_staff   ON sessions(staff_code, created_at DESC);

CREATE TABLE orders (
    id                BIGSERIAL PRIMARY KEY,
    session_id        TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    closing_text      TEXT,
    customer_confirm  TEXT NOT NULL CHECK (customer_confirm IN ('yes','no','none')),
    needs_review      BOOLEAN NOT NULL DEFAULT FALSE,   -- còn SKU/số lượng/giá chưa chắc
    reviewed          BOOLEAN NOT NULL DEFAULT FALSE,   -- SA/BA đã xác nhận trên app
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_orders_session ON orders(session_id);
CREATE INDEX idx_orders_created ON orders(created_at DESC);

CREATE TABLE order_items (
    id           BIGSERIAL PRIMARY KEY,
    order_id     BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    position     SMALLINT NOT NULL,
    sku_id       TEXT NOT NULL REFERENCES skus(sku_id),
    sku_name     TEXT NOT NULL,                -- chụp tên tại thời điểm chốt
    qty          INTEGER NOT NULL CHECK (qty BETWEEN 1 AND 999),
    unit_price   INTEGER CHECK (unit_price IS NULL OR unit_price > 0),   -- đồng / 1 sản phẩm
    price_source TEXT NOT NULL CHECK (price_source IN ('spoken','manual','missing')),
    conf         REAL,
    qty_assumed  BOOLEAN NOT NULL DEFAULT FALSE,
    need_confirm BOOLEAN NOT NULL DEFAULT FALSE,
    manual       BOOLEAN NOT NULL DEFAULT FALSE,
    raw          TEXT,
    candidates   JSONB NOT NULL DEFAULT '[]',
    CHECK ((unit_price IS NULL) = (price_source = 'missing'))
);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_sku   ON order_items(sku_id);
