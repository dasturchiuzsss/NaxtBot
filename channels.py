import logging
import sqlite3
import time
import json
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import (
	Message, CallbackQuery, InlineKeyboardMarkup,
	InlineKeyboardButton, ChatJoinRequest, TelegramObject, User
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram import BaseMiddleware
from aiogram.exceptions import TelegramBadRequest
import aiohttp
from config import ADMINS, BOT_TOKEN, DB_PATH, TELEGRAM_API_BASE
from database import create_connection
# Mavjud importlardan keyin quyidagi importni qo'shing
from typing import Any, Awaitable, Callable, Dict
import admin
import re
from database import get_setting

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

channels_router = Router()

subscription_cache = {}
CACHE_TIMEOUT = 300

join_request_users = {}

class ChannelState(StatesGroup):
	waiting_for_channel_forward = State()
	waiting_for_channel_name = State()
	waiting_for_channel_link = State()
	waiting_for_bot_name = State()
	waiting_for_bot_username = State()
	waiting_for_bot_token = State()
	waiting_for_link_name = State()
	waiting_for_link_url = State()

class ChannelStates(StatesGroup):
	waiting_for_channel_id = State()
	waiting_for_channel_title = State()
	waiting_for_channel_url = State()
	waiting_for_link_name = State()
	waiting_for_link_url = State()

# BotStatusMiddleware klassini qo'shing
class BotStatusMiddleware(BaseMiddleware):
	async def __call__(
		  self,
		  handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
		  event: TelegramObject,
		  data: Dict[str, Any]
	) -> Any:
		# Foydalanuvchini olish
		user = data.get("event_from_user", None)
		
		if user and isinstance(user, User):
			# Admin bo'lsa, o'tkazib yuborish
			if user.id in ADMINS:
				return await handler(event, data)
			
			# Bot statusini tekshirish
			bot_status = admin.get_bot_status()
			
			# Agar bot active bo'lmasa (ya'ni ta'mirlash rejimida bo'lsa)
			if bot_status != "active":
				bot = data.get("bot")
				
				# Foydalanuvchiga xabar yuborish
				if hasattr(event, "chat") and hasattr(event, "message_id"):
					try:
						await bot.send_message(
							chat_id=event.chat.id,
							text="⚠️ Botda tamirlash ishlari olib borilmoqda. Iltimos, keyinroq qayta urinib ko'ring."
						)
					except Exception as e:
						logging.error(f"Error sending maintenance message: {e}")
					return
				
				# Callback query bo'lsa
				if hasattr(event, "message") and hasattr(event, "id"):
					try:
						await bot.answer_callback_query(
							callback_query_id=event.id,
							text="⚠️ Botda tamirlash ishlari olib borilmoqda. Iltimos, keyinroq qayta urinib ko'ring.",
							show_alert=True
						)
						return
					except Exception as e:
						logging.error(f"Error answering callback query: {e}")
		
		# Agar bot active bo'lsa yoki admin bo'lsa, normal davom etish
		return await handler(event, data)

async def init_channels_tables():
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS required_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id TEXT NOT NULL,
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
        CREATE TABLE IF NOT EXISTS channel_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
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
		
		# Also create bot_status table
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_by INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		# Check if there are any records in bot_status
		cursor.execute("SELECT COUNT(*) FROM bot_status")
		count = cursor.fetchone()[0]
		
		# If no records, insert default active status
		if count == 0:
			cursor.execute(
				"INSERT INTO bot_status (is_active, updated_by) VALUES (?, ?)",
				(1, None)
			)
		
		conn.commit()
		logging.info("Channel tables initialized successfully")
		return True
	except sqlite3.Error as e:
		logging.error(f"Error creating channels tables: {e}")
		return False
	finally:
		conn.close()

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
			logging.info(f"Updated existing channel {channel_id} with new invite link: {invite_link}")
		else:
			cursor.execute(
				"INSERT INTO required_channels (channel_id, channel_name, invite_link, added_by) VALUES (?, ?, ?, ?)",
				(channel_id, channel_name, invite_link, added_by)
			)
			logging.info(f"Added new channel {channel_id} with invite link: {invite_link}")
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Database error in add_required_channel: {e}")
		return False
	finally:
		conn.close()

def add_custom_link(name, url, added_by):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"INSERT INTO custom_links (name, url, added_by) VALUES (?, ?, ?)",
			(name, url, added_by)
		)
		
		conn.commit()
		logging.info(f"Added new custom link: {name} - {url}")
		return True
	except sqlite3.Error as e:
		logging.error(f"Database error in add_custom_link: {e}")
		return False
	finally:
		conn.close()

def get_custom_links():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM custom_links ORDER BY id")
		links = cursor.fetchall()
		
		result = []
		for link in links:
			result.append({
				'id': link[0],
				'name': link[1],
				'url': link[2],
				'added_by': link[3],
				'created_at': link[4]
			})
		
		return result
	except sqlite3.Error as e:
		logging.error(f"Error getting custom links: {e}")
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
		logging.error(f"Error deleting custom link: {e}")
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
		logging.error(f"Error getting required channels: {e}")
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
		logging.error(f"Error deleting required channel: {e}")
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
		logging.error(f"Error adding required bot: {e}")
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
		logging.error(f"Error getting required bots: {e}")
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
		logging.error(f"Error deleting required bot: {e}")
		return False
	finally:
		conn.close()

def save_join_request(user_id, channel_id):
	"""
	Foydalanuvchi qo'shilish so'rovini ma'lumotlar bazasiga saqlash
	"""
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute(
			"SELECT id FROM channel_join_requests WHERE user_id = ? AND channel_id = ?",
			(user_id, channel_id)
		)
		existing = cursor.fetchone()
		
		if existing:
			cursor.execute(
				"UPDATE channel_join_requests SET created_at = CURRENT_TIMESTAMP WHERE id = ?",
				(existing[0],)
			)
		else:
			cursor.execute(
				"INSERT INTO channel_join_requests (user_id, channel_id) VALUES (?, ?)",
				(user_id, channel_id)
			)
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Error saving join request: {e}")
		return False
	finally:
		conn.close()

def check_join_request_in_db(user_id, channel_id):
	"""
	Foydalanuvchi qo'shilish so'rovini ma'lumotlar bazasidan tekshirish
	"""
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS channel_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
		
		cursor.execute(
			"""
			SELECT id FROM channel_join_requests
			WHERE user_id = ? AND channel_id = ?
			AND datetime(created_at) > datetime('now', '-1 day')
			""",
			(user_id, channel_id)
		)
		
		result = cursor.fetchone()
		return result is not None
	except sqlite3.Error as e:
		logging.error(f"Error checking join request: {e}")
		return False
	finally:
		conn.close()

def clear_subscription_cache_for_user(user_id):
	keys_to_remove = []
	for key in subscription_cache.keys():
		if key.startswith(f"sub_{user_id}_") or key.startswith(f"bot_start_{user_id}_"):
			keys_to_remove.append(key)
	
	for key in keys_to_remove:
		subscription_cache.pop(key, None)
	
	logging.info(f"Cleared subscription and bot start cache for user {user_id}")

async def check_bot_permissions(bot, channel_id):
	"""
	Botning kanalda to'g'ri huquqlarga ega ekanligini tekshirish
	"""
	try:
		bot_id = bot.id
		bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot_id)
		
		if bot_member.status != "administrator":
			logging.error(f"Bot is not an administrator in channel {channel_id}")
			return False
		
		can_invite_users = getattr(bot_member, 'can_invite_users', False)
		can_manage_chat = getattr(bot_member, 'can_manage_chat', False)
		
		logging.info(
			f"Bot permissions in channel {channel_id}: can_invite_users={can_invite_users}, can_manage_chat={can_manage_chat}")
		
		if not can_invite_users or not can_manage_chat:
			logging.error(f"Bot does not have required permissions in channel {channel_id}")
			return False
		
		return True
	except Exception as e:
		logging.error(f"Error checking bot permissions: {e}")
		return False

async def check_user_subscribed_to_channel(bot, user_id, channel_id, bypass_cache=False):
	try:
		cache_key = f"sub_{user_id}_{channel_id}"
		if not bypass_cache and cache_key in subscription_cache:
			cache_data = subscription_cache[cache_key]
			if time.time() - cache_data["timestamp"] < CACHE_TIMEOUT:
				logging.debug(
					f"Using cached subscription status for user {user_id} in channel {channel_id}: {cache_data['is_subscribed']}")
				return cache_data["is_subscribed"]
		
		logging.debug(f"Performing fresh check of subscription status for user {user_id} in channel {channel_id}")
		
		try:
			chat = await bot.get_chat(chat_id=channel_id)
			logging.debug(f"Successfully got chat info for {channel_id}: {chat.title}")
		except Exception as chat_error:
			logging.error(f"Error getting chat info for channel {channel_id}: {chat_error}")
			
			if not str(channel_id).startswith('@') and not str(channel_id).startswith('-100'):
				try:
					if str(channel_id).startswith('-'):
						formatted_channel_id = channel_id
					else:
						formatted_channel_id = f"@{channel_id}"
					
					logging.debug(f"Trying with formatted channel ID: {formatted_channel_id}")
					chat = await bot.get_chat(chat_id=formatted_channel_id)
					channel_id = formatted_channel_id
					logging.debug(f"Successfully got chat info with formatted ID: {chat.title}")
				except Exception as format_error:
					logging.error(f"Error with formatted channel ID: {format_error}")
					return False
			else:
				return False
		
		has_permissions = await check_bot_permissions(bot, channel_id)
		if not has_permissions:
			logging.warning(f"Bot does not have required permissions in channel {channel_id}")
		
		chat_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
		status = chat_member.status
		
		logging.debug(f"User {user_id} status in channel {channel_id}: {status}")
		
		is_subscribed = status in ['member', 'administrator', 'creator']
		
		if status == 'restricted':
			is_member = getattr(chat_member, 'is_member', None)
			logging.debug(f"User {user_id} is restricted in channel {channel_id}, is_member: {is_member}")
			if is_member:
				is_subscribed = True
		
		if status == 'left':
			user_request = join_request_users.get(user_id)
			if user_request and str(user_request["channel_id"]) == str(channel_id):
				if time.time() - user_request["timestamp"] < 86400:
					is_subscribed = True
					logging.info(f"User {user_id} has pending join request for channel {channel_id} (from cache)")
			
			if not is_subscribed:
				has_request_in_db = check_join_request_in_db(user_id, channel_id)
				if has_request_in_db:
					is_subscribed = True
					logging.info(f"User {user_id} has pending join request for channel {channel_id} (from database)")
		
		subscription_cache[cache_key] = {
			"timestamp": time.time(),
			"is_subscribed": is_subscribed
		}
		
		logging.info(f"Final subscription status for user {user_id} in channel {channel_id}: {is_subscribed}")
		return is_subscribed
	
	except Exception as e:
		logging.error(f"Error checking channel subscription for user {user_id} in channel {channel_id}: {e}")
		import traceback
		logging.error(traceback.format_exc())
		
		try:
			user_request = join_request_users.get(user_id)
			if user_request and str(user_request["channel_id"]) == str(channel_id):
				if time.time() - user_request["timestamp"] < 86400:
					is_subscribed = True
					logging.info(
						f"User {user_id} has pending join request for channel {channel_id} (from cache fallback)")
					
					subscription_cache[cache_key] = {
						"timestamp": time.time(),
						"is_subscribed": is_subscribed
					}
					
					return is_subscribed
			
			has_request_in_db = check_join_request_in_db(user_id, channel_id)
			if has_request_in_db:
				is_subscribed = True
				logging.info(
					f"User {user_id} has pending join request for channel {channel_id} (from database fallback)")
				
				subscription_cache[cache_key] = {
					"timestamp": time.time(),
					"is_subscribed": is_subscribed
				}
				
				return is_subscribed
		except Exception as req_error:
			logging.error(f"Error checking join request (fallback): {req_error}")
		
		error_text = str(e).lower()
		if "chat not found" in error_text:
			logging.error(f"Channel {channel_id} not found. Please verify the channel ID.")
		elif "user not found" in error_text:
			logging.error(f"User {user_id} not found. Please verify the user ID.")
		elif "bot is not a member" in error_text:
			logging.error(f"Bot is not a member of channel {channel_id}. Please add the bot to the channel.")
		
		return False

async def test_channel_subscription(bot, user_id, channel_id):
	logging.info(f"Testing channel subscription for user {user_id} in channel {channel_id}")
	
	try:
		logging.info("Test 1: Getting chat info...")
		try:
			chat = await bot.get_chat(chat_id=channel_id)
			logging.info(f"Chat info: {chat.title} (type: {chat.type})")
		except Exception as e:
			logging.error(f"Error getting chat info: {e}")
			return False
		
		logging.info("Test 2: Checking bot's status in the channel...")
		try:
			bot_member = await bot.get_chat_member(chat_id=channel_id, user_id=bot.id)
			logging.info(f"Bot status in channel: {bot_member.status}")
			
			can_invite_users = getattr(bot_member, 'can_invite_users', False)
			can_manage_chat = getattr(bot_member, 'can_manage_chat', False)
			
			logging.info(f"Bot permissions: can_invite_users={can_invite_users}, can_manage_chat={can_manage_chat}")
			
			if not can_invite_users or not can_manage_chat:
				logging.warning(
					"Bot does not have required permissions. Please add can_invite_users and can_manage_chat permissions.")
		except Exception as e:
			logging.error(f"Error getting bot's status: {e}")
			return False
		
		logging.info("Test 3: Checking user's status in the channel...")
		try:
			user_member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
			logging.info(f"User status in channel: {user_member.status}")
		except Exception as e:
			logging.error(f"Error getting user's status: {e}")
			return False
		
		logging.info("Test 4: Checking join requests in database...")
		try:
			has_request_in_db = check_join_request_in_db(user_id, channel_id)
			logging.info(f"User has join request in database: {has_request_in_db}")
		except Exception as e:
			logging.error(f"Error checking join requests in database: {e}")
			return False
		
		return True
	except Exception as e:
		logging.error(f"Error in test_channel_subscription: {e}")
		import traceback
		logging.error(traceback.format_exc())
		return False

async def check_user_started_bot(bot_token, user_id, bypass_cache=False):
	try:
		cache_key = f"bot_start_{user_id}_{bot_token[:8]}"
		if not bypass_cache and cache_key in subscription_cache:
			cache_data = subscription_cache[cache_key]
			if time.time() - cache_data["timestamp"] < CACHE_TIMEOUT:
				return cache_data["is_started"]
		
		logging.debug(f"Performing fresh check if user {user_id} started bot with token {bot_token[:8]}...")
		
		url = f"{TELEGRAM_API_BASE}{bot_token}/getChat"
		params = {
			"chat_id": user_id
		}
		
		async with aiohttp.ClientSession() as session:
			async with session.get(url, params=params) as response:
				data = await response.json()
				
				is_started = response.status == 200 and data.get('ok')
				
				logging.debug(f"User {user_id} started bot with token {bot_token[:8]}: {is_started}")
				
				subscription_cache[cache_key] = {
					"timestamp": time.time(),
					"is_started": is_started
				}
				
				return is_started
	
	except Exception as e:
		logging.error(f"Error checking bot start: {e}")
		return False

async def check_subscription_status(bot, user_id, bypass_cache=False):
	channels = get_required_channels()
	bots = get_required_bots()
	
	channel_tasks = []
	for channel in channels:
		task = asyncio.create_task(check_user_subscribed_to_channel(bot, user_id, channel['channel_id'], bypass_cache))
		channel_tasks.append((channel, task))
	
	bot_tasks = []
	for bot_info in bots:
		task = asyncio.create_task(check_user_started_bot(bot_info['bot_token'], user_id, bypass_cache))
		bot_tasks.append((bot_info, task))
	
	channel_status = []
	all_channels_subscribed = True
	
	for channel, task in channel_tasks:
		is_subscribed = await task
		if not is_subscribed:
			all_channels_subscribed = False
			logging.info(
				f"User {user_id} is NOT subscribed to channel {channel['channel_id']} ({channel['channel_name']})")
		else:
			logging.info(f"User {user_id} is subscribed to channel {channel['channel_id']} ({channel['channel_name']})")
		
		channel_status.append({
			**channel,
			'is_subscribed': is_subscribed
		})
	
	bot_status = []
	all_bots_started = True
	
	for bot_info, task in bot_tasks:
		is_started = await task
		if not is_started:
			all_bots_started = False
			logging.info(f"User {user_id} has NOT started bot {bot_info['bot_username']}")
		else:
			logging.info(f"User {user_id} has started bot {bot_info['bot_username']}")
		
		bot_status.append({
			**bot_info,
			'is_started': is_started
		})
	
	all_subscribed = all_channels_subscribed and all_bots_started
	
	logging.info(
		f"Final subscription status for user {user_id}: {all_subscribed} (channels: {all_channels_subscribed}, bots: {all_bots_started})")
	
	return all_subscribed, channel_status, bot_status

def create_subscription_keyboard(channel_status=None, bot_status=None):
	if channel_status is None:
		channels = get_required_channels()
		channel_status = [{**channel, 'is_subscribed': False} for channel in channels]
	
	if bot_status is None:
		bots = get_required_bots()
		bot_status = [{**bot, 'is_started': False} for bot in bots]
	
	inline_keyboard = []
	
	for channel in channel_status:
		emoji = "✅" if channel.get('is_subscribed', False) else "❌"
		inline_keyboard.append([
			InlineKeyboardButton(
				text=f"{emoji} {channel['channel_name']} - A'zo bo'lish",
				url=channel['invite_link']
			)
		])
	
	for bot_info in bot_status:
		emoji = "✅" if bot_info.get('is_started', False) else "❌"
		inline_keyboard.append([
			InlineKeyboardButton(
				text=f"{emoji} {bot_info['bot_name']} - Start berish",
				url=f"https://t.me/{bot_info['bot_username'].replace('@', '')}"
			)
		])
	
	# Add custom links to the keyboard
	custom_links = get_custom_links()
	for link in custom_links:
		inline_keyboard.append([
			InlineKeyboardButton(
				text=f"🔗 {link['name']}",
				url=link['url']
			)
		])
	
	if not inline_keyboard:
		return None
	
	inline_keyboard.append([
		InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_subscription")
	])
	
	return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

async def show_subscription_keyboard_if_needed(message, bot, user_id):
	if user_id in ADMINS:
		return True
	
	all_subscribed, channel_status, bot_status = await check_subscription_status(bot, user_id, bypass_cache=True)
	
	if not all_subscribed:
		keyboard = create_subscription_keyboard(channel_status, bot_status)
		
		if keyboard:
			await message.answer(
				"📢 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n\n"
				"1. Kanal tugmasini bosing\n"
				"2. Kanalga qo'shilish so'rovini yuboring\n"
				"3. \"✅ Tekshirish\" tugmasini bosing",
				reply_markup=keyboard,
				parse_mode="HTML"
			)
			return False
	
	return True

@channels_router.chat_join_request()
async def handle_join_request(event: ChatJoinRequest, bot: Bot):
	user = event.from_user
	chat = event.chat
	
	logging.info(f"User {user.id} ({user.full_name}) sent join request to channel {chat.id} ({chat.title})")
	
	success = save_join_request(user.id, chat.id)
	
	if success:
		logging.info(f"Successfully saved join request for user {user.id} in channel {chat.id}")
	else:
		logging.error(f"Failed to save join request for user {user.id} in channel {chat.id}")
	
	join_request_users[user.id] = {
		"channel_id": chat.id,
		"timestamp": time.time()
	}

@channels_router.callback_query(F.data == "check_subscription")
async def check_subscription_callback(callback: CallbackQuery):
	user_id = callback.from_user.id
	
	logging.info(f"User {user_id} pressed check subscription button")
	
	clear_subscription_cache_for_user(user_id)
	
	all_subscribed, channel_status, bot_status = await check_subscription_status(callback.bot, user_id,
	                                                                             bypass_cache=True)
	
	try:
		await callback.message.delete()
	except Exception as e:
		logging.error(f"Error deleting message: {e}")
	
	if not all_subscribed and user_id not in ADMINS:
		keyboard = create_subscription_keyboard(channel_status, bot_status)
		
		not_subscribed_channels = [ch['channel_name'] for ch in channel_status if not ch['is_subscribed']]
		not_started_bots = [bot['bot_name'] for bot in bot_status if not bot['is_started']]
		
		error_message = ""
		if not_subscribed_channels:
			channel_names = ", ".join([f"<b>{name}</b>" for name in not_subscribed_channels])
			error_message += f"❌ Siz quyidagi kanallarga a'zo bo'lmagansiz yoki qo'shilish so'rovini yubormagansiz: {channel_names}\n\n"
		
		if not_started_bots:
			bot_names = ", ".join([f"<b>{name}</b>" for name in not_started_bots])
			error_message += f"❌ Siz quyidagi botlarga start bermagansiz: {bot_names}\n\n"
		
		await callback.message.answer(
			f"📢 <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'ling:</b>\n\n"
			f"{error_message}"
			f"1. Kanal tugmasini bosing\n"
			f"2. Kanalga qo'shilish so'rovini yuboring\n"
			f"3. \"✅ Tekshirish\" tugmasini bosing",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
		
		await callback.answer("❌ Siz hali barcha kanallarga a'zo bo'lmagansiz yoki botlarga start bosmagansiz.")
		return
	
	try:
		from bot import show_main_menu
		from database import get_user
		
		user = get_user(user_id)
		
		if user:
			await show_main_menu(callback.message, user)
			await callback.answer("✅ Tekshiruv muvaffaqiyatli yakunlandi!")
		else:
			await callback.message.answer(
				"⚠️ Foydalanuvchi ma'lumotlari topilmadi. Iltimos, /start buyrug'ini qayta yuboring."
			)
	except Exception as e:
		logging.error(f"Error showing main menu after subscription check: {e}")
		await callback.message.answer(
			"✅ Tekshiruv muvaffaqiyatli yakunlandi! Iltimos, /start buyrug'ini qayta yuboring."
		)
	
	await callback.answer()

@channels_router.callback_query(F.data == "admin_channels")
async def admin_channels_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="📢 Kanallar", callback_data="manage_channels"),
				InlineKeyboardButton(text="🤖 Botlar", callback_data="manage_bots")
			],
			[
				InlineKeyboardButton(text="🔗 Linklar", callback_data="manage_links")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"📢 <b>Majburiy obuna boshqaruvi</b>\n\n"
		"Quyidagi amallardan birini tanlang:",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@channels_router.callback_query(F.data == "manage_links")
async def manage_links_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	links = get_custom_links()
	
	inline_keyboard = [
		[
			InlineKeyboardButton(text="🔗 Linklar ro'yxati", callback_data="view_links"),
			InlineKeyboardButton(text="➕ Link qo'shish", callback_data="add_link")
		],
		[
			InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="admin_channels")
		]
	]
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		f"🔗 <b>Linklar boshqaruvi</b>\n\n"
		f"Linklar soni: {len(links)} ta\n\n"
		f"Quyidagi amallardan birini tanlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data == "view_links")
async def view_links_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	links = get_custom_links()
	
	if not links:
		await callback.message.edit_text(
			"🔗 <b>Linklar</b>\n\n"
			"❌ Hozircha linklar qo'shilmagan.\n\n"
			"Link qo'shish uchun \"Link qo'shish\" tugmasini bosing.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="➕ Link qo'shish", callback_data="add_link")
					],
					[
						InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_links")
					]
				]
			),
			parse_mode="HTML"
		)
		await callback.answer()
		return
	
	inline_keyboard = []
	
	for link in links:
		inline_keyboard.append([
			InlineKeyboardButton(text=f"🔗 {link['name']}", callback_data=f"link_info_{link['id']}"),
			InlineKeyboardButton(text="❌", callback_data=f"delete_link_{link['id']}")
		])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="➕ Link qo'shish", callback_data="add_link")
	])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_links")
	])
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		"🔗 <b>Linklar</b>\n\n"
		"Quyida qo'shilgan linklar ro'yxati.\n"
		"Link ma'lumotlarini ko'rish uchun link nomini bosing.\n"
		"Linkni o'chirish uchun ❌ tugmasini bosing.",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("link_info_"))
async def link_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	link_id = int(callback.data.split("_")[2])
	links = get_custom_links()
	
	link = next((l for l in links if l['id'] == link_id), None)
	
	if not link:
		await callback.answer("❌ Link topilmadi.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔗 Linkga o'tish", url=link['url'])
			],
			[
				InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_link_{link_id}")
			],
			[
				InlineKeyboardButton(text="🔙 Orqaga", callback_data="view_links")
			]
		]
	)
	
	await callback.message.edit_text(
		f"🔗 <b>{link['name']}</b> linki haqida ma'lumot\n\n"
		f"🆔 Link ID: <code>{link['id']}</code>\n"
		f"🔗 URL: <code>{link['url']}</code>\n"
		f"📅 Qo'shilgan sana: {link['created_at']}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("delete_link_"))
async def delete_link_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	link_id = int(callback.data.split("_")[2])
	
	success = delete_custom_link(link_id)
	
	if not success:
		await callback.answer("❌ Linkni o'chirishda xatolik yuz berdi.")
		return
	
	await callback.answer("✅ Link muvaffaqiyatli o'chirildi!")
	await view_links_callback(callback)

@channels_router.callback_query(F.data == "add_link")
async def add_link_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(ChannelState.waiting_for_link_name)
	
	await callback.message.edit_text(
		"🔗 <b>Link qo'shish</b>\n\n"
		"Link nomini kiriting:",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_links")
				]
			]
		),
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.message(ChannelState.waiting_for_link_name)
async def process_link_name(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	link_name = message.text.strip()
	
	if not link_name:
		await message.answer("❌ Link nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(link_name=link_name)
	await state.set_state(ChannelState.waiting_for_link_url)
	
	await message.answer(
		"🔗 <b>Link qo'shish</b>\n\n"
		"Link URL manzilini kiriting:\n\n"
		"Masalan: https://t.me/example",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_links")
				]
			]
		),
		parse_mode="HTML"
	)

@channels_router.message(ChannelState.waiting_for_link_url)
async def process_link_url(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	link_url = message.text.strip()
	
	if not link_url:
		await message.answer("❌ Link URL manzili bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	if not link_url.startswith(("http://", "https://", "tg://")):
		link_url = "https://" + link_url
	
	state_data = await state.get_data()
	link_name = state_data.get("link_name")
	
	success = add_custom_link(link_name, link_url, message.from_user.id)
	
	if not success:
		await message.answer(
			"❌ Linkni qo'shishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
		)
		await state.clear()
		return
	
	await message.answer(
		f"✅ <b>Muvaffaqiyatli!</b>\n\n"
		f"Link <b>{link_name}</b> qo'shildi.\n\n"
		f"🔗 URL: <code>{link_url}</code>",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="⬅️ Orqaga", callback_data="manage_links")
				]
			]
		),
		parse_mode="HTML"
	)
	
	await state.clear()

@channels_router.callback_query(F.data == "manage_channels")
async def manage_channels_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	channels = get_required_channels()
	
	inline_keyboard = [
		[
			InlineKeyboardButton(text="📢 Kanallar ro'yxati", callback_data="view_channels"),
			InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")
		],
		[
			InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="admin_channels")
		]
	]
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		f"📢 <b>Kanallar boshqaruvi</b>\n\n"
		f"Majburiy obuna uchun kanallar soni: {len(channels)} ta\n\n"
		f"Quyidagi amallardan birini tanlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data == "view_channels")
async def view_channels_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	channels = get_required_channels()
	
	if not channels:
		await callback.message.edit_text(
			"📢 <b>Kanallar</b>\n\n"
			"❌ Hozircha majburiy obuna uchun kanallar qo'shilmagan.\n\n"
			"Kanal qo'shish uchun \"Kanal qo'shish\" tugmasini bosing.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")
					],
					[
						InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_channels")
					]
				]
			),
			parse_mode="HTML"
		)
		await callback.answer()
		return
	
	inline_keyboard = []
	
	for channel in channels:
		inline_keyboard.append([
			InlineKeyboardButton(text=f"📢 {channel['channel_name']}", callback_data=f"channel_info_{channel['id']}"),
			InlineKeyboardButton(text="❌", callback_data=f"delete_required_channel_{channel['id']}")
		])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="add_channel")
	])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_channels")
	])
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		"📢 <b>Kanallar</b>\n\n"
		"Quyida majburiy obuna uchun qo'shilgan kanallar ro'yxati.\n"
		"Kanal ma'lumotlarini ko'rish uchun kanal nomini bosing.\n"
		"Kanalni o'chirish uchun ❌ tugmasini bosing.",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("channel_info_"))
async def channel_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	channel_id = int(callback.data.split("_")[2])
	channels = get_required_channels()
	
	channel = next((c for c in channels if c['id'] == channel_id), None)
	
	if not channel:
		await callback.answer("❌ Kanal topilmadi.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔗 Kanalga o'tish", url=channel['invite_link'])
			],
			[
				InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_required_channel_{channel_id}")
			],
			[
				InlineKeyboardButton(text="🔙 Orqaga", callback_data="view_channels")
			]
		]
	)
	
	await callback.message.edit_text(
		f"📢 <b>{channel['channel_name']}</b> kanali haqida ma'lumot\n\n"
		f"🆔 Kanal ID: <code>{channel['channel_id']}</code>\n"
		f"🔗 Havola: {channel['invite_link']}\n"
		f"📅 Qo'shilgan sana: {channel['created_at']}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("delete_required_channel_"))
async def delete_required_channel_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	channel_id = int(callback.data.split("_")[3])
	
	success = delete_required_channel(channel_id)
	
	if not success:
		await callback.answer("❌ Kanalni o'chirishda xatolik yuz berdi.")
		return
	
	await callback.answer("✅ Kanal muvaffaqiyatli o'chirildi!")
	await view_channels_callback(callback)

@channels_router.callback_query(F.data == "add_channel")
async def add_channel_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(ChannelState.waiting_for_channel_forward)
	
	await callback.message.edit_text(
		"📢 <b>Kanal qo'shish</b>\n\n"
		"1. Botni kanalga admin qiling (barcha huquqlar bilan)\n"
		"2. Kanaldan biror xabarni forward qilib yuboring\n\n"
		"⚠️ Bot kanalda admin bo'lishi shart!\n\n"
		"Bot avtomatik ravishda kanalga qo'shilish so'rovi havolasini yaratadi.",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_channels")
				]
			]
		),
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.message(ChannelState.waiting_for_channel_forward)
async def process_channel_forward(message: Message, state: FSMContext, bot: Bot):
	if message.from_user.id not in ADMINS:
		return
	
	if not message.forward_from_chat:
		await message.answer(
			"❌ Bu xabar kanaldan forward qilinmagan. Iltimos, kanaldan xabarni forward qilib yuboring."
		)
		return
	
	try:
		chat_id = message.forward_from_chat.id
		chat_title = message.forward_from_chat.title
		
		logging.info(f"Processing channel forward for chat_id: {chat_id}, title: {chat_title}")
		
		bot_member = await bot.get_chat_member(chat_id=chat_id, user_id=bot.id)
		
		logging.info(f"Bot status in channel: {bot_member.status}")
		
		if bot_member.status != "administrator":
			await message.answer(
				"❌ Bot kanalda admin emas. Iltimos, botni kanalga admin qiling va qaytadan urinib ko'ring.\n\n"
				"Botga quyidagi huquqlarni berish kerak:\n"
				"- Foydalanuvchilarni qo'shish\n"
				"- Havolalarni boshqarish\n"
				"- Chat boshqaruvi"
			)
			return
		
		if not bot_member.can_invite_users:
			await message.answer(
				"❌ Botda kerakli huquqlar yo'q. Iltimos, botga quyidagi huquqlarni bering:\n"
				"- Foydalanuvchilarni qo'shish\n"
				"- Havolalarni boshqarish\n"
				"- Chat boshqaruvi"
			)
			return
		
		try:
			invite_link_obj = await bot.create_chat_invite_link(
				chat_id=chat_id,
				creates_join_request=True,
				name=f"Bot created join request link {int(time.time())}"
			)
			
			invite_link = invite_link_obj.invite_link
			
			logging.info(f"Created join request link: {invite_link}")
			
			if not invite_link:
				await message.answer("❌ Qo'shilish so'rovi havolasi yaratishda xatolik yuz berdi.")
				return
			
			success = add_required_channel(
				channel_id=str(chat_id),
				channel_name=chat_title,
				invite_link=invite_link,
				added_by=message.from_user.id
			)
			
			if not success:
				await message.answer(
					"❌ Kanalni qo'shishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
				)
				await state.clear()
				return
			
			await message.answer(
				f"✅ <b>Muvaffaqiyatli!</b>\n\n"
				f"Kanal <b>{chat_title}</b> majburiy obuna ro'yxatiga qo'shildi.\n\n"
				f"📎 Qo'shilish so'rovi havolasi: <code>{invite_link}</code>\n\n"
				f"ℹ️ Bu havola orqali foydalanuvchilar kanalga qo'shilish so'rovini yuborishlari mumkin.\n\n"
				f"⚠️ Muhim: Bot kanalga yuborilgan qo'shilish so'rovlarini qabul qilishi uchun botni ishga tushirib qo'ying.",
				reply_markup=InlineKeyboardMarkup(
					inline_keyboard=[
						[
							InlineKeyboardButton(text="⬅️ Orqaga", callback_data="manage_channels")
						]
					]
				),
				parse_mode="HTML"
			)
			
			await state.clear()
		
		except Exception as e:
			logging.error(f"Error creating join request link: {e}")
			await message.answer(
				f"❌ Qo'shilish so'rovi havolasi yaratishda xatolik: {e}\n\n"
				f"Iltimos, botga kerakli huquqlarni berganingizni tekshiring."
			)
			await state.clear()
	
	except Exception as e:
		logging.error(f"Error adding channel: {e}")
		await message.answer(
			"❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.\n\n"
			"Bot kanalda admin ekanligini tekshiring."
		)
		await state.clear()

@channels_router.callback_query(F.data == "manage_bots")
async def manage_bots_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	bots = get_required_bots()
	
	inline_keyboard = [
		[
			InlineKeyboardButton(text="🤖 Botlar ro'yxati", callback_data="view_bots"),
			InlineKeyboardButton(text="➕ Bot qo'shish", callback_data="add_bot")
		],
		[
			InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="admin_channels")
		]
	]
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		f"🤖 <b>Botlar boshqaruvi</b>\n\n"
		f"Majburiy obuna uchun botlar soni: {len(bots)} ta\n\n"
		f"Quyidagi amallardan birini tanlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data == "view_bots")
async def view_bots_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	bots = get_required_bots()
	
	if not bots:
		await callback.message.edit_text(
			"🤖 <b>Botlar</b>\n\n"
			"❌ Hozircha majburiy obuna uchun botlar qo'shilmagan.\n\n"
			"Bot qo'shish uchun \"Bot qo'shish\" tugmasini bosing.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="➕ Bot qo'shish", callback_data="add_bot")
					],
					[
						InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_bots")
					]
				]
			),
			parse_mode="HTML"
		)
		await callback.answer()
		return
	
	inline_keyboard = []
	
	for bot_info in bots:
		inline_keyboard.append([
			InlineKeyboardButton(text=f"🤖 {bot_info['bot_name']}", callback_data=f"bot_info_{bot_info['id']}"),
			InlineKeyboardButton(text="❌", callback_data=f"delete_bot_{bot_info['id']}")
		])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="➕ Bot qo'shish", callback_data="add_bot")
	])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="manage_bots")
	])
	
	keyboard = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		"🤖 <b>Botlar</b>\n\n"
		"Quyida majburiy obuna uchun qo'shilgan botlar ro'yxati.\n"
		"Bot ma'lumotlarini ko'rish uchun bot nomini bosing.\n"
		"Botni o'chirish uchun ❌ tugmasini bosing.",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("bot_info_"))
async def bot_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	bot_id = int(callback.data.split("_")[2])
	bots = get_required_bots()
	
	bot_info = next((b for b in bots if b['id'] == bot_id), None)
	
	if not bot_info:
		await callback.answer("❌ Bot topilmadi.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔗 Botga o'tish",
				                     url=f"https://t.me/{bot_info['bot_username'].replace('@', '')}")
			],
			[
				InlineKeyboardButton(text="❌ O'chirish", callback_data=f"delete_bot_{bot_id}")
			],
			[
				InlineKeyboardButton(text="🔙 Orqaga", callback_data="view_bots")
			]
		]
	)
	
	masked_token = bot_info['bot_token'][:8] + "..." + bot_info['bot_token'][-4:] if len(
		bot_info['bot_token']) > 12 else "***"
	
	await callback.message.edit_text(
		f"🤖 <b>{bot_info['bot_name']}</b> boti haqida ma'lumot\n\n"
		f"👤 Username: {bot_info['bot_username']}\n"
		f"🔑 Token: <code>{masked_token}</code>\n"
		f"📅 Qo'shilgan sana: {bot_info['created_at']}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.callback_query(F.data.startswith("delete_bot_"))
async def delete_bot_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	bot_id = int(callback.data.split("_")[2])
	
	success = delete_required_bot(bot_id)
	
	if not success:
		await callback.answer("❌ Botni o'chirishda xatolik yuz berdi.")
		return
	
	await callback.answer("✅ Bot muvaffaqiyatli o'chirildi!")
	await view_bots_callback(callback)

@channels_router.callback_query(F.data == "add_bot")
async def add_bot_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(ChannelState.waiting_for_bot_name)
	
	await callback.message.edit_text(
		"🤖 <b>Bot qo'shish</b>\n\n"
		"Bot nomini kiriting:",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_bots")
				]
			]
		),
		parse_mode="HTML"
	)
	
	await callback.answer()

@channels_router.message(ChannelState.waiting_for_bot_name)
async def process_bot_name(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	bot_name = message.text.strip()
	
	if not bot_name:
		await message.answer("❌ Bot nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(bot_name=bot_name)
	await state.set_state(ChannelState.waiting_for_bot_username)
	
	await message.answer(
		"🤖 <b>Bot qo'shish</b>\n\n"
		"Bot username'ini kiriting:\n\n"
		"Masalan: @example_bot yoki example_bot",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_bots")
				]
			]
		),
		parse_mode="HTML"
	)

@channels_router.message(ChannelState.waiting_for_bot_username)
async def process_bot_username(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	bot_username = message.text.strip()
	
	if not bot_username:
		await message.answer("❌ Bot username'i bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	# Remove @ if present
	if bot_username.startswith('@'):
		bot_username = bot_username[1:]
	
	await state.update_data(bot_username=bot_username)
	await state.set_state(ChannelState.waiting_for_bot_token)
	
	await message.answer(
		"🤖 <b>Bot qo'shish</b>\n\n"
		"Bot tokenini kiriting:\n\n"
		"Masalan: 1234567890:ABCDefGhIJKlmnOPQrsTUVwxyZ",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manage_bots")
				]
			]
		),
		parse_mode="HTML"
	)

@channels_router.message(ChannelState.waiting_for_bot_token)
async def process_bot_token(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	bot_token = message.text.strip()
	
	if not bot_token:
		await message.answer("❌ Bot tokeni bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	if not re.match(r'^\d+:[A-Za-z0-9_-]+$', bot_token):
		await message.answer("❌ Bot tokeni noto'g'ri formatda. Iltimos, qaytadan kiriting:")
		return
	
	state_data = await state.get_data()
	bot_name = state_data.get("bot_name")
	bot_username = state_data.get("bot_username")
	
	# Verify bot token by making a getMe request
	try:
		url = f"{TELEGRAM_API_BASE}{bot_token}/getMe"
		async with aiohttp.ClientSession() as session:
			async with session.get(url) as response:
				data = await response.json()
				
				if not response.status == 200 or not data.get('ok'):
					await message.answer("❌ Bot tokeni noto'g'ri. Iltimos, qaytadan kiriting:")
					return
				
				bot_info = data.get('result', {})
				actual_username = bot_info.get('username', '')
				
				if not actual_username:
					await message.answer("❌ Bot ma'lumotlarini olishda xatolik. Iltimos, qaytadan urinib ko'ring.")
					return
				
				if actual_username.lower() != bot_username.lower():
					await message.answer(
						f"⚠️ Kiritilgan username ({bot_username}) bot haqiqiy username'i ({actual_username}) bilan mos kelmaydi.\n\n"
						f"Iltimos, to'g'ri username kiriting:"
					)
					await state.set_state(ChannelState.waiting_for_bot_username)
					return
	except Exception as e:
		logging.error(f"Error verifying bot token: {e}")
		await message.answer("❌ Bot tokenini tekshirishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
		return
	
	success = add_required_bot(bot_token, bot_username, bot_name, message.from_user.id)
	
	if not success:
		await message.answer(
			"❌ Botni qo'shishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
		)
		await state.clear()
		return
	
	await message.answer(
		f"✅ <b>Muvaffaqiyatli!</b>\n\n"
		f"Bot <b>{bot_name}</b> majburiy obuna ro'yxatiga qo'shildi.\n\n"
		f"👤 Username: @{bot_username}\n"
		f"🔑 Token: <code>{bot_token[:8]}...{bot_token[-4:]}</code>",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="⬅️ Orqaga", callback_data="manage_bots")
				]
			]
		),
		parse_mode="HTML"
	)
	
	await state.clear()

def get_bot_status():
	"""
	Bot statusini olish
	"""
	conn = create_connection()
	if not conn:
		return "active"  # Default is active
	
	cursor = conn.cursor()
	
	try:
		# First ensure the table exists
		cursor.execute('''
		CREATE TABLE IF NOT EXISTS bot_status (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			is_active INTEGER NOT NULL DEFAULT 1,
			updated_by INTEGER,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
		''')
		conn.commit()
		
		# Check if there are any records
		cursor.execute("SELECT COUNT(*) FROM bot_status")
		count = cursor.fetchone()[0]
		
		# If no records, insert default active status
		if count == 0:
			cursor.execute(
				"INSERT INTO bot_status (is_active, updated_by) VALUES (?, ?)",
				(1, None)
			)
			conn.commit()
			return "active"
		
		# Get the latest status
		cursor.execute("SELECT is_active FROM bot_status ORDER BY id DESC LIMIT 1")
		result = cursor.fetchone()
		
		if result:
			return "active" if result[0] else "inactive"
		else:
			return "active"  # Default to active if no result
	except sqlite3.Error as e:
		logging.error(f"Error getting bot status: {e}")
		return "active"  # Default to active on error
	finally:
		conn.close()

def set_bot_status(is_active, updated_by):
	"""
	Bot statusini o'zgartirish
	"""
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		# First ensure the table exists
		cursor.execute('''
		CREATE TABLE IF NOT EXISTS bot_status (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			is_active INTEGER NOT NULL DEFAULT 1,
			updated_by INTEGER,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
		''')
		conn.commit()
		
		# Insert new status record
		cursor.execute(
			"INSERT INTO bot_status (is_active, updated_by) VALUES (?, ?)",
			(1 if is_active else 0, updated_by)
		)
		
		conn.commit()
		return True
	except sqlite3.Error as e:
		logging.error(f"Error setting bot status: {e}")
		return False
	finally:
		conn.close()

async def init_bot_status_table():
	"""Initialize bot_status table"""
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		# Create bot_status table
		cursor.execute('''
		CREATE TABLE IF NOT EXISTS bot_status (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			is_active INTEGER NOT NULL DEFAULT 1,
			updated_by INTEGER,
			updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
		)
		''')
		
		# Check if there are any records
		cursor.execute("SELECT COUNT(*) FROM bot_status")
		count = cursor.fetchone()[0]
		
		# If no records, insert default active status
		if count == 0:
			cursor.execute(
				"INSERT INTO bot_status (is_active, updated_by) VALUES (?, ?)",
				(1, None)
			)
		
		conn.commit()
		logging.info("Bot status table initialized successfully")
		return True
	except sqlite3.Error as e:
		logging.error(f"Error initializing bot status table: {e}")
		return False
	finally:
		conn.close()

@channels_router.callback_query(F.data == "bot_status")
async def bot_status_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	current_status = get_bot_status()
	is_active = current_status == "active"
	
	new_status = not is_active
	success = set_bot_status(new_status, callback.from_user.id)
	
	if not success:
		await callback.answer("❌ Bot statusini o'zgartirishda xatolik yuz berdi.")
		return
	
	new_status_text = "✅ Faol" if new_status else "❌ Faol emas"
	
	await callback.answer(f"✅ Bot statusi o'zgartirildi: {new_status_text}")
	
	# Update settings menu
	min_payment_amount = get_setting("min_payment_amount", "1000")
	referral_reward = get_setting("referral_reward_uzb", "100")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text=f"💰 Minimal to'lov: {min_payment_amount} UZS",
					callback_data="change_min_payment"
				)
			],
			[
				InlineKeyboardButton(
					text=f"👥 Referal mukofoti: {referral_reward} UZS",
					callback_data="change_referral_reward"
				)
			],
			[
				InlineKeyboardButton(
					text=f"🤖 Bot holati: {new_status_text}",
					callback_data="bot_status"
				)
			],
			[
				InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"⚙️ Sozlamalar\n\n"
		"O'zgartirmoqchi bo'lgan sozlamani tanlang:",
		reply_markup=inline_keyboard
	)

def register_channels_handlers(dp):
	"""
	Kanallar bilan bog'liq handler'larni ro'yxatdan o'tkazish
	"""
	dp.include_router(channels_router)
