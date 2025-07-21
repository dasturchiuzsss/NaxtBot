import sqlite3
import logging
from datetime import datetime

DB_PATH = "bot_database.db"

def create_connection():
	try:
		conn = sqlite3.connect(DB_PATH)
		return conn
	except sqlite3.Error as e:
		logging.error(f"Database connection error: {e}")
		return None

def create_tables():
	conn = create_connection()
	if not conn:
		logging.error("Ma'lumotlar bazasiga ulanib bo'lmadi")
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            bot_id TEXT UNIQUE,
            balance REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrer_id INTEGER,
            referral_count INTEGER DEFAULT 0,
            phone_number TEXT,
            country_code TEXT,
            is_blocked INTEGER DEFAULT 0
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            transaction_type TEXT,
            payment_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS counters (
            name TEXT PRIMARY KEY,
            value INTEGER
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            card_number TEXT NOT NULL,
            full_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            wallet_id INTEGER,
            amount REAL,
            receipt_photo_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (wallet_id) REFERENCES wallets (id)
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS payment_methods (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            payment_token TEXT NOT NULL,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_channel_subscriptions (
            user_id INTEGER,
            channel_id INTEGER,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, channel_id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (channel_id) REFERENCES channels (id)
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL UNIQUE,
            channel_name TEXT NOT NULL,
            invite_link TEXT NOT NULL,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS required_bots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot_token TEXT NOT NULL,
            bot_username TEXT NOT NULL,
            bot_name TEXT NOT NULL,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            added_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL DEFAULT 50000,
            media_type TEXT CHECK(media_type IN ('photo', 'video')),
            media_file_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            created_by INTEGER NOT NULL,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        ''')
		
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS product_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
        ''')
		
		cursor.execute("INSERT OR IGNORE INTO counters (name, value) VALUES ('bot_id', 0)")
		cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_reward_uzb', '100')")
		cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_reward_foreign', '80')")
		cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('min_payment_amount', '1000')")
		cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('order_channel_id', '')")
		
		cursor.execute("SELECT COUNT(*) FROM bot_status")
		count = cursor.fetchone()[0]
		if count == 0:
			cursor.execute("INSERT INTO bot_status (is_active, updated_by) VALUES (1, NULL)")
		
		conn.commit()
		logging.info("Barcha ma'lumotlar bazasi jadvallari muvaffaqiyatli yaratildi")
		return True
	except sqlite3.Error as e:
		logging.error(f"Jadvallarni yaratishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_next_bot_id():
	conn = create_connection()
	if not conn:
		return "ERROR"
	
	cursor = conn.cursor()
	next_id = "ERROR"
	
	try:
		cursor.execute("UPDATE counters SET value = value + 1 WHERE name = 'bot_id'")
		cursor.execute("SELECT value FROM counters WHERE name = 'bot_id'")
		result = cursor.fetchone()
		if result:
			next_id = result[0]
		
		conn.commit()
	except sqlite3.Error as e:
		logging.error(f"Bot ID olishda xatolik: {e}")
	finally:
		conn.close()
	
	return str(next_id)

async def add_user(user_id, username, full_name, bot_id, bot=None, phone_number=None, country_code=None,
                   referrer_id=None):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
		existing_user = cursor.fetchone()
		
		if existing_user:
			if phone_number:
				cursor.execute(
					"UPDATE users SET phone_number = ?, country_code = ? WHERE id = ?",
					(phone_number, country_code, user_id)
				)
				conn.commit()
			return True
		
		if referrer_id:
			cursor.execute(
				"INSERT OR IGNORE INTO users (id, username, full_name, bot_id, referrer_id, phone_number, country_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
				(user_id, username, full_name, bot_id, referrer_id, phone_number, country_code)
			)
			
			cursor.execute(
				"UPDATE users SET referral_count = referral_count + 1 WHERE id = ?",
				(referrer_id,)
			)
			
			is_foreign = False
			if country_code and country_code != "UZ":
				is_foreign = True
			
			reward_key = "referral_reward_foreign" if is_foreign else "referral_reward_uzb"
			cursor.execute("SELECT value FROM settings WHERE key = ?", (reward_key,))
			reward_row = cursor.fetchone()
			reward_amount = float(reward_row[0]) if reward_row else 100.0
			
			cursor.execute(
				"UPDATE users SET balance = balance + ? WHERE id = ?",
				(reward_amount, referrer_id)
			)
			
			cursor.execute(
				"INSERT INTO transactions (user_id, amount, transaction_type, payment_id) VALUES (?, ?, ?, ?)",
				(referrer_id, reward_amount, "referral", f"ref_{user_id}")
			)
			
			if bot:
				try:
					cursor.execute("SELECT balance FROM users WHERE id = ?", (referrer_id,))
					referrer_balance = cursor.fetchone()[0]
					
					country_name = "O'zbekiston" if country_code == "UZ" else "Boshqa davlat"
					
					await bot.send_message(
						chat_id=referrer_id,
						text=f"🎉 Tabriklaymiz! Yangi foydalanuvchi sizning referal havolangiz orqali ro'yxatdan o'tdi!\n\n"
						     f"👤 Foydalanuvchi: {full_name}\n"
						     f"🌍 Mamlakat: {country_name}\n"
						     f"💰 Sizga berilgan mukofot: {reward_amount} so'm\n"
						     f"💵 Yangi balans: {referrer_balance} so'm\n\n"
						     f"Referal dasturida ishtirok etganingiz uchun rahmat!"
					)
				except Exception as e:
					logging.error(f"Referal bildirishnomasi yuborishda xatolik: {e}")
		else:
			cursor.execute(
				"INSERT OR IGNORE INTO users (id, username, full_name, bot_id, phone_number, country_code) VALUES (?, ?, ?, ?, ?, ?)",
				(user_id, username, full_name, bot_id, phone_number, country_code)
			)
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi qo'shishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_user(user_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
		user = cursor.fetchone()
		return user
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def get_user_by_bot_id(bot_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM users WHERE bot_id = ?", (bot_id,))
		user = cursor.fetchone()
		return user
	except sqlite3.Error as e:
		logging.error(f"Bot ID orqali foydalanuvchi olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def update_balance(user_id, new_balance):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Balansni yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_transaction(user_id, amount, transaction_type, payment_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO transactions (user_id, amount, transaction_type, payment_id) VALUES (?, ?, ?, ?)",
			(user_id, amount, transaction_type, payment_id)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Tranzaksiya qo'shishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_user_transactions(user_id):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
		transactions = cursor.fetchall()
		return transactions
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi tranzaksiyalarini olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_all_users():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM users")
		users = cursor.fetchall()
		return users
	except sqlite3.Error as e:
		logging.error(f"Barcha foydalanuvchilarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def add_wallet(name, card_number, full_name):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO wallets (name, card_number, full_name) VALUES (?, ?, ?)",
			(name, card_number, full_name)
		)
		wallet_id = cursor.lastrowid
		conn.commit()
		return True, wallet_id
	except sqlite3.Error as e:
		logging.error(f"Hamyon qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_all_wallets():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM wallets ORDER BY name")
		wallets = cursor.fetchall()
		return wallets
	except sqlite3.Error as e:
		logging.error(f"Barcha hamyonlarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_wallet(wallet_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM wallets WHERE id = ?", (wallet_id,))
		wallet = cursor.fetchone()
		return wallet
	except sqlite3.Error as e:
		logging.error(f"Hamyonni olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def delete_wallet(wallet_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM wallets WHERE id = ?", (wallet_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Hamyonni o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_pending_payment(user_id, wallet_id, amount, receipt_photo_id):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO pending_payments (user_id, wallet_id, amount, receipt_photo_id) VALUES (?, ?, ?, ?)",
			(user_id, wallet_id, amount, receipt_photo_id)
		)
		payment_id = cursor.lastrowid
		conn.commit()
		return True, payment_id
	except sqlite3.Error as e:
		logging.error(f"Kutilayotgan to'lovni qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_pending_payment(payment_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM pending_payments WHERE id = ?", (payment_id,))
		payment = cursor.fetchone()
		return payment
	except sqlite3.Error as e:
		logging.error(f"Kutilayotgan to'lovni olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def update_payment_status(payment_id, status):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE pending_payments SET status = ? WHERE id = ?", (status, payment_id))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"To'lov holatini yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_payment_method(name, payment_token, image_url):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO payment_methods (name, payment_token, image_url) VALUES (?, ?, ?)",
			(name, payment_token, image_url)
		)
		method_id = cursor.lastrowid
		conn.commit()
		return True, method_id
	except sqlite3.Error as e:
		logging.error(f"To'lov usulini qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_all_payment_methods():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM payment_methods ORDER BY name")
		payments = cursor.fetchall()
		return payments
	except sqlite3.Error as e:
		logging.error(f"Barcha to'lov usullarini olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_payment_method(payment_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM payment_methods WHERE id = ?", (payment_id,))
		payment = cursor.fetchone()
		return payment
	except sqlite3.Error as e:
		logging.error(f"To'lov usulini olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def delete_payment_method(payment_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM payment_methods WHERE id = ?", (payment_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"To'lov usulini o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_setting(key, default=None):
	conn = create_connection()
	if not conn:
		return default
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
		setting = cursor.fetchone()
		return setting[0] if setting else default
	except sqlite3.Error as e:
		logging.error(f"Sozlamani olishda xatolik: {e}")
		return default
	finally:
		conn.close()

def update_setting(key, value):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
			(key, value)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Sozlamani yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_top_referrers(limit=10):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"SELECT id, username, full_name, referral_count FROM users ORDER BY referral_count DESC LIMIT ?",
			(limit,)
		)
		top_referrers = cursor.fetchall()
		return top_referrers
	except sqlite3.Error as e:
		logging.error(f"Top referrallarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_user_referrals(user_id):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"SELECT * FROM users WHERE referrer_id = ?",
			(user_id,)
		)
		referrals = cursor.fetchall()
		return referrals
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi referrallarini olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_user_referral_count(user_id):
	conn = create_connection()
	if not conn:
		return 0
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT referral_count FROM users WHERE id = ?", (user_id,))
		result = cursor.fetchone()
		return result[0] if result else 0
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi referal sonini olishda xatolik: {e}")
		return 0
	finally:
		conn.close()

def block_user(user_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchini bloklashda xatolik: {e}")
		return False
	finally:
		conn.close()

def unblock_user(user_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi blokini ochishda xatolik: {e}")
		return False
	finally:
		conn.close()

def is_user_blocked(user_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,))
		result = cursor.fetchone()
		return bool(result[0]) if result else False
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi bloklanganligini tekshirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def search_user_by_id(user_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
		user = cursor.fetchone()
		return user
	except sqlite3.Error as e:
		logging.error(f"ID orqali foydalanuvchi qidirishda xatolik: {e}")
		return None
	finally:
		conn.close()

def search_user_by_bot_id(bot_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM users WHERE bot_id = ?", (bot_id,))
		user = cursor.fetchone()
		return user
	except sqlite3.Error as e:
		logging.error(f"Bot ID orqali foydalanuvchi qidirishda xatolik: {e}")
		return None
	finally:
		conn.close()

def add_money_to_user(user_id, amount):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
		result = cursor.fetchone()
		if not result:
			return False
		
		current_balance = result[0]
		new_balance = current_balance + amount
		
		cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
		
		cursor.execute(
			"INSERT INTO transactions (user_id, amount, transaction_type, payment_id) VALUES (?, ?, ?, ?)",
			(user_id, amount, "admin_add", f"admin_add_{datetime.now().timestamp()}")
		)
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchiga pul qo'shishda xatolik: {e}")
		return False
	finally:
		conn.close()

def subtract_money_from_user(user_id, amount):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
		result = cursor.fetchone()
		if not result:
			return False
		
		current_balance = result[0]
		new_balance = current_balance - amount
		
		if new_balance < 0:
			new_balance = 0
		
		cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
		
		cursor.execute(
			"INSERT INTO transactions (user_id, amount, transaction_type, payment_id) VALUES (?, ?, ?, ?)",
			(user_id, -amount, "admin_subtract", f"admin_subtract_{datetime.now().timestamp()}")
		)
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchidan pul ayirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_all_channels():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM channels ORDER BY is_active DESC, name")
		channels = cursor.fetchall()
		return channels
	except sqlite3.Error as e:
		logging.error(f"Barcha kanallarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_active_channels():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM channels WHERE is_active = 1 ORDER BY name")
		channels = cursor.fetchall()
		return channels
	except sqlite3.Error as e:
		logging.error(f"Faol kanallarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def add_channel(username, name, is_active=1):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		if username.startswith('@'):
			username = username[1:]
		
		cursor.execute("SELECT id FROM channels WHERE username = ?", (username,))
		existing_channel = cursor.fetchone()
		
		if existing_channel:
			cursor.execute(
				"UPDATE channels SET name = ?, is_active = ? WHERE username = ?",
				(name, is_active, username)
			)
			conn.commit()
			return True, existing_channel[0]
		
		cursor.execute(
			"INSERT INTO channels (username, name, is_active) VALUES (?, ?, ?)",
			(username, name, is_active)
		)
		
		channel_id = cursor.lastrowid
		conn.commit()
		return True, channel_id
	except sqlite3.Error as e:
		logging.error(f"Kanal qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_channel(channel_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM channels WHERE id = ?", (channel_id,))
		channel = cursor.fetchone()
		return channel
	except sqlite3.Error as e:
		logging.error(f"Kanalni olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def get_channel_by_username(username):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		if username.startswith('@'):
			username = username[1:]
		
		cursor.execute("SELECT * FROM channels WHERE username = ?", (username,))
		channel = cursor.fetchone()
		return channel
	except sqlite3.Error as e:
		logging.error(f"Username orqali kanalni olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def update_channel_status(channel_id, is_active):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"UPDATE channels SET is_active = ? WHERE id = ?",
			(is_active, channel_id)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Kanal holatini yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def delete_channel(channel_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
		cursor.execute("DELETE FROM user_channel_subscriptions WHERE channel_id = ?", (channel_id,))
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Kanalni o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_user_subscription(user_id, channel_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT OR REPLACE INTO user_channel_subscriptions (user_id, channel_id) VALUES (?, ?)",
			(user_id, channel_id)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi obunasini qo'shishda xatolik: {e}")
		return False
	finally:
		conn.close()

def remove_user_subscription(user_id, channel_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"DELETE FROM user_channel_subscriptions WHERE user_id = ? AND channel_id = ?",
			(user_id, channel_id)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi obunasini olib tashlashda xatolik: {e}")
		return False
	finally:
		conn.close()

def is_user_subscribed(user_id, channel_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"SELECT 1 FROM user_channel_subscriptions WHERE user_id = ? AND channel_id = ?",
			(user_id, channel_id)
		)
		result = cursor.fetchone()
		return bool(result)
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi obunasini tekshirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_user_subscriptions(user_id):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("""
            SELECT c.* FROM channels c
            JOIN user_channel_subscriptions ucs ON c.id = ucs.channel_id
            WHERE ucs.user_id = ?
            ORDER BY c.name
        """, (user_id,))
		channels = cursor.fetchall()
		return channels
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi obunalarini olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_channel_subscribers_count(channel_id):
	conn = create_connection()
	if not conn:
		return 0
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"SELECT COUNT(*) FROM user_channel_subscriptions WHERE channel_id = ?",
			(channel_id,)
		)
		count = cursor.fetchone()[0]
		return count
	except sqlite3.Error as e:
		logging.error(f"Kanal obunachilari sonini olishda xatolik: {e}")
		return 0
	finally:
		conn.close()

def check_user_subscriptions(user_id):
	active_channels = get_active_channels()
	if not active_channels:
		return True, []
	
	not_subscribed_channels = []
	
	for channel in active_channels:
		channel_id = channel[0]
		if not is_user_subscribed(user_id, channel_id):
			not_subscribed_channels.append(channel)
	
	is_subscribed_to_all = len(not_subscribed_channels) == 0
	return is_subscribed_to_all, not_subscribed_channels

def add_required_channel(channel_id, channel_name, invite_link, added_by):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT id FROM required_channels WHERE channel_id = ?", (channel_id,))
		existing_channel = cursor.fetchone()
		
		if existing_channel:
			cursor.execute(
				"UPDATE required_channels SET channel_name = ?, invite_link = ? WHERE channel_id = ?",
				(channel_name, invite_link, channel_id)
			)
			logging.info(f"Mavjud kanal yangilandi {channel_id} yangi havola bilan: {invite_link}")
		else:
			cursor.execute(
				"INSERT INTO required_channels (channel_id, channel_name, invite_link, added_by) VALUES (?, ?, ?, ?)",
				(channel_id, channel_name, invite_link, added_by)
			)
			logging.info(f"Yangi kanal qo'shildi {channel_id} havola bilan: {invite_link}")
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Majburiy kanal qo'shishda ma'lumotlar bazasi xatoligi: {e}")
		return False
	finally:
		conn.close()

def get_required_channels():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM required_channels ORDER BY id")
		channels = cursor.fetchall()
		
		result = []
		for channel in channels:
			result.append({
				'id': channel[0],
				'channel_id': channel[1],
				'channel_name': channel[2],
				'invite_link': channel[3],
				'added_by': channel[4],
				'created_at': channel[5]
			})
		
		return result
	except sqlite3.Error as e:
		logging.error(f"Majburiy kanallarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def delete_required_channel(channel_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM required_channels WHERE id = ?", (channel_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Majburiy kanalni o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_required_bot(bot_token, bot_username, bot_name, added_by):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO required_bots (bot_token, bot_username, bot_name, added_by) VALUES (?, ?, ?, ?)",
			(bot_token, bot_username, bot_name, added_by)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Majburiy bot qo'shishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_required_bots():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM required_bots ORDER BY id")
		bots = cursor.fetchall()
		
		result = []
		for bot in bots:
			result.append({
				'id': bot[0],
				'bot_token': bot[1],
				'bot_username': bot[2],
				'bot_name': bot[3],
				'added_by': bot[4],
				'created_at': bot[5]
			})
		
		return result
	except sqlite3.Error as e:
		logging.error(f"Majburiy botlarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def delete_required_bot(bot_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM required_bots WHERE id = ?", (bot_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Majburiy botni o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_custom_link(name, url, added_by):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO custom_links (name, url, added_by) VALUES (?, ?, ?)",
			(name, url, added_by)
		)
		link_id = cursor.lastrowid
		conn.commit()
		return True, link_id
	except sqlite3.Error as e:
		logging.error(f"Maxsus havola qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_custom_links():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM custom_links ORDER BY name")
		links = cursor.fetchall()
		return links
	except sqlite3.Error as e:
		logging.error(f"Maxsus havolalarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def delete_custom_link(link_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM custom_links WHERE id = ?", (link_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Maxsus havolani o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_bot_status():
	conn = create_connection()
	if not conn:
		return True
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT is_active FROM bot_status ORDER BY id DESC LIMIT 1")
		result = cursor.fetchone()
		return bool(result[0]) if result else True
	except sqlite3.Error as e:
		logging.error(f"Bot holatini olishda xatolik: {e}")
		return True
	finally:
		conn.close()

def update_bot_status(is_active, updated_by):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO bot_status (is_active, updated_by) VALUES (?, ?)",
			(is_active, updated_by)
		)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Bot holatini yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_product(name, description, media_type, media_file_id, created_by, price=50000):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO products (name, description, price, media_type, media_file_id, created_by) VALUES (?, ?, ?, ?, ?, ?)",
			(name, description, price, media_type, media_file_id, created_by)
		)
		product_id = cursor.lastrowid
		conn.commit()
		return True, product_id
	except sqlite3.Error as e:
		logging.error(f"Mahsulot qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_all_products(active_only=True):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		if active_only:
			cursor.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY created_at DESC")
		else:
			cursor.execute("SELECT * FROM products ORDER BY created_at DESC")
		products = cursor.fetchall()
		return products
	except sqlite3.Error as e:
		logging.error(f"Mahsulotlarni olishda xatolik: {e}")
		return []
	finally:
		conn.close()

def get_product(product_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
		product = cursor.fetchone()
		return product
	except sqlite3.Error as e:
		logging.error(f"Mahsulot ma'lumotlarini olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def update_product(product_id, name=None, description=None, is_active=None):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		updates = []
		params = []
		
		if name is not None:
			updates.append("name = ?")
			params.append(name)
		
		if description is not None:
			updates.append("description = ?")
			params.append(description)
		
		if is_active is not None:
			updates.append("is_active = ?")
			params.append(1 if is_active else 0)
		
		if not updates:
			return False
		
		params.append(product_id)
		query = f"UPDATE products SET {', '.join(updates)} WHERE id = ?"
		
		cursor.execute(query, params)
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Mahsulotni yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def delete_product(product_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE products SET is_active = 0 WHERE id = ?", (product_id,))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Mahsulotni o'chirishda xatolik: {e}")
		return False
	finally:
		conn.close()

def add_product_order(user_id, product_id, amount, payment_method):
	conn = create_connection()
	if not conn:
		return False, None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO product_orders (user_id, product_id, amount, payment_method) VALUES (?, ?, ?, ?)",
			(user_id, product_id, amount, payment_method)
		)
		order_id = cursor.lastrowid
		conn.commit()
		return True, order_id
	except sqlite3.Error as e:
		logging.error(f"Mahsulot buyurtmasini qo'shishda xatolik: {e}")
		return False, None
	finally:
		conn.close()

def get_product_order(order_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("""
            SELECT po.*, p.name as product_name, u.full_name as user_name, u.bot_id
            FROM product_orders po
            JOIN products p ON po.product_id = p.id
            JOIN users u ON po.user_id = u.id
            WHERE po.id = ?
        """, (order_id,))
		order = cursor.fetchone()
		return order
	except sqlite3.Error as e:
		logging.error(f"Mahsulot buyurtmasi ma'lumotlarini olishda xatolik: {e}")
		return None
	finally:
		conn.close()

def update_product_order_status(order_id, status):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE product_orders SET status = ? WHERE id = ?", (status, order_id))
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Buyurtma holatini yangilashda xatolik: {e}")
		return False
	finally:
		conn.close()

def get_user_product_orders(user_id, limit=10):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("""
            SELECT po.*, p.name as product_name
            FROM product_orders po
            JOIN products p ON po.product_id = p.id
            WHERE po.user_id = ?
            ORDER BY po.created_at DESC
            LIMIT ?
        """, (user_id, limit))
		orders = cursor.fetchall()
		return orders
	except sqlite3.Error as e:
		logging.error(f"Foydalanuvchi buyurtmalarini olishda xatolik: {e}")
		return []
	finally:
		conn.close()
