"""
account_manager.py
Manages multiple MT5 accounts with Fernet-encrypted credential storage.
Supports demo accounts where password may be provided via email from broker.
"""

import json
import os
from typing import Optional

from cryptography.fernet import Fernet

from config import ACCOUNTS_FILE, KEY_FILE
from logger import logger


def _load_or_create_key() -> Fernet:
    """Load existing encryption key or generate and save a new one."""
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            key = f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        logger.info("New encryption key generated.")
    return Fernet(key)


def _load_accounts_raw() -> dict:
    """Load the raw (encrypted values) accounts JSON file."""
    if not os.path.exists(ACCOUNTS_FILE):
        return {}
    with open(ACCOUNTS_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def _save_accounts_raw(data: dict) -> None:
    """Persist the accounts dict to disk."""
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_account(alias: str, login: int, password: str, server: str) -> None:
    """
    Encrypt and store a new MT5 account.
    alias    – user-friendly nickname for selection
    login    – MT5 account number (integer)
    password – MT5 account password (from broker email for demo accounts)
    server   – MT5 broker server string (e.g. MetaQuotes-Demo)
    """
    fernet = _load_or_create_key()
    accounts = _load_accounts_raw()

    encrypted_password = fernet.encrypt(password.encode()).decode()
    encrypted_server = fernet.encrypt(server.encode()).decode()

    accounts[alias] = {
        "login": login,
        "password": encrypted_password,
        "server": encrypted_server,
    }
    _save_accounts_raw(accounts)
    logger.info(f"Account '{alias}' saved (login={login}).")


def list_accounts() -> list[str]:
    """Return a list of all saved account aliases."""
    return list(_load_accounts_raw().keys())


def get_account(alias: str) -> Optional[dict]:
    """
    Decrypt and return account credentials for the given alias.
    Returns: {"login": int, "password": str, "server": str} or None.
    """
    fernet = _load_or_create_key()
    accounts = _load_accounts_raw()

    if alias not in accounts:
        logger.error(f"Account '{alias}' not found.")
        return None

    raw = accounts[alias]
    try:
        password = fernet.decrypt(raw["password"].encode()).decode()
        server = fernet.decrypt(raw["server"].encode()).decode()
    except Exception as exc:
        logger.error(f"Failed to decrypt account '{alias}': {exc}")
        return None

    return {
        "login": int(raw["login"]),
        "password": password,
        "server": server,
    }


def delete_account(alias: str) -> bool:
    """Remove a saved account. Returns True on success."""
    accounts = _load_accounts_raw()
    if alias not in accounts:
        return False
    del accounts[alias]
    _save_accounts_raw(accounts)
    logger.info(f"Account '{alias}' deleted.")
    return True