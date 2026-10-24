import os

from debate.pg.db import asyncpg_url, normalize_url, psycopg_dsn, psycopg_sa_url


def test_jdbc_url_without_credentials_gets_db_user_and_password(monkeypatch):
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", "p@ss/word")
    u = normalize_url("jdbc:postgresql://db.example.rds.amazonaws.com:5432/tangent")
    assert u.startswith("postgresql://app:p%40ss%2Fword@db.example.rds.amazonaws.com:5432/tangent")
    assert "sslmode=require" in u


def test_local_hosts_stay_without_ssl_and_explicit_ssl_is_kept(monkeypatch):
    monkeypatch.delenv("DB_USER", raising=False)
    assert "ssl" not in normalize_url("postgresql://u:p@localhost:5432/d")
    assert "sslmode=verify-full" in normalize_url("postgresql://u:p@remote/d?sslmode=verify-full")


def test_driver_urls_and_checkpointer_dsn_carry_ssl(monkeypatch):
    monkeypatch.delenv("DB_USER", raising=False)
    raw = "postgresql://u:p@remote.example.com/d"
    assert asyncpg_url(raw).startswith("postgresql+asyncpg://") and "ssl=require" in asyncpg_url(raw)
    assert psycopg_sa_url(raw).startswith("postgresql+psycopg://") and "sslmode=require" in psycopg_sa_url(raw)
    dsn = psycopg_dsn(raw)
    assert "sslmode=require" in dsn and "search_path" in dsn
