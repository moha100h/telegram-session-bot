-- SMM Panel + Multi-Panel — Full Schema v3.0
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(64), first_name VARCHAR(64), last_name VARCHAR(64), phone VARCHAR(20),
    balance DECIMAL(14,6) DEFAULT 0.0 NOT NULL, is_banned BOOLEAN DEFAULT FALSE NOT NULL,
    referral_code VARCHAR(16) UNIQUE, referral_count INTEGER DEFAULT 0 NOT NULL,
    referred_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL, updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY, telegram_id BIGINT UNIQUE NOT NULL, username VARCHAR(64),
    role VARCHAR(32) DEFAULT 'admin' NOT NULL, permissions TEXT DEFAULT '{}' NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR(32) NOT NULL, amount DECIMAL(14,6) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, method VARCHAR(32),
    tx_hash VARCHAR(128), wallet_address VARCHAR(128), description TEXT,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL, service_name VARCHAR(255), link TEXT NOT NULL,
    quantity INTEGER NOT NULL, cost_price DECIMAL(14,6) NOT NULL, sell_price DECIMAL(14,6) NOT NULL,
    status VARCHAR(32) DEFAULT 'pending' NOT NULL, api_order_id VARCHAR(64),
    start_count INTEGER, remains INTEGER,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL, updated_at TIMESTAMP DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS admin_settings (
    id SERIAL PRIMARY KEY, key VARCHAR(64) UNIQUE NOT NULL, value TEXT
);
CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY, telegram_id BIGINT NOT NULL, code VARCHAR(8) NOT NULL,
    is_used BOOLEAN DEFAULT FALSE NOT NULL, expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS panels (
    id SERIAL PRIMARY KEY, name VARCHAR(64) NOT NULL, button_label VARCHAR(64) NOT NULL,
    description TEXT, group_chat_id BIGINT,
    is_active BOOLEAN DEFAULT TRUE NOT NULL, order_index INTEGER DEFAULT 0 NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS panel_categories (
    id SERIAL PRIMARY KEY, panel_id INTEGER NOT NULL REFERENCES panels(id) ON DELETE CASCADE,
    name VARCHAR(64) NOT NULL, icon VARCHAR(8) DEFAULT '📂' NOT NULL,
    order_index INTEGER DEFAULT 0 NOT NULL, is_active BOOLEAN DEFAULT TRUE NOT NULL
);
CREATE TABLE IF NOT EXISTS panel_services (
    id SERIAL PRIMARY KEY, category_id INTEGER NOT NULL REFERENCES panel_categories(id) ON DELETE CASCADE,
    name VARCHAR(128) NOT NULL, description TEXT, price DECIMAL(14,6) NOT NULL,
    min_qty INTEGER DEFAULT 1 NOT NULL, max_qty INTEGER DEFAULT 10000 NOT NULL,
    is_active BOOLEAN DEFAULT TRUE NOT NULL, order_index INTEGER DEFAULT 0 NOT NULL,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL
);
CREATE TABLE IF NOT EXISTS panel_orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    panel_id INTEGER NOT NULL REFERENCES panels(id) ON DELETE CASCADE,
    service_id INTEGER NOT NULL REFERENCES panel_services(id) ON DELETE CASCADE,
    service_name VARCHAR(128), panel_name VARCHAR(64),
    quantity INTEGER NOT NULL, unit_price DECIMAL(14,6) NOT NULL, total_price DECIMAL(14,6) NOT NULL,
    link TEXT, note TEXT, status VARCHAR(32) DEFAULT 'pending' NOT NULL,
    completed_qty INTEGER, refund_amount DECIMAL(14,6) DEFAULT 0.0 NOT NULL,
    group_message_id BIGINT, admin_note TEXT,
    created_at TIMESTAMP DEFAULT NOW() NOT NULL, updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_tg          ON users(telegram_id);
CREATE INDEX IF NOT EXISTS ix_users_banned       ON users(is_banned);
CREATE INDEX IF NOT EXISTS ix_tx_user_status     ON transactions(user_id, status);
CREATE INDEX IF NOT EXISTS ix_tx_created         ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_orders_user_status ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS ix_orders_api         ON orders(api_order_id);
CREATE INDEX IF NOT EXISTS ix_vc_tg              ON verification_codes(telegram_id, is_used);
CREATE INDEX IF NOT EXISTS ix_panels_active      ON panels(is_active, order_index);
CREATE INDEX IF NOT EXISTS ix_pcat_panel         ON panel_categories(panel_id, is_active);
CREATE INDEX IF NOT EXISTS ix_psvc_cat           ON panel_services(category_id, is_active);
CREATE INDEX IF NOT EXISTS ix_porder_user        ON panel_orders(user_id);
CREATE INDEX IF NOT EXISTS ix_porder_panel       ON panel_orders(panel_id, status);
CREATE INDEX IF NOT EXISTS ix_porder_created     ON panel_orders(created_at DESC);
CREATE INDEX IF NOT EXISTS ix_adm_key            ON admin_settings(key);
INSERT INTO admin_settings (key, value) VALUES
    ('bot_name','SMM Panel'),('welcome_message','خوش آمدید! 👋'),
    ('smm_markup_percent','20'),('smm_panel_title','🚀 پنل SMM'),('smmpass_api_key',''),
    ('min_deposit','1'),('max_deposit','1000'),
    ('backup_interval_hours','1'),('backup_auto_enabled','1'),
    ('backup_group_id',''),('last_backup_time',''),('last_backup_size',''),('last_backup_status',''),
    ('show_user_id_in_orders','1')
ON CONFLICT (key) DO NOTHING;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='referred_by')
    THEN ALTER TABLE users ADD COLUMN referred_by INTEGER REFERENCES users(id); END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='api_order_id')
    THEN ALTER TABLE orders ADD COLUMN api_order_id VARCHAR(64); END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='updated_at')
    THEN ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP DEFAULT NOW(); END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='orders' AND column_name='panel_name')
    THEN ALTER TABLE orders ADD COLUMN panel_name VARCHAR(64); END IF;
END $$;
