import csv
import os
from datetime import datetime

LOG_FILE = "data/trade_logs.csv"

def log_trade(result):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, "a", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["time", "order", "profit"])

        writer.writerow([datetime.now(), result.order, result.comment])