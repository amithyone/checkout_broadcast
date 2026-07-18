-- Checkout Broadcast terminal registry (MySQL)
-- Run on check-outpay.com checkout Laravel database

CREATE TABLE IF NOT EXISTS broadcast_terminals (
    terminal_id VARCHAR(64) PRIMARY KEY,
    signing_key VARCHAR(256) NOT NULL,
    merchant_name VARCHAR(128) NOT NULL,
    bank_name VARCHAR(64) NOT NULL,
    bank_name_hash VARCHAR(128) NOT NULL,
    masked_account_suffix VARCHAR(16) NOT NULL,
    account_number VARCHAR(10) NULL,
    recipient_bank_code VARCHAR(6) NULL,
    business_id BIGINT UNSIGNED NULL,
    active TINYINT(1) NOT NULL DEFAULT 1,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    INDEX idx_broadcast_terminals_business (business_id)
);

CREATE TABLE IF NOT EXISTS broadcast_used_sessions (
    session_uuid CHAR(36) PRIMARY KEY,
    terminal_id VARCHAR(64) NOT NULL,
    used_at BIGINT NOT NULL,
    INDEX idx_broadcast_sessions_terminal (terminal_id),
    CONSTRAINT fk_broadcast_sessions_terminal
        FOREIGN KEY (terminal_id) REFERENCES broadcast_terminals(terminal_id)
);
