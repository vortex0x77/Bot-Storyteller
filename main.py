import os
import sqlite3
from datetime import datetime, timedelta, time
import logging
import pytz
from openai import OpenAI
import asyncio
import re
import asyncio
from telegram.error import TimedOut, NetworkError
import requests
import json
import Config
import uuid
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, JobQueue
)

# ==================== Конфигурация ====================
TELEGRAM_TOKEN = Config.TELEGRAM
OPENAI_API_KEY = Config.OPENAI_KEY
# ЮKassa настройки
YUKASSA_SHOP_ID = Config.YUKASSA_SHOP_ID  # Замените на ваш shop_id от ЮKassa
YUKASSA_SECRET_KEY = Config.YUKASSA_SECRET_KEY  # Замените на ваш секретный ключ от ЮKassa
YUKASSA_API_URL = "https://api.yookassa.ru/v3/payments"

ADMIN_ID = Config.ADMIN_ID

# Список тестеров (ID пользователей, которые могут бесплатно создавать сказки)
TESTER_IDS = [
    1968139479,
    5952409238
]

# Московская временная зона
MSK_TZ = pytz.timezone('Europe/Moscow')

TARIFFS = {
    "week": {"price": 199, "stories": 10, "duration_days": 7},
    "month": {"price": 399, "stories": 40, "duration_days": 30},
    "year": {"price": 3990, "stories": 365, "duration_days": 365}
}
FREE_LIMIT = 1

MORALS = [
    "Дружба важнее всего",
    "Смелость помогает преодолеть страх",
    "Всегда верь в себя"
]

THEMES = [
    "🪄 Магия", "🚀 Космос", "👻 Страхи", "🧸 Игрушки",
    "🍭 Еда", "⏳ Сны и Время", "🏗 Стройки", "🌳 Природа",
    "🧠 Изобретения", "✍️ Своя"
]

# Сокращенные ID для тем (для callback_data)
THEME_IDS = {
    "🪄 Магия": "magic",
    "🚀 Космос": "space", 
    "👻 Страхи": "fears",
    "🧸 Игрушки": "toys",
    "🍭 Еда": "food",
    "⏳ Сны и Время": "dreams",
    "🏗 Стройки": "build",
    "🌳 Природа": "nature",
    "🧠 Изобретения": "invent",
    "✍️ Своя": "custom"
}

# Обратный словарь для получения темы по ID
ID_TO_THEME = {v: k for k, v in THEME_IDS.items()}

# Обновленные шаблоны сюжетов с короткими ID
PLOT_TEMPLATES = {
    "magic": {
        "princess": "Принцесса забыла своё имя и теперь думает, что она капуста. Только смелый герой сможет спасти её и напомнить, кто она есть!",
        "dragon": "Этот дракон чихает огнём и каждый раз сжигает свои носки! Нужно помочь ему перестать портить свой гардероб — или победить его, если он слишком разбушуется.",
        "tournament": "Великий турнир волшебников, где даже жюри состоит из пельменей! Пройдёшь ли ты все заколдованные испытания?",
        "spell": "В этом мире одно важное заклинание спряталось и отказывается работать. Его надо найти и уговорить вернуться к волшебникам!",
        "school": "Школу магии кто-то превратил в огромный блин! Сможешь ли ты вернуть её обратно?",
        "castle": "Замок превратился в гигантское мороженое и начал таять. Герою нужно спасти его прежде, чем он растает!",
        "teacher": "Учитель случайно телепортировался в старый тапок. Его надо срочно вытащить обратно!",
        "witch": "Ведьма прикинулась кексом и прячется среди десертов. Сумеешь её разоблачить?"
    },
    "space": {
        "candy": "Добраться до далёкой планеты, где маршмеллоу устроили бунт, и всё вокруг прилипает! Тебе предстоит их остановить.",
        "race": "Оседлать огромный астероид и устроить настоящие гонки вокруг чёрной дыры — рискнёшь?",
        "robot": "Твой робот-друг пропал и теперь живёт с пылесосами в далёком космосе. Придётся его выручать!",
        "king": "Этот король запретил всем прыгать на луне. Тебе придётся сразиться с ним, чтобы вернуть веселье космонавтам.",
        "rocket": "Собери свою собственную ракету из старого холодильника и отправляйся к далёкой звезде!",
        "mars": "На Марсе марсиане случайно застряли в банке с вареньем. Кто, если не ты, поможет им выбраться?",
        "planet": "Ты оказался на планете, где всё вверх ногами. Сможешь найти дорогу домой?",
        "donut": "Инопланетный пончик всех липко обнимает и не отпускает! Надо его остановить, пока не задушил всех своей сладостью."
    },
    "fears": {
        "monster": "Монстр под кроватью оказывается очень боится щекотки! Сумеешь его подружить и перестать бояться самому?",
        "snore": "В этом доме живёт настоящий храп — и он не даёт спать никому. Нужно пройти через дом, не разбудив его!",
        "spider": "Этот паук прячет все носки и смеётся. Пора положить конец его проделкам!",
        "cat": "Маленький кот застрял в страшной коробке, которая пугает всех громким «Бууу!». Поможешь его спасти?",
        "light": "Этот светлячок светит только тогда, когда кто-то пукает! С его помощью можно осветить самый тёмный угол.",
        "doubt": "Монстр Сомнения шепчет: «Ты не сможешь». Нужно его прогнать и поверить в себя!",
        "city": "В этом городе все боятся говорить вслух, и всё только шепчет. Сможешь найти там друзей и разгадать тайну?",
        "closet": "Каждую ночь там шуршит что-то страшное, а оказалось — это Трусишкин-Одеяло! Выясни, что он хочет."
    },
    "toys": {
        "rock": "Твоя любимая игрушка сбежала и теперь даёт рок-концерты! Поможешь её вернуть домой?",
        "nose": "У плюшевого медведя потерялся нос — а теперь он стал компасом! Надо его найти и вернуть на место.",
        "city": "На игрушечный город напали злые тапки. Сможешь всех спасти?",
        "magic": "Эта игрушка ломается и превращает всех в пиццу! Срочно почини её.",
        "soldiers": "Армия солдатиков уснула прямо на посту. Нужно их разбудить, пока не случилась беда.",
        "lego": "Лего-герою не хватает кусочка — буквально! Поможешь ему найти его?",
        "box": "Все игрушки исчезли из коробки, остался только сыр. Разберись, куда они делись!",
        "spring": "Злая Пружинка заставляет всех танцевать без остановки. Пора с ней покончить!"
    },
    "food": {
        "queen": "Королева Конфета в плену в замке Леденцов, и Слюнявый Великан уже идёт за ней! Спасёшь её?",
        "jelly": "Желе-монстр украл все ложки! Как же теперь есть десерт? Надо остановить его!",
        "rain": "Без клубничного дождя земляника не растёт. Нужно вернуть его в мир сладостей!",
        "soup": "Говорят, есть суп, который заставляет летать. Но его рецепт куда-то пропал…",
        "cake": "Этот торт дразнится кремовыми шутками и всех обижает. Перепеки его по-доброму!",
        "marsh": "Зефирные воины заперты в холодильной темнице. Освободи их!",
        "bridge": "Через Лава-Кетчуп не перейти без моста из спагетти. Поможешь построить?",
        "carrot": "Суп заколдовал маму и превратил её в морковку! Пора её вернуть!"
    },
    "dreams": {
        "clock": "Эти странные часы начинают день с ужина! Надо их починить, пока всё не запуталось.",
        "snail": "Твой друг застрял в сне, где все двигаются, как улитки. Поможешь ему выбраться?",
        "repeat": "Повторяшка превращает каждый день в одинаковый. Разорвёшь это заколдованное кольцо?",
        "pillow": "В лабиринте снов спрятана подушка-хранитель. Только она умеет показывать путь назад.",
        "dreamer": "Сновидца поймала ловушка Забвения — без него мир снов исчезнет!",
        "toy": "Где-то в сновидении спряталась твоя любимая игрушка. Ты сможешь её найти?",
        "alarm": "Этот будильник разрушает все сны и орёт \"Подъём!\". Надо его успокоить!",
        "funny": "Придумай такой смешной и радостный сон, чтобы спасти весь мир от скуки."
    },
    "build": {
        "bridge": "Мост из лего развалился, а по нему должны пробегать поезда. Срочно чиним!",
        "crane": "Этот забывчивый кран постоянно теряет дома и путает этажи. Надо его остановить!",
        "house": "Огромный пингвин хочет уютный дом — давай поможем ему с планировкой!",
        "excavator": "Экскаватор застрял прямо в куче пельменей. Вытащишь его?",
        "rainbow": "Изобрести машину, которая превращает мусор в радугу — крутая миссия!",
        "tunnel": "Построить подземный путь, чтобы сбежать на пикник. Приключение гарантировано!",
        "elevator": "Лифт превратился в портал в джунгли и не возвращает людей. Надо разобраться!",
        "tower": "Башня, уходящая прямо в облака. Кто сможет её достроить до конца?"
    },
    "nature": {
        "ant": "Муравей-архитектор строил город, но огромная лужа-цунами смыла всё! Поможешь его спасти?",
        "butterfly": "Маленькая бабочка боится летать высоко. Сумеешь её научить не бояться?",
        "mosquito": "Этот коварный комар сосёт не кровь, а мечты. Надо остановить его, пока он не выпил вдохновение у всех!",
        "forest": "Деревья в этом лесу ходят, шепчут сказки и прячут путь. Сумеешь выбраться?",
        "owl": "Маленький совёнок потерял своё гнездо, и остался только фонарик. Нужно его найти!",
        "bugs": "Твои друзья — жуки. Им нужен новый дом. Построишь?",
        "snails": "Устроим безумные гонки на улитках прямо по каплям росы! Готов к мокрому безумию?",
        "bee": "Пчела-королева уснула прямо в цветке. Без неё ульи не работают! Пора её будить!"
    },
    "invent": {
        "invisible": "Невидимка страдает — у него чешется спина! Придумай для него специальную чешущую машину.",
        "slippers": "В лаборатории всё пошло не так — тапки ожили и ведут себя, как гении зла! Надо спасать учёных.",
        "brush": "Полёт на зубной щётке — не шутка! Твоя цель — шоколадная планета. Сможешь долететь?",
        "alarm": "Этот будильник поёт песни… голосом кота. Построй его и проверь, проснутся ли все.",
        "button": "Изобрети кнопку, которая включает хорошее настроение — в любой момент!",
        "helmet": "Шлем случайно стал превращать мысли в пельмени. Срочно исправить, пока не стало вкусно навсегда.",
        "fridge": "Этот холодильник мечтает стать певцом. Сумеешь поддержать его мечту и подружиться с ним?",
        "umbrella": "Придумай зонт, который создаёт радугу, когда тебе грустно. Он нужен всему миру!"
    }
}

# Названия сюжетов для отображения
PLOT_NAMES = {
    "magic": {
        "princess": "🧝‍♀️ Спасти принцессу",
        "dragon": "🐉 Победить дракона", 
        "tournament": "🧙 Турнир волшебников",
        "spell": "✨ Найти заклинание",
        "school": "🏫 Спасти школу магии",
        "castle": "🏰 Расколдовать замок",
        "teacher": "👨‍🏫 Вернуть учителя",
        "witch": "🧁 Поймать ведьму"
    },
    "space": {
        "candy": "🍭 Планета сладостей",
        "race": "☄️ Гонки на астероиде",
        "robot": "🤖 Найти робота",
        "king": "🪐 Победить Короля Метеоритов",
        "rocket": "🚀 Построить ракету",
        "mars": "🛸 Спасти марсиан",
        "planet": "🌌 Вернуться с планеты",
        "donut": "🍩 Победить пончика"
    },
    "fears": {
        "monster": "👾 Подружиться с монстром",
        "snore": "💤 Дом храпа",
        "spider": "🕷 Победить Паука-Шутника",
        "cat": "🐱 Спасти кота",
        "light": "🔦 Найти светлячка",
        "doubt": "😈 Победить Сомнения",
        "city": "🏙 Пройти город шёпотов",
        "closet": "👻 Тайна шороха в шкафу"
    },
    "toys": {
        "rock": "🎸 Вернуть рок-звезду",
        "nose": "🧭 Нос медведя",
        "city": "👞 Спасти город",
        "magic": "🍕 Починить игрушку",
        "soldiers": "🪖 Разбудить солдатиков",
        "lego": "🧩 Найти кусочек",
        "box": "📦 Вернуть коробку",
        "spring": "🌀 Побороть Пружинку"
    },
    "food": {
        "queen": "🍬 Спасти королеву",
        "jelly": "🍮 Победить Желе-монстра",
        "rain": "🍓 Вернуть дождь",
        "soup": "🍲 Найти суп",
        "cake": "🎂 Перепечь торт",
        "marsh": "🍡 Освободить зефиры",
        "bridge": "🍝 Построить мост",
        "carrot": "🥕 Спасти маму-морковку"
    },
    "dreams": {
        "clock": "⏰ Починить часы",
        "snail": "🐌 Освободить друга",
        "repeat": "🔁 Победить Повторяшку",
        "pillow": "🛌 Найти подушку",
        "dreamer": "🌠 Спасти Сновидца",
        "toy": "🧸 Найти игрушку",
        "alarm": "📢 Остановить будильник",
        "funny": "😂 Придумать сон"
    },
    "build": {
        "bridge": "🧩 Починить мост",
        "crane": "🏗 Победить Крана",
        "house": "🏠 Построить дом",
        "excavator": "🚜 Спасти экскаватор",
        "rainbow": "🌈 Создать машину",
        "tunnel": "🕳 Вырыть ход",
        "elevator": "🛗 Освободить лифт",
        "tower": "☁️ Построить башню"
    },
    "nature": {
        "ant": "🐜 Спасти муравья",
        "butterfly": "🦋 Помочь бабочке",
        "mosquito": "🦟 Победить комара",
        "forest": "🌲 Пройти лес",
        "owl": "🦉 Найти гнездо",
        "bugs": "🏡 Построить дом жукам",
        "snails": "🐌 Гонки на улитках",
        "bee": "🐝 Разбудить пчелу"
    },
    "invent": {
        "invisible": "🤖 Машина для невидимки",
        "slippers": "🩴 Ожившие тапки",
        "brush": "🪥 Реактивная щётка",
        "alarm": "🎵 Будильник-кот",
        "button": "😊 Кнопка настроения",
        "helmet": "🧠 Шлем-пельменемёт",
        "fridge": "🧊 Холодильник-певец",
        "umbrella": "🌈 Зонт радуги"
    }
}

# ==================== Логирование ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== ЮKassa API ====================
def create_yukassa_payment(amount, description, user_id, tariff):
    """Создание платежа через ЮKassa"""
    try:
        # Генерируем уникальный идентификатор платежа
        idempotence_key = str(uuid.uuid4())
        
        # Данные для создания платежа
        payment_data = {
            "amount": {
                "value": str(amount),
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": f"https://t.me/fairytales_skazki_bot"  # Замените на ваш бот
            },
            "capture": True,
            "description": description,
            "metadata": {
                "user_id": str(user_id),
                "tariff": tariff,
                "bot_payment": "true"
            }
        }
        
        # Заголовки для запроса
        headers = {
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json"
        }
        
        # Отправляем запрос к ЮKassa
        response = requests.post(
            YUKASSA_API_URL,
            json=payment_data,
            headers=headers,
            auth=(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY)
        )
        
        if response.status_code == 200:
            payment_info = response.json()
            
            # Сохраняем информацию о платеже в базу данных
            save_payment_info(
                payment_info["id"],
                user_id,
                tariff,
                amount,
                payment_info["status"]
            )
            
            return payment_info
        else:
            logger.error(f"ЮKassa API error: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error creating ЮKassa payment: {str(e)}")
        return None

def save_payment_info(payment_id, user_id, tariff, amount, status):
    """Сохранить информацию о платеже в базу данных"""
    try:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        
        # Сохраняем платеж
        c.execute("""INSERT OR REPLACE INTO payments 
                     (id, user_id, tariff, amount, status, created_at, updated_at) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (payment_id, user_id, tariff, amount, status, 
                   datetime.now().isoformat(), datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Payment info saved: {payment_id}")
        
    except Exception as e:
        logger.error(f"Error saving payment info: {str(e)}")

def check_payment_status(payment_id):
    """Проверить статус платежа в ЮKassa"""
    try:
        response = requests.get(
            f"{YUKASSA_API_URL}/{payment_id}",
            auth=(YUKASSA_SHOP_ID, YUKASSA_SECRET_KEY)
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error checking payment status: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return None

def update_payment_status(payment_id, status):
    """Обновить статус платежа в базе данных"""
    try:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("UPDATE payments SET status = ?, updated_at = ? WHERE id = ?",
                  (status, datetime.now().isoformat(), payment_id))
        conn.commit()
        conn.close()
        logger.info(f"Payment status updated: {payment_id} -> {status}")
    except Exception as e:
        logger.error(f"Error updating payment status: {str(e)}")

def activate_subscription(user_id, tariff):
    """Активировать подписку пользователя"""
    try:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        
        # Вычисляем дату окончания подписки
        end_date = datetime.now() + timedelta(days=TARIFFS[tariff]["duration_days"])
        
        # Обновляем данные пользователя
        c.execute("""UPDATE users 
                     SET subscription = ?, subscription_end = ?, stories_used = 0, last_paid = ?
                     WHERE id = ?""",
                  (tariff, end_date.isoformat(), datetime.now().isoformat(), user_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Subscription activated for user {user_id}: {tariff}")
        
    except Exception as e:
        logger.error(f"Error activating subscription: {str(e)}")

# ==================== База данных ====================
def ensure_column_exists(conn, table, column, coltype):
    """Добавляет столбец в таблицу, если его нет"""
    c = conn.cursor()
    c.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in c.fetchall()]
    if column not in columns:
        # Для SQLite нужно использовать простые DEFAULT значения
        if "DEFAULT 0" in coltype:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} INTEGER DEFAULT 0")
        elif "DEFAULT CURRENT_TIMESTAMP" in coltype:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT")
        elif "DEFAULT 'UTC'" in coltype:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT DEFAULT 'UTC'")
        else:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
        conn.commit()
        logger.info(f"Column '{column}' added to table '{table}'.")

def load_prices_from_db():
    """Загрузить цены из базы данных при запуске"""
    global TARIFFS
    try:
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        
        # Проверяем, существует ли таблица настроек
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if not c.fetchone():
            conn.close()
            return
        
        # Загружаем сохраненные цены
        c.execute("SELECT key, value FROM settings WHERE key LIKE '%_price'")
        prices = c.fetchall()
        
        for key, value in prices:
            try:
                price_value = int(value)  # Приводим к int
                if key == "week_price":
                    TARIFFS["week"]["price"] = price_value
                elif key == "month_price":
                    TARIFFS["month"]["price"] = price_value
                elif key == "year_price":
                    TARIFFS["year"]["price"] = price_value
            except (ValueError, TypeError):
                logger.warning(f"Invalid price value for {key}: {value}")
                continue
        
        conn.close()
        logger.info("Prices loaded from database")
        
    except Exception as e:
        logger.error(f"Error loading prices from database: {str(e)}")
def init_db():
    """Инициализация базы данных с автоматической миграцией"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Создание таблиц
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            name TEXT,
            age INTEGER,
            subscription TEXT,
            subscription_end TEXT,
            stories_used INTEGER DEFAULT 0,
            last_paid TEXT,
            timezone TEXT DEFAULT 'UTC',
            is_blocked INTEGER DEFAULT 0,
            is_tester INTEGER DEFAULT 0,
            agreed_terms INTEGER DEFAULT 0  -- Столбец для согласия
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            content TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    
    # Таблица для шаблонов промптов
    c.execute("""CREATE TABLE IF NOT EXISTS prompts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT UNIQUE,
        content TEXT
    )""")
    
    # Таблица для настроек
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    
    # Таблица для платежей ЮKassa
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            tariff TEXT,
            amount INTEGER,
            status TEXT,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    
    # Автоматическая миграция столбцов
    ensure_column_exists(conn, "users", "is_blocked", "INTEGER DEFAULT 0")
    ensure_column_exists(conn, "users", "is_tester", "INTEGER DEFAULT 0")
    ensure_column_exists(conn, "users", "subscription", "TEXT")
    ensure_column_exists(conn, "users", "subscription_end", "TEXT")
    ensure_column_exists(conn, "users", "stories_used", "INTEGER DEFAULT 0")
    ensure_column_exists(conn, "users", "last_paid", "TEXT")
    ensure_column_exists(conn, "users", "timezone", "TEXT DEFAULT 'UTC'")
    ensure_column_exists(conn, "users", "agreed_terms", "INTEGER DEFAULT 0")
    ensure_column_exists(conn, "stories", "created_at", "TEXT")
    
    # Исправляем NULL значения и неправильные типы данных
    try:
        c.execute("UPDATE users SET stories_used = 0 WHERE stories_used IS NULL OR stories_used = ''")
        c.execute("UPDATE users SET is_blocked = 0 WHERE is_blocked IS NULL OR is_blocked = ''")
        c.execute("UPDATE users SET is_tester = 0 WHERE is_tester IS NULL OR is_tester = ''")
        c.execute("UPDATE users SET agreed_terms = 0 WHERE agreed_terms IS NULL OR agreed_terms = ''")
        c.execute("UPDATE users SET timezone = 'UTC' WHERE timezone IS NULL OR timezone = ''")
        
        # Исправляем неправильные значения в stories_used (если там попали строки)
        c.execute("""UPDATE users SET stories_used = 0 
                     WHERE typeof(stories_used) != 'integer' 
                     OR stories_used < 0""")
        
        # Обновляем created_at для существующих записей без этого поля
        c.execute("UPDATE stories SET created_at = datetime('now') WHERE created_at IS NULL OR created_at = ''")
        
    except Exception as e:
        logger.warning(f"Error fixing database values: {e}")
    
    # Добавляем дефолтные промпты
    c.execute("INSERT OR IGNORE INTO prompts (role, content) VALUES (?, ?)", 
              ("author", "Ты — волшебный детский сказочник. Создай увлекательную сказку."))
    c.execute("INSERT OR IGNORE INTO prompts (role, content) VALUES (?, ?)", 
              ("critic", "Ты — ребёнок 5-8 лет. Оцени сказку и улучши её."))
    c.execute("INSERT OR IGNORE INTO prompts (role, content) VALUES (?, ?)", 
              ("final", "Создай финальную версию сказки с учётом всех улучшений."))
    
    # Гарантируем, что админ есть и не заблокирован
    c.execute("""INSERT OR REPLACE INTO users 
                 (id, name, age, stories_used, is_blocked, is_tester, timezone, agreed_terms) 
                 VALUES (?, ?, ?, 0, 0, 0, 'UTC', 1)""",
              (ADMIN_ID, "Admin", 99))
    
    # Добавляем тестеров из списка
    for tester_id in TESTER_IDS:
        c.execute("""INSERT OR IGNORE INTO users 
                     (id, name, age, stories_used, is_blocked, is_tester, timezone, agreed_terms) 
                     VALUES (?, ?, ?, 0, 0, 1, 'UTC', 1)""",
                  (tester_id, f"Tester_{tester_id}", 25))
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

def has_agreed_terms(user_id):
    """Проверить, согласился ли пользователь с условиями"""
    user = get_user(user_id)
    if not user:
        return False
    return user.get('agreed_terms', 0) == 1

# ==================== Управление промптами ====================

async def show_prompt_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню управления промптами"""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    # Получаем текущие промпты из базы данных
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT role, content FROM prompts WHERE role IN ('author', 'critic')")
    prompts = dict(c.fetchall())
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("✍️ Редактировать промпт автора", callback_data="edit_prompt_author")],
        [InlineKeyboardButton("👶 Редактировать промпт критика", callback_data="edit_prompt_critic")],
        [InlineKeyboardButton("📋 Показать текущие промпты", callback_data="show_current_prompts")],
        [InlineKeyboardButton("🔄 Сбросить к дефолтным", callback_data="reset_prompts")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    author_preview = prompts.get('author', 'Не установлен')[:100] + "..." if len(prompts.get('author', '')) > 100 else prompts.get('author', 'Не установлен')
    critic_preview = prompts.get('critic', 'Не установлен')[:100] + "..." if len(prompts.get('critic', '')) > 100 else prompts.get('critic', 'Не установлен')
    
    text = f"""📝 *Управление промптами*

🤖 *Промпт автора (превью):*
{author_preview}

👶 *Промпт критика (превью):*
{critic_preview}

Выберите действие:"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_current_prompts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать текущие промпты полностью"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT role, content FROM prompts WHERE role IN ('author', 'critic')")
    prompts = dict(c.fetchall())
    conn.close()
    
    author_prompt = prompts.get('author', 'Не установлен')
    critic_prompt = prompts.get('critic', 'Не установлен')
    
    # Разбиваем длинные промпты на части
    text = f"""📋 *Текущие промпты*

🤖 **ПРОМПТ АВТОРА:**
{author_prompt[:2000]}"""
    
    if len(author_prompt) > 2000:
        text += "...\n\n*(промпт обрезан для отображения)*"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад к управлению", callback_data="admin_prompts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    # Отправляем промпт критика отдельным сообщением
    critic_text = f"""👶 **ПРОМПТ КРИТИКА:**
{critic_prompt[:2000]}"""
    
    if len(critic_prompt) > 2000:
        critic_text += "...\n\n*(промпт обрезан для отображения)*"
    
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=critic_text,
        parse_mode='Markdown'
    )
async def edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать редактирование промпта"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    prompt_type = query.data.split("_")[2]  # author или critic
    
    # Получаем текущий промпт
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT content FROM prompts WHERE role = ?", (prompt_type,))
    result = c.fetchone()
    current_prompt = result[0] if result else "Промпт не найден"
    conn.close()
    
    # Сохраняем информацию о редактируемом промпте
    context.user_data['editing_prompt'] = prompt_type
    context.user_data['prompt_step'] = 'waiting_prompt'
    
    prompt_names = {
        'author': 'автора сказок',
        'critic': 'детского критика'
    }
    
    text = f"""✍️ *Редактирование промпта {prompt_names.get(prompt_type, prompt_type)}*

**Текущий промпт:**
{current_prompt[:1500]}{'...' if len(current_prompt) > 1500 else ''}

**Инструкция:**
Отправьте новый промпт текстовым сообщением. Промпт будет полностью заменен на ваш текст.

Для отмены используйте команду /cancel"""
    
    keyboard = [[InlineKeyboardButton("❌ Отменить", callback_data="admin_prompts")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_prompt_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода нового промпта"""
    if not context.user_data.get('editing_prompt') or context.user_data.get('prompt_step') != 'waiting_prompt':
        return False  # Не наш случай
    
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав администратора")
        return True
    
    new_prompt = update.message.text.strip()
    prompt_type = context.user_data['editing_prompt']
    
    if len(new_prompt) < 10:
        await update.message.reply_text("❌ Промпт слишком короткий. Минимум 10 символов.")
        return True
    
    if len(new_prompt) > 10000:
        await update.message.reply_text("❌ Промпт слишком длинный. Максимум 10000 символов.")
        return True
    
    # Сохраняем новый промпт в базу данных
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO prompts (role, content) VALUES (?, ?)", 
              (prompt_type, new_prompt))
    conn.commit()
    conn.close()
    
    # Очищаем состояние
    context.user_data.pop('editing_prompt', None)
    context.user_data.pop('prompt_step', None)
    
    prompt_names = {
        'author': 'автора сказок',
        'critic': 'детского критика'
    }
    
    keyboard = [
        [InlineKeyboardButton("📝 Управление промптами", callback_data="admin_prompts")],
        [InlineKeyboardButton("🏠 Админ панель", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"✅ Промпт {prompt_names.get(prompt_type, prompt_type)} успешно обновлен!\n\n"
        f"Новый промпт будет использоваться для всех последующих сказок.",
        reply_markup=reply_markup
    )
    
    logger.info(f"Prompt {prompt_type} updated by admin {update.effective_user.id}")
    return True

async def reset_prompts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сбросить промпты к дефолтным значениям"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    # Дефолтные промпты
    default_author_prompt = f"""Ты — профессиональный детский сказочник с 20-летним опытом, лауреат международных конкурсов и создатель бестселлеров, которые читают на ночь дети по всему миру. 

Твои сказки отличаются особым детским юмором, неожиданными поворотами и живыми диалогами. Ты интуитивно понимаешь психологию детей 5-8 лет и знаешь, как удерживать их внимание. 

Представь, что ты работаешь в тандеме с группой детей 5-8 лет. Они подсказывают тебе самые интересные детали: какие монстры смешные, какие приключения захватывающие, какие помощники классные. Твоя задача - воплотить эти идеи в структурированную историю, сохраняя детскую непосредственность. 
 

Создай яркую, динамичную, персонализированную сказку длиной 3-5 страниц, которая будет развивать воображение ребёнка. 

🔹 Параметры:
Имя героя: {{child_name}}
Возраст: {{child_age}}
Основная тема: {{theme_name}}
Мораль: {{plot_description}}

🚀 Структура сказки: 

    Захватывающее начало (первые 2 абзаца):
    • Мощный триггер (портал, говорящее животное, загадочное письмо)
    • Немедленное погружение в действие
    • Первое знакомство с волшебным миром
     

🌈 Создание мира:
• Все объекты оживают и взаимодействуют
• Каждый элемент имеет свою уникальную особенность
• Мир полон звуков, запахов, движений и сюрпризов
• Включай комичные детали и абсурдные ситуации 

⚔️ Сюжетная линия:
• 2-3 основных испытания
• Чередование вызовов и помощников
• Неожиданные повороты событий
• Возможность для героя совершать ошибки и учиться на них 

🧙‍♂️ Персонажи:
• Уникальные способности и характеры
• Чёткая мотивация каждого персонажа
• Комические черты и особенности
• Естественные диалоги с юмором 

🧠 Взаимодействие с читателем:
• Прямые вопросы к читателю
• Предположения о возможных решениях
• Участие в принятии решений
• Элементы "умного юмора" 

✨ Финал:
• Возвращение героя с важным приобретением
• Магический элемент в завершении
• Открытый финал для продолжения приключений 

🎭 Особенности стиля:
• Живой разговорный язык
• Короткие динамичные предложения
• Множество диалогов
• Описания через действия
• Эмоциональная вовлечённость
• Абсурдный юмор
• Детская логика событий 

📚 Формат:
• Разделение на короткие главы
• Подзаголовки для каждой части
• Визуальные маркеры важных моментов 

Важные ограничения:
• Без морализаторства
• Без назидательности
• Без страшных или травматичных ситуаций
• Без сложных конфликтов
• Только положительные эмоции 

Создавай сказку так, будто рассказываешь её вечером перед сном, с живыми интонациями и искренним увлечением. Пусть каждая страница будит воображение и вызывает улыбку.
⚠️ ВАЖНО:   

    Начинай сказку сразу с повествования, без вводных фраз.  
    Пиши динамичную, смешную, волшебную историю с абсурдно-удивительным миром, запоминающимися персонажами и магическим финалом.  
    Строго избегай любых упоминаний насилия, страха, жестокости, сексуальных намёков или тем, не подходящих для детей 5–8 лет.  
    Делай текст лаконичным, разделяя на короткие главы с подзаголовками и эмодзи для акцента.  
    Включи мораль "{{moral}}" естественно, через завершающую фразу героя или событие.  
    В ответе — только готовая сказка без пояснений, технических пометок или лишних слов.  
    Убедись в безупречности грамматики и детской доступности языка.
     

Пример начала:
В мире, где реки текли из варенья, а горы смеялись, когда их щекотали облака, {{child_name}} обнаружил дверь в стволе баобаба. За ней прыгал кролик в очках, держащий в лапах карту, нарисованную светлячками. """


    default_critic_prompt = f"""Ты — ребёнок 5–8 лет, для которого писалась эта сказка. Ты любишь яркие, весёлые и захватывающие истории, полные волшебства, юмора и неожиданных поворотов. Вот текст сказки:

{{first_story}}

Прочитай её внимательно и представь, что ты — главный критик-ребёнок. Подумай, как сделать её ещё интереснее, живее и увлекательнее.

✨ Задачи:
1. Найди слабые места:  
   - Где стало скучно?  
   - Какие персонажи показались неинтересными или слишком предсказуемыми?  
   - Есть ли моменты, которые можно сделать смешнее, ярче или магичнее?  

2. Предложи улучшения:  
   - Добавь больше деталей, чтобы мир стал ещё волшебнее.  
   - Сделай диалоги живее и смешнее.  
   - Включи больше магии, игривых элементов и неожиданных поворотов.  
   - Усиль вовлечение: задай вопросы читателю, добавь моменты, где он может представлять себя на месте героя.  

3. Перепиши сказку, устранив все замечания:  
   - Сделай историю динамичной, эмоциональной и увлекательной.  
   - Добавь больше юмора, абсурда и магии.  
   - Убедись, что каждая страница вызывает улыбку или удивление.  
   - Проверь, чтобы все персонажи были уникальными и запоминающимися.  

🎯 Важно:   

    Никаких страшных, жестоких или взрослых тем — только доброе волшебство, дружелюбные персонажи и ситуации, от которых становится тепло и весело.  
    Все испытания героя решаются смекалкой, юмором или помощью друзей, никакого насилия, даже в шутку.  
    Если герой волнуется — это как перед каруселями, а не перед монстрами: «У {{child_name}} коленки дрожали, будто он проглотил живого комарика!»  
    Проверяй каждую фразу: «Могу ли я рассказать это бабушке, пока она укладывает меня спать?» Если нет — удаляй!  
    Только позитив: даже злодеи оказываются милыми чудаками (например, дракон, который боится щекотки облаками).  
    Нулевой намёк на реальные проблемы — только игра, магия и смех. Даже если герой теряет что-то, он находит в 10 раз больше радости («Потерял конфету? Зато нашёл радугу, которая прыгает через лужи!»).

Пример начала:
В мире, где реки текли из варенья, а горы смеялись, когда их щекотали облака, {{child_name}} обнаружил дверь в стволе баобаба. За ней прыгал кролик в очках, держащий в лапах карту, нарисованную светлячками. """


    # Сохраняем дефолтные промпты
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO prompts (role, content) VALUES (?, ?)", 
              ('author', default_author_prompt))
    c.execute("INSERT OR REPLACE INTO prompts (role, content) VALUES (?, ?)", 
              ('critic', default_critic_prompt))
    conn.commit()
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📝 Управление промптами", callback_data="admin_prompts")],
        [InlineKeyboardButton("🏠 Админ панель", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ Промпты сброшены к дефолтным значениям!\n\n"
        "Все новые сказки будут создаваться с использованием стандартных промптов.",
        reply_markup=reply_markup
    )
    
    logger.info(f"Prompts reset to default by admin {query.from_user.id}")

async def generate_story_with_custom_prompts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    theme_id = context.user_data.get('selected_theme')
    plot_id = context.user_data.get('selected_plot')
    plot_description = context.user_data.get('plot_description')
    child_name = context.user_data.get('child_name')
    child_age = context.user_data.get('child_age')
    moral = context.user_data.get('selected_moral')

    if theme_id == "custom":
        theme_name = context.user_data.get('custom_theme', 'Своя тема')
        plot_description = context.user_data.get('plot_description', 'Своя цель')
    else:
        theme_name = ID_TO_THEME.get(theme_id, "")
    
    if not all([theme_id, plot_id, child_name, child_age, moral]):
        try:
            await query.edit_message_text("❌ Не хватает данных для создания сказки")
        except:
            pass
        return
    
    # Показываем сообщение о генерации
    try:
        await query.edit_message_text("✨ Создаю вашу уникальную сказку...\n\nЭто может занять несколько минут.")
    except:
        pass
    
    try:
        # Получаем промпты из базы данных
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT role, content FROM prompts WHERE role IN ('author', 'critic')")
        prompts = dict(c.fetchall())
        conn.close()
        
        # Создаем клиент OpenAI с таймаутом
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            timeout=120.0  # Таймаут 2 минуты
        )
        
        # Формируем данные для промптов
        theme_name = ID_TO_THEME.get(theme_id, "")
        
        # ЭТАП 1: Создание сказки с кастомным промптом автора
        author_prompt_template = prompts.get('author', 'Создай детскую сказку.')
        
        # Добавляем данные к промпту автора
        full_author_prompt = f"""{author_prompt_template}

🔹 Данные:
Имя: {child_name}. Возраст: {child_age}. Тема: {theme_name}. Цель: {plot_description}.
Мораль: {moral}

Создай сказку с учетом этих данных. Обязательно включи мораль "{moral}" в конце сказки."""
        
        # Обновляем сообщение о прогрессе
        try:
            await query.edit_message_text("✨ Создаю черновик сказки...\n\n📝 Этап 1/2: Профессиональный сказочник работает...")
        except:
            pass
        
        # Генерируем первую версию сказки с таймаутом
        try:
            response1 = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Ты профессиональный детский сказочник с огромным опытом создания захватывающих историй для детей. ⚠️ ВАЖНО: Начинай сказку сразу с основного повествования. НЕ используй вводные фразы типа О, эта сказка очень классная..., Раз, два, три - сказка!, Жил-был... (если не является частью стиля конкретной сказки)."},
                        {"role": "user", "content": full_author_prompt}
                    ],
                    max_tokens=2000,
                    temperature=0.9
                ),
                timeout=90.0  # Таймаут 90 секунд для первого запроса
            )
        except asyncio.TimeoutError:
            raise Exception("Таймаут при создании первой версии сказки")
        
        first_story = response1.choices[0].message.content
        
        # ЭТАП 2: Редактирование сказки с кастомным промптом критика
        critic_prompt_template = prompts.get('critic', 'Улучши эту сказку.')
        
        full_critic_prompt = f"""{critic_prompt_template}

Вот текст сказки:
{first_story}"""
        
        # Обновляем сообщение о прогрессе
        try:
            await query.edit_message_text("✨ Улучшаю сказку...\n\n🎨 Этап 2/2: Детский редактор добавляет магию...")
        except:
            pass
        
        # Генерируем улучшенную версию сказки с таймаутом
        try:
            response2 = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": "Ты ребёнок 5-8 лет, который умеет делать сказки ещё более интересными и захватывающими для других детей.Убедись, что сказка НАЧИНАЕТСЯ сразу с основного действия или описания, БЕЗ вводных фраз от рассказчика (например, О, эта сказка очень классная...) "},
                        {"role": "user", "content": full_critic_prompt}
                    ],
                    max_tokens=2200,
                    temperature=0.7
                ),
                timeout=90.0  # Таймаут 90 секунд для второго запроса
            )
        except asyncio.TimeoutError:
            # Если второй этап не удался, используем первую версию
            logger.warning("Timeout in second stage, using first story version")
            final_story = first_story
        else:
            final_story = response2.choices[0].message.content
        
        # Создаем заголовок сказки
        plot_name = PLOT_NAMES.get(theme_id, {}).get(plot_id, "Приключение")
        story_title = f"{plot_name} - сказка для {child_name}"
        
        # Сохраняем сказку в базу данных
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("INSERT INTO stories (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, story_title, final_story, datetime.now().isoformat()))
        story_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Увеличиваем счетчик использованных сказок
        update_user_stories_count(user_id)
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
        # Отправляем сказку пользователю
        keyboard = [
            [InlineKeyboardButton("📚 Создать ещё сказку", callback_data="create_story")],
            [InlineKeyboardButton("📖 Мои сказки", callback_data="my_stories")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Разбиваем длинную сказку на части, если нужно
        if len(final_story) > 4000:
            # Отправляем заголовок
            try:
                await query.edit_message_text(f"✨ {story_title}\n\n{final_story[:4000]}...")
            except:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✨ {story_title}\n\n{final_story[:4000]}..."
                )
            
            # Отправляем продолжение
            remaining_content = final_story[4000:]
            while remaining_content:
                chunk = remaining_content[:4000]
                remaining_content = remaining_content[4000:]
                
                try:
                    if remaining_content:
                        await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)
                    else:
                        # Последняя часть с кнопками
                        await context.bot.send_message(
                            chat_id=query.message.chat_id, 
                            text=chunk,
                            reply_markup=reply_markup
                        )
                except Exception as e:
                    logger.error(f"Error sending story chunk: {e}")
                    break
        else:
            try:
                await query.edit_message_text(
                    f"✨ {story_title}\n\n{final_story}",
                    reply_markup=reply_markup
                )
            except:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"✨ {story_title}\n\n{final_story}",
                    reply_markup=reply_markup
                )
        
        logger.info(f"Story generated with custom prompts for user {user_id}: {story_title}")
        
    except Exception as e:
        logger.error(f"Error generating story with custom prompts: {str(e)}")
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data="create_story")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        error_message = "❌ Произошла ошибка при создании сказки."
        if "таймаут" in str(e).lower() or "timeout" in str(e).lower():
            error_message = "⏰ Создание сказки заняло слишком много времени. Попробуйте позже."
        
        try:
            await query.edit_message_text(error_message, reply_markup=reply_markup)
        except:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=error_message,
                reply_markup=reply_markup
            )


# ==================== Вспомогательные функции ====================
def filter_inappropriate_content(story_text):
    """Фильтрация неподходящего контента в сказках"""
    if not story_text:
        return story_text
    
    # Список неподходящих фраз и их замены
    inappropriate_phrases = {
        # Грубые выражения
        r'\bдурак\b': 'глупышка',
        r'\bидиот\b': 'забывашка',
        r'\bтупой\b': 'рассеянный',
        r'\bглупый\b': 'невнимательный',
        r'\bдебил\b': 'забывчивый',
        r'\bкретин\b': 'растеряшка',
        r'\bтупица\b': 'мечтатель',
        
        # Агрессивные выражения
        r'\bубью\b': 'остановлю',
        r'\bубить\b': 'остановить',
        r'\bзадушу\b': 'поймаю',
        r'\bзадушить\b': 'поймать',
        r'\bпобью\b': 'догоню',
        r'\bпобить\b': 'догнать',
        r'\bразобью\b': 'остановлю',
        r'\bразбить\b': 'остановить',
        
        # Неподходящие для детей темы
        r'\bпьяный\b': 'сонный',
        r'\bпьяная\b': 'сонная',
        r'\bвыпил\b': 'попил воды',
        r'\bвыпила\b': 'попила воды',
        r'\bкурит\b': 'дышит',
        r'\bкурить\b': 'дышать',
        
        # Страшные или пугающие фразы
        r'\bужасно\b': 'очень',
        r'\bстрашно\b': 'удивительно',
        r'\bкошмар\b': 'приключение',
        r'\bкровь\b': 'красная краска',
        r'\bкровавый\b': 'красный',
        
        # Негативные характеристики
        r'\bотвратительный\b': 'необычный',
        r'\bгадкий\b': 'странный',
        r'\bмерзкий\b': 'неприятный',
        r'\bпротивный\b': 'капризный',
        
        # Фразы из примера
        r'засмущала': 'удивила',
        r'грубовата': 'необычна',
        r'хитрющие': 'озорные',
        r'пошалить': 'поиграть',
    }
    
    # Применяем замены
    filtered_text = story_text
    for pattern, replacement in inappropriate_phrases.items():
        filtered_text = re.sub(pattern, replacement, filtered_text, flags=re.IGNORECASE)
    
    # Дополнительная проверка на общие неподходящие паттерны
    # Убираем слишком сложные или взрослые темы
    adult_patterns = [
        r'\b(алкоголь|наркотик|сигарет|табак)\w*\b',
        r'\b(смерть|умер|умирать|погиб)\w*\b',
        r'\b(развод|расстались|бросил|бросила)\w*\b',
    ]
    
    for pattern in adult_patterns:
        filtered_text = re.sub(pattern, 'приключение', filtered_text, flags=re.IGNORECASE)
    
    # Убираем излишне эмоциональные или негативные концовки
    negative_endings = [
        r'И больше они никогда не встречались\.?',
        r'И он навсегда исчез\.?',
        r'И никто его больше не видел\.?',
        r'Конец этой грустной истории\.?',
    ]
    
    for pattern in negative_endings:
        filtered_text = re.sub(pattern, 'И они жили долго и счастливо!', filtered_text, flags=re.IGNORECASE)
    
    # Добавляем позитивные элементы, если их нет
    if not any(word in filtered_text.lower() for word in ['счастлив', 'радост', 'весел', 'смех', 'улыбк']):
        # Если в сказке нет позитивных эмоций, добавляем их в конец
        if filtered_text.strip() and not filtered_text.strip().endswith('.'):
            filtered_text += '.'
        filtered_text += ' И все были очень счастливы!'
    
    return filtered_text

def add_child_friendly_ending(story_text, moral):
    """Добавляет детскую дружелюбную концовку к сказке"""
    if not story_text:
        return story_text
    
    # Проверяем, есть ли уже хорошая концовка
    good_endings = ['счастливо', 'радостно', 'весело', 'дружно', 'мирно']
    has_good_ending = any(ending in story_text.lower()[-200:] for ending in good_endings)
    
    if not has_good_ending:
        # Добавляем позитивную концовку
        if not story_text.strip().endswith('.'):
            story_text += '.'
        
        story_text += f'\n\nИ запомни: {moral}! ✨'
    
    return story_text

def get_user(user_id):
    """Получить пользователя из базы данных"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Получаем информацию о структуре таблицы
    c.execute("PRAGMA table_info(users)")
    columns_info = c.fetchall()
    column_names = [col[1] for col in columns_info]
    
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user_data = c.fetchone()
    conn.close()
    
    if not user_data:
        return None
    
    # Создаем словарь для удобного доступа к данным
    user_dict = {}
    for i, column_name in enumerate(column_names):
        if i < len(user_data):
            user_dict[column_name] = user_data[i]
    
    return user_dict

def is_user_blocked(user_id):
    """Проверить, заблокирован ли пользователь"""
    user = get_user(user_id)
    if not user:
        return False
    return user.get('is_blocked', 0) == 1

def is_user_tester(user_id):
    """Проверить, является ли пользователь тестером"""
    user = get_user(user_id)
    if not user:
        return False
    return user.get('is_tester', 0) == 1

def can_generate_story(user_id):
    """Проверить, может ли пользователь создавать сказки"""
    if is_user_blocked(user_id):
        return False, "Ваш аккаунт заблокирован"
    if not has_agreed_terms(user_id):
        return False, "Пожалуйста, пройдите согласие с условиями"

    user = get_user(user_id)
    if not user:
        return False, "Пользователь не найден"

    try:
        stories_used = int(user.get('stories_used', 0) or 0)
    except (ValueError, TypeError):
        stories_used = 0

    subscription = user.get('subscription')
    subscription_end = user.get('subscription_end')

    if subscription and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end)
            if datetime.now() < end_date:
                tariff = TARIFFS.get(subscription)
                if tariff and stories_used < tariff["stories"]:
                    return True, f"Подписка активна ({tariff['stories'] - stories_used} сказок осталось)"
        except Exception as e:
            logger.warning(f"Error parsing subscription_end: {e}")

    if stories_used < FREE_LIMIT:
        return True, f"Бесплатный лимит ({FREE_LIMIT - stories_used} сказок осталось)"

    return False, "Лимит исчерпан. Нужна подписка"
def update_user_stories_count(user_id):
    """Увеличить счетчик использованных сказок"""
    if is_user_tester(user_id):
        return  # Тестеры не тратят лимит
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Безопасно обновляем счетчик
    c.execute("UPDATE users SET stories_used = COALESCE(stories_used, 0) + 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_stats():
    """Получить статистику пользователей"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    try:
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        # Проверяем, существует ли столбец subscription_end
        c.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in c.fetchall()]
        
        if 'subscription_end' in columns:
            c.execute("SELECT COUNT(*) FROM users WHERE subscription IS NOT NULL AND subscription_end > datetime('now')")
            active_subscribers = c.fetchone()[0]
        else:
            active_subscribers = 0
        
        if 'is_blocked' in columns:
            c.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
            blocked_users = c.fetchone()[0]
        else:
            blocked_users = 0
        
        if 'is_tester' in columns:
            c.execute("SELECT COUNT(*) FROM users WHERE is_tester = 1")
            testers = c.fetchone()[0]
        else:
            testers = 0
        
        c.execute("SELECT COUNT(*) FROM stories")
        total_stories = c.fetchone()[0]
        
    except Exception as e:
        logger.error(f"Error getting user stats: {e}")
        total_users = 0
        active_subscribers = 0
        blocked_users = 0
        testers = 0
        total_stories = 0
    
    finally:
        conn.close()
    
    return {
        'total_users': total_users,
        'active_subscribers': active_subscribers,
        'blocked_users': blocked_users,
        'testers': testers,
        'total_stories': total_stories
    }
# ==================== Основные команды бота ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name

    # Проверяем, заблокирован ли пользователь
    if is_user_blocked(user_id):
        error_message = "❌ Ваш аккаунт заблокирован. Обратитесь к администратору."
        if update.callback_query:
            await update.callback_query.edit_message_text(error_message)
        else:
            await update.message.reply_text(error_message)
        return

    # Проверяем, новый ли пользователь
    user = get_user(user_id)
    is_new = False
    if not user:
        is_new = True
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (id, name) VALUES (?, ?)", (user_id, user_name))
        conn.commit()
        conn.close()

    # Текст приветствия
    welcome_text = f"""🌟 Добро пожаловать в мир сказок!
Я помогу создать персональную сказку специально для вас! 
✨ Что я умею:
• Создавать уникальные сказки по вашему выбору
• Адаптировать истории под возраст ребёнка
• Включать имя ребёнка в сказку
• Добавлять поучительную мораль
🎁 У вас есть {FREE_LIMIT} бесплатная сказка!"""

    # Отправляем приветствие только для новых пользователей или обычных сообщений
    if not update.callback_query:
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

# Для новых пользователей показываем соглашение
    if is_new and not update.callback_query:
        TERMS_MESSAGE = """🔒 Пожалуйста, прочитайте следующие условия использования:
🔗 [Политика обработки персональных данных](https://docs.google.com/document/d/1bQ8GPviklu2Titj2AFNER6hwJnHgI7hjJqI47oQW6wE/edit?usp=sharing)
🔗 [Оферта](https://docs.google.com/document/d/1JqirUs2KLvr-aRXRpXMqGNDP9-tHYvvh-e_uUub6mkY/edit?usp=sharing)
🔗 [Положение](https://docs.google.com/document/d/13F-qfLelERefRIewWwE9r9-GejgRW0wuUDytRMI81p8/edit?usp=sharing)

✅ Нажимая кнопку ниже, вы подтверждаете согласие с этими условиями и можете начать пользоваться ботом."""
        keyboard = [[InlineKeyboardButton("✅ Я согласен", callback_data="agree_terms")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(TERMS_MESSAGE, reply_markup=reply_markup, parse_mode='Markdown', disable_web_page_preview=True)
    else:
        # Если пользователь уже согласился или это callback, показываем главное меню
        await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать главное меню"""
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📚 Создать сказку", callback_data="create_story")],
        [InlineKeyboardButton("📖 Мои сказки", callback_data="my_stories")],
        [InlineKeyboardButton("💎 Подписка", callback_data="subscription")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🔧 Админ панель", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "Выберите действие:"
    
    # Проверяем, вызвана ли функция из callback query или из обычного сообщения
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)



async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    help_text = """🆘 Помощь

🌟 Как пользоваться ботом:

1️⃣ Нажмите "📚 Создать сказку"
2️⃣ Выберите тему сказки
3️⃣ Выберите сюжет
4️⃣ Укажите имя ребёнка и возраст
5️⃣ Получите уникальную сказку!

💎 Подписка даёт:
• Больше сказок в месяц
• Приоритетную обработку
• Новые темы и сюжеты

📞 Поддержка: @support_username"""
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup)

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода"""
    user_id = update.effective_user.id
    waiting_for = context.user_data.get('waiting_for')

    # Проверяем, заблокирован ли пользователь
    if is_user_blocked(user_id):
        await update.message.reply_text("❌ Ваш аккаунт заблокирован")
        return

    # Сначала проверяем обработку промптов (только для админа)
    if context.user_data.get('prompt_step') == 'waiting_prompt':
        if await handle_prompt_input(update, context):
            return  # Если промпт обработан, выходим

    # Обработка ввода пользовательской темы
    if waiting_for == 'custom_theme':
        custom_theme = update.message.text.strip()
        
        if len(custom_theme) < 3:
            await update.message.reply_text("❌ Тема слишком короткая. Попробуйте подробнее:")
            return
        
        if len(custom_theme) > 100:
            await update.message.reply_text("❌ Тема слишком длинная. Попробуйте покороче (до 100 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?]+$', custom_theme):
            await update.message.reply_text("❌ Тема содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        context.user_data['custom_theme'] = custom_theme
        context.user_data['waiting_for'] = 'custom_plot'
        
        await update.message.reply_text(
            f"✨ Отлично! Тема: «{custom_theme}»\n\n"
            "✍️ Теперь опишите цель или сюжет сказки:\n\n"
            "Например:\n"
            "• 'Главный герой находит волшебный камень'\n"
            "• 'Спасти принцессу от злого дракона'\n"
            "• 'Построить дом для лесных зверей'\n\n"
            "Напишите вашу идею:"
        )
        return

    # Обработка ввода пользовательского сюжета
    elif waiting_for == 'custom_plot':
        custom_plot = update.message.text.strip()
        
        if len(custom_plot) < 5:
            await update.message.reply_text("❌ Сюжет слишком короткий. Попробуйте подробнее:")
            return
        
        if len(custom_plot) > 200:
            await update.message.reply_text("❌ Сюжет слишком длинный. Попробуйте покороче (до 200 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?()]+$', custom_plot):
            await update.message.reply_text("❌ Сюжет содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        context.user_data['plot_description'] = custom_plot
        context.user_data['selected_plot'] = 'custom'
        context.user_data['waiting_for'] = 'name'
        
        # Показываем подтверждение и переходим к вводу имени
        keyboard = [
            [InlineKeyboardButton("✅ Да, продолжить", callback_data="confirm_custom_plot")],
            [InlineKeyboardButton("✏️ Изменить сюжет", callback_data="edit_custom_plot")],
            [InlineKeyboardButton("🔙 К выбору темы", callback_data="create_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📖 Ваша сказка:\n\n"
            f"🎭 Тема: {context.user_data.get('custom_theme', 'Своя тема')}\n"
            f"🎯 Сюжет: {custom_plot}\n\n"
            f"Продолжаем создание сказки?",
            reply_markup=reply_markup
        )
        return

    # Обработка ввода имени ребёнка
    elif waiting_for == 'name':
        child_name = update.message.text.strip()

        if len(child_name) < 1:
            await update.message.reply_text("❌ Имя не может быть пустым. Попробуйте ещё раз:")
            return

        if len(child_name) > 50:
            await update.message.reply_text("❌ Имя слишком длинное. Попробуйте короче:")
            return

        # Проверяем, что имя содержит только буквы и пробелы
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z\s\-]+$', child_name):
            await update.message.reply_text("❌ Имя должно содержать только буквы. Попробуйте ещё раз:")
            return

        context.user_data['child_name'] = child_name
        context.user_data['waiting_for'] = 'age'
        
        await update.message.reply_text(
            f"👶 Отлично! Главного героя зовут {child_name}.\n\n"
            "Сколько ему/ей лет? (Введите число от 0 до 80)"
        )
        return

    # Обработка ввода возраста
    elif waiting_for == 'age':
        age_text = update.message.text.strip()
        
        if not age_text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введите возраст числом (например, 5):")
            return
        
        age = int(age_text)
        if age < 0 or age > 80:
            await update.message.reply_text("❌ Возраст должен быть от 0 до 80 лет. Попробуйте ещё раз:")
            return
        
        context.user_data['child_age'] = age
        context.user_data['waiting_for'] = None
        
        # Переходим к выбору морали
        await show_moral_selection(update, context)
        return

    # Обработка ввода пользовательской морали
    elif waiting_for == 'custom_moral':
        custom_moral = update.message.text.strip()
        
        if len(custom_moral) < 5:
            await update.message.reply_text("❌ Мораль слишком короткая. Напишите хотя бы несколько слов:")
            return
        
        if len(custom_moral) > 200:
            await update.message.reply_text("❌ Мораль слишком длинная. Попробуйте покороче (до 200 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?()«»"]+$', custom_moral):
            await update.message.reply_text("❌ Мораль содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        # Сохраняем пользовательскую мораль
        context.user_data['selected_moral'] = custom_moral
        context.user_data['waiting_for'] = None
        
        # Показываем подтверждение и начинаем генерацию
        keyboard = [
            [InlineKeyboardButton("✅ Да, создавать сказку", callback_data="confirm_custom_moral")],
            [InlineKeyboardButton("✏️ Изменить мораль", callback_data="moral_custom")],
            [InlineKeyboardButton("🔙 К выбору морали", callback_data="back_to_moral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💭 Ваша мораль для сказки:\n\n"
            f"«{custom_moral}»\n\n"
            f"Создаём сказку с этой моралью?",
            reply_markup=reply_markup
        )
        return

    # Обработка ввода новой цены (админская функция)
    elif context.user_data.get('price_step') == 'waiting_price':
        await handle_price_input(update, context)
        return

    # Если нет активного состояния ожидания, показываем главное меню
    else:
        # Проверяем, согласился ли пользователь с условиями
        if not has_agreed_terms(user_id):
            await update.message.reply_text(
                "❌ Пожалуйста, сначала согласитесь с условиями использования, нажав /start"
            )
            return
        
        # Обычное сообщение - показываем главное меню
        await start(update, context)

async def handle_custom_plot_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждения пользовательского сюжета"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_custom_plot":
        # Переходим к вводу имени
        context.user_data['waiting_for'] = 'name'
        
        await query.edit_message_text(
            "👶 Расскажите о ребёнке\n\n"
            "Как зовут главного героя сказки?\n"
            "(Напишите имя в чат)"
        )
        
    elif query.data == "edit_custom_plot":
        # Возвращаемся к вводу сюжета
        context.user_data['waiting_for'] = 'custom_plot'
        
        await query.edit_message_text(
            "✍️ Опишите цель или сюжет сказки:\n\n"
            "Например:\n"
            "• 'Главный герой находит волшебный камень'\n"
            "• 'Спасти принцессу от злого дракона'\n"
            "• 'Построить дом для лесных зверей'\n\n"
            "Напишите вашу идею:"
        )



async def handle_agree_terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("UPDATE users SET agreed_terms = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    # Показываем главное меню
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton("📚 Создать сказку", callback_data="create_story")],
        [InlineKeyboardButton("📖 Мои сказки", callback_data="my_stories")],
        [InlineKeyboardButton("💎 Подписка", callback_data="subscription")],
        [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🔧 Админ панель", callback_data="admin_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "✅ Спасибо за согласие!\n\nВыберите действие:",
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда помощи"""
    help_text = """🆘 Помощь

🌟 Как пользоваться ботом:

1️⃣ Нажмите "📚 Создать сказку"
2️⃣ Выберите тему сказки
3️⃣ Выберите сюжет
4️⃣ Укажите имя ребёнка и возраст
5️⃣ Получите уникальную сказку!

💎 Подписка даёт:
• Больше сказок в месяц
• Приоритетную обработку
• Новые темы и сюжеты

📞 Поддержка: @support_username"""
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="start")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(help_text, reply_markup=reply_markup)

# ==================== Подписки и платежи через ЮKassa ====================
async def show_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать информацию о подписке"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Ошибка получения данных пользователя")
        return
    
    # Безопасно получаем значения
    try:
        stories_used = int(user.get('stories_used', 0) or 0)
    except (ValueError, TypeError):
        stories_used = 0
    
    subscription = user.get('subscription')
    subscription_end = user.get('subscription_end')
    
    # Проверяем статус подписки
    is_active = False
    end_date = None
    if subscription and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end)
            is_active = datetime.now() < end_date
        except Exception as e:
            logger.warning(f"Error parsing subscription_end: {e}")
            is_active = False
    
    if is_active and subscription in TARIFFS:
        tariff = TARIFFS[subscription]
        try:
            remaining_stories = int(tariff.get("stories", 0)) - stories_used
        except (ValueError, TypeError):
            remaining_stories = 0
        
        text = f"""💎 Ваша подписка

✅ Статус: Активна
📅 Тариф: {subscription.title()}
⏰ До: {end_date.strftime('%d.%m.%Y %H:%M')}
📚 Сказок осталось: {remaining_stories}
📊 Использовано: {stories_used}"""
        
        keyboard = [
            [InlineKeyboardButton("📚 Создать сказку", callback_data="create_story")],
            [InlineKeyboardButton("💎 Продлить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]
    else:
        remaining_free = max(0, FREE_LIMIT - stories_used)
        text = f"""💎 Подписка

❌ Статус: Не активна
📚 Бесплатных сказок: {remaining_free} из {FREE_LIMIT}

💎 Преимущества подписки:
• Больше сказок в месяц
• Приоритетная обработка
• Новые темы и сюжеты
• Персонализация историй"""
        
        keyboard = [
            [InlineKeyboardButton("💎 Оформить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup)


async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить статус платежа"""
    query = update.callback_query
    await query.answer()
    
    # Безопасно извлекаем payment_id
    try:
        payment_id = query.data.split("_")[2]
    except IndexError:
        await query.edit_message_text("❌ Ошибка в данных платежа")
        return
    
    # Проверяем статус платежа в ЮKassa
    payment_info = check_payment_status(payment_id)
    
    if payment_info:
        status = payment_info.get("status")
        
        if status == "succeeded":
            # Платеж успешен - активируем подписку
            metadata = payment_info.get("metadata", {})
            try:
                user_id = int(metadata.get("user_id", query.from_user.id))
            except (ValueError, TypeError):
                user_id = query.from_user.id
                
            tariff = metadata.get("tariff")
            
            if tariff and tariff in TARIFFS:
                activate_subscription(user_id, tariff)
                
                # Обновляем статус платежа в базе
                update_payment_status(payment_id, "succeeded")
                
                tariff_info = TARIFFS[tariff]
                
                keyboard = [
                    [InlineKeyboardButton("📚 Создать сказку", callback_data="create_story")],
                    [InlineKeyboardButton("💎 Моя подписка", callback_data="subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Платёж успешно обработан!\n\n"
                    f"🎉 Подписка активирована!\n"
                    f"📅 Тариф: {tariff.title()}\n"
                    f"📚 Доступно сказок: {tariff_info['stories']}\n"
                    f"⏰ Действует: {tariff_info['duration_days']} дней\n\n"
                    f"Спасибо за покупку! Теперь вы можете создавать сказки.",
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text("❌ Ошибка в данных платежа")
                
        elif status == "pending":
            keyboard = [
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⏳ Платеж в обработке...\n\n"
                "Попробуйте проверить через несколько минут.",
                reply_markup=reply_markup
            )
            
        elif status == "canceled":
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data="buy_subscription")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Платеж отменен\n\n"
                "Вы можете попробовать оплатить снова.",
                reply_markup=reply_markup
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❓ Статус платежа: {status}\n\n"
                "Попробуйте проверить позже.",
                reply_markup=reply_markup
            )
    else:
        await query.edit_message_text("❌ Ошибка при проверке платежа")


async def show_tariffs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать тарифы подписки"""
    query = update.callback_query
    await query.answer()
    
    text = """💎 Выберите тариф:

Все тарифы включают:
• Уникальные персонализированные сказки
• Приоритетную обработку
• Доступ ко всем темам
• Техническую поддержку

💳 Оплата через ЮKassa (банковские карты)"""
    
    keyboard = []
    for tariff_key, tariff_info in TARIFFS.items():
        price = tariff_info["price"]
        stories = tariff_info["stories"]
        days = tariff_info["duration_days"]
        
        if tariff_key == "week":
            tariff_name = f"📅 Неделя - {price}₽"
            description = f"{stories} сказок на {days} дней"
        elif tariff_key == "month":
            tariff_name = f"📅 Месяц - {price}₽"
            description = f"{stories} сказок на {days} дней"
        else:  # year
            tariff_name = f"📅 Год - {price}₽"
            description = f"{stories} сказок на {days} дней"
        
        keyboard.append([InlineKeyboardButton(
            f"{tariff_name} - {description}", 
            callback_data=f"pay_{tariff_key}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="subscription")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка платежа через ЮKassa"""
    query = update.callback_query
    await query.answer()
    
    tariff = query.data.split("_")[1]
    
    if tariff not in TARIFFS:
        await query.edit_message_text("❌ Неверный тариф")
        return
    
    tariff_info = TARIFFS[tariff]
    price = tariff_info["price"]
    user_id = query.from_user.id
    
    # Создаем платеж в ЮKassa
    description = f"Подписка на сказки - {tariff} ({tariff_info['stories']} сказок на {tariff_info['duration_days']} дней)"
    
    payment_info = create_yukassa_payment(price, description, user_id, tariff)
    
    if payment_info and payment_info.get("confirmation"):
        payment_url = payment_info["confirmation"]["confirmation_url"]
        payment_id = payment_info["id"]
        
        keyboard = [
            [InlineKeyboardButton("💳 Оплатить", url=payment_url)],
            [InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_payment_{payment_id}")],
            [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="buy_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"💳 Ссылка для оплаты создана!\n\n"
            f"📦 Тариф: {tariff.title()}\n"
            f"💰 Сумма: {price}₽\n"
            f"📚 Сказок: {tariff_info['stories']}\n"
            f"⏰ Период: {tariff_info['duration_days']} дней\n\n"
            f"🔗 Нажмите 'Оплатить' для перехода к оплате\n"
            f"После оплаты нажмите 'Проверить оплату'",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"pay_{tariff}")],
            [InlineKeyboardButton("🔙 Назад к тарифам", callback_data="buy_subscription")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ Ошибка при создании платежа. Попробуйте позже.",
            reply_markup=reply_markup
        )

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Проверить статус платежа"""
    query = update.callback_query
    await query.answer()
    
    payment_id = query.data.split("_")[2]
    
    # Проверяем статус платежа в ЮKassa
    payment_info = check_payment_status(payment_id)
    
    if payment_info:
        status = payment_info.get("status")
        
        if status == "succeeded":
            # Платеж успешен - активируем подписку
            metadata = payment_info.get("metadata", {})
            user_id = int(metadata.get("user_id", query.from_user.id))
            tariff = metadata.get("tariff")
            
            if tariff and tariff in TARIFFS:
                activate_subscription(user_id, tariff)
                
                # Обновляем статус платежа в базе
                update_payment_status(payment_id, "succeeded")
                
                tariff_info = TARIFFS[tariff]
                
                keyboard = [
                    [InlineKeyboardButton("📚 Создать сказку", callback_data="create_story")],
                    [InlineKeyboardButton("💎 Моя подписка", callback_data="subscription")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await query.edit_message_text(
                    f"✅ Платёж успешно обработан!\n\n"
                    f"🎉 Подписка активирована!\n"
                    f"📅 Тариф: {tariff.title()}\n"
                    f"📚 Доступно сказок: {tariff_info['stories']}\n"
                    f"⏰ Действует: {tariff_info['duration_days']} дней\n\n"
                    f"Спасибо за покупку! Теперь вы можете создавать сказки.",
                    reply_markup=reply_markup
                )
            else:
                await query.edit_message_text("❌ Ошибка в данных платежа")
                
        elif status == "pending":
            keyboard = [
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "⏳ Платеж в обработке...\n\n"
                "Попробуйте проверить через несколько минут.",
                reply_markup=reply_markup
            )
            
        elif status == "canceled":
            keyboard = [
                [InlineKeyboardButton("🔄 Попробовать снова", callback_data="buy_subscription")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                "❌ Платеж отменен\n\n"
                "Вы можете попробовать оплатить снова.",
                reply_markup=reply_markup
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_payment_{payment_id}")],
                [InlineKeyboardButton("🔙 Назад", callback_data="subscription")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"❓ Статус платежа: {status}\n\n"
                "Попробуйте проверить позже.",
                reply_markup=reply_markup
            )
    else:
        await query.edit_message_text("❌ Ошибка при проверке платежа")

# ==================== Создание сказок ====================
async def create_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать создание сказки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Проверяем, может ли пользователь создавать сказки
    can_create, message = can_generate_story(user_id)
    if not can_create:
        keyboard = [[InlineKeyboardButton("💎 Оформить подписку", callback_data="subscription")],
                   [InlineKeyboardButton("🔙 Назад", callback_data="start")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ {message}\n\n"
            "Оформите подписку для создания новых сказок!",
            reply_markup=reply_markup
        )
        return
    
    # Показываем выбор темы
    await show_theme_selection(update, context)

async def show_theme_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать выбор темы"""
    query = update.callback_query
    
    keyboard = []
    for i in range(0, len(THEMES), 2):
        row = []
        for j in range(2):
            if i + j < len(THEMES):
                theme = THEMES[i + j]
                theme_id = THEME_IDS[theme]
                row.append(InlineKeyboardButton(theme, callback_data=f"theme_{theme_id}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """🎭 Выберите тему сказки:

Каждая тема содержит уникальные приключения и персонажей!"""
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def show_plot_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать выбор сюжета или запросить пользовательскую тему"""
    query = update.callback_query
    await query.answer()
    
    theme_id = query.data.split("_")[1]
    theme_name = ID_TO_THEME.get(theme_id, "Неизвестная тема")
    context.user_data['selected_theme'] = theme_id

    # Если выбрана пользовательская тема
    if theme_id == "custom":
        context.user_data['waiting_for'] = 'custom_theme'
        
        keyboard = [[InlineKeyboardButton("🔙 К выбору темы", callback_data="create_story")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✍️ Напишите свою тему для сказки\n\n"
            "Например:\n"
            "• 'Путешествие в мир динозавров'\n"
            "• 'Приключения в стране сладостей'\n"
            "• 'Подводное царство русалок'\n"
            "• 'Космическое путешествие к звёздам'\n\n"
            "Напишите вашу тему:",
            reply_markup=reply_markup
        )
        return

    # Обычная обработка для предустановленных тем
    plots = PLOT_TEMPLATES.get(theme_id, {})
    plot_names = PLOT_NAMES.get(theme_id, {})

    if not plots:
        await query.edit_message_text("❌ Сюжеты для этой темы пока не готовы")
        return

    keyboard = []
    for plot_id, plot_name in plot_names.items():
        keyboard.append([InlineKeyboardButton(plot_name, callback_data=f"plot_{plot_id}")])

    keyboard.append([InlineKeyboardButton("🔙 К выбору темы", callback_data="create_story")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"""📖 {theme_name}

Выберите приключение:"""

    await query.edit_message_text(text, reply_markup=reply_markup)





async def show_plot_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать подтверждение выбранного сюжета"""
    query = update.callback_query
    await query.answer()
    
    # Извлекаем ID сюжета
    plot_id = query.data.split("_")[1]
    theme_id = context.user_data.get('selected_theme')
    
    if not theme_id:
        await query.edit_message_text("❌ Ошибка: тема не выбрана")
        return
    
    # Получаем описание сюжета
    plot_description = PLOT_TEMPLATES.get(theme_id, {}).get(plot_id)
    plot_name = PLOT_NAMES.get(theme_id, {}).get(plot_id)
    
    if not plot_description:
        await query.edit_message_text("❌ Сюжет не найден")
        return
    
    # Сохраняем выбранный сюжет
    context.user_data['selected_plot'] = plot_id
    context.user_data['plot_description'] = plot_description
    
    keyboard = [
        [InlineKeyboardButton("✅ Да, начинай", callback_data="confirm_plot")],
        [InlineKeyboardButton("🔄 Выбрать другую цель", callback_data=f"theme_{theme_id}")],
        [InlineKeyboardButton("🔙 К выбору темы", callback_data="create_story")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""📖 {plot_name}

{plot_description}

Начинаем эту сказку?"""
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def request_child_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запросить информацию о ребёнке"""
    query = update.callback_query
    await query.answer()
    
    # Устанавливаем состояние ожидания имени
    context.user_data['waiting_for'] = 'name'
    
    text = """👶 Расскажите о ребёнке

Как зовут главного героя сказки?
(Напишите имя в чат)"""
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="create_story")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def handle_age_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора возраста"""
    query = update.callback_query
    await query.answer()
    
    age = int(query.data.split("_")[1])
    context.user_data['child_age'] = age
    
    # Показываем выбор морали
    await show_moral_selection(update, context)

async def show_moral_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать выбор морали"""
    keyboard = []
    for i, moral in enumerate(MORALS):
        keyboard.append([InlineKeyboardButton(moral, callback_data=f"moral_{i}")])
    
    # Добавляем кнопку для ввода своей морали
    keyboard.append([InlineKeyboardButton("✍️ Написать свою мораль", callback_data="moral_custom")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="create_story")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = """💭 Выберите мораль сказки:
Какой урок должен извлечь ребёнок?"""

    # Проверяем, был ли это callback query или обычное сообщение
    if update.callback_query:
        # Если это callback query, редактируем сообщение
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        # Если это обычное сообщение (например, после ввода возраста),
        # отправляем новое сообщение
        await update.message.reply_text(text, reply_markup=reply_markup)



async def handle_moral_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора морали"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "moral_custom":
        # Пользователь хочет ввести свою мораль
        context.user_data['waiting_for'] = 'custom_moral'
        
        text = """✍️ Напишите свою мораль для сказки

Какой урок должен извлечь ребёнок из этой истории?

Например:
• "Важно помогать друзьям в трудную минуту"
• "Нужно верить в свои силы"
• "Доброта всегда побеждает зло"

Напишите вашу мораль в чат:"""
        
        keyboard = [[InlineKeyboardButton("🔙 К выбору морали", callback_data="back_to_moral")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup)
        return
    
    # Обработка выбора готовой морали
    moral_index = int(query.data.split("_")[1])
    moral = MORALS[moral_index]
    context.user_data['selected_moral'] = moral
    
    # Начинаем генерацию сказки
    await generate_story_with_custom_prompts(update, context)



async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
    user_id = update.effective_user.id
    waiting_for = context.user_data.get('waiting_for')

    # Проверяем, заблокирован ли пользователь
    if is_user_blocked(user_id):
        await update.message.reply_text("❌ Ваш аккаунт заблокирован")
        return

    # Сначала проверяем обработку промптов (только для админа)
    if context.user_data.get('prompt_step') == 'waiting_prompt':
        if await handle_prompt_input(update, context):
            return  # Если промпт обработан, выходим

    # Обработка ввода пользовательской темы
    if waiting_for == 'custom_theme':
        custom_theme = update.message.text.strip()
        
        if len(custom_theme) < 3:
            await update.message.reply_text("❌ Тема слишком короткая. Попробуйте подробнее:")
            return
        
        if len(custom_theme) > 100:
            await update.message.reply_text("❌ Тема слишком длинная. Попробуйте покороче (до 100 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?]+$', custom_theme):
            await update.message.reply_text("❌ Тема содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        context.user_data['custom_theme'] = custom_theme
        context.user_data['waiting_for'] = 'custom_plot'
        
        await update.message.reply_text(
            f"✨ Отлично! Тема: «{custom_theme}»\n\n"
            "✍️ Теперь опишите цель или сюжет сказки:\n\n"
            "Например:\n"
            "• 'Главный герой находит волшебный камень'\n"
            "• 'Спасти принцессу от злого дракона'\n"
            "• 'Построить дом для лесных зверей'\n\n"
            "Напишите вашу идею:"
        )
        return

    # Обработка ввода пользовательского сюжета
    elif waiting_for == 'custom_plot':
        custom_plot = update.message.text.strip()
        
        if len(custom_plot) < 5:
            await update.message.reply_text("❌ Сюжет слишком короткий. Попробуйте подробнее:")
            return
        
        if len(custom_plot) > 200:
            await update.message.reply_text("❌ Сюжет слишком длинный. Попробуйте покороче (до 200 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?()]+$', custom_plot):
            await update.message.reply_text("❌ Сюжет содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        context.user_data['plot_description'] = custom_plot
        context.user_data['selected_plot'] = 'custom'
        context.user_data['waiting_for'] = None  # Убираем состояние ожидания
        
        # Показываем подтверждение и переходим к вводу имени
        keyboard = [
            [InlineKeyboardButton("✅ Да, продолжить", callback_data="confirm_custom_plot")],
            [InlineKeyboardButton("✏️ Изменить сюжет", callback_data="edit_custom_plot")],
            [InlineKeyboardButton("🔙 К выбору темы", callback_data="create_story")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"📖 Ваша сказка:\n\n"
            f"🎭 Тема: {context.user_data.get('custom_theme', 'Своя тема')}\n"
            f"🎯 Сюжет: {custom_plot}\n\n"
            f"Продолжаем создание сказки?",
            reply_markup=reply_markup
        )
        return

    # Обработка ввода имени ребёнка
    elif waiting_for == 'name':
        child_name = update.message.text.strip()

        if len(child_name) < 1:
            await update.message.reply_text("❌ Имя не может быть пустым. Попробуйте ещё раз:")
            return

        if len(child_name) > 50:
            await update.message.reply_text("❌ Имя слишком длинное. Попробуйте короче:")
            return

        # Проверяем, что имя содержит только буквы и пробелы
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z\s\-]+$', child_name):
            await update.message.reply_text("❌ Имя должно содержать только буквы. Попробуйте ещё раз:")
            return

        context.user_data['child_name'] = child_name
        context.user_data['waiting_for'] = 'age'
        
        await update.message.reply_text(
            f"👶 Отлично! Главного героя зовут {child_name}.\n\n"
            "Сколько ему/ей лет? (Введите число от 0 до 80)"
        )
        return

    # Обработка ввода возраста
    elif waiting_for == 'age':
        age_text = update.message.text.strip()
        
        if not age_text.isdigit():
            await update.message.reply_text("❌ Пожалуйста, введите возраст числом (например, 5):")
            return
        
        age = int(age_text)
        if age < 0 or age > 80:
            await update.message.reply_text("❌ Возраст должен быть от 0 до 80 лет. Попробуйте ещё раз:")
            return
        
        context.user_data['child_age'] = age
        context.user_data['waiting_for'] = None
        
        # Переходим к выбору морали
        await show_moral_selection(update, context)
        return

    # Обработка ввода пользовательской морали
    elif waiting_for == 'custom_moral':
        custom_moral = update.message.text.strip()
        
        if len(custom_moral) < 5:
            await update.message.reply_text("❌ Мораль слишком короткая. Напишите хотя бы несколько слов:")
            return
        
        if len(custom_moral) > 200:
            await update.message.reply_text("❌ Мораль слишком длинная. Попробуйте покороче (до 200 символов):")
            return
        
        # Проверяем на недопустимый контент
        if not re.match(r'^[а-яёА-ЯЁa-zA-Z0-9\s\-.,!?()«»"]+$', custom_moral):
            await update.message.reply_text("❌ Мораль содержит недопустимые символы. Используйте только буквы, цифры и знаки препинания:")
            return
        
        # Сохраняем пользовательскую мораль
        context.user_data['selected_moral'] = custom_moral
        context.user_data['waiting_for'] = None
        
        # Показываем подтверждение и начинаем генерацию
        keyboard = [
            [InlineKeyboardButton("✅ Да, создавать сказку", callback_data="confirm_custom_moral")],
            [InlineKeyboardButton("✏️ Изменить мораль", callback_data="moral_custom")],
            [InlineKeyboardButton("🔙 К выбору морали", callback_data="back_to_moral")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"💭 Ваша мораль для сказки:\n\n"
            f"«{custom_moral}»\n\n"
            f"Создаём сказку с этой моралью?",
            reply_markup=reply_markup
        )
        return

    # Обработка ввода новой цены (админская функция)
    elif context.user_data.get('price_step') == 'waiting_price':
        await handle_price_input(update, context)
        return

    # Если нет активного состояния ожидания, показываем главное меню
    else:
        # Проверяем, согласился ли пользователь с условиями
        if not has_agreed_terms(user_id):
            await update.message.reply_text(
                "❌ Пожалуйста, сначала согласитесь с условиями использования, нажав /start"
            )
            return
        
        # Обычное сообщение - показываем главное меню
        await start(update, context)


async def handle_custom_moral_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка подтверждения пользовательской морали"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_custom_moral":
        # Начинаем генерацию сказки с пользовательской моралью
        await generate_story_with_custom_prompts(update, context)
        
    elif query.data == "back_to_moral":
        # Возвращаемся к выбору морали
        await show_moral_selection(update, context)







async def generate_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерация сказки с помощью OpenAI с двухэтапным процессом"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Получаем данные для генерации
    theme_id = context.user_data.get('selected_theme')
    plot_id = context.user_data.get('selected_plot')
    plot_description = context.user_data.get('plot_description')
    child_name = context.user_data.get('child_name')
    child_age = context.user_data.get('child_age')
    moral = context.user_data.get('selected_moral')
    
    if not all([theme_id, plot_id, child_name, child_age, moral]):
        await query.edit_message_text("❌ Не хватает данных для создания сказки")
        return
    
    # Показываем сообщение о генерации
    await query.edit_message_text("✨ Создаю вашу уникальную сказку...\n\nЭто может занять несколько минут.")
    
    try:
        # Создаем клиент OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        # Формируем данные для промптов
        theme_name = ID_TO_THEME.get(theme_id, "")
        
        # ЭТАП 1: Создание сказки профессиональным сказочником
        author_prompt = f"""Ты профессиональный детский сказочник. Создай увлекательную, яркую и короткую сказку с учетом следующих данных:  
Имя главного героя: {{child_name}}  
Возраст ребёнка: {{child_age}} лет  
Тема: {{theme_text}}  
Сюжет: {{plot_text}}  
Мораль: {{moral}}  

⚠️ ВАЖНО:  
- Начинай сказку сразу с повествования, без вводных фраз типа "Жил-был...", "Эта сказка о..." или любых пояснений.  
- Пиши динамичную, смешную, волшебную сказку с ярким началом, абсурдно-удивительным миром, испытаниями, запоминающимися персонажами и магическим финалом.  
- Делай текст лаконичным, без лишних деталей, чтобы сказка оставалась увлекательной и подходила для детей 5-8 лет.  
- Разделяй сказку на короткие главы с подзаголовками и используй эмодзи для выделения ключевых моментов.  
- Пиши живым, искренним языком, будто рассказываешь детям на ночь.  
- Обязательно включи мораль "{{moral}}" в конце сказки.  
- В ответе только текст сказки, без пояснений, комментариев или лишних слов.  
- Убедись, что текст грамматически и стилистически безупречен, без ошибок.  

Пример правильного начала:  
В далекой стране, где облака пели песни, а деревья танцевали под луной, жила отважная девочка по имени Лиза. Ей было шесть лет, и её любопытство могло заставить даже звёзды спуститься с неба, чтобы поболтать."""

        # Обновляем сообщение о прогрессе
        await query.edit_message_text("✨ Создаю черновик сказки...\n\n📝 Этап 1/2: Профессиональный сказочник работает...")
        
        # Генерируем первую версию сказки
        response1 = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Используем более мощную модель для лучшего качества
            messages=[
                {"role": "system", "content": "Ты профессиональный детский сказочник с огромным опытом создания захватывающих историй для детей. Убедись, что сказка НАЧИНАЕТСЯ сразу с основного действия или описания, БЕЗ вводных фраз от рассказчика (например, О, эта сказка очень классная...) "},
                {"role": "user", "content": author_prompt}
            ],
            max_tokens=2000,
            temperature=0.8
        )
        
        first_story = response1.choices[0].message.content
        
        # ЭТАП 2: Редактирование сказки детским редактором
        critic_prompt = f"""Ты — ребёнок 5-8 лет, для которого писалась эта сказка. Перепиши сказку, чтобы она стала яркой, увлекательной и короткой, основываясь на следующем:  
1. Проанализируй оригинальную сказку как ребёнок: найди слабые места (скучные моменты, мало магии, слабые эмоции).  
2. Улучши её, добавив больше магии, юмора, живых диалогов, ярких деталей и вовлекающих элементов.  

⚠️ ВАЖНО:  
- Начинай сказку сразу с действия или яркого описания, без вводных фраз типа "Эта сказка о...", "Жил-был..." или любых пояснений.  
- Пиши короткими предложениями, с дружеским тоном, полным эмоций, юмора и удивления.  
- Добавляй живые диалоги и магические элементы, чтобы каждая сцена вызывала радость или смех.  
- Разделяй сказку на короткие главы с подзаголовками и используй эмодзи для выделения ключевых моментов.  
- Сохрани мораль оригинальной сказки в конце.  
- Убедись, что текст грамматически безупречен, без ошибок, и подходит для детей 5-8 лет.  
- В ответе только текст переписанной сказки, без анализа, пояснений или лишних слов.  

Пример правильного начала:  
В волшебном лесу, где деревья шептались друг с другом, а звёзды пели колыбельные, жил мальчик по имени Саша. Ему было семь лет, и его смех мог заставить даже облака хихикать!"""
        # Обновляем сообщение о прогрессе
        await query.edit_message_text("✨ Улучшаю сказку...\n\n🎨 Этап 2/2: Детский редактор добавляет магию...")
        
        # Генерируем улучшенную версию сказки
        response2 = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты ребёнок 5-8 лет, который умеет делать сказки ещё более интересными и захватывающими для других детей.Убедись, что сказка НАЧИНАЕТСЯ сразу с основного действия или описания, БЕЗ вводных фраз от рассказчика (например, О, эта сказка очень классная...) "},
                {"role": "user", "content": critic_prompt}
            ],
            max_tokens=2200,
            temperature=0.7
        )
        
        final_story = response2.choices[0].message.content
        
        # Создаем заголовок сказки
        plot_name = PLOT_NAMES.get(theme_id, {}).get(plot_id, "Приключение")
        story_title = f"{plot_name} - сказка для {child_name}"
        
        # Сохраняем сказку в базу данных
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("INSERT INTO stories (user_id, title, content, created_at) VALUES (?, ?, ?, ?)",
                  (user_id, story_title, final_story, datetime.now().isoformat()))
        story_id = c.lastrowid
        conn.commit()
        conn.close()
        
        # Увеличиваем счетчик использованных сказок
        update_user_stories_count(user_id)
        
        # Очищаем данные пользователя
        context.user_data.clear()
        
        # Отправляем сказку пользователю
        keyboard = [
            [InlineKeyboardButton("📚 Создать ещё сказку", callback_data="create_story")],
            [InlineKeyboardButton("📖 Мои сказки", callback_data="my_stories")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Разбиваем длинную сказку на части, если нужно
        if len(final_story) > 4000:
            # Отправляем заголовок
            await query.edit_message_text(f"✨ {story_title}\n\n{final_story[:4000]}...")
            
            # Отправляем продолжение
            remaining_content = final_story[4000:]
            while remaining_content:
                chunk = remaining_content[:4000]
                remaining_content = remaining_content[4000:]
                
                if remaining_content:
                    await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)
                else:
                    # Последняя часть с кнопками
                    await context.bot.send_message(
                        chat_id=query.message.chat_id, 
                        text=chunk,
                        reply_markup=reply_markup
                    )
        else:
            await query.edit_message_text(
                f"✨ {story_title}\n\n{final_story}",
                reply_markup=reply_markup
            )
        
        logger.info(f"Enhanced story generated for user {user_id}: {story_title}")
        
    except Exception as e:
        logger.error(f"Error generating enhanced story: {str(e)}")
        
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data="create_story")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "❌ Произошла ошибка при создании сказки. Попробуйте позже.",
            reply_markup=reply_markup
        )
def update_story_prompts():
    """Обновить промпты в базе данных"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Промпт для автора сказок
    author_prompt = """Ты — профессиональный детский сказочник с 20-летним опытом, лауреат международных конкурсов и создатель бестселлеров, которые читают на ночь дети по всему миру.

Ты мастер визуального и эмоционального сторителлинга. Твои сказки не просто развлекают — они погружают, захватывают, вызывают взрыв фантазии, заставляют сопереживать, смеяться, бояться и радоваться. Ты знаешь, что нужно ребёнку 5–8 лет, чтобы сказка стала его любимой.

Создай яркую, живую, смешную, динамичную, по-настоящему персонализированную сказку с мощным началом, абсурдно-волшебным миром, испытаниями, уникальными персонажами и магическим финалом."""
    
    # Промпт для детского критика
    critic_prompt = """Ты — ребёнок, для которого писалась эта сказка. Проанализируй её как ребёнок: найди слабые места, предложи улучшения и перепиши сказку, устранив все замечания, добавив эмоции, детали, магию, юмор, диалоги, вовлекающие элементы. Не включай анализ в ответ — только итоговую сказку!"""
    
    # Обновляем промпты в базе данных
    c.execute("INSERT OR REPLACE INTO prompts (role, content) VALUES (?, ?)", 
              ("author", author_prompt))
    c.execute("INSERT OR REPLACE INTO prompts (role, content) VALUES (?, ?)", 
              ("critic", critic_prompt))
    
    conn.commit()
    conn.close()
    logger.info("Story prompts updated in database")

def get_story_prompts():
    """Получить промпты из базы данных"""
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    c.execute("SELECT role, content FROM prompts WHERE role IN ('author', 'critic')")
    prompts = dict(c.fetchall())
    
    conn.close()
    return prompts

# ==================== Просмотр сказок ====================
async def show_my_stories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать сказки пользователя"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM stories WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
              (user_id,))
    stories = c.fetchall()
    conn.close()
    
    if not stories:
        keyboard = [
            [InlineKeyboardButton("📚 Создать первую сказку", callback_data="create_story")],
            [InlineKeyboardButton("🔙 Назад", callback_data="start")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📖 У вас пока нет сказок\n\nСоздайте свою первую уникальную сказку!",
            reply_markup=reply_markup
        )
        return
    
    keyboard = []
    for story_id, title, created_at in stories:
        # Ограничиваем длину заголовка для кнопки
        short_title = title[:40] + "..." if len(title) > 40 else title
        keyboard.append([InlineKeyboardButton(short_title, callback_data=f"story_{story_id}")])
    
    keyboard.append([InlineKeyboardButton("📚 Создать новую сказку", callback_data="create_story")])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="start")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""📖 Ваши сказки ({len(stories)}):

Выберите сказку для чтения:"""
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def show_story(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать конкретную сказку"""
    query = update.callback_query
    await query.answer()
    
    story_id = int(query.data.split("_")[1])
    user_id = query.from_user.id
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    c.execute("SELECT title, content FROM stories WHERE id = ? AND user_id = ?", (story_id, user_id))
    story = c.fetchone()
    conn.close()
    
    if not story:
        await query.edit_message_text("❌ Сказка не найдена")
        return
    
    title, content = story
    
    keyboard = [
        [InlineKeyboardButton("📖 Мои сказки", callback_data="my_stories")],
        [InlineKeyboardButton("📚 Создать новую", callback_data="create_story")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Разбиваем длинную сказку на части, если нужно
    if len(content) > 4000:
        await query.edit_message_text(f"📖 {title}\n\n{content[:4000]}...")
        
        # Отправляем продолжение
        remaining_content = content[4000:]
        while remaining_content:
            chunk = remaining_content[:4000]
            remaining_content = remaining_content[4000:]
            
            if remaining_content:
                await context.bot.send_message(chat_id=query.message.chat_id, text=chunk)
            else:
                # Последняя часть с кнопками
                await context.bot.send_message(
                    chat_id=query.message.chat_id, 
                    text=chunk,
                    reply_markup=reply_markup
                )
    else:
        await query.edit_message_text(
            f"📖 {title}\n\n{content}",
            reply_markup=reply_markup
        )

# ==================== Админские команды ====================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская панель"""
    if update.effective_user.id != ADMIN_ID:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ У вас нет прав администратора")
        else:
            await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    stats = get_user_stats()
    
    keyboard = [
        [InlineKeyboardButton("👤 Управление пользователями", callback_data="admin_users")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("📝 Управление промптами", callback_data="admin_prompts")],
        [InlineKeyboardButton("💸 Управление ценами", callback_data="admin_prices")]
        
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""🔧 *Админская панель*

📊 *Статистика:*
👥 Всего пользователей: {stats['total_users']}
💎 Активных подписчиков: {stats['active_subscribers']}
🚫 Заблокированных: {stats['blocked_users']}
📚 Всего сказок: {stats['total_stories']}"""
    
    # Проверяем, вызвана ли функция из callback или из команды
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка админских callback-запросов"""
    query = update.callback_query
    data = query.data
    
    # Проверка прав администратора
    if query.from_user.id != ADMIN_ID:
        try:
            await query.edit_message_text("❌ У вас нет прав администратора")
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.error(f"Error editing message for non-admin: {e}")
        return
    
    # Админ-панель и навигация
    try:
        if data == "admin_stats":
            stats = get_user_stats()
            text = f"""📊 *Подробная статистика*
👥 Всего пользователей: {stats['total_users']}
💎 Активных подписчиков: {stats['active_subscribers']}
🚫 Заблокированных: {stats['blocked_users']}
📚 Всего сказок создано: {stats['total_stories']}
📈 *Конверсия:*
Подписчиков от общего числа: {(stats['active_subscribers']/max(stats['total_users'], 1)*100):.1f}%"""
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_prompts":
            await show_prompt_management(update, context)
        
        elif data == "admin_users":
            text = """👤 *Управление пользователями*
Доступные команды:
• /block\\_user <user\\_id> - заблокировать пользователя
• /unblock\\_user <user\\_id> - разблокировать пользователя
• /user\\_info <user\\_id> - информация о пользователе
Или используйте список пользователей ниже:"""
            keyboard = [
                [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users_list")],
                [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_subscriptions":
            text = """💰 *Управление подписками*
Доступные команды:
• /extend\\_sub <user\\_id> <tariff> - продлить подписку
Тарифы: week, month, year
• /reset\\_stories <user\\_id> - сбросить счетчик сказок
• /sub\\_info <user\\_id> - информация о подписке
Используйте команды в чате с ботом."""
            keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        
        elif data == "admin_prices":
            await show_price_management(update, context)
        
        elif data == "admin_back":
            await admin_panel(update, context)
        
        elif data == "admin_users_list":
            await show_users_list(update, context, page=0)
        
        elif data.startswith("users_page_"):
            page = int(data.split("_")[2])
            await show_users_list(update, context, page=page)
        
        elif data.startswith("user_info_"):
            user_id = int(data.split("_")[2])
            await show_user_info(update, context, user_id)
        
        elif data.startswith("block_user_"):
            user_id = int(data.split("_")[2])
            conn = sqlite3.connect("bot.db")
            c = conn.cursor()
            c.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            await query.answer(f"✅ Пользователь {user_id} заблокирован", show_alert=True)
            context.user_data['temp_callback'] = f"user_info_{user_id}"
            await show_user_info(update, context, user_id)
        
        elif data.startswith("unblock_user_"):
            user_id = int(data.split("_")[2])
            conn = sqlite3.connect("bot.db")
            c = conn.cursor()
            c.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            await query.answer(f"✅ Пользователь {user_id} разблокирован", show_alert=True)
            context.user_data['temp_callback'] = f"user_info_{user_id}"
            await show_user_info(update, context, user_id)
        
        elif data.startswith("reset_stories_"):
            user_id = int(data.split("_")[2])
            conn = sqlite3.connect("bot.db")
            c = conn.cursor()
            c.execute("UPDATE users SET stories_count = 0 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            await query.answer(f"✅ Счетчик сказок для пользователя {user_id} сброшен", show_alert=True)
            context.user_data['temp_callback'] = f"user_info_{user_id}"
            await show_user_info(update, context, user_id)
        
        elif data.startswith("extend_"):
            user_id = int(data.split("_")[2])
            await show_extend_subscription_menu(update, context, user_id)
        
        elif data.startswith("make_tester_"):
            user_id = int(data.split("_")[2])
            conn = sqlite3.connect("bot.db")
            c = conn.cursor()
            c.execute("UPDATE users SET is_tester = 1 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            await query.answer(f"✅ Пользователь {user_id} добавлен в тестеры", show_alert=True)
            context.user_data['temp_callback'] = f"user_info_{user_id}"
            await show_user_info(update, context, user_id)
        
        elif data.startswith("remove_tester_"):
            user_id = int(data.split("_")[2])
            conn = sqlite3.connect("bot.db")
            c = conn.cursor()
            c.execute("UPDATE users SET is_tester = 0 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            await query.answer(f"✅ Пользователь {user_id} удален из тестеров", show_alert=True)
            context.user_data['temp_callback'] = f"user_info_{user_id}"
            await show_user_info(update, context, user_id)
        
        # Управление промптами
        elif data.startswith("edit_prompt_"):
            await edit_prompt(update, context)
        
        elif data == "show_current_prompts":
            await show_current_prompts(update, context)
        
        elif data == "reset_prompts":
            await reset_prompts(update, context)
        
        else:
            await query.edit_message_text("❌ Неизвестная админская команда")
    
    except Exception as e:
        logger.error(f"Error in admin callback handler: {str(e)}")
        try:
            await query.edit_message_text("❌ Произошла ошибка при обработке запроса")
        except Exception as edit_error:
            if "Message is not modified" not in str(edit_error):
                logger.error(f"Error editing message after exception: {edit_error}")
async def show_price_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать меню управления ценами"""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    # Создаем кнопки для быстрого изменения цен
    keyboard = [
        [InlineKeyboardButton("📅 Изменить цену недели", callback_data="change_week_price")],
        [InlineKeyboardButton("📅 Изменить цену месяца", callback_data="change_month_price")],
        [InlineKeyboardButton("📅 Изменить цену года", callback_data="change_year_price")],
        [InlineKeyboardButton("💰 Показать текущие цены", callback_data="show_current_prices")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""💰 *Управление ценами*

Текущие тарифы:
📅 Неделя: {TARIFFS['week']['price']}₽ ({TARIFFS['week']['stories']} сказок)
📅 Месяц: {TARIFFS['month']['price']}₽ ({TARIFFS['month']['stories']} сказок)
📅 Год: {TARIFFS['year']['price']}₽ ({TARIFFS['year']['stories']} сказок)

Выберите действие или используйте команду:
/change\\_prices <неделя> <месяц> <год>"""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def handle_price_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка изменения цен через callback"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    if query.data == "show_current_prices":
        text = f"""💰 *Текущие цены*

📅 **Неделя:** {TARIFFS['week']['price']}₽
   • Сказок: {TARIFFS['week']['stories']}
   • Дней: {TARIFFS['week']['duration_days']}

📅 **Месяц:** {TARIFFS['month']['price']}₽
   • Сказок: {TARIFFS['month']['stories']}
   • Дней: {TARIFFS['month']['duration_days']}

📅 **Год:** {TARIFFS['year']['price']}₽
   • Сказок: {TARIFFS['year']['stories']}
   • Дней: {TARIFFS['year']['duration_days']}

Для изменения используйте:
/change\\_prices <неделя> <месяц> <год>"""
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_prices")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data in ["change_week_price", "change_month_price", "change_year_price"]:
        tariff_names = {
            "change_week_price": "недели",
            "change_month_price": "месяца", 
            "change_year_price": "года"
        }
        
        tariff_keys = {
            "change_week_price": "week",
            "change_month_price": "month",
            "change_year_price": "year"
        }
        
        tariff_name = tariff_names[query.data]
        tariff_key = tariff_keys[query.data]
        current_price = TARIFFS[tariff_key]['price']
        
        # Сохраняем информацию о том, какую цену меняем
        context.user_data['changing_price'] = tariff_key
        context.user_data['price_step'] = 'waiting_price'
        
        await query.edit_message_text(
            f"💰 Изменение цены {tariff_name}\n\n"
            f"Текущая цена: {current_price}₽\n\n"
            f"Введите новую цену (только число):"
        )

async def handle_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода новой цены"""
    global TARIFFS
    
    if not context.user_data.get('changing_price') or context.user_data.get('price_step') != 'waiting_price':
        return
    
    try:
        new_price = int(update.message.text.strip())
        
        if new_price < 1:
            await update.message.reply_text("❌ Цена должна быть больше 0. Попробуйте еще раз:")
            return
        
        tariff_key = context.user_data['changing_price']
        old_price = int(TARIFFS[tariff_key]['price'])  # Приводим к int
        
        # Обновляем цену
        TARIFFS[tariff_key]['price'] = new_price
        
        # Сохраняем в базу данных
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        
        c.execute("""CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                  (f"{tariff_key}_price", str(new_price)))
        
        conn.commit()
        conn.close()
        
        # Очищаем состояние
        context.user_data.pop('changing_price', None)
        context.user_data.pop('price_step', None)
        
        tariff_names = {
            "week": "недели",
            "month": "месяца",
            "year": "года"
        }
        
        keyboard = [
            [InlineKeyboardButton("💰 Управление ценами", callback_data="admin_prices")],
            [InlineKeyboardButton("🏠 Админ панель", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ Цена {tariff_names[tariff_key]} изменена!\n\n"
            f"Было: {old_price}₽\n"
            f"Стало: {new_price}₽",
            reply_markup=reply_markup
        )
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Введите только число:")
    except Exception as e:
        logger.error(f"Error in handle_price_input: {str(e)}")
        await update.message.reply_text("❌ Произошла ошибка при изменении цены.")


async def show_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
    """Показать список пользователей с пагинацией"""
    query = update.callback_query
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    # Получаем пользователей из базы данных
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Считаем общее количество пользователей
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    # Получаем пользователей для текущей страницы (по 5 на страницу)
    offset = page * 5
    c.execute("""
        SELECT u.id, u.name, u.subscription, u.subscription_end, u.is_blocked, u.is_tester,
               COALESCE(u.stories_used, 0) as stories_used,
               COUNT(s.id) as total_stories
        FROM users u
        LEFT JOIN stories s ON u.id = s.user_id
        GROUP BY u.id, u.name, u.subscription, u.subscription_end, u.is_blocked, u.is_tester, u.stories_used
        ORDER BY u.id DESC
        LIMIT 5 OFFSET ?
    """, (offset,))
    
    users = c.fetchall()
    conn.close()
    
    if not users:
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("👤 Пользователи не найдены", reply_markup=reply_markup)
        return
    
    # Формируем клавиатуру с пользователями
    keyboard = []
    
    for user_data in users:
        user_id, name, subscription, subscription_end, is_blocked, is_tester, stories_used, total_stories = user_data
        
        # Определяем статус пользователя
        status_emoji = ""
        if is_blocked:
            status_emoji = "🚫"
        elif subscription and subscription_end:
            try:
                end_date = datetime.fromisoformat(subscription_end)
                if datetime.now() < end_date:
                    status_emoji = "💎"
                else:
                    status_emoji = "⏰"  # Подписка истекла
            except:
                status_emoji = "❓"
        
        # Формируем текст кнопки
        button_text = f"{status_emoji} {user_id} | {stories_used}📚 | {total_stories}📖"
        if subscription:
            button_text += f" | {subscription}"
        
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"user_info_{user_id}")])
    
    # Добавляем навигацию
    nav_buttons = []
    total_pages = (total_users + 4) // 5  # Округляем вверх
    
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"users_page_{page-1}"))
    
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("➡️ Далее", callback_data=f"users_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка возврата
    keyboard.append([InlineKeyboardButton("🔙 Админ панель", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Формируем текст сообщения
    text = f"""👥 **Список пользователей** (стр. {page + 1}/{total_pages})

**Легенда:**
🚫 - Заблокирован
💎 - Активная подписка
⏰ - Подписка истекла
📚 - Использовано сказок
📖 - Всего создано сказок

**Формат:** ID | Использовано📚 | Создано📖 | Подписка

Нажмите на пользователя для подробной информации."""
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать подробную информацию о пользователе"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    # Извлекаем ID пользователя
    try:
        user_id = int(query.data.split("_")[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный ID пользователя")
        return
    
    # Получаем информацию о пользователе
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    # Основная информация о пользователе
    c.execute("""
        SELECT id, name, subscription, subscription_end, stories_used, last_paid, 
               is_blocked, is_tester, agreed_terms, timezone
        FROM users WHERE id = ?
    """, (user_id,))
    
    user_data = c.fetchone()
    
    if not user_data:
        await query.edit_message_text("❌ Пользователь не найден")
        conn.close()
        return
    
    # Получаем статистику сказок
    c.execute("SELECT COUNT(*) FROM stories WHERE user_id = ?", (user_id,))
    total_stories = c.fetchone()[0]
    
    # Получаем последние сказки
    c.execute("""
        SELECT title, created_at FROM stories 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 3
    """, (user_id,))
    recent_stories = c.fetchall()
    
    # Получаем информацию о платежах
    c.execute("""
        SELECT COUNT(*), SUM(amount) FROM payments 
        WHERE user_id = ? AND status = 'succeeded'
    """, (user_id,))
    payment_stats = c.fetchone()
    
    conn.close()
    
    # Распаковываем данные пользователя
    (uid, name, subscription, subscription_end, stories_used, last_paid, 
     is_blocked, is_tester, agreed_terms, timezone) = user_data
    
    # Безопасно обрабатываем значения
    name = name or "Не указано"
    stories_used = stories_used or 0
    
    # Формируем информацию о статусе
    status_text = "👤 Обычный пользователь"
    if is_blocked:
        status_text = "🚫 Заблокирован"
    elif subscription and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end)
            if datetime.now() < end_date:
                status_text = f"💎 Подписчик ({subscription})"
            else:
                status_text = f"⏰ Подписка истекла ({subscription})"
        except:
            status_text = f"❓ Подписка ({subscription})"
    
    # Формируем информацию о подписке
    subscription_info = "❌ Нет активной подписки"
    if subscription and subscription_end:
        try:
            end_date = datetime.fromisoformat(subscription_end)
            if datetime.now() < end_date:
                subscription_info = f"✅ {subscription.title()} до {end_date.strftime('%d.%m.%Y %H:%M')}"
            else:
                subscription_info = f"⏰ {subscription.title()} истекла {end_date.strftime('%d.%m.%Y')}"
        except:
            subscription_info = f"❓ {subscription} (ошибка даты)"
    
    # Формируем информацию о платежах
    payment_info = "💰 Платежей не было"
    if payment_stats and payment_stats[0] > 0:
        payment_count, total_amount = payment_stats
        payment_info = f"💰 Платежей: {payment_count}, на сумму: {total_amount or 0}₽"
    
    # Формируем список последних сказок
    stories_text = "📚 Сказок пока нет"
    if recent_stories:
        stories_list = []
        for title, created_at in recent_stories:
            try:
                date = datetime.fromisoformat(created_at).strftime('%d.%m')
                # Экранируем специальные символы для HTML
                safe_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                short_title = safe_title[:30] + "..." if len(safe_title) > 30 else safe_title
                stories_list.append(f"• {short_title} ({date})")
            except:
                # Экранируем специальные символы для HTML
                safe_title = title.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                short_title = safe_title[:30] + "..." if len(safe_title) > 30 else safe_title
                stories_list.append(f"• {short_title}")
        
        stories_text = f"📚 Последние сказки ({total_stories} всего):\n" + "\n".join(stories_list)
    
    # Экранируем имя пользователя для HTML
    safe_name = name.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Формируем полный текст с HTML форматированием
    text = f"""👤 <b>Информация о пользователе</b>

<b>ID:</b> {uid}
<b>Имя:</b> {safe_name}
<b>Статус:</b> {status_text}

<b>📊 Статистика:</b>
📚 Использовано сказок: {stories_used}
📖 Создано сказок: {total_stories}
✅ Согласие с условиями: {'Да' if agreed_terms else 'Нет'}


<b>💎 Подписка:</b>
{subscription_info}

<b>💰 Платежи:</b>
{payment_info}

<b>📚 Сказки:</b>
{stories_text}

<b>🕐 Последняя активность:</b>
{last_paid or 'Не определена'}"""
    
    # Формируем клавиатуру с действиями
    keyboard = []
    
    # Действия с пользователем
    if is_blocked:
        keyboard.append([InlineKeyboardButton("✅ Разблокировать", callback_data=f"unblock_user_{user_id}")])
    else:
        keyboard.append([InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block_user_{user_id}")])
    
    if subscription and subscription_end:
        keyboard.append([InlineKeyboardButton("➕ Продлить подписку", callback_data=f"extend_sub_{user_id}")])
    
    # Навигация
    keyboard.append([InlineKeyboardButton("👥 К списку пользователей", callback_data="admin_users_list")])
    keyboard.append([InlineKeyboardButton("🔙 Админ панель", callback_data="admin_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Используем HTML форматирование вместо Markdown
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def handle_tester_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с тестерами"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    action_data = query.data.split("_")
    
    try:
        if len(action_data) >= 3:
            action = "_".join(action_data[:2])  # make_tester или remove_tester
            user_id = int(action_data[2])
        else:
            await query.edit_message_text("❌ Неверный формат команды")
            return
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный ID пользователя")
        return
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    if action == "make_tester":
        c.execute("UPDATE users SET is_tester = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await query.answer("✅ Пользователь добавлен в тестеры", show_alert=True)
        
    elif action == "remove_tester":
        c.execute("UPDATE users SET is_tester = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await query.answer("✅ Пользователь удален из тестеров", show_alert=True)
    
    else:
        conn.close()
        await query.edit_message_text("❌ Неизвестное действие")
        return
    
    # Обновляем информацию о пользователе
    context.user_data['temp_callback'] = f"user_info_{user_id}"
    await show_user_info(update, context)



async def handle_user_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий с пользователями"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    action_data = query.data.split("_")
    action = action_data[0] + "_" + action_data[1]  # block_user, unblock_user, etc.
    
    try:
        user_id = int(action_data[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный ID пользователя")
        return
    
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()
    
    if action == "block_user":
        c.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await query.answer("✅ Пользователь заблокирован", show_alert=True)
        # Обновляем информацию о пользователе
        context.user_data['temp_callback'] = f"user_info_{user_id}"
        await show_user_info(update, context)
        
    elif action == "unblock_user":
        c.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await query.answer("✅ Пользователь разблокирован", show_alert=True)
        # Обновляем информацию о пользователе
        context.user_data['temp_callback'] = f"user_info_{user_id}"
        await show_user_info(update, context)
        
    elif action == "reset_stories":
        c.execute("UPDATE users SET stories_used = 0 WHERE id = ?", (user_id,))
        conn.commit()
        conn.close()
        
        await query.answer("✅ Счетчик сказок сброшен", show_alert=True)
        # Обновляем информацию о пользователе
        context.user_data['temp_callback'] = f"user_info_{user_id}"
        await show_user_info(update, context)
        
    elif action == "extend_sub":
        # Показываем меню выбора тарифа для продления
        keyboard = [
            [InlineKeyboardButton("📅 Неделя", callback_data=f"extend_week_{user_id}")],
            [InlineKeyboardButton("📅 Месяц", callback_data=f"extend_month_{user_id}")],
            [InlineKeyboardButton("📅 Год", callback_data=f"extend_year_{user_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"user_info_{user_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"📅 Выберите тариф для продления подписки пользователя {user_id}:",
            reply_markup=reply_markup
        )
        conn.close()

async def handle_extend_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка продления подписки"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    action_data = query.data.split("_")
    tariff = action_data[1]  # week, month, year
    
    try:
        user_id = int(action_data[2])
    except (IndexError, ValueError):
        await query.edit_message_text("❌ Неверный ID пользователя")
        return
    
    if tariff not in TARIFFS:
        await query.edit_message_text("❌ Неверный тариф")
        return
    
    # Активируем подписку
    activate_subscription(user_id, tariff)
    
    tariff_info = TARIFFS[tariff]
    
    await query.answer(f"✅ Подписка {tariff} активирована для пользователя {user_id}", show_alert=True)
    
    # Возвращаемся к информации о пользователе
    context.user_data['temp_callback'] = f"user_info_{user_id}"
    await show_user_info(update, context)

# Обновите функцию handle_admin_callback, добавив новый пункт меню:

async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка админских callback-запросов"""
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.edit_message_text("❌ У вас нет прав администратора")
        return
    
    if query.data == "admin_stats":
        stats = get_user_stats()
        text = f"""📊 *Подробная статистика*

👥 Всего пользователей: {stats['total_users']}
💎 Активных подписчиков: {stats['active_subscribers']}
🚫 Заблокированных: {stats['blocked_users']}
📚 Всего сказок создано: {stats['total_stories']}

📈 *Конверсия:*
Подписчиков от общего числа: {(stats['active_subscribers']/max(stats['total_users'], 1)*100):.1f}%"""
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "admin_users":
        text = """👤 *Управление пользователями*

Доступные команды:
• /block\\_user <user\\_id> - заблокировать пользователя
• /unblock\\_user <user\\_id> - разблокировать пользователя
• /user\\_info <user\\_id> - информация о пользователе

Или используйте список пользователей ниже:"""
        
        keyboard = [
            [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users_list")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "admin_users_list":
        await show_users_list(update, context, page=0)
    
    elif query.data.startswith("users_page_"):
        page = int(query.data.split("_")[2])
        await show_users_list(update, context, page=page)
    
    elif query.data.startswith("user_info_"):
        await show_user_info(update, context)
    
    elif query.data.startswith(("block_user_", "unblock_user_", "reset_stories_", "extend_sub_")):
        await handle_user_action(update, context)
    
    elif query.data.startswith("extend_"):
        await handle_extend_subscription(update, context)
    
    elif query.data == "admin_subscriptions":
        text = """💰 *Управление подписками*

Доступные команды:
• /extend\\_sub <user\\_id> <tariff> - продлить подписку
  Тарифы: week, month, year
• /reset\\_stories <user\\_id> - сбросить счетчик сказок
• /sub\\_info <user\\_id> - информация о подписке

Используйте команды в чате с ботом."""
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "admin_prices":
        await show_price_management(update, context)
    
    elif query.data == "admin_back":
        # Возвращаемся к главной админской панели
        await admin_panel(update, context)

# Также обновите функцию admin_panel, добавив кнопку "Список пользователей":

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админская панель"""
    if update.effective_user.id != ADMIN_ID:
        if update.callback_query:
            await update.callback_query.edit_message_text("❌ У вас нет прав администратора")
        else:
            await update.message.reply_text("❌ У вас нет прав администратора")
        return
    
    stats = get_user_stats()
    
    keyboard = [
        [InlineKeyboardButton("👥 Список пользователей", callback_data="admin_users_list")],
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton("💸 Управление ценами", callback_data="admin_prices")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""🔧 *Админская панель*

📊 *Статистика:*
👥 Всего пользователей: {stats['total_users']}
💎 Активных подписчиков: {stats['active_subscribers']}
🚫 Заблокированных: {stats['blocked_users']}
📚 Всего сказок: {stats['total_stories']}"""
    
    # Проверяем, вызвана ли функция из callback или из команды
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')



# ==================== Обработчики callback-запросов ====================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главный обработчик callback-запросов"""
    query = update.callback_query
    data = query.data
    
    # ОТВЕЧАЕМ НА CALLBACK ТОЛЬКО ОДИН РАЗ (здесь)
    await query.answer()
    
    # Проверяем, является ли запрос админским
    admin_command_prefixes = [
        "admin_", "user_info_", "users_page_", "block_user_", "unblock_user_",
        "reset_stories_", "extend_", "remove_tester_", 
        "edit_prompt_", "show_current_prompts", "reset_prompts"
    ]
    if any(data.startswith(prefix) for prefix in admin_command_prefixes):
        await handle_admin_callback(update, context)
        return
    
    # Проверяем, заблокирован ли пользователь (кроме админских команд)
    if is_user_blocked(query.from_user.id):
        await query.edit_message_text("❌ Ваш аккаунт заблокирован")
        return
    
    # Сразу отвечаем на callback query, чтобы избежать таймаута
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")

    try:
        # Обработка согласия
        if data == "agree_terms":
            await handle_agree_terms(update, context)
            return

        # ИСПРАВЛЕНИЕ: Добавляем обработку подтверждения пользовательского сюжета
        elif data in ["confirm_custom_plot", "edit_custom_plot"]:
            await handle_custom_plot_confirmation(update, context)
            return

        # ИСПРАВЛЕНИЕ: Добавляем обработку подтверждения пользовательской морали
        elif data in ["confirm_custom_moral", "back_to_moral"]:
            await handle_custom_moral_confirmation(update, context)
            return

        # Проверяем, заблокирован ли пользователь (кроме админских команд)
        if not data.startswith("admin_") and not data.startswith("users_page_") and not data.startswith("user_info_") and not data.startswith(("block_user_", "unblock_user_", "reset_stories_", "extend_", "make_tester_", "remove_tester_", "edit_prompt_", "show_current_prompts", "reset_prompts")) and is_user_blocked(query.from_user.id):
            try:
                await query.edit_message_text("❌ Ваш аккаунт заблокирован")
            except:
                pass
            return

        # Основные команды меню
        if data == "start":
            await start(update, context)
        elif data == "create_story":
            await create_story(update, context)
        elif data == "my_stories":
            await show_my_stories(update, context)
        elif data == "subscription":
            await show_subscription(update, context)
        elif data == "buy_subscription":
            await show_tariffs(update, context)
        elif data == "help":
            await help_command(update, context)
        elif query.data == "admin_back":
            await admin_panel(update, context)


        # Управление промптами (только для админа)
        elif data == "admin_prompts":
            if query.from_user.id != ADMIN_ID:
                try:
                    await query.edit_message_text("❌ У вас нет прав администратора")
                except:
                    pass
                return
            await show_prompt_management(update, context)
        
        elif data.startswith("edit_prompt_"):
            if query.from_user.id != ADMIN_ID:
                try:
                    await query.edit_message_text("❌ У вас нет прав администратора")
                except:
                    pass
                return
            await edit_prompt(update, context)
        
        elif data == "show_current_prompts":
            if query.from_user.id != ADMIN_ID:
                try:
                    await query.edit_message_text("❌ У вас нет прав администратора")
                except:
                    pass
                return
            await show_current_prompts(update, context)
        
        elif data == "reset_prompts":
            if query.from_user.id != ADMIN_ID:
                try:
                    await query.edit_message_text("❌ У вас нет прав администратора")
                except:
                    pass
                return
            await reset_prompts(update, context)
        
        # Обработка выбора темы
        elif data.startswith("theme_"):
            await show_plot_selection(update, context)
        
        # Обработка выбора сюжета
        elif data.startswith("plot_"):
            await show_plot_confirmation(update, context)
        
        # Подтверждение сюжета
        elif data == "confirm_plot":
            await request_child_info(update, context)
        
        # Обработка выбора возраста
        elif data.startswith("age_"):
            await handle_age_selection(update, context)
        
        # Обработка выбора морали
        elif data.startswith("moral_"):
            await handle_moral_selection(update, context)
        
        # Просмотр конкретной сказки
        elif data.startswith("story_"):
            await show_story(update, context)
        
        # Обработка платежей
        elif data.startswith("pay_"):
            await process_payment(update, context)
        elif data.startswith("check_payment_"):
            await check_payment(update, context)
        
        # Остальные обработчики остаются без изменений...
        # [здесь остальная часть функции handle_callback_query]
        
        else:
            logger.warning(f"Unknown callback data: {data}")
            try:
                await query.edit_message_text("❓ Неизвестная команда")
            except:
                pass
            
    except Exception as e:
        logger.error(f"Error in callback handler: {str(e)}")
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Произошла ошибка. Попробуйте позже."
            )
        except:
            pass



def main():
    """Основная функция запуска бота"""
    # Проверяем наличие файла базы данных и инициализируем, если нужно
    if not os.path.exists("bot.db"):
        print("База данных не найдена. Инициализация...")
        init_db()
    else:
        # Проверяем, есть ли таблица users
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not c.fetchone():
            print("Таблица users не найдена. Инициализация базы данных...")
            init_db()
        conn.close()

    # Загружаем цены из базы данных
    load_prices_from_db()
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # Добавляем обработчики callback-запросов
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Добавляем обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    
    # Запускаем бота
    logger.info("Bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()



