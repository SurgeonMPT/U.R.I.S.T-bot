import os
from datetime import datetime, timedelta

BOT_TOKEN = "8677231360:AAH6hdCpqqVquWkHJLSRMBK_g_tLDLxH_j0"

# Путь к общей базе данных с веб-сайтом.
# По умолчанию ищет data/urist.db рядом с папкой tg-bot (../U.R.I.S.T WEB/data/urist.db).
# Можно переопределить переменной окружения URIST_DB_PATH.
_default_db = 'urist.db'

DB_NAME = os.environ.get('URIST_DB_PATH', _default_db)

# Рабочие часы юриста
AVAILABLE_TIMES = [
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "15:00",
    "16:00",
    "17:00",
]

# На сколько дней вперёд открываем запись
DAYS_AHEAD = 7


def get_available_dates() -> list[str]:
    today = datetime.now().date()
    dates = []
    for i in range(DAYS_AHEAD):
        day = today + timedelta(days=i)
        dates.append(day.strftime("%Y-%m-%d"))
    return dates
