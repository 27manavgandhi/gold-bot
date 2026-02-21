import json
import os
from cryptography.fernet import Fernet

KEY_FILE = "data/key.key"
ACCOUNTS_FILE = "data/accounts.json"

def generate_key():
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)

def load_key():
    return open(KEY_FILE, "rb").read()

def encrypt(data):
    f = Fernet(load_key())
    return f.encrypt(data.encode()).decode()

def decrypt(data):
    f = Fernet(load_key())
    return f.decrypt(data.encode()).decode()

def save_account(name, login, password, server):
    if not os.path.exists(KEY_FILE):
        generate_key()

    account = {
        "login": encrypt(login),
        "password": encrypt(password),
        "server": encrypt(server)
    }

    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, "r") as f:
            accounts = json.load(f)
    else:
        accounts = {}

    accounts[name] = account

    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, indent=4)

def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return {}

    with open(ACCOUNTS_FILE, "r") as f:
        accounts = json.load(f)

    decrypted = {}
    for name, acc in accounts.items():
        decrypted[name] = {
            "login": decrypt(acc["login"]),
            "password": decrypt(acc["password"]),
            "server": decrypt(acc["server"])
        }

    return decrypted