import logging
import re
import time
import aiohttp
from aiogram import Bot, Router, F, BaseMiddleware
from aiogram.types import (
	Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
	ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command, BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from typing import Union, Dict, Any

from config import ADMINS, BOT_TOKEN
from database import (
	get_user, get_all_users, update_balance, add_transaction,
	add_wallet, get_all_wallets, delete_wallet, get_wallet,
	add_payment_method, get_all_payment_methods, delete_payment_method, get_payment_method,
	get_setting, update_setting, search_user_by_id, search_user_by_bot_id,
	block_user, unblock_user, is_user_blocked, add_money_to_user, subtract_money_from_user,
	create_connection
)
from channels import (
	get_required_channels, delete_required_channel, add_required_channel,
	get_required_bots, delete_required_bot, add_required_bot,
	create_subscription_keyboard, check_subscription_status,
	get_custom_links, add_custom_link, delete_custom_link
)

router = Router()

class AdminHolati(StatesGroup):
	hamyon_nomi_kutilmoqda = State()
	karta_raqami_kutilmoqda = State()
	karta_egasi_kutilmoqda = State()
	tolov_nomi_kutilmoqda = State()
	tolov_tokeni_kutilmoqda = State()
	tolov_rasmi_kutilmoqda = State()
	referal_mukofot_kutilmoqda = State()
	user_id_kutilmoqda = State()
	bot_id_kutilmoqda = State()
	pul_miqdori_kutilmoqda = State()
	kanal_username_kutilmoqda = State()
	kanal_nomi_kutilmoqda = State()
	admin_id_kutilmoqda = State()

class ChannelState(StatesGroup):
	waiting_for_channel_forward = State()
	waiting_for_channel_name = State()
	waiting_for_channel_link = State()
	waiting_for_bot_name = State()
	waiting_for_bot_username = State()
	waiting_for_bot_token = State()
	waiting_for_link_name = State()
	waiting_for_link_url = State()

class AdminFilter(BaseFilter):
	async def __call__(self, message: Message) -> Union[bool, Dict[str, Any]]:
		return message.from_user.id in ADMINS

def get_main_admin():
	if ADMINS and len(ADMINS) > 0:
		return ADMINS[0]
	return None

@router.message(Command("admin"))
async def admin_command(message: Message):
	user_id = message.from_user.id
	
	if user_id not in ADMINS:
		await message.answer("⚠️ Bu buyruq faqat adminlar uchun.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="👛 Hamyonlar", callback_data="admin_wallets"),
				InlineKeyboardButton(text="💳 To'lovlar", callback_data="admin_payments")
			],
			[
				InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users"),
				InlineKeyboardButton(text="⚙️ Referal sozlamalari", callback_data="admin_referral_settings")
			],
			[
				InlineKeyboardButton(text="📢 Kanallar", callback_data="admin_channels"),
				InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")
			],
			[
				InlineKeyboardButton(text="👑 Adminlar", callback_data="admin_management"),
				InlineKeyboardButton(text="🤖 Bot holati", callback_data="bot_status")
			],
			[
				InlineKeyboardButton(text="📝 Post yaratish", callback_data="create_post")
			]
		]
	)
	
	await message.answer(
		"👑 Admin panel\n\n"
		"Quyidagi bo'limlardan birini tanlang:",
		reply_markup=inline_keyboard
	)

@router.callback_query(F.data == "admin_management")
async def admin_management_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="👑 Adminlar ro'yxati", callback_data="admin_list"),
				InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_admin")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"👑 <b>Adminlar boshqaruvi</b>\n\n"
		f"Jami adminlar soni: {len(ADMINS)}\n\n"
		"Adminlar ro'yxatini ko'rish yoki yangi admin qo'shish uchun tugmalardan birini tanlang.",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data == "admin_list")
async def admin_list_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	inline_keyboard = []
	main_admin = get_main_admin()
	
	for admin_id in ADMINS:
		user = get_user(admin_id)
		admin_name = user[2] if user else f"Admin {admin_id}"
		
		if admin_id == main_admin:
			inline_keyboard.append([
				InlineKeyboardButton(text=f"👑 {admin_name} (Asosiy admin)", callback_data=f"admin_info_{admin_id}")
			])
		elif admin_id == callback.from_user.id:
			inline_keyboard.append([
				InlineKeyboardButton(text=f"👑 {admin_name} (Siz)", callback_data=f"admin_info_{admin_id}")
			])
		else:
			inline_keyboard.append([
				InlineKeyboardButton(text=f"👑 {admin_name}", callback_data=f"admin_info_{admin_id}"),
				InlineKeyboardButton(text="❌", callback_data=f"remove_admin_{admin_id}")
			])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Adminlar boshqaruvi", callback_data="admin_management")
	])
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await callback.message.edit_text(
		"👑 <b>Adminlar ro'yxati</b>\n\n"
		f"Jami adminlar soni: {len(ADMINS)}\n\n"
		"Admin ma'lumotlarini ko'rish uchun admin nomini bosing.\n"
		"Adminni o'chirish uchun ❌ tugmasini bosing.",
		reply_markup=markup,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data.startswith("admin_info_"))
async def admin_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	admin_id = int(callback.data.split("_")[2])
	user = get_user(admin_id)
	main_admin = get_main_admin()
	
	if not user:
		await callback.answer("⚠️ Admin ma'lumotlari topilmadi.")
		return
	
	inline_keyboard = []
	
	if admin_id != main_admin and admin_id != callback.from_user.id:
		inline_keyboard.append([
			InlineKeyboardButton(text="❌ Adminlikdan olib tashlash", callback_data=f"remove_admin_{admin_id}")
		])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Adminlar ro'yxati", callback_data="admin_list")
	])
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	admin_status = ""
	if admin_id == main_admin:
		admin_status = " (Asosiy admin)"
	elif admin_id == callback.from_user.id:
		admin_status = " (Siz)"
	
	await callback.message.edit_text(
		f"👑 <b>Admin ma'lumotlari{admin_status}</b>\n\n"
		f"🆔 ID: <code>{admin_id}</code>\n"
		f"👤 Ism: {user[2]}\n"
		f"🌐 Username: {user[1] or 'Mavjud emas'}\n"
		f"📱 Telefon: {user[8] or 'Mavjud emas'}",
		reply_markup=markup,
		parse_mode="HTML"
	)
	
	await callback.answer()

@router.callback_query(F.data == "add_admin")
async def add_admin_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(AdminHolati.admin_id_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="admin_management")
			]
		]
	)
	
	await callback.message.edit_text(
		"👑 <b>Admin qo'shish</b>\n\n"
		"Yangi admin qo'shish uchun foydalanuvchi ID raqamini kiriting:\n\n"
		"Masalan: <code>123456789</code>",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@router.message(AdminHolati.admin_id_kutilmoqda)
async def process_admin_id(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		new_admin_id = int(message.text.strip())
		
		user = get_user(new_admin_id)
		
		if not user:
			await message.answer(
				"⚠️ Bunday foydalanuvchi topilmadi. Iltimos, to'g'ri ID kiriting yoki bekor qilish uchun /admin buyrug'ini yuboring."
			)
			return
		
		if new_admin_id in ADMINS:
			await message.answer(
				"⚠️ Bu foydalanuvchi allaqachon admin hisoblanadi."
			)
			await state.clear()
			return
		
		ADMINS.append(new_admin_id)
		
		update_config_file()
		
		await message.answer(
			f"✅ Foydalanuvchi {user[2]} (ID: {new_admin_id}) muvaffaqiyatli admin qilib tayinlandi!"
		)
		
		try:
			await message.bot.send_message(
				chat_id=new_admin_id,
				text="🎉 Tabriklaymiz! Siz bot admini etib tayinlandingiz.\n\n"
				     "Admin panelini ochish uchun /admin buyrug'ini yuboring."
			)
		except Exception as e:
			logging.error(f"Yangi adminga xabar yuborishda xatolik: {e}")
		
		await state.clear()
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="👑 Adminlar ro'yxati", callback_data="admin_list"),
					InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_admin")
				],
				[
					InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
				]
			]
		)
		
		await message.answer(
			"👑 <b>Adminlar boshqaruvi</b>\n\n"
			f"Jami adminlar soni: {len(ADMINS)}\n\n"
			"Adminlar ro'yxatini ko'rish yoki yangi admin qo'shish uchun tugmalardan birini tanlang.",
			reply_markup=inline_keyboard,
			parse_mode="HTML"
		)
	
	except ValueError:
		await message.answer(
			"❌ Noto'g'ri format. Iltimos, raqamlardan iborat ID kiriting."
		)
	except Exception as e:
		logging.exception(f"Admin qo'shishda xatolik: {e}")
		await message.answer(
			"⚠️ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
		)
		await state.clear()

@router.callback_query(F.data.startswith("remove_admin_"))
async def remove_admin_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	admin_id = int(callback.data.split("_")[2])
	main_admin = get_main_admin()
	
	if admin_id == main_admin:
		await callback.answer("⚠️ Asosiy adminni o'chirib bo'lmaydi.")
		return
	
	if admin_id == callback.from_user.id:
		await callback.answer("⚠️ Siz o'zingizni adminlikdan olib tashlay olmaysiz.")
		return
	
	if len(ADMINS) <= 1:
		await callback.answer("⚠️ Kamida 1 ta admin qolishi kerak.")
		return
	
	if admin_id in ADMINS:
		ADMINS.remove(admin_id)
		
		update_config_file()
		
		user = get_user(admin_id)
		user_name = user[2] if user else f"ID: {admin_id}"
		
		await callback.answer(f"✅ {user_name} adminlikdan olib tashlandi.")
		
		try:
			await callback.bot.send_message(
				chat_id=admin_id,
				text="ℹ️ Siz bot adminligidan olib tashlangansiz."
			)
		except Exception as e:
			logging.error(f"Adminlikdan olib tashlangan foydalanuvchiga xabar yuborishda xatolik: {e}")
	else:
		await callback.answer("❌ Bu foydalanuvchi admin emas.")
	
	await admin_list_callback(callback)

def update_config_file():
	try:
		with open('config.py', 'r', encoding='utf-8') as file:
			lines = file.readlines()
		
		for i, line in enumerate(lines):
			if line.startswith('ADMINS'):
				lines[i] = f"ADMINS = {ADMINS}\n"
				break
		
		with open('config.py', 'w', encoding='utf-8') as file:
			file.writelines(lines)
		
		return True
	except Exception as e:
		logging.error(f"Config faylini yangilashda xatolik: {e}")
		return False

@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	users = get_all_users()
	total_users = len(users)
	
	total_balance = sum(user[4] for user in users if user[4])
	blocked_users = sum(1 for user in users if user[10] == 1)
	users_with_phone = sum(1 for user in users if user[8])
	
	wallets = get_all_wallets()
	total_wallets = len(wallets)
	
	payment_methods = get_all_payment_methods()
	total_payment_methods = len(payment_methods)
	
	channels = get_required_channels()
	total_channels = len(channels)
	
	bots = get_required_bots()
	total_bots = len(bots)
	
	links = get_custom_links()
	total_links = len(links)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_stats")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"📊 Statistika:\n\n"
		f"👥 Jami foydalanuvchilar: {total_users}\n"
		f"📱 Telefon raqamli foydalanuvchilar: {users_with_phone}\n"
		f"🚫 Bloklangan foydalanuvchilar: {blocked_users}\n"
		f"💰 Jami balans: {total_balance:,.0f} UZS\n"
		f"👛 Jami hamyonlar: {total_wallets}\n"
		f"💳 Jami to'lov usullari: {total_payment_methods}\n"
		f"📢 Jami majburiy kanallar: {total_channels}\n"
		f"🤖 Jami majburiy botlar: {total_bots}\n"
		f"🔗 Jami linklar: {total_links}",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "refresh_stats")
async def refresh_stats_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	users = get_all_users()
	total_users = len(users)
	
	total_balance = sum(user[4] for user in users if user[4])
	blocked_users = sum(1 for user in users if user[10] == 1)
	users_with_phone = sum(1 for user in users if user[8])
	
	wallets = get_all_wallets()
	total_wallets = len(wallets)
	
	payment_methods = get_all_payment_methods()
	total_payment_methods = len(payment_methods)
	
	channels = get_required_channels()
	total_channels = len(channels)
	
	bots = get_required_bots()
	total_bots = len(bots)
	
	links = get_custom_links()
	total_links = len(links)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_stats")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"📊 Statistika:\n\n"
		f"👥 Jami foydalanuvchilar: {total_users}\n"
		f"📱 Telefon raqamli foydalanuvchilar: {users_with_phone}\n"
		f"🚫 Bloklangan foydalanuvchilar: {blocked_users}\n"
		f"💰 Jami balans: {total_balance:,.0f} UZS\n"
		f"👛 Jami hamyonlar: {total_wallets}\n"
		f"💳 Jami to'lov usullari: {total_payment_methods}\n"
		f"📢 Jami majburiy kanallar: {total_channels}\n"
		f"🤖 Jami majburiy botlar: {total_bots}\n"
		f"🔗 Jami linklar: {total_links}",
		reply_markup=inline_keyboard
	)
	await callback.answer("✅ Statistika yangilandi!")

@router.callback_query(F.data == "admin_wallets")
async def admin_wallets_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	wallets = get_all_wallets()
	
	inline_keyboard = []
	
	if wallets:
		for wallet in wallets:
			wallet_id, wallet_name = wallet[0], wallet[1]
			inline_keyboard.append([
				InlineKeyboardButton(text=f"💳 {wallet_name}", callback_data=f"wallet_info_{wallet_id}"),
				InlineKeyboardButton(text="🗑️", callback_data=f"delete_wallet_{wallet_id}")
			])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="➕ Hamyon qo'shish", callback_data="add_wallet")
	])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
	])
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	if wallets:
		await callback.message.edit_text(
			"👛 Hamyonlar ro'yxati:\n\n"
			"ℹ️ Hamyon haqida ma'lumot olish uchun hamyon nomini bosing.\n"
			"🗑️ Hamyonni o'chirish uchun 🗑️ tugmasini bosing.",
			reply_markup=markup
		)
	else:
		await callback.message.edit_text(
			"👛 Hamyonlar ro'yxati bo'sh.\n\n"
			"Yangi hamyon qo'shish uchun quyidagi tugmani bosing:",
			reply_markup=markup
		)
	await callback.answer()

@router.callback_query(F.data == "admin_payments")
async def admin_payments_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	payments = get_all_payment_methods()
	
	inline_keyboard = []
	
	if payments:
		for payment in payments:
			payment_id, payment_name = payment[0], payment[1]
			inline_keyboard.append([
				InlineKeyboardButton(text=f"💳 {payment_name}", callback_data=f"payment_method_info_{payment_id}"),
				InlineKeyboardButton(text="🗑️", callback_data=f"delete_payment_{payment_id}")
			])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="➕ To'lov qo'shish", callback_data="add_payment")
	])
	
	inline_keyboard.append([
		InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
	])
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	if payments:
		await callback.message.edit_text(
			"💳 To'lov usullari ro'yxati:\n\n"
			"ℹ️ To'lov usuli haqida ma'lumot olish uchun to'lov nomini bosing.\n"
			"🗑️ To'lov usulini o'chirish uchun 🗑️ tugmasini bosing.",
			reply_markup=markup
		)
	else:
		await callback.message.edit_text(
			"💳 To'lov usullari ro'yxati bo'sh.\n\n"
			"Yangi to'lov usuli qo'shish uchun quyidagi tugmani bosing:",
			reply_markup=markup
		)
	await callback.answer()

@router.callback_query(F.data == "admin_users")
async def admin_users_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔍 ID orqali qidirish", callback_data="search_user_by_id")
			],
			[
				InlineKeyboardButton(text="🔢 Bot ID orqali qidirish", callback_data="search_user_by_bot_id")
			],
			[
				InlineKeyboardButton(text="👥 Barcha foydalanuvchilar", callback_data="list_all_users")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"👥 Foydalanuvchilar boshqaruvi\n\n"
		"Quyidagi amallardan birini tanlang:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "search_user_by_id")
async def search_user_by_id_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(AdminHolati.user_id_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_search_user")
			]
		]
	)
	
	await callback.message.edit_text(
		"🔍 ID orqali foydalanuvchi qidirish\n\n"
		"Foydalanuvchi ID raqamini kiriting:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.user_id_kutilmoqda)
async def process_user_id_search(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		user_id = int(message.text.strip())
		user = search_user_by_id(user_id)
		
		await state.clear()
		
		if user:
			await show_user_info(message, user)
		else:
			inline_keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
					]
				]
			)
			
			await message.answer(
				"❌ Foydalanuvchi topilmadi.\n\n"
				f"ID: {user_id}",
				reply_markup=inline_keyboard
			)
	except ValueError:
		await message.answer("❌ Noto'g'ri format. Iltimos, raqam kiriting:")

@router.callback_query(F.data == "search_user_by_bot_id")
async def search_user_by_bot_id_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(AdminHolati.bot_id_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_search_user")
			]
		]
	)
	
	await callback.message.edit_text(
		"🔢 Bot ID orqali foydalanuvchi qidirish\n\n"
		"Bot tomonidan berilgan ID raqamini kiriting:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.bot_id_kutilmoqda)
async def process_bot_id_search(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	bot_id = message.text.strip()
	user = search_user_by_bot_id(bot_id)
	
	await state.clear()
	
	if user:
		await show_user_info(message, user)
	else:
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
				]
			]
		)
		
		await message.answer(
			"❌ Foydalanuvchi topilmadi.\n\n"
			f"Bot ID: {bot_id}",
			reply_markup=inline_keyboard
		)

async def show_user_info(message, user):
	user_id = user[0]
	username = user[1] or "Mavjud emas"
	full_name = user[2]
	bot_id = user[3]
	balance = user[4]
	created_at = user[5]
	referrer_id = user[6]
	referral_count = user[7]
	phone_number = user[8] or "Mavjud emas"
	country_code = user[9] or "Mavjud emas"
	is_blocked = bool(user[10])
	
	block_text = "Blokdan chiqarish" if is_blocked else "Bloklash"
	block_data = f"unblock_user_{user_id}" if is_blocked else f"block_user_{user_id}"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💰 Pul qo'shish", callback_data=f"add_money_{user_id}"),
				InlineKeyboardButton(text="💸 Pul ayirish", callback_data=f"subtract_money_{user_id}")
			],
			[
				InlineKeyboardButton(text=f"🚫 {block_text}", callback_data=block_data)
			],
			[
				InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
			]
		]
	)
	
	status_text = "🚫 Bloklangan" if is_blocked else "✅ Faol"
	
	await message.answer(
		f"👤 Foydalanuvchi ma'lumotlari\n\n"
		f"🆔 ID: <code>{user_id}</code>\n"
		f"👤 Username: @{username}\n"
		f"📝 To'liq ismi: {full_name}\n"
		f"🤖 Bot ID: <code>{bot_id}</code>\n"
		f"💰 Balans: {balance:,.0f} UZS\n"
		f"📱 Telefon: {phone_number}\n"
		f"🌍 Mamlakat kodi: {country_code}\n"
		f"👥 Referallar soni: {referral_count}\n"
		f"📊 Holati: {status_text}\n"
		f"📅 Ro'yxatdan o'tgan sana: {created_at}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.callback_query(F.data.startswith("block_user_"))
async def block_user_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[2])
	user = get_user(user_id)
	
	if not user:
		await callback.answer("❌ Foydalanuvchi topilmadi.")
		return
	
	success = block_user(user_id)
	
	if success:
		await callback.answer("✅ Foydalanuvchi bloklandi.")
		user = get_user(user_id)
		await show_user_info_callback(callback, user)
	else:
		await callback.answer("❌ Foydalanuvchini bloklashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("unblock_user_"))
async def unblock_user_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[2])
	user = get_user(user_id)
	
	if not user:
		await callback.answer("❌ Foydalanuvchi topilmadi.")
		return
	
	success = unblock_user(user_id)
	
	if success:
		await callback.answer("✅ Foydalanuvchi blokdan chiqarildi.")
		user = get_user(user_id)
		await show_user_info_callback(callback, user)
	else:
		await callback.answer("❌ Foydalanuvchini blokdan chiqarishda xatolik yuz berdi.")

async def show_user_info_callback(callback, user):
	user_id = user[0]
	username = user[1] or "Mavjud emas"
	full_name = user[2]
	bot_id = user[3]
	balance = user[4]
	created_at = user[5]
	referrer_id = user[6]
	referral_count = user[7]
	phone_number = user[8] or "Mavjud emas"
	country_code = user[9] or "Mavjud emas"
	is_blocked = bool(user[10])
	
	block_text = "Blokdan chiqarish" if is_blocked else "Bloklash"
	block_data = f"unblock_user_{user_id}" if is_blocked else f"block_user_{user_id}"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💰 Pul qo'shish", callback_data=f"add_money_{user_id}"),
				InlineKeyboardButton(text="💸 Pul ayirish", callback_data=f"subtract_money_{user_id}")
			],
			[
				InlineKeyboardButton(text=f"🚫 {block_text}", callback_data=block_data)
			],
			[
				InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
			]
		]
	)
	
	status_text = "🚫 Bloklangan" if is_blocked else "✅ Faol"
	
	await callback.message.edit_text(
		f"👤 Foydalanuvchi ma'lumotlari\n\n"
		f"🆔 ID: <code>{user_id}</code>\n"
		f"👤 Username: @{username}\n"
		f"📝 To'liq ismi: {full_name}\n"
		f"🤖 Bot ID: <code>{bot_id}</code>\n"
		f"💰 Balans: {balance:,.0f} UZS\n"
		f"📱 Telefon: {phone_number}\n"
		f"🌍 Mamlakat kodi: {country_code}\n"
		f"👥 Referallar soni: {referral_count}\n"
		f"📊 Holati: {status_text}\n"
		f"📅 Ro'yxatdan o'tgan sana: {created_at}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.callback_query(F.data.startswith("add_money_"))
async def add_money_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[2])
	user = get_user(user_id)
	
	if not user:
		await callback.answer("❌ Foydalanuvchi topilmadi.")
		return
	
	await state.update_data(target_user_id=user_id, action="add")
	await state.set_state(AdminHolati.pul_miqdori_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_money_operation_{user_id}")
			]
		]
	)
	
	await callback.message.edit_text(
		f"💰 Foydalanuvchiga pul qo'shish\n\n"
		f"👤 Foydalanuvchi: {user[2]}\n"
		f"🆔 ID: {user_id}\n"
		f"💰 Hozirgi balans: {user[4]:,.0f} UZS\n\n"
		f"✏️ Qo'shiladigan pul miqdorini kiriting (UZS):",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data.startswith("subtract_money_"))
async def subtract_money_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[2])
	user = get_user(user_id)
	
	if not user:
		await callback.answer("❌ Foydalanuvchi topilmadi.")
		return
	
	await state.update_data(target_user_id=user_id, action="subtract")
	await state.set_state(AdminHolati.pul_miqdori_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_money_operation_{user_id}")
			]
		]
	)
	
	await callback.message.edit_text(
		f"💸 Foydalanuvchidan pul ayirish\n\n"
		f"👤 Foydalanuvchi: {user[2]}\n"
		f"🆔 ID: {user_id}\n"
		f"💰 Hozirgi balans: {user[4]:,.0f} UZS\n\n"
		f"✏️ Ayiriladigan pul miqdorini kiriting (UZS):",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.pul_miqdori_kutilmoqda)
async def process_money_amount(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		amount = float(message.text.strip())
		
		if amount <= 0:
			await message.answer("❌ Miqdor musbat son bo'lishi kerak. Iltimos, qaytadan kiriting:")
			return
		
		state_data = await state.get_data()
		user_id = state_data.get("target_user_id")
		action = state_data.get("action")
		
		user = get_user(user_id)
		if not user:
			await message.answer("❌ Foydalanuvchi topilmadi.")
			await state.clear()
			return
		
		if action == "add":
			success = add_money_to_user(user_id, amount)
			action_text = "qo'shildi"
			transaction_type = "admin_add"
		else:
			success = subtract_money_from_user(user_id, amount)
			action_text = "ayirildi"
			transaction_type = "admin_subtract"
		
		await state.clear()
		
		if success:
			updated_user = get_user(user_id)
			
			add_transaction(user_id, amount, transaction_type, f"admin_{message.from_user.id}")
			
			inline_keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="👤 Foydalanuvchi ma'lumotlari", callback_data=f"view_user_{user_id}")
					],
					[
						InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
					]
				]
			)
			
			await message.answer(
				f"✅ Muvaffaqiyatli {action_text}!\n\n"
				f"👤 Foydalanuvchi: {user[2]}\n"
				f"🆔 ID: {user_id}\n"
				f"💰 Miqdor: {amount:,.0f} UZS\n"
				f"💵 Yangi balans: {updated_user[4]:,.0f} UZS",
				reply_markup=inline_keyboard
			)
		else:
			await message.answer(f"❌ Pul {action_text}shda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
	
	except ValueError:
		await message.answer("❌ Noto'g'ri format. Iltimos, raqam kiriting:")

@router.callback_query(F.data.startswith("cancel_money_operation_"))
async def cancel_money_operation_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[3])
	user = get_user(user_id)
	
	await state.clear()
	
	if user:
		await show_user_info_callback(callback, user)
	else:
		await callback.message.edit_text(
			"❌ Foydalanuvchi topilmadi.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="🔙 Foydalanuvchilar", callback_data="admin_users")
					]
				]
			)
		)
	
	await callback.answer("❌ Amaliyot bekor qilindi.")

@router.callback_query(F.data.startswith("view_user_"))
async def view_user_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	user_id = int(callback.data.split("_")[2])
	user = get_user(user_id)
	
	if user:
		await show_user_info_callback(callback, user)
	else:
		await callback.answer("❌ Foydalanuvchi topilmadi.")

@router.callback_query(F.data == "list_all_users")
async def list_all_users_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	users = get_all_users()
	
	if not users:
		await callback.message.edit_text(
			"👥 Foydalanuvchilar ro'yxati bo'sh.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
					]
				]
			)
		)
		await callback.answer()
		return
	
	total_users = len(users)
	
	await callback.message.edit_text(
		f"👥 Foydalanuvchilar soni: {total_users}\n\n"
		f"Foydalanuvchi haqida ma'lumot olish uchun ID orqali qidiring.",
		reply_markup=InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔍 ID orqali qidirish", callback_data="search_user_by_id")
				],
				[
					InlineKeyboardButton(text="🔢 Bot ID orqali qidirish", callback_data="search_user_by_bot_id")
				],
				[
					InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
				]
			]
		)
	)
	await callback.answer()

@router.callback_query(F.data == "cancel_search_user")
async def cancel_search_user_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	await admin_users_callback(callback)
	await callback.answer("❌ Qidirish bekor qilindi.")

@router.callback_query(F.data == "admin_referral_settings")
async def admin_referral_settings_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="O'zbek referallari uchun", callback_data="change_reward_uzb")
			],
			[
				InlineKeyboardButton(text="Boshqa davlat referallari uchun", callback_data="change_reward_foreign")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"⚙️ Referal sozlamalari\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm\n\n"
		f"Qaysi mukofot miqdorini o'zgartirmoqchisiz?",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "change_reward_uzb")
async def change_reward_uzb_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(reward_type="referral_reward_uzb")
	await state.set_state(AdminHolati.referal_mukofot_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_change_reward")
			]
		]
	)
	
	await callback.message.edit_text(
		"💰 O'zbek referallari uchun yangi mukofot miqdorini kiriting (so'm):\n\n"
		"Masalan: 100",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "change_reward_foreign")
async def change_reward_foreign_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(reward_type="referral_reward_foreign")
	await state.set_state(AdminHolati.referal_mukofot_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_change_reward")
			]
		]
	)
	
	await callback.message.edit_text(
		"💰 Boshqa davlat referallari uchun yangi mukofot miqdorini kiriting (so'm):\n\n"
		"Masalan: 80",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.referal_mukofot_kutilmoqda)
async def process_referral_reward(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		new_reward = int(message.text.strip())
		
		if new_reward <= 0:
			await message.answer("❌ Mukofot miqdori musbat son bo'lishi kerak. Iltimos, qaytadan kiriting:")
			return
		
		state_data = await state.get_data()
		reward_type = state_data.get("reward_type")
		
		if not reward_type:
			await message.answer("⚠️ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
			await state.clear()
			return
		
		update_setting(reward_type, str(new_reward))
		
		reward_uzb = get_setting("referral_reward_uzb", "100")
		reward_foreign = get_setting("referral_reward_foreign", "80")
		
		await state.clear()
		
		reward_type_text = "O'zbek referallari" if reward_type == "referral_reward_uzb" else "Boshqa davlat referallari"
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="⚙️ Referal sozlamalari", callback_data="admin_referral_settings")
				],
				[
					InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
				]
			]
		)
		
		await message.answer(
			f"✅ {reward_type_text} uchun mukofot miqdori {new_reward} so'mga o'zgartirildi.\n\n"
			f"⚙️ Referal sozlamalari\n\n"
			f"Hozirgi mukofot miqdorlari:\n"
			f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
			f"- Boshqa davlat referallari uchun: {reward_foreign} so'm",
			reply_markup=inline_keyboard
		)
	except ValueError:
		await message.answer("❌ Noto'g'ri format. Iltimos, mukofot miqdorini raqamlar bilan kiriting:")
	except Exception as e:
		logging.exception(f"❌ Xato yuz berdi: {e}")
		await message.answer("⚠️ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
		await state.clear()

@router.callback_query(F.data == "cancel_change_reward")
async def cancel_change_reward_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="O'zbek referallari uchun", callback_data="change_reward_uzb")
			],
			[
				InlineKeyboardButton(text="Boshqa davlat referallari uchun", callback_data="change_reward_foreign")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"⚙️ Referal sozlamalari\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm\n\n"
		f"Qaysi mukofot miqdorini o'zgartirmoqchisiz?",
		reply_markup=inline_keyboard
	)
	await callback.answer("❌ Mukofot miqdorini o'zgartirish bekor qilindi.")

@router.callback_query(F.data == "back_to_admin")
async def back_to_admin_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="👛 Hamyonlar", callback_data="admin_wallets"),
				InlineKeyboardButton(text="💳 To'lovlar", callback_data="admin_payments")
			],
			[
				InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users"),
				InlineKeyboardButton(text="⚙️ Referal sozlamalari", callback_data="admin_referral_settings")
			],
			[
				InlineKeyboardButton(text="📢 Kanallar", callback_data="admin_channels"),
				InlineKeyboardButton(text="📊 Statistika", callback_data="admin_stats")
			],
			[
				InlineKeyboardButton(text="👑 Adminlar", callback_data="admin_management"),
				InlineKeyboardButton(text="🤖 Bot holati", callback_data="bot_status")
			],
			[
				InlineKeyboardButton(text="📝 Post yaratish", callback_data="create_post")
			]
		]
	)
	
	await callback.message.edit_text(
		"👑 Admin panel\n\n"
		"Quyidagi bo'limlardan birini tanlang:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

def create_bot_status_table():
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
        CREATE TABLE IF NOT EXISTS bot_status (
            id INTEGER PRIMARY KEY,
            is_active INTEGER DEFAULT 1,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_by INTEGER
        )
        ''')
		
		cursor.execute("SELECT COUNT(*) FROM bot_status")
		count = cursor.fetchone()[0]
		
		if count == 0:
			cursor.execute(
				"INSERT INTO bot_status (id, is_active) VALUES (1, 1)"
			)
		
		conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error creating bot status table: {e}")
		return False
	finally:
		conn.close()

def get_bot_status():
	conn = create_connection()
	if not conn:
		return True
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT is_active FROM bot_status WHERE id = 1")
		result = cursor.fetchone()
		
		if result:
			return bool(result[0])
		else:
			cursor.execute(
				"INSERT INTO bot_status (id, is_active) VALUES (1, 1)"
			)
			conn.commit()
			return True
	except Exception as e:
		logging.error(f"Error getting bot status: {e}")
		return True
	finally:
		conn.close()

def set_bot_status(is_active, updated_by):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute(
			"UPDATE bot_status SET is_active = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ? WHERE id = 1",
			(1 if is_active else 0, updated_by)
		)
		
		conn.commit()
		return True
	except Exception as e:
		logging.error(f"Error setting bot status: {e}")
		return False
	finally:
		conn.close()

class BotStatusMiddleware(BaseMiddleware):
	async def __call__(self, handler, event, data):
		if hasattr(event, 'from_user') and event.from_user and event.from_user.id in ADMINS:
			return await handler(event, data)
		
		if isinstance(event, CallbackQuery) and event.data == "check_subscription":
			return await handler(event, data)
		
		is_active = get_bot_status()
		
		if not is_active:
			if isinstance(event, Message):
				await event.answer(
					"🔧 <b>Botda texnik ishlar olib borilmoqda.</b>\n\n"
					"Iltimos, keyinroq qayta urinib ko'ring.",
					parse_mode="HTML"
				)
			elif isinstance(event, CallbackQuery):
				await event.answer(
					"🔧 Botda texnik ishlar olib borilmoqda. Iltimos, keyinroq qayta urinib ko'ring.",
					show_alert=True
				)
			return None
		
		return await handler(event, data)

@router.callback_query(F.data == "bot_status")
async def bot_status_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	is_active = get_bot_status()
	
	status_text = "✅ Yoqilgan" if is_active else "❌ O'chirilgan"
	toggle_text = "❌ O'chirish" if is_active else "✅ Yoqish"
	toggle_data = "toggle_bot_off" if is_active else "toggle_bot_on"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"🤖 <b>Bot holati</b>\n\n"
		f"Joriy holat: {status_text}\n\n"
		f"Bot o'chirilganda, foydalanuvchilar botdan foydalana olmaydilar va "
		f"\"Botda texnik ishlar olib borilmoqda\" xabarini oladilar.",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

@router.callback_query(F.data.startswith("toggle_bot_"))
async def toggle_bot_status_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	action = callback.data.split("_")[2]
	is_active = action == "on"
	
	success = set_bot_status(is_active, callback.from_user.id)
	
	if not success:
		await callback.answer("❌ Bot holatini o'zgartirishda xatolik yuz berdi.")
		return
	
	status_text = "✅ Yoqilgan" if is_active else "❌ O'chirilgan"
	toggle_text = "❌ O'chirish" if is_active else "✅ Yoqish"
	toggle_data = "toggle_bot_off" if is_active else "toggle_bot_on"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"🤖 <b>Bot holati</b>\n\n"
		f"Joriy holat: {status_text}\n\n"
		f"✅ Bot holati muvaffaqiyatli o'zgartirildi!\n\n"
		f"Bot o'chirilganda, foydalanuvchilar botdan foydalana olmaydilar va "
		f"\"Botda texnik ishlar olib borilmoqda\" xabarini oladilar.",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer("✅ Bot holati muvaffaqiyatli o'zgartirildi!")

@router.callback_query(F.data.startswith("wallet_info_"))
async def wallet_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	wallet_id = int(callback.data.split("_")[2])
	wallet = get_wallet(wallet_id)
	
	if not wallet:
		await callback.answer("⚠️ Hamyon topilmadi.")
		return
	
	wallet_name = wallet[1]
	card_number = wallet[2]
	full_name = wallet[3]
	created_at = wallet[4]
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="📋 Hamyonlar ro'yxati", callback_data="admin_wallets")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"💳 <b>{wallet_name}</b> hamyoni haqida ma'lumot\n\n"
		f"🔢 ID: <code>{wallet_id}</code>\n"
		f"💳 Karta raqami: <code>{card_number}</code>\n"
		f"👤 Ism-familiya: <b>{full_name}</b>\n"
		f"📅 Qo'shilgan sana: {created_at}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data.startswith("payment_method_info_"))
async def payment_method_info_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	method_id = int(callback.data.split("_")[3])
	method = get_payment_method(method_id)
	
	if not method:
		await callback.answer("⚠️ To'lov usuli topilmadi.")
		return
	
	method_name = method[1]
	payment_token = method[2]
	image_url = method[3]
	created_at = method[4]
	
	masked_token = payment_token[:8] + "..." + payment_token[-4:] if len(payment_token) > 12 else "***"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="📋 To'lovlar ro'yxati", callback_data="admin_payments")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"💳 <b>{method_name}</b> to'lov usuli haqida ma'lumot\n\n"
		f"🔢 ID: <code>{method_id}</code>\n"
		f"🔑 Token: <code>{masked_token}</code>\n"
		f"🖼️ Rasm URL: <code>{image_url}</code>\n"
		f"📅 Qo'shilgan sana: {created_at}",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data.startswith("delete_payment_"))
async def delete_payment_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	payment_id = int(callback.data.split("_")[2])
	payment = get_payment_method(payment_id)
	
	if not payment:
		await callback.answer("⚠️ To'lov usuli topilmadi.")
		return
	
	payment_name = payment[1]
	
	success = delete_payment_method(payment_id)
	
	if success:
		await callback.answer(f"✅ \"{payment_name}\" to'lov usuli o'chirildi.")
	else:
		await callback.answer("❌ To'lov usulini o'chirishda xatolik yuz berdi.")
	
	await admin_payments_callback(callback)

@router.callback_query(F.data == "add_payment")
async def add_payment_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(AdminHolati.tolov_nomi_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_payment")
			]
		]
	)
	
	await callback.message.edit_text(
		"➕ Yangi to'lov usuli qo'shish\n\n"
		"✏️ To'lov usuli nomini kiriting:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.tolov_nomi_kutilmoqda)
async def process_payment_name(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	payment_name = message.text.strip()
	
	if not payment_name:
		await message.answer("⚠️ To'lov usuli nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(payment_name=payment_name)
	await state.set_state(AdminHolati.tolov_tokeni_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_payment")
			]
		]
	)
	
	await message.answer(
		f"➕ Yangi to'lov usuli: <b>{payment_name}</b>\n\n"
		f"🔑 To'lov tokenini kiriting:",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.message(AdminHolati.tolov_tokeni_kutilmoqda)
async def process_payment_token(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	payment_token = message.text.strip()
	
	if not payment_token:
		await message.answer("⚠️ To'lov tokeni bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(payment_token=payment_token)
	await state.set_state(AdminHolati.tolov_rasmi_kutilmoqda)
	
	state_data = await state.get_data()
	payment_name = state_data.get("payment_name")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_payment")
			]
		]
	)
	
	await message.answer(
		f"➕ Yangi to'lov usuli: <b>{payment_name}</b>\n\n"
		f"🖼 To'lov usuli rasmining URL manzilini kiriting:",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.message(AdminHolati.tolov_rasmi_kutilmoqda)
async def process_payment_image(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	payment_image = message.text.strip()
	
	if not payment_image:
		await message.answer("⚠️ Rasm URL manzili bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	state_data = await state.get_data()
	payment_name = state_data.get("payment_name")
	payment_token = state_data.get("payment_token")
	
	success, payment_id = add_payment_method(payment_name, payment_token, payment_image)
	
	if success:
		await message.answer(
			f"✅ Yangi to'lov usuli muvaffaqiyatli qo'shildi!\n\n"
			f"💳 To'lov usuli: <b>{payment_name}</b>",
			parse_mode="HTML"
		)
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="💳 To'lovlar ro'yxati", callback_data="admin_payments")
				],
				[
					InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
				]
			]
		)
		
		await message.answer(
			"Quyidagi amallardan birini tanlang:",
			reply_markup=inline_keyboard
		)
	else:
		await message.answer("❌ To'lov usulini qo'shishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
	
	await state.clear()

@router.callback_query(F.data == "cancel_add_payment")
async def cancel_add_payment_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovlar ro'yxati", callback_data="admin_payments")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"❌ To'lov usuli qo'shish bekor qilindi.",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data.startswith("delete_wallet_"))
async def delete_wallet_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	wallet_id = int(callback.data.split("_")[2])
	wallet = get_wallet(wallet_id)
	
	if not wallet:
		await callback.answer("⚠️ Hamyon topilmadi.")
		return
	
	wallet_name = wallet[1]
	
	success = delete_wallet(wallet_id)
	
	if success:
		await callback.answer(f"✅ \"{wallet_name}\" hamyoni o'chirildi.")
	else:
		await callback.answer("❌ Hamyonni o'chirishda xatolik yuz berdi.")
	
	await admin_wallets_callback(callback)

@router.callback_query(F.data == "add_wallet")
async def add_wallet_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(AdminHolati.hamyon_nomi_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_wallet")
			]
		]
	)
	
	await callback.message.edit_text(
		"👛 Yangi hamyon qo'shish\n\n"
		"✏️ Hamyon nomini kiriting:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.message(AdminHolati.hamyon_nomi_kutilmoqda)
async def process_wallet_name(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	wallet_name = message.text.strip()
	
	if not wallet_name:
		await message.answer("⚠️ Hamyon nomi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(wallet_name=wallet_name)
	await state.set_state(AdminHolati.karta_raqami_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_wallet")
			]
		]
	)
	
	await message.answer(
		f"👛 Yangi hamyon: <b>{wallet_name}</b>\n\n"
		f"💳 Karta raqamini kiriting (masalan, 8600123456789012):",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.message(AdminHolati.karta_raqami_kutilmoqda)
async def process_card_number(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	card_number = message.text.strip()
	
	if not card_number:
		await message.answer("⚠️ Karta raqami bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(card_number=card_number)
	await state.set_state(AdminHolati.karta_egasi_kutilmoqda)
	
	state_data = await state.get_data()
	wallet_name = state_data.get("wallet_name")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_wallet")
			]
		]
	)
	
	await message.answer(
		f"👛 Yangi hamyon: <b>{wallet_name}</b>\n"
		f"💳 Karta raqami: <code>{card_number}</code>\n\n"
		f"👤 Karta egasining to'liq ismini kiriting:",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)

@router.message(AdminHolati.karta_egasi_kutilmoqda)
async def process_card_owner(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	card_owner = message.text.strip()
	
	if not card_owner:
		await message.answer("⚠️ Karta egasi ismi bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	state_data = await state.get_data()
	wallet_name = state_data.get("wallet_name")
	card_number = state_data.get("card_number")
	
	success, wallet_id = add_wallet(wallet_name, card_number, card_owner)
	
	if success:
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="👛 Hamyonlar ro'yxati", callback_data="admin_wallets")
				],
				[
					InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
				]
			]
		)
		
		await message.answer(
			f"✅ Yangi hamyon muvaffaqiyatli qo'shildi!\n\n"
			f"👛 Hamyon nomi: <b>{wallet_name}</b>\n"
			f"💳 Karta raqami: <code>{card_number}</code>\n"
			f"👤 Ism-familiya: <b>{card_owner}</b>",
			reply_markup=inline_keyboard,
			parse_mode="HTML"
		)
	else:
		await message.answer(
			"❌ Hamyonni qo'shishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring."
		)
	
	await state.clear()

@router.callback_query(F.data == "cancel_add_wallet")
async def cancel_add_wallet_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="👛 Hamyonlar ro'yxati", callback_data="admin_wallets")
			],
			[
				InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		"❌ Hamyon qo'shish bekor qilindi.",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "admin_channels")
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