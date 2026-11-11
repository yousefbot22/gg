-- Migration: one-time password support
-- التاريخ: 2026-11-11

CREATE TABLE IF NOT EXISTS groups (
    group_id TEXT PRIMARY KEY,
    tier_name TEXT NOT NULL,
    password_hash TEXT NOT NULL UNIQUE,
    max_users INTEGER NOT NULL,
    members_count INTEGER NOT NULL DEFAULT 0,
    completed_count INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_one_time INTEGER NOT NULL DEFAULT 0,
    used_by_user_id INTEGER NULL,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS group_members (
    group_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TIMESTAMP NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_groups_password_hash
    ON groups(password_hash);

CREATE INDEX IF NOT EXISTS idx_group_members_user
    ON group_members(user_id);