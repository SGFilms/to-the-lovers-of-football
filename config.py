import os
from dotenv import load_dotenv

# Загружаем переменные окружения, если есть файл .env
load_dotenv()

# Telegram
TOKEN = os.getenv("BOT_TOKEN", "ТВОЙ_ТОКЕН_ЗДЕСЬ")

# YooKassa
SHOP_ID = os.getenv("SHOP_ID", "ТВОЙ_SHOP_ID")
YK_API_KEY = os.getenv("YK_API_KEY", "ТВОЙ_SECRET_KEY")

# Email settings
SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT = 587
SMTP_USER = os.getenv("SMTP_USER", "stas.golovanov.07@mail.ru")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "M1qvmiFTuBM7n1Yr3dJg")
TARGET_EMAIL = "tothefootballers@gmail.com"

# DB
DB_NAME = "users.db"