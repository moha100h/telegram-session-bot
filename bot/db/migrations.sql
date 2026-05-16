-- SMM Panel Database Schema
-- Run once to initialize the database

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    phone VARCHAR(30),
    balance DECIMAL(10,4) DEFAULT 0,
    is_banned BOOLEAN DEFAULT FALSE,
    referral_code VARCHAR(20) UNIQUE,
    referral_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    role VARCHAR(50) DEFAULT 'admin',
    permissions TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    type VARCHAR(50) NOT NULL,
    amount DECIMAL(10,4) NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    method VARCHAR(50),
    tx_hash VARCHAR(255),
    wallet_address VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    service_id INTEGER NOT NULL,
    service_name VARCHAR(255) NOT NULL,
    link TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    charge DECIMAL(10,4) NOT NULL,
    cost DECIMAL(10,4),
    status VARCHAR(20) DEFAULT 'pending',
    start_count INTEGER,
    remains INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL,
    code VARCHAR(10) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admin_settings (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    description TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS ix_users_is_banned ON users(is_banned);
CREATE INDEX IF NOT EXISTS ix_tx_user_status ON transactions(user_id, status);
CREATE INDEX IF NOT EXISTS ix_order_user_status ON orders(user_id, status);
CREATE INDEX IF NOT EXISTS ix_vc_tg_used ON verification_codes(telegram_id, is_used);

-- Default settings
INSERT INTO admin_settings (key, value, description) VALUES
    ('smm_markup_percent', '20',        'Markup % added to SMMPass prices for users'),
    ('min_deposit',        '1',         'Minimum deposit amount (USD)'),
    ('max_deposit',        '1000',      'Maximum deposit amount (USD)'),
    ('usdt_trc20_wallet',  '',          'USDT TRC20 wallet address'),
    ('usdt_erc20_wallet',  '',          'USDT ERC20 wallet address'),
    ('ton_wallet',         '',          'TON wallet address'),
    ('trx_wallet',         '',          'TRX wallet address'),
    ('support_username',   '',          'Support Telegram username'),
    ('bot_name',           'SMM Panel', 'Bot display name')
ON CONFLICT (key) DO NOTHING;
