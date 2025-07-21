import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
	Message, LabeledPrice, PreCheckoutQuery, ContentType,
	InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
	ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
	Contact, Location
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime
from tovar import router as tovar_router, show_product_with_payment_buttons, FIXED_PAYMENT_AMOUNT, get_product, \
	save_order_to_google_sheets, record_sale
from config import BOT_TOKEN, PAYMENT_TOKEN, ADMINS, ORDER_CHANNEL, TASDIQID, HELPER_ID
from database import (
	create_tables, add_user, get_user, update_balance,
	add_transaction, get_next_bot_id, get_user_transactions,
	add_pending_payment, get_pending_payment, update_payment_status,
	get_all_wallets, get_wallet, get_payment_method, get_all_payment_methods,
	get_user_by_bot_id, get_user_referral_count, is_user_blocked, get_setting
)
import admin
from admin import BotStatusMiddleware  # YANGI: Middleware import qilish
import referral
import channels
from channels import register_channels_handlers, show_subscription_keyboard_if_needed
import post
from utils import create_wallet_keyboard

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# YANGI: BotStatusMiddleware ni qo'shish
dp.message.middleware(BotStatusMiddleware())
dp.callback_query.middleware(BotStatusMiddleware())

router = Router()
dp.include_router(router)
dp.include_router(tovar_router)
dp.include_router(admin.router)
dp.include_router(referral.router)
dp.include_router(post.router)
register_channels_handlers(dp)

class TolovHolati(StatesGroup):
	tolov_kutilmoqda = State()
	miqdor_kutilmoqda = State()
	tolov_usuli_kutilmoqda = State()
	hamyon_tanlash = State()
	chek_kutilmoqda = State()
	summa_kutilmoqda = State()
	click_miqdor_kutilmoqda = State()
	# Mijoz ma'lumotlari uchun state'lar
	mijoz_ismi_kutilmoqda = State()
	mijoz_telefoni_kutilmoqda = State()
	mijoz_joylashuvi_kutilmoqda = State()
	mijoz_tasdiqlash = State()
	# Admin summa kiritish uchun state
	admin_summa_kutilmoqda = State()
	# Wallet payment states - YANGILANGAN
	wallet_chek_kutilmoqda = State()
	wallet_tasdiqlash = State()
	wallet_5000_chek_kutilmoqda = State()
	wallet_custom_amount_kutilmoqda = State()
	wallet_custom_confirmation = State()
	# TASDIQID states - YANGI
	tasdiqid_custom_amount_input = State()
	tasdiqid_custom_amount_confirm = State()

HISOBNI_TOLDIRISH = ""
HISOBIM = ""
TOLOVLAR_TARIXI = "📊 To'lovlar tarixi"
BOSH_MENYU = "🔙 Bosh menyu"
ORQAGA = "🔙 Orqaga"
CLICK_TOLOV = "💳 CLICK [ Avto ]"
UzCard = "🇺🇿  UzCard [ Avto ] "
HumoCard = "🇺🇿  HumoCard  [ Avto ] "
REFERRAL_BUTTON = ""
SERVICES_BUTTON = ""

# Global dictionary to store wallet payment data for users
wallet_payment_data = {}
# Global dictionary to store TASDIQID custom amount data - TUZATILGAN
tasdiqid_custom_data = {}

async def safe_edit_text(message, text, reply_markup=None, parse_mode=None):
	try:
		await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
	except Exception as e:
		logging.debug(f"Edit text failed, sending new message: {e}")
		await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

def extract_user_id_from_caption(caption):
	"""Caption dan user ID ni olish uchun yaxshilangan funksiya"""
	if not caption:
		return None
	
	# Turli xil formatlarni sinab ko'rish
	patterns = [
		r'🆔 <b>User ID:</b> <code>(\d+)</code>',  # Asosiy format
		r'User ID:</b> <code>(\d+)</code>',  # Qisqartirilgan format
		r'User ID.*?(\d+)',  # Umumiy format
		r'ID:\s*(\d+)',  # Oddiy format
		r'user.*?(\d+)',  # Kichik harflar bilan
		r'USER.*?(\d+)',  # Katta harflar bilan
	]
	
	for pattern in patterns:
		match = re.search(pattern, caption, re.IGNORECASE)
		if match:
			try:
				user_id = int(match.group(1))
				logging.info(f"User ID found with pattern '{pattern}': {user_id}")
				return user_id
			except (ValueError, IndexError):
				continue
	
	logging.error(f"Could not extract user ID from caption: {caption}")
	return None

@router.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
	logging.info(f"Start command received from user {message.from_user.id}")
	
	user_id = message.from_user.id
	username = message.from_user.username
	full_name = message.from_user.full_name
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	is_subscribed = await show_subscription_keyboard_if_needed(message, message.bot, user_id)
	if not is_subscribed:
		return
	
	args = message.text.split()[1:] if len(message.text.split()) > 1 else []
	
	user = get_user(user_id)
	
	if not user:
		bot_id = get_next_bot_id()
		
		referrer_id = None
		if args and args[0].startswith("ref_"):
			try:
				referrer_id = int(args[0].split("_")[1])
				referrer = get_user(referrer_id)
				if not referrer or referrer_id == user_id:
					referrer_id = None
			except (ValueError, IndexError):
				referrer_id = None
		
		success = await add_user(user_id, username, full_name, bot_id, message.bot, None, "UZ", referrer_id)
		
		if not success:
			await message.answer("⚠️ Ro'yxatdan o'tishda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
			return
		
		user = get_user(user_id)
	
	# PRODUCT START HANDLER - YANGILANGAN
	if args and args[0].startswith("product_"):
		product_id = args[0].replace("product_", "")
		
		product = get_product(product_id)
		
		if not product or not product[9]:  # product[9] - is_active
			await message.answer("❌ Bu tovar mavjud emas yoki faol emas.")
			return
		
		# Tovarni rasm/video bilan ko'rsatish - YANGILANGAN DIZAYN
		await show_product_with_payment_buttons(message, product_id, is_callback=False)
		return
	
	if args and args[0].startswith("ref_"):
		try:
			referrer_id = int(args[0].split("_")[1])
			
			referrer = get_user(referrer_id)
			if referrer and referrer_id != user_id:
				await show_main_menu(message, user)
				return
		except (ValueError, IndexError):
			pass
	
	await show_main_menu(message, user)

async def show_main_menu(message, user):
	if not user:
		await message.answer(
			"⚠️ Foydalanuvchi ma'lumotlarini olishda xatolik yuz berdi. Iltimos, /start buyrug'ini qayta yuboring."
		)
		return
	
	# TUZATILGAN: To'g'ri indexlar
	bot_id = user[3]  # bot_id - 3-index
	balance = user[4]  # balance - 4-index
	
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text=HISOBNI_TOLDIRISH),
				KeyboardButton(text=HISOBIM)
			],
			[
				KeyboardButton(text=REFERRAL_BUTTON),
				KeyboardButton(text=SERVICES_BUTTON)
			]
		],
		resize_keyboard=True,
		is_persistent=True
	)
	
	bot_id_text = f"`{bot_id}`"
	
	if message.from_user.id in ADMINS:
		admin_keyboard = ReplyKeyboardMarkup(
			keyboard=[
				[
					KeyboardButton(text=HISOBNI_TOLDIRISH),
					KeyboardButton(text=HISOBIM)
				],
				[
					KeyboardButton(text=REFERRAL_BUTTON),
					KeyboardButton(text=SERVICES_BUTTON)
				],
				[
					# KeyboardButton(text="/admin"),
					# KeyboardButton(text="/tovar")
				]
			],
			resize_keyboard=True,
			is_persistent=True
		)
		
		await message.answer(
			f"🎉 Assalomu alaykum, {user[2]}!\n\n"
			f"✨ To'lov botiga xush kelibsiz! ✨\n"
			f"🆔 Sizning ID: {bot_id_text}\n"
			f"💰 Balans: {balance:,.0f} so'm\n\n"
			f"👑 Siz admin sifatida tizimga kirdingiz.\n"
			f"👇 Quyidagi tugmalardan birini tanlang:",
			reply_markup=admin_keyboard,
			parse_mode="Markdown"
		)
	else:
		await message.answer(
			f"🎉 Assalomu alaykum, {user[2]}!\n\n"
			f"✨ To'lov botiga xush kelibsiz! ✨\n"
			f"🆔 Sizning ID: {bot_id_text}\n"
			f"💰 Balans: {balance:,.0f} so'm\n\n"
			f"👇 Quyidagi tugmalardan birini tanlang:",
			reply_markup=keyboard,
			parse_mode="Markdown"
		)

# YANGI: BACK TO PRODUCT HANDLER - ASOSIY TUZATISH
@router.callback_query(F.data.startswith("back_to_product_"))
async def back_to_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Tovar sahifasiga qaytish - TO'LOV USULIDAN ORTGA QAYTISH"""
	product_id = callback.data.split("_")[3]

	# State ni tozalash
	await state.clear()

	product = get_product(product_id)

	if not product or not product[9]:  # product[9] - is_active
		await callback.answer("❌ Bu tovar mavjud emas yoki faol emas.")
		return

	try:
		await callback.message.delete()  # Xabarni o‘chirish
	except Exception:
		pass

	# Tovarni qayta ko‘rsatish
	await show_product_with_payment_buttons(callback, product_id, is_callback=True)
	await callback.answer()


# CANCEL PRODUCT ORDER HANDLER
@router.callback_query(F.data.startswith("cancel_product_order_"))
async def cancel_product_order_callback(callback: CallbackQuery, state: FSMContext):
	"""Tovar buyurtmasini bekor qilish"""
	await state.clear()
	
	# Asosiy klaviaturani qaytarish
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text=HISOBNI_TOLDIRISH),
				KeyboardButton(text=HISOBIM)
			],
			[
				KeyboardButton(text=REFERRAL_BUTTON),
				KeyboardButton(text=SERVICES_BUTTON)
			]
		],
		resize_keyboard=True
	)
	
	try:
		await callback.message.delete()
	except Exception:
		pass
	
	await callback.message.answer(
		"❌ Buyurtma bekor qilindi.\n"
		"Bosh menyuga qaytdingiz.",
		reply_markup=keyboard
	)
	await callback.answer("Buyurtma bekor qilindi")

# ADMIN PAYMENT METHODS HANDLERS - YANGILANGAN
@router.callback_query(F.data.startswith("auto_payment_product_"))
async def auto_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Admin tomonidan qo'shilgan auto payment usuli"""
	parts = callback.data.split("_")
	if len(parts) < 5:
		await callback.answer("⚠️ Noto'g'ri callback data.")
		return
	
	method_id = int(parts[3])
	product_id = parts[4]
	
	logging.info(f"Auto payment callback: method_id={method_id}, product_id={product_id}")
	
	method = get_payment_method(method_id)
	if not method:
		await callback.answer("⚠️ To'lov usuli topilmadi.")
		return
	
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	await state.update_data(
		product_id=product_id,
		payment_method_id=method_id,
		payment_amount=FIXED_PAYMENT_AMOUNT,
		product_name=product_name,
		product_price=product_price
	)
	await state.set_state(TolovHolati.tolov_kutilmoqda)
	
	method_name = method[1]
	payment_token = method[2]
	image_url = method[3] if len(method) > 3 else "https://roobotmee.uz/img/ksjdns.png"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	try:
		# Joriy xabarni o'chirish
		await callback.message.delete()
	except Exception as e:
		logging.debug(f"Message deletion failed: {e}")
	
	try:
		invoice_message = await callback.bot.send_invoice(
			chat_id=callback.message.chat.id,
			title=f"🛍 {method_name} orqali tovar to'lovi - {FIXED_PAYMENT_AMOUNT:,.0f} UZS",
			description=f"✨ {product_name} uchun {FIXED_PAYMENT_AMOUNT:,.0f} UZS to'lov",
			payload=f"product_payment_{product_id}_{FIXED_PAYMENT_AMOUNT}_{method_name.lower()}",
			provider_token=payment_token,
			currency="UZS",
			prices=[
				LabeledPrice(label=f"Tovar to'lovi", amount=FIXED_PAYMENT_AMOUNT * 100),
			],
			start_parameter=f"product_{product_id}",
			provider_data=None,
			photo_url=image_url,
			photo_size=512,
			photo_width=512,
			photo_height=512,
			need_name=False,
			need_phone_number=False,
			need_email=False,
			need_shipping_address=False,
			send_phone_number_to_provider=False,
			send_email_to_provider=False,
			is_flexible=False,
			disable_notification=False,
			protect_content=False,
			reply_to_message_id=None,
			allow_sending_without_reply=True,
			request_timeout=15,
			reply_markup=inline_keyboard
		)
		
		await state.update_data(invoice_message_id=invoice_message.message_id)
		
		# YANGILANGAN: Product ID ni ham yuborish
		asyncio.create_task(
			delete_invoice_after_timeout(
				callback.bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				method_name,
				product_id  # YANGI: Product ID qo'shildi
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

# DEFAULT PAYMENT HANDLERS - UzCard, HumoCard, CLICK - YANGILANGAN
@router.callback_query(F.data.startswith("uzcard_payment_product_"))
async def uzcard_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle UzCard payment for product - 50,000 UZS"""
	product_id = callback.data.split("_")[3]
	
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	await state.update_data(
		product_id=product_id,
		payment_amount=FIXED_PAYMENT_AMOUNT,
		product_name=product_name,
		product_price=product_price
	)
	await state.set_state(TolovHolati.tolov_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	try:
		await callback.message.delete()
	except Exception as e:
		logging.debug(f"Message deletion failed: {e}")
	
	try:
		invoice_message = await bot.send_invoice(
			chat_id=callback.message.chat.id,
			title=f"🛍 UzCard orqali tovar to'lovi - {FIXED_PAYMENT_AMOUNT:,.0f} UZS",
			description=f"✨ {product_name} uchun {FIXED_PAYMENT_AMOUNT:,.0f} UZS to'lov",
			payload=f"product_payment_{product_id}_{FIXED_PAYMENT_AMOUNT}_uzcard",
			provider_token=PAYMENT_TOKEN,
			currency="UZS",
			prices=[
				LabeledPrice(label=f"Tovar to'lovi", amount=FIXED_PAYMENT_AMOUNT * 100),
			],
			start_parameter=f"product_{product_id}",
			provider_data=None,
			photo_url="https://roobotmee.uz/img/ksjdns.png",
			photo_size=512,
			photo_width=512,
			photo_height=512,
			need_name=False,
			need_phone_number=False,
			need_email=False,
			need_shipping_address=False,
			send_phone_number_to_provider=False,
			send_email_to_provider=False,
			is_flexible=False,
			disable_notification=False,
			protect_content=False,
			reply_to_message_id=None,
			allow_sending_without_reply=True,
			request_timeout=15,
			reply_markup=inline_keyboard
		)
		
		await state.update_data(invoice_message_id=invoice_message.message_id)
		
		# YANGILANGAN: Product ID ni ham yuborish
		asyncio.create_task(
			delete_invoice_after_timeout(
				bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"UzCard",
				product_id  # YANGI: Product ID qo'shildi
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

@router.callback_query(F.data.startswith("humo_payment_product_"))
async def humo_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle HumoCard payment for product - 50,000 UZS"""
	product_id = callback.data.split("_")[3]
	
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	await state.update_data(
		product_id=product_id,
		payment_amount=FIXED_PAYMENT_AMOUNT,
		product_name=product_name,
		product_price=product_price
	)
	await state.set_state(TolovHolati.tolov_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	try:
		await callback.message.delete()
	except Exception as e:
		logging.debug(f"Message deletion failed: {e}")
	
	try:
		invoice_message = await bot.send_invoice(
			chat_id=callback.message.chat.id,
			title=f"🛍 HumoCard orqali tovar to'lovi - {FIXED_PAYMENT_AMOUNT:,.0f} UZS",
			description=f"✨ {product_name} uchun {FIXED_PAYMENT_AMOUNT:,.0f} UZS to'lov",
			payload=f"product_payment_{product_id}_{FIXED_PAYMENT_AMOUNT}_humo",
			provider_token=PAYMENT_TOKEN,
			currency="UZS",
			prices=[
				LabeledPrice(label=f"Tovar to'lovi", amount=FIXED_PAYMENT_AMOUNT * 100),
			],
			start_parameter=f"product_{product_id}",
			provider_data=None,
			photo_url="https://roobotmee.uz/img/hdusafd3sajhjkasd.png",
			photo_size=512,
			photo_width=512,
			photo_height=512,
			need_name=False,
			need_phone_number=False,
			need_email=False,
			need_shipping_address=False,
			send_phone_number_to_provider=False,
			send_email_to_provider=False,
			is_flexible=False,
			disable_notification=False,
			protect_content=False,
			reply_to_message_id=None,
			allow_sending_without_reply=True,
			request_timeout=15,
			reply_markup=inline_keyboard
		)
		
		await state.update_data(invoice_message_id=invoice_message.message_id)
		
		# YANGILANGAN: Product ID ni ham yuborish
		asyncio.create_task(
			delete_invoice_after_timeout(
				bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"HumoCard",
				product_id  # YANGI: Product ID qo'shildi
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

@router.callback_query(F.data.startswith("click_payment_product_"))
async def click_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle CLICK payment for product - 50,000 UZS"""
	product_id = callback.data.split("_")[3]
	
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	await state.update_data(
		product_id=product_id,
		payment_amount=FIXED_PAYMENT_AMOUNT,
		product_name=product_name,
		product_price=product_price
	)
	await state.set_state(TolovHolati.tolov_kutilmoqda)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	try:
		await callback.message.delete()
	except Exception as e:
		logging.debug(f"Message deletion failed: {e}")
	
	try:
		invoice_message = await bot.send_invoice(
			chat_id=callback.message.chat.id,
			title=f"🛍 CLICK orqali tovar to'lovi - {FIXED_PAYMENT_AMOUNT:,.0f} UZS",
			description=f"✨ {product_name} uchun {FIXED_PAYMENT_AMOUNT:,.0f} UZS to'lov",
			payload=f"product_payment_{product_id}_{FIXED_PAYMENT_AMOUNT}_click",
			provider_token=PAYMENT_TOKEN,
			currency="UZS",
			prices=[
				LabeledPrice(label=f"Tovar to'lovi", amount=FIXED_PAYMENT_AMOUNT * 100),
			],
			start_parameter=f"product_{product_id}",
			provider_data=None,
			photo_url="https://marketing.uz/uz/uploads/articles/1222/article-original.jpg",
			photo_size=512,
			photo_width=512,
			photo_height=512,
			need_name=False,
			need_phone_number=False,
			need_email=False,
			need_shipping_address=False,
			send_phone_number_to_provider=False,
			send_email_to_provider=False,
			is_flexible=False,
			disable_notification=False,
			protect_content=False,
			reply_to_message_id=None,
			allow_sending_without_reply=True,
			request_timeout=15,
			reply_markup=inline_keyboard
		)
		
		await state.update_data(invoice_message_id=invoice_message.message_id)
		
		# YANGILANGAN: Product ID ni ham yuborish
		asyncio.create_task(
			delete_invoice_after_timeout(
				bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"CLICK",
				product_id  # YANGI: Product ID qo'shildi
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

# WALLET PAYMENT HANDLERS - MUKAMMAL TUZATILGAN TIZIM
@router.callback_query(F.data.startswith("wallet_payment_product_"))
async def wallet_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle wallet payment for product - YANGILANGAN: avvalgi xabarni o‘chirish va yangi yuborish"""
	parts = callback.data.split("_")
	if len(parts) < 5:
		await callback.answer("⚠️ Noto'g'ri callback data.")
		return
	
	wallet_id = int(parts[3])
	product_id = parts[4]
	
	logging.info(f"Wallet payment callback: wallet_id={wallet_id}, product_id={product_id}")
	
	wallet = get_wallet(wallet_id)
	if not wallet:
		await callback.answer("⚠️ Hamyon topilmadi.")
		return
	
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	# State ga ma'lumotlarni saqlash
	await state.update_data(
		wallet_id=wallet_id,
		product_id=product_id,
		payment_amount=FIXED_PAYMENT_AMOUNT,
		product_name=product_name,
		product_price=product_price
	)
	
	wallet_name = wallet[1]
	card_number = wallet[2]
	full_name = wallet[3]
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ To'lov qildim",
				                     callback_data=f"wallet_payment_made_{wallet_id}_{product_id}")
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	# Avvalgi xabarni o‘chirish
	try:
		await callback.message.delete()
	except Exception as e:
		logging.warning(f"Xabarni o‘chirishda xatolik: {e}")
	
	# Yangi xabarni yuborish
	await callback.message.answer(
		f"💳 <b>{wallet_name}</b> orqali to'lov\n\n"
		f"💰 <b>Summa:</b> {FIXED_PAYMENT_AMOUNT:,} UZS\n"
		f"💳 <b>Karta raqami:</b> <code>{card_number}</code>\n"
		f"👤 <b>Ism-familiya:</b> <b>{full_name}</b>\n\n"
		f"🛍 <b>Tovar:</b> {product_name}\n\n"
		f"ℹ️ Iltimos, ko'rsatilgan kartaga {FIXED_PAYMENT_AMOUNT:,} UZS to'lovni amalga oshiring va \"To'lov qildim\" tugmasini bosing.",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	
	await callback.answer()

# WALLET PAYMENT MADE HANDLER - MUKAMMAL TUZATILGAN
@router.callback_query(F.data.startswith("wallet_payment_made_"))
async def wallet_payment_made_callback(callback: CallbackQuery, state: FSMContext):
	"""Wallet to'lov qildim tugmasi bosilganda - MUKAMMAL TUZATILGAN"""
	parts = callback.data.split("_")
	if len(parts) < 5:
		await callback.answer("⚠️ Noto'g'ri callback data.")
		return
	
	wallet_id = int(parts[3])
	product_id = parts[4]
	
	# State ni wallet chek kutish holatiga o'tkazish
	await state.set_state(TolovHolati.wallet_chek_kutilmoqda)
	
	# Ortga qaytish tugmasini qo'shish
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}")
			]
		]
	)
	
	try:
		await callback.message.edit_text(
			f"📷 <b>To'lov chekini yuboring</b>\n\n"
			f"💰 <b>Summa:</b> {FIXED_PAYMENT_AMOUNT:,} UZS\n"
			f"🛍 <b>Tovar uchun to'lov</b>\n\n"
			f"📸 Iltimos, to'lov chekining rasmini yuboring:",
			reply_markup=inline_keyboard,
			parse_mode="HTML"
		)
	except Exception as e:
		logging.error(f"Error editing message: {e}")
		await callback.message.answer(
			f"📷 <b>To'lov chekini yuboring</b>\n\n"
			f"💰 <b>Summa:</b> {FIXED_PAYMENT_AMOUNT:,} UZS\n"
			f"🛍 <b>Tovar uchun to'lov</b>\n\n"
			f"📸 Iltimos, to'lov chekining rasmini yuboring:",
			reply_markup=inline_keyboard,
			parse_mode="HTML"
		)
	
	await callback.answer()

# WALLET CHECK HANDLER - MUKAMMAL TUZATILGAN
@router.message(TolovHolati.wallet_chek_kutilmoqda, F.photo)
async def wallet_check_photo_handler(message: Message, state: FSMContext):
	"""Wallet to'lov cheki qabul qilish - MUKAMMAL TUZATILGAN"""
	state_data = await state.get_data()
	wallet_id = state_data.get('wallet_id')
	product_id = state_data.get('product_id')
	product_name = state_data.get('product_name')
	payment_amount = state_data.get('payment_amount', FIXED_PAYMENT_AMOUNT)
	
	# Chek rasmini saqlash
	check_photo_id = message.photo[-1].file_id
	await state.update_data(check_photo_id=check_photo_id)
	
	# TUZATILGAN: Callback data formatini to'g'rilash
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="✅ Tasdiqlash",
					callback_data=f"confirm_wallet_payment_{wallet_id}_{product_id}_{message.from_user.id}"
				),
				InlineKeyboardButton(
					text="❌ Bekor qilish",
					callback_data=f"cancel_wallet_payment_{wallet_id}_{product_id}_{message.from_user.id}"
				)
			],
			[
				InlineKeyboardButton(
					text="💰 Boshqa summa",
					callback_data=f"other_amount_wallet_{wallet_id}_{product_id}_{message.from_user.id}"
				)
			]
		]
	)
	
	# Chekni TASDIQID ga yuborish
	admin_text = (
		f"💳 <b>Yangi wallet to'lov cheki!</b>\n\n"
		f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
		f"🆔 <b>User ID:</b> <code>{message.from_user.id}</code>\n"
		f"👨‍💻 <b>Username:</b> @{message.from_user.username or 'Yo\'q'}\n\n"
		f"🛍 <b>Tovar:</b> {product_name}\n"
		f"💰 <b>Summa:</b> {payment_amount:,} UZS\n\n"
		f"📅 <b>Vaqt:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}"
	)
	
	try:
		await message.bot.send_photo(
			chat_id=TASDIQID,
			photo=check_photo_id,
			caption=admin_text,
			parse_mode="HTML",
			reply_markup=inline_keyboard
		)
		logging.info(f"Payment check sent to TASDIQID: {TASDIQID}")
	except Exception as e:
		logging.error(f"Error sending check to TASDIQID {TASDIQID}: {e}")
	
	# Foydalanuvchiga javob
	await message.answer(
		f"✅ <b>To'lov cheki qabul qilindi!</b>\n\n"
		f"📋 Chekingiz tasdiqlash uchun yuborildi.\n"
		f"⏳ Iltimos, biroz kuting...\n\n"
		f"💰 <b>Summa:</b> {payment_amount:,} UZS\n"
		f"🛍 <b>Tovar:</b> {product_name}",
		parse_mode="HTML"
	)
	
	await state.set_state(TolovHolati.wallet_tasdiqlash)

@router.message(TolovHolati.wallet_chek_kutilmoqda)
async def wallet_check_invalid_handler(message: Message):
	"""Noto'g'ri fayl turi yuborilganda"""
	await message.answer(
		"⚠️ Iltimos, to'lov chekining rasmini yuboring.\n"
		"Faqat rasm fayllari qabul qilinadi."
	)

# TASDIQID WALLET PAYMENT CONFIRMATION HANDLERS - MUKAMMAL TIZIM - TUZATILGAN
@router.callback_query(F.data.startswith("confirm_wallet_payment_"))
async def confirm_wallet_payment_callback(callback: CallbackQuery):
	"""TASDIQID tomonidan wallet to'lovni tasdiqlash - MUKAMMAL TUZATILGAN"""
	if callback.from_user.id != TASDIQID:
		await callback.answer("⚠️ Bu funksiya faqat tasdiqlash uchun.")
		return
	
	parts = callback.data.split("_")
	logging.info(f"Callback data parts: {parts}")
	
	# TUZATILGAN: Callback data formatini tekshirish
	if len(parts) < 6:
		await callback.answer("❌ Noto'g'ri callback data formati.")
		logging.error(f"Invalid callback data format: {callback.data}")
		return
	
	try:
		# TUZATILGAN: To'g'ri indexlarni ishlatish
		wallet_id_str = parts[3]
		product_id = parts[4]
		user_id_str = parts[5]
		
		# TUZATILGAN: None va bo'sh qiymatlarni tekshirish
		if wallet_id_str == 'None' or not wallet_id_str:
			await callback.answer("❌ Wallet ID topilmadi.")
			logging.error(f"Wallet ID is None or empty: {wallet_id_str}")
			return
		
		if user_id_str == 'None' or not user_id_str:
			await callback.answer("❌ User ID topilmadi.")
			logging.error(f"User ID is None or empty: {user_id_str}")
			return
		
		wallet_id = int(wallet_id_str)
		user_id = int(user_id_str)
		
		logging.info(f"TASDIQID confirming payment: wallet_id={wallet_id}, product_id={product_id}, user_id={user_id}")
	
	except (ValueError, IndexError) as e:
		await callback.answer("❌ Callback data formatida xatolik.")
		logging.error(f"Error parsing callback data: {e}, data: {callback.data}")
		return
	
	# Foydalanuvchi va tovar ma'lumotlarini olish
	user = get_user(user_id)
	product = get_product(product_id)
	
	if not user or not product:
		await callback.answer("❌ Foydalanuvchi yoki tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	username = user[1] or "Yo'q"
	
	# Admin xabarini yangilash
	try:
		await callback.message.edit_caption(
			caption=f"✅ <b>TASDIQLANDI</b>\n\n{callback.message.caption}",
			parse_mode="HTML"
		)
	except Exception:
		pass
	
	# Foydalanuvchiga xabar yuborish - YANGILANGAN
	try:
		remaining_debt = product_price - FIXED_PAYMENT_AMOUNT
		success_text = (
			f"🎉 <b>To'lov tasdiqlandi!</b>\n\n"
			f"✅ To'langan: {FIXED_PAYMENT_AMOUNT:,.0f} UZS\n"
			f"🛍 Tovar: {product_name}\n"
			f"💰 Asosiy narx: {product_price:,.0f} UZS\n"
		)
		
		if remaining_debt > 0:
			success_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,.0f} UZS\n"
		elif remaining_debt < 0:
			success_text += f"🎁 <b>Chegirma:</b> {abs(remaining_debt):,.0f} UZS\n"
		else:
			success_text += "✅ <b>To'liq to'lov</b>\n"
		
		success_text += f"\n📋 <b>Buyurtmangizni rasmiylashtirish uchun ma'lumotlaringizni kiriting</b>"
		
		await callback.bot.send_message(
			chat_id=user_id,
			text=success_text,
			parse_mode="HTML"
		)
		
		# Mijoz ma'lumotlarini so'rash
		await callback.bot.send_message(
			chat_id=user_id,
			text="👤 <b>Ism-familiyangizni kiriting:</b>",
			parse_mode="HTML",
			reply_markup=ReplyKeyboardRemove()
		)
		
		# Foydalanuvchi state ni o'rnatish
		from aiogram.fsm.storage.base import StorageKey
		from aiogram.fsm.context import FSMContext
		
		# State yaratish
		storage_key = StorageKey(bot_id=callback.bot.id, chat_id=user_id, user_id=user_id)
		user_state = FSMContext(storage=dp.storage, key=storage_key)
		
		await user_state.update_data(
			product_id=product_id,
			product_name=product_name,
			product_price=product_price,
			payment_amount=FIXED_PAYMENT_AMOUNT,
			payment_method="WALLET",
			remaining_debt=remaining_debt
		)
		await user_state.set_state(TolovHolati.mijoz_ismi_kutilmoqda)
	
	except Exception as e:
		logging.error(f"Error sending confirmation to user: {e}")
	
	await callback.answer("✅ To'lov tasdiqlandi!")

@router.callback_query(F.data.startswith("cancel_wallet_payment_"))
async def cancel_wallet_payment_callback(callback: CallbackQuery):
	"""TASDIQID tomonidan wallet to'lovni bekor qilish - TUZATILGAN"""
	if callback.from_user.id != TASDIQID:
		await callback.answer("⚠️ Bu funksiya faqat tasdiqlash uchun.")
		return
	
	parts = callback.data.split("_")
	
	# TUZATILGAN: Callback data formatini tekshirish
	if len(parts) < 6:
		await callback.answer("❌ Noto'g'ri callback data formati.")
		return
	
	try:
		user_id = int(parts[5])
	except (ValueError, IndexError):
		await callback.answer("❌ User ID formatida xatolik.")
		return
	
	# Admin xabarini yangilash
	try:
		await callback.message.edit_caption(
			caption=f"❌ <b>BEKOR QILINDI</b>\n\n{callback.message.caption}",
			parse_mode="HTML"
		)
	except Exception:
		pass
	
	# Foydalanuvchiga xabar yuborish
	try:
		await callback.bot.send_message(
			chat_id=user_id,
			text="❌ <b>To'lov bekor qilindi</b>\n\n"
			     "Sizning to'lov chekingiz tasdiqlash uchun javobgar shaxs tomonidan bekor qilindi.\n"
			     "Iltimos, to'g'ri summa to'lang yoki admin bilan bog'laning.",
			parse_mode="HTML"
		)
	except Exception as e:
		logging.error(f"Error sending cancellation to user: {e}")
	
	await callback.answer("❌ To'lov bekor qilindi!")

# TASDIQID BOSHQA SUMMA HANDLER - MUKAMMAL TUZATILGAN TIZIM
@router.callback_query(F.data.startswith("other_amount_wallet_"))
async def other_amount_wallet_callback(callback: CallbackQuery, state: FSMContext):
	"""TASDIQID tomonidan boshqa summa belgilash - TASDIQID dan summa so'rash - TUZATILGAN"""
	if callback.from_user.id != TASDIQID:
		await callback.answer("⚠️ Bu funksiya faqat tasdiqlash uchun.")
		return
	
	parts = callback.data.split("_")
	
	# TUZATILGAN: Callback data formatini tekshirish
	if len(parts) < 6:
		await callback.answer("❌ Noto'g'ri callback data formati.")
		return
	
	try:
		wallet_id = int(parts[3])
		product_id = parts[4]
		user_id = int(parts[5])
	except (ValueError, IndexError):
		await callback.answer("❌ Callback data formatida xatolik.")
		return
	
	logging.info(
		f"TASDIQID requesting custom amount: wallet_id={wallet_id}, product_id={product_id}, user_id={user_id}")
	
	# TASDIQID ma'lumotlarini saqlash - TUZATILGAN
	tasdiqid_custom_data[callback.from_user.id] = {
		'wallet_id': wallet_id,
		'product_id': product_id,
		'user_id': user_id,
		'original_message_id': callback.message.message_id,
		'original_caption': callback.message.caption
	}
	
	# Admin xabarini yangilash
	try:
		await callback.message.edit_caption(
			caption=f"💰 <b>BOSHQA SUMMA</b>\n\n{callback.message.caption}",
			parse_mode="HTML"
		)
	except Exception:
		pass
	
	# TASDIQID dan summa so'rash
	await callback.message.answer(
		f"💰 <b>Haqiqiy to'lov miqdorini kiriting</b>\n\n"
		f"To'lov summasini kiriting (UZS):\n\n"
		f"💡 Minimal: 5,000 UZS\n"
		f"💡 Maksimal: 10,000,000 UZS\n\n"
		f"Masalan: 75000",
		parse_mode="HTML"
	)
	
	# TASDIQID state ni o'rnatish - TUZATILGAN
	from aiogram.fsm.storage.base import StorageKey
	from aiogram.fsm.context import FSMContext
	
	storage_key = StorageKey(bot_id=callback.bot.id, chat_id=callback.from_user.id, user_id=callback.from_user.id)
	tasdiqid_state = FSMContext(storage=dp.storage, key=storage_key)
	await tasdiqid_state.set_state(TolovHolati.tasdiqid_custom_amount_input)
	
	await callback.answer("💰 Haqiqiy to'lov miqdorini kiriting")

# TASDIQID CUSTOM AMOUNT INPUT HANDLER - TUZATILGAN
@router.message(TolovHolati.tasdiqid_custom_amount_input)
async def tasdiqid_custom_amount_input_handler(message: Message, state: FSMContext):
	"""TASDIQID tomonidan kiritilgan custom summa - TUZATILGAN"""
	if message.from_user.id != TASDIQID:
		await message.answer("⚠️ Bu funksiya faqat TASDIQID uchun.")
		return
	
	logging.info(f"TASDIQID entered custom amount: {message.text}")
	
	try:
		custom_amount = float(message.text.strip().replace(",", "").replace(" ", ""))
		if custom_amount <= 0:
			raise ValueError("Summa musbat bo'lishi kerak")
		if custom_amount < 5000:
			await message.answer("⚠️ Minimal summa 5,000 UZS bo'lishi kerak.")
			return
		if custom_amount > 10000000:
			await message.answer("⚠️ Maksimal summa 10,000,000 UZS.")
			return
	except ValueError:
		await message.answer("⚠️ Noto'g'ri summa formati. Faqat raqam kiriting.\nMasalan: 75000")
		return
	
	# TASDIQID ma'lumotlarini olish - TUZATILGAN
	if message.from_user.id not in tasdiqid_custom_data:
		await message.answer("❌ Ma'lumotlar topilmadi. Qaytadan boshlang.")
		return
	
	data = tasdiqid_custom_data[message.from_user.id]
	wallet_id = data['wallet_id']
	product_id = data['product_id']
	user_id = data['user_id']
	
	# Product ma'lumotlarini olish
	product = get_product(product_id)
	if not product:
		await message.answer("❌ Tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	
	# Custom amount ni saqlash - TUZATILGAN
	tasdiqid_custom_data[message.from_user.id]['custom_amount'] = custom_amount
	
	await state.set_state(TolovHolati.tasdiqid_custom_amount_confirm)
	
	# TASDIQID dan tasdiqlash so'rash - TUZATILGAN
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ Ha, tasdiqlash",
				                     callback_data=f"tasdiqid_confirm_custom_{wallet_id}_{product_id}_{user_id}_{int(custom_amount)}"),
				InlineKeyboardButton(text="❌ Yo'q, qaytadan",
				                     callback_data=f"tasdiqid_retry_custom_{wallet_id}_{product_id}_{user_id}")
			]
		]
	)
	
	remaining_debt = product_price - custom_amount
	debt_text = ""
	if remaining_debt > 0:
		debt_text = f"📋 <b>Qolgan qarz:</b> {remaining_debt:,} UZS\n"
	elif remaining_debt < 0:
		debt_text = f"🎁 <b>Ortiqcha to'lov:</b> {abs(remaining_debt):,} UZS\n"
	else:
		debt_text = f"✅ <b>To'liq to'lov</b>\n"
	
	await message.answer(
		f"💰 <b>Summa tasdiqlash</b>\n\n"
		f"🛍 <b>Tovar:</b> {product_name}\n"
		f"💰 <b>Asosiy narx:</b> {product_price:,} UZS\n"
		f"💳 <b>To'lov summasi:</b> {custom_amount:,} UZS\n"
		f"{debt_text}\n"
		f"Bu summa to'g'ri bo'lsa, tasdiqlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

# TASDIQID CUSTOM AMOUNT CONFIRM HANDLER - MUKAMMAL TUZATILGAN
@router.callback_query(F.data.startswith("tasdiqid_confirm_custom_"))
async def tasdiqid_confirm_custom_callback(callback: CallbackQuery, state: FSMContext):
	"""TASDIQID tomonidan custom summani tasdiqlash - MUKAMMAL TUZATILGAN"""
	if callback.from_user.id != TASDIQID:
		await callback.answer("⚠️ Bu funksiya faqat TASDIQID uchun.")
		return
	
	parts = callback.data.split("_")
	if len(parts) < 7:
		await callback.answer("❌ Noto'g'ri callback data.")
		return
	
	wallet_id = int(parts[3])
	product_id = parts[4]
	user_id = int(parts[5])
	custom_amount = float(parts[6])
	
	logging.info(f"TASDIQID confirming custom amount: {custom_amount} for user {user_id}")
	
	# Foydalanuvchi va tovar ma'lumotlarini olish
	user = get_user(user_id)
	product = get_product(product_id)
	
	if not user or not product:
		await callback.answer("❌ Foydalanuvchi yoki tovar topilmadi.")
		return
	
	product_name = product[2]
	product_price = product[4]
	username = user[1] or "Yo'q"
	
	# TASDIQID xabarini yangilash
	try:
		await callback.message.edit_text(
			f"✅ <b>CUSTOM SUMMA TASDIQLANDI</b>\n\n"
			f"💰 Summa: {custom_amount:,} UZS\n"
			f"🛍 Tovar: {product_name}\n"
			f"👤 Mijoz: {user[2]}",
			parse_mode="HTML"
		)
	except Exception:
		pass
	
	# Original admin xabarini yangilash
	if callback.from_user.id in tasdiqid_custom_data:
		data = tasdiqid_custom_data[callback.from_user.id]
		try:
			await callback.bot.edit_message_caption(
				chat_id=TASDIQID,
				message_id=data['original_message_id'],
				caption=f"✅ <b>CUSTOM SUMMA TASDIQLANDI</b>\n💰 {custom_amount:,} UZS\n\n{data['original_caption']}",
				parse_mode="HTML"
			)
		except Exception as e:
			logging.error(f"Error updating original message: {e}")
		
		# Ma'lumotlarni tozalash
		del tasdiqid_custom_data[callback.from_user.id]
	
	# Foydalanuvchiga xabar yuborish - YANGILANGAN
	try:
		remaining_debt = product_price - custom_amount
		success_text = (
			f"🎉 <b>To'lov tasdiqlandi!</b>\n\n"
			f"✅ To'langan: {custom_amount:,.0f} UZS\n"
			f"🛍 Tovar: {product_name}\n"
			f"💰 Asosiy narx: {product_price:,.0f} UZS\n"
		)
		
		if remaining_debt > 0:
			success_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,.0f} UZS\n"
		elif remaining_debt < 0:
			success_text += f"🎁 <b>Ortiqcha to'lov:</b> {abs(remaining_debt):,.0f} UZS\n"
		else:
			success_text += "✅ <b>To'liq to'lov</b>\n"
		
		success_text += f"\n📋 <b>Buyurtmangizni rasmiylashtirish uchun ma'lumotlaringizni kiriting</b>"
		
		await callback.bot.send_message(
			chat_id=user_id,
			text=success_text,
			parse_mode="HTML"
		)
		
		# Mijoz ma'lumotlarini so'rash
		await callback.bot.send_message(
			chat_id=user_id,
			text="👤 <b>Ism-familiyangizni kiriting:</b>",
			parse_mode="HTML",
			reply_markup=ReplyKeyboardRemove()
		)
		
		# Foydalanuvchi state ni o'rnatish
		from aiogram.fsm.storage.base import StorageKey
		from aiogram.fsm.context import FSMContext
		
		storage_key = StorageKey(bot_id=callback.bot.id, chat_id=user_id, user_id=user_id)
		user_state = FSMContext(storage=dp.storage, key=storage_key)
		
		await user_state.update_data(
			product_id=product_id,
			product_name=product_name,
			product_price=product_price,
			payment_amount=custom_amount,
			payment_method="WALLET_CUSTOM",
			remaining_debt=remaining_debt
		)
		await user_state.set_state(TolovHolati.mijoz_ismi_kutilmoqda)
	
	except Exception as e:
		logging.error(f"Error sending confirmation to user: {e}")
	
	await state.clear()
	await callback.answer("✅ Custom summa tasdiqlandi!")

# TASDIQID RETRY CUSTOM HANDLER - TUZATILGAN
@router.callback_query(F.data.startswith("tasdiqid_retry_custom_"))
async def tasdiqid_retry_custom_callback(callback: CallbackQuery, state: FSMContext):
	"""TASDIQID tomonidan custom summani qaytadan kiritish"""
	if callback.from_user.id != TASDIQID:
		await callback.answer("⚠️ Bu funksiya faqat TASDIQID uchun.")
		return
	
	await state.set_state(TolovHolati.tasdiqid_custom_amount_input)
	
	await callback.message.edit_text(
		f"💰 <b>Haqiqiy to'lov miqdorini qaytadan kiriting</b>\n\n"
		f"To'lov summasini kiriting (UZS):\n\n"
		f"💡 Minimal: 5,000 UZS\n"
		f"💡 Maksimal: 10,000,000 UZS\n\n"
		f"Masalan: 75000",
		parse_mode="HTML"
	)
	
	await callback.answer("💰 Qaytadan summa kiriting")

# CUSTOMER INFO COLLECTION HANDLERS - YANGILANGAN
@router.message(TolovHolati.mijoz_ismi_kutilmoqda)
async def customer_name_handler(message: Message, state: FSMContext):
	"""Mijoz ismini qabul qilish"""
	customer_name = message.text.strip()
	
	if len(customer_name) < 2:
		await message.answer("⚠️ Ism kamida 2 ta belgidan iborat bo'lishi kerak.")
		return
	
	await state.update_data(customer_name=customer_name)
	await state.set_state(TolovHolati.mijoz_telefoni_kutilmoqda)
	
	# Telefon raqam so'rash
	phone_keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]
		],
		resize_keyboard=True,
		one_time_keyboard=True
	)
	
	await message.answer(
		f"✅ Ism qabul qilindi: <b>{customer_name}</b>\n\n"
		f"📱 <b>Telefon raqamingizni yuboring:</b>\n"
		f"Tugmani bosing yoki qo'lda kiriting (+998901234567)",
		reply_markup=phone_keyboard,
		parse_mode="HTML"
	)

@router.message(TolovHolati.mijoz_telefoni_kutilmoqda, F.contact)
async def customer_phone_contact_handler(message: Message, state: FSMContext):
	"""Mijoz telefon raqamini contact orqali qabul qilish"""
	phone_number = message.contact.phone_number
	
	await state.update_data(customer_phone=phone_number)
	await state.set_state(TolovHolati.mijoz_joylashuvi_kutilmoqda)
	
	# Joylashuv so'rash

	
	await message.answer(
		f"✅ Telefon qabul qilindi: <b>{phone_number}</b>\n\n"
		f"📍 <b>Joylashuvingizni yuboring:</b>\n"
		f"Tugmani bosing yoki manzilni yozing",
		parse_mode="HTML"
	)

@router.message(TolovHolati.mijoz_telefoni_kutilmoqda)
async def customer_phone_text_handler(message: Message, state: FSMContext):
	"""Mijoz telefon raqamini matn orqali qabul qilish"""
	phone_text = message.text.strip()
	
	# Telefon raqam formatini tekshirish
	phone_pattern = r'^(\+998|998|8)?[0-9]{9}$'
	if not re.match(phone_pattern, phone_text.replace(' ', '').replace('-', '')):
		await message.answer(
			"⚠️ Noto'g'ri telefon raqam formati.\n"
			"To'g'ri format: +998901234567 yoki 901234567"
		)
		return
	
	await state.update_data(customer_phone=phone_text)
	await state.set_state(TolovHolati.mijoz_joylashuvi_kutilmoqda)
	
	# Joylashuv so'rash
	location_keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[KeyboardButton(text="📍 Joylashuvni yuborish", request_location=True)],
			[KeyboardButton(text="✍️ Manzilni yozish")]
		],
		resize_keyboard=True,
		one_time_keyboard=True
	)
	
	await message.answer(
		f"✅ Telefon qabul qilindi: <b>{phone_text}</b>\n\n"
		f"📍 <b>Joylashuvingizni yuboring:</b>\n"
		f"Tugmani bosing yoki manzilni yozing",
		reply_markup=location_keyboard,
		parse_mode="HTML"
	)

@router.message(TolovHolati.mijoz_joylashuvi_kutilmoqda, F.location)
async def customer_location_handler(message: Message, state: FSMContext):
	"""Mijoz joylashuvini qabul qilish"""
	latitude = message.location.latitude
	longitude = message.location.longitude
	location_text = f"Lat: {latitude}, Lon: {longitude}"
	
	await state.update_data(customer_location=location_text)
	await show_customer_info_confirmation(message, state)

@router.message(TolovHolati.mijoz_joylashuvi_kutilmoqda)
async def customer_location_text_handler(message: Message, state: FSMContext):
	"""Mijoz manzilini matn orqali qabul qilish"""
	if message.text == "✍️ Manzilni yozish":
		await message.answer(
			"✍️ <b>Manzilni yozing:</b>\n"
			"Masalan: Toshkent, Chilonzor tumani, 5-kvartal",
			parse_mode="HTML",
			reply_markup=ReplyKeyboardRemove()
		)
		return
	
	location_text = message.text.strip()
	
	if len(location_text) < 5:
		await message.answer("⚠️ Manzil kamida 5 ta belgidan iborat bo'lishi kerak.")
		return
	
	await state.update_data(customer_location=location_text)
	await show_customer_info_confirmation(message, state)

async def show_customer_info_confirmation(message: Message, state: FSMContext):
	"""Mijoz ma'lumotlarini tasdiqlash uchun ko'rsatish"""
	state_data = await state.get_data()
	
	customer_name = state_data.get('customer_name')
	customer_phone = state_data.get('customer_phone')
	customer_location = state_data.get('customer_location')
	product_name = state_data.get('product_name')
	product_price = state_data.get('product_price')
	payment_amount = state_data.get('payment_amount')
	payment_method = state_data.get('payment_method', 'WALLET')
	remaining_debt = state_data.get('remaining_debt', 0)
	
	# Ma'lumotlarni ko'rsatish
	confirmation_text = (
		f"📋 <b>Ma'lumotlaringizni tasdiqlang:</b>\n\n"
		f"👤 <b>Ism:</b> {customer_name}\n"
		f"📱 <b>Telefon:</b> {customer_phone}\n"
		f"📍 <b>Manzil:</b> {customer_location}\n\n"
		f"🛍 <b>Tovar:</b> {product_name}\n"
		f"💰 <b>Asosiy narx:</b> {product_price:,} UZS\n"
		f"💳 <b>To'langan:</b> {payment_amount:,} UZS\n"
	)
	
	if remaining_debt > 0:
		confirmation_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,} UZS\n"
	elif remaining_debt < 0:
		confirmation_text += f"🎁 <b>Ortiqcha to'lov:</b> {abs(remaining_debt):,} UZS\n"
	else:
		confirmation_text += "✅ <b>To'liq to'lov</b>\n"
	
	confirmation_text += f"\n❓ Ma'lumotlar to'g'rimi?"
	
	# Tasdiqlash tugmalari
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ Ha, to'g'ri", callback_data="confirm_customer_info"),
				InlineKeyboardButton(text="✏️ O'zgartirish", callback_data="edit_customer_info")
			]
		]
	)
	
	await state.set_state(TolovHolati.mijoz_tasdiqlash)
	
	await message.answer(
		confirmation_text,
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.callback_query(F.data == "confirm_customer_info")
async def confirm_customer_info_callback(callback: CallbackQuery, state: FSMContext):
	"""Mijoz ma'lumotlarini tasdiqlash"""
	await finalize_customer_order(callback.message, state)
	await callback.answer()

@router.callback_query(F.data == "edit_customer_info")
async def edit_customer_info_callback(callback: CallbackQuery, state: FSMContext):
	"""Mijoz ma'lumotlarini o'zgartirish"""
	await state.set_state(TolovHolati.mijoz_ismi_kutilmoqda)
	
	await callback.message.edit_text(
		"✏️ <b>Ma'lumotlarni qaytadan kiriting</b>\n\n"
		"👤 <b>Ism-familiyangizni kiriting:</b>",
		parse_mode="HTML"
	)
	await callback.answer()

async def finalize_customer_order(message: Message, state: FSMContext):
	"""Mijoz buyurtmasini yakunlash - MUKAMMAL TUZATILGAN"""
	state_data = await state.get_data()
	
	customer_name = state_data.get('customer_name')
	customer_phone = state_data.get('customer_phone')
	customer_location = state_data.get('customer_location')
	product_id = state_data.get('product_id')
	product_name = state_data.get('product_name')
	product_price = state_data.get('product_price')
	payment_amount = state_data.get('payment_amount')
	payment_method = state_data.get('payment_method', 'WALLET')
	remaining_debt = state_data.get('remaining_debt', 0)
	
	# Sotishni qayd qilish
	success = record_sale(
		product_id=product_id,
		user_id=message.from_user.id,
		product_price=product_price,
		payment_method=payment_method,
		customer_name=customer_name,
		customer_phone=customer_phone,
		customer_location=customer_location
	)
	
	if success:
		# Google Sheets ga saqlash
		order_data = {
			'sana': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			'mijoz_ismi': customer_name,
			'telefon': customer_phone,
			'manzil': customer_location,
			'tovar': product_name,
			'asosiy_narx': f'{product_price:,} UZS',
			'tolangan_summa': f'{payment_amount:,} UZS',
			'qolgan_qarz': f'{remaining_debt:,} UZS',
			'tolov_usuli': payment_method,
			'username': f'@{message.from_user.username or "Yo\'q"}',
			'user_id': str(message.from_user.id)
		}
		
		sheets_success = save_order_to_google_sheets(order_data)
		
		# Adminlarga to'liq ma'lumot yuborish - YANGILANGAN TASDIQLASH TUGMASI BILAN
		admin_text = (
			f"📋 <b>TO'LIQ BUYURTMA MA'LUMOTLARI</b>\n\n"
			f"🛍 <b>Tovar:</b> {product_name}\n"
			f"💰 <b>Narx:</b> {product_price:,} UZS\n"
			f"💳 <b>To'langan:</b> {payment_amount:,} UZS\n"
			f"📋 <b>Qarz:</b> {remaining_debt:,} UZS\n"
			f"💳 <b>To'lov:</b> {payment_method}\n\n"
			f"👤 <b>Mijoz ma'lumotlari:</b>\n"
			f"• Ism: {customer_name}\n"
			f"• Telefon: {customer_phone}\n"
			f"• Manzil: {customer_location}\n"
			f"• Username: @{message.from_user.username or 'Yo\'q'}\n"
			f"• User ID: {message.from_user.id}\n\n"
			f"📊 Google Sheets: {'✅ Saqlandi' if sheets_success else '❌ Xatolik'}"
		)
		
		# YANGI: Tasdiqlash tugmasi - faqat HELPER_ID uchun
		order_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(
						text="✅ Buyurtmani tasdiqlash",
						callback_data=f"confirm_order_{message.from_user.id}_{product_id}"
					)
				]
			]
		)
		
		# Adminlarga yuborish
		for admin_id in ADMINS:
			try:
				await message.bot.send_message(
					chat_id=admin_id,
					text=admin_text,
					parse_mode="HTML"
				)
			except Exception as e:
				logging.error(f"Error sending to admin {admin_id}: {e}")
		
		# ORDER_CHANNEL ga yuborish - TASDIQLASH TUGMASI BILAN
		if ORDER_CHANNEL:
			try:
				await message.bot.send_message(
					chat_id=ORDER_CHANNEL,
					text=admin_text,
					reply_markup=order_keyboard,
					parse_mode="HTML"
				)
			except Exception as e:
				logging.error(f"Error sending to ORDER_CHANNEL: {e}")
		
		# Mijozga yakuniy xabar
		final_text = (
			f"🎉 <b>Buyurtma muvaffaqiyatli rasmiylashtrildi!</b>\n\n"
			f"📋 <b>Buyurtma ma'lumotlari:</b>\n"
			f"👤 Ism: {customer_name}\n"
			f"📱 Telefon: {customer_phone}\n"
			f"📍 Manzil: {customer_location}\n\n"
			f"🛍 <b>Tovar:</b> {product_name}\n"
			f"💰 <b>Narx:</b> {product_price:,} UZS\n"
			f"💳 <b>To'langan:</b> {payment_amount:,} UZS\n"
		)
		
		if remaining_debt > 0:
			final_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,} UZS\n"
		elif remaining_debt < 0:
			final_text += f"🎁 <b>Ortiqcha to'lov:</b> {abs(remaining_debt):,} UZS\n"
		
		final_text += f"\n✅ Tez orada siz bilan bog'lanamiz!"
		
		# Asosiy klaviaturani qaytarish
		main_keyboard = ReplyKeyboardMarkup(
			keyboard=[
				[
					KeyboardButton(text=HISOBNI_TOLDIRISH),
					KeyboardButton(text=HISOBIM)
				],
				[
					KeyboardButton(text=REFERRAL_BUTTON),
					KeyboardButton(text=SERVICES_BUTTON)
				]
			],
			resize_keyboard=True
		)
		
		await message.answer(
			final_text,
			reply_markup=main_keyboard,
			parse_mode="HTML"
		)
	
	await state.clear()

# YANGI: ORDER CONFIRMATION HANDLER - FAQAT HELPER_ID UCHUN
@router.callback_query(F.data.startswith("confirm_order_"))
async def confirm_order_callback(callback: CallbackQuery):
	"""Buyurtmani tasdiqlash - faqat HELPER_ID uchun"""
	if callback.from_user.id != HELPER_ID:
		await callback.answer("⚠️ Bu funksiya uchun sizda huquq yo'q!", show_alert=True)
		return
	
	parts = callback.data.split("_")
	if len(parts) < 4:
		await callback.answer("❌ Noto'g'ri callback data.")
		return
	
	user_id = int(parts[2])
	product_id = parts[3]
	
	# Xabarni yangilash
	try:
		await callback.message.edit_text(
			f"✅ <b>BUYURTMA TASDIQLANDI</b>\n\n{callback.message.text}",
			parse_mode="HTML"
		)
	except Exception:
		pass
	
	# Mijozga tasdiqlash xabari yuborish
	try:
		await callback.bot.send_message(
			chat_id=user_id,
			text="🎉 <b>Buyurtmangiz tasdiqlandi!</b>\n\n"
			     "✅ Sizning buyurtmangiz qabul qilindi va tez orada yetkazib beriladi.\n"
			     "📞 Agar savollaringiz bo'lsa, admin bilan bog'laning.",
			parse_mode="HTML"
		)
	except Exception as e:
		logging.error(f"Error sending confirmation to user {user_id}: {e}")
	
	await callback.answer("✅ Buyurtma tasdiqlandi!")

# INVOICE TIMEOUT HANDLER - YANGILANGAN PRODUCT QAYTARISH BILAN
async def delete_invoice_after_timeout(bot, chat_id, message_id, user_id, payment_method, product_id=None, timeout=300):
	"""5 daqiqadan keyin invoice ni o'chirish va product qaytarish"""
	await asyncio.sleep(timeout)
	
	try:
		await bot.delete_message(chat_id=chat_id, message_id=message_id)
		logging.info(f"Invoice deleted after timeout for user {user_id}, method {payment_method}")
		
		# YANGI: Product ID mavjud bo'lsa, tovarni qaytadan ko'rsatish
		if product_id:
			product = get_product(product_id)
			if product and product[9]:  # product faol bo'lsa
				await bot.send_message(
					chat_id=chat_id,
					text=f"⏰ {payment_method} to'lov vaqti tugadi.\n"
					     f"Tovar qaytadan ko'rsatilmoqda...",
				)
				
				# Tovarni qaytadan ko'rsatish
				from tovar import show_product_with_payment_buttons
				
				# Fake message object yaratish
				class FakeMessage:
					def __init__(self, chat_id, bot):
						self.chat = type('obj', (object,), {'id': chat_id})
						self.bot = bot
					
					
					async def answer(self, text, **kwargs):
						return await self.bot.send_message(chat_id=self.chat.id, text=text, **kwargs)
					
					
					async def answer_photo(self, photo, **kwargs):
						return await self.bot.send_photo(chat_id=self.chat.id, photo=photo, **kwargs)
					
					
					async def answer_video(self, video, **kwargs):
						return await self.bot.send_video(chat_id=self.chat.id, video=video, **kwargs)
				
				fake_message = FakeMessage(chat_id, bot)
				await show_product_with_payment_buttons(fake_message, product_id, is_callback=False)
			else:
				await bot.send_message(
					chat_id=chat_id,
					text=f"⏰ {payment_method} to'lov vaqti tugadi.\n"
					     f"Iltimos, qaytadan urinib ko'ring.",
				)
		else:
			await bot.send_message(
				chat_id=chat_id,
				text=f"⏰ {payment_method} to'lov vaqti tugadi.\n"
				     f"Iltimos, qaytadan urinib ko'ring.",
			)
	except Exception as e:
		logging.debug(f"Could not delete invoice: {e}")

# PRE-CHECKOUT HANDLER
@router.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery, state: FSMContext):
	"""Pre-checkout query handler"""
	logging.info(f"Pre-checkout query from user {pre_checkout_query.from_user.id}")
	
	try:
		await pre_checkout_query.answer(ok=True)
		logging.info("Pre-checkout query answered successfully")
	except Exception as e:
		logging.error(f"Error in pre-checkout: {e}")
		await pre_checkout_query.answer(ok=False, error_message="To'lovda xatolik yuz berdi.")

# SUCCESSFUL PAYMENT HANDLER - YANGILANGAN
@router.message(F.successful_payment)
async def successful_payment_handler(message: Message, state: FSMContext):
	"""Muvaffaqiyatli to'lov handler"""
	payment = message.successful_payment
	user_id = message.from_user.id
	
	logging.info(f"Successful payment from user {user_id}: {payment.total_amount / 100} UZS")
	
	# Payload dan ma'lumotlarni olish
	payload_parts = payment.invoice_payload.split("_")
	
	if len(payload_parts) >= 4 and payload_parts[0] == "product" and payload_parts[1] == "payment":
		# Product payment
		product_id = payload_parts[2]
		amount = int(payload_parts[3])
		payment_method = payload_parts[4] if len(payload_parts) > 4 else "telegram"
		
		product = get_product(product_id)
		user = get_user(user_id)
		
		if not product or not user:
			await message.answer("❌ Xatolik yuz berdi. Admin bilan bog'laning.")
			return
		
		product_name = product[2]
		product_price = product[4]
		username = user[1] or "Yo'q"
		
		# Foydalanuvchiga muvaffaqiyat xabari - YANGILANGAN
		remaining_debt = product_price - amount
		success_text = (
			f"🎉 <b>To'lov muvaffaqiyatli amalga oshirildi!</b>\n\n"
			f"✅ To'langan: {amount:,.0f} UZS\n"
			f"🛍 Tovar: {product_name}\n"
			f"💰 Asosiy narx: {product_price:,.0f} UZS\n"
		)
		
		if remaining_debt > 0:
			success_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,.0f} UZS\n"
		elif remaining_debt < 0:
			success_text += f"🎁 <b>Chegirma:</b> {abs(remaining_debt):,.0f} UZS\n"
		else:
			success_text += "✅ <b>To'liq to'lov</b>\n"
		
		success_text += f"\n📋 <b>Buyurtmangizni rasmiylashtirish uchun ma'lumotlaringizni kiriting</b>"
		
		await message.answer(success_text, parse_mode="HTML")
		
		# Mijoz ma'lumotlarini so'rash
		await message.answer(
			"👤 <b>Ism-familiyangizni kiriting:</b>",
			parse_mode="HTML",
			reply_markup=ReplyKeyboardRemove()
		)
		
		await state.update_data(
			product_id=product_id,
			product_name=product_name,
			product_price=product_price,
			payment_amount=amount,
			payment_method=payment_method.upper(),
			remaining_debt=remaining_debt
		)
		await state.set_state(TolovHolati.mijoz_ismi_kutilmoqda)
	
	else:
		# Boshqa to'lovlar (hisobni to'ldirish)
		amount = payment.total_amount // 100
		
		user = get_user(user_id)
		if user:
			old_balance = user[4]  # TUZATILGAN: balance index
			new_balance = old_balance + amount
			
			success = update_balance(user_id, new_balance)
			
			if success:
				add_transaction(user_id, amount, "deposit", f"Telegram to'lov: {amount:,} UZS")
				
				await message.answer(
					f"✅ <b>To'lov muvaffaqiyatli!</b>\n\n"
					f"💰 <b>To'langan summa:</b> {amount:,} UZS\n"
					f"💳 <b>Eski balans:</b> {old_balance:,} UZS\n"
					f"💎 <b>Yangi balans:</b> {new_balance:,} UZS\n\n"
					f"🎉 Hisobingiz muvaffaqiyatli to'ldirildi!",
					parse_mode="HTML"
				)
				
				# Adminlarga xabar yuborish
				admin_text = (
					f"💰 <b>Yangi to'lov!</b>\n\n"
					f"👤 <b>Foydalanuvchi:</b> {user[2]}\n"
					f"🆔 <b>User ID:</b> {user_id}\n"
					f"💰 <b>Summa:</b> {amount:,} UZS\n"
					f"💎 <b>Yangi balans:</b> {new_balance:,} UZS"
				)
				
				for admin_id in ADMINS:
					try:
						await message.bot.send_message(
							chat_id=admin_id,
							text=admin_text,
							parse_mode="HTML"
						)
					except Exception as e:
						logging.error(f"Error sending to admin {admin_id}: {e}")
			else:
				await message.answer("❌ Balansni yangilashda xatolik yuz berdi.")
		else:
			await message.answer("❌ Foydalanuvchi ma'lumotlari topilmadi.")
		
		# State ni tozalash faqat hisobni to'ldirish uchun
		await state.clear()

# MAIN MENU HANDLERS
@router.message(F.text == HISOBNI_TOLDIRISH)
async def balance_refill_handler(message: Message, state: FSMContext):
	user_id = message.from_user.id
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	is_subscribed = await show_subscription_keyboard_if_needed(message, message.bot, user_id)
	if not is_subscribed:
		return
	
	user = get_user(user_id)
	if not user:
		await message.answer("⚠️ Foydalanuvchi ma'lumotlari topilmadi.")
		return
	
	balance = user[4]  # TUZATILGAN: balance index
	
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text=CLICK_TOLOV),
				KeyboardButton(text=UzCard)
			],
			[
				KeyboardButton(text=HumoCard)
			],
			[
				KeyboardButton(text=BOSH_MENYU)
			]
		],
		resize_keyboard=True
	)
	
	await message.answer(
		f"💰 <b>Hisobni to'ldirish</b>\n\n"
		f"💎 <b>Joriy balans:</b> {balance:,} UZS\n\n"
		f"💳 To'lov usulini tanlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.message(F.text == HISOBIM)
async def my_account_handler(message: Message):
	user_id = message.from_user.id
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	is_subscribed = await show_subscription_keyboard_if_needed(message, message.bot, user_id)
	if not is_subscribed:
		return
	
	user = get_user(user_id)
	if not user:
		await message.answer("⚠️ Foydalanuvchi ma'lumotlari topilmadi.")
		return
	
	bot_id = user[3]  # TUZATILGAN: bot_id index
	balance = user[4]  # TUZATILGAN: balance index
	referral_count = get_user_referral_count(user_id)
	
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text=TOLOVLAR_TARIXI)
			],
			[
				KeyboardButton(text=BOSH_MENYU)
			]
		],
		resize_keyboard=True
	)
	
	await message.answer(
		f"👤 <b>Sizning hisobingiz</b>\n\n"
		f"🆔 <b>ID:</b> <code>{bot_id}</code>\n"
		f"👤 <b>Ism:</b> {user[2]}\n"
		f"💰 <b>Balans:</b> {balance:,} UZS\n"
		f"👥 <b>Taklif qilganlar:</b> {referral_count} kishi\n"
		f"📅 <b>Ro'yxatdan o'tgan:</b> {user[5][:10] if user[5] else 'Noma\'lum'}",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.message(F.text == TOLOVLAR_TARIXI)
async def payment_history_handler(message: Message):
	user_id = message.from_user.id
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	transactions = get_user_transactions(user_id)
	
	if not transactions:
		await message.answer(
			"📊 <b>To'lovlar tarixi</b>\n\n"
			"❌ Hozircha to'lovlar mavjud emas.",
			parse_mode="HTML"
		)
		return
	
	text = "📊 <b>To'lovlar tarixi</b>\n\n"
	
	for transaction in transactions[-10:]:  # Oxirgi 10 ta tranzaksiya
		trans_type = "➕" if transaction[3] == "deposit" else "➖"
		text += f"{trans_type} <b>{transaction[2]:,} UZS</b> - {transaction[4]}\n"
		text += f"📅 {transaction[5][:16]}\n\n"
	
	if len(transactions) > 10:
		text += f"... va yana {len(transactions) - 10} ta tranzaksiya"
	
	await message.answer(text, parse_mode="HTML")

@router.message(F.text == BOSH_MENYU)
async def main_menu_handler(message: Message):
	user_id = message.from_user.id
	user = get_user(user_id)
	
	if not user:
		await message.answer("⚠️ Foydalanuvchi ma'lumotlari topilmadi. /start buyrug'ini yuboring.")
		return
	
	await show_main_menu(message, user)

@router.message(F.text == SERVICES_BUTTON)
async def services_handler(message: Message):
	user_id = message.from_user.id
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	is_subscribed = await show_subscription_keyboard_if_needed(message, message.bot, user_id)
	if not is_subscribed:
		return
	
	await message.answer(
		"🛍 <b>Xizmatlar bo'limi</b>\n\n"
		"Bu yerda turli xizmatlar va tovarlar bo'ladi.\n"
		"Hozircha ishlab chiqilmoqda...",
		parse_mode="HTML"
	)

# PAYMENT METHOD HANDLERS
@router.message(F.text.in_([CLICK_TOLOV, UzCard, HumoCard]))
async def payment_method_handler(message: Message, state: FSMContext):
	user_id = message.from_user.id
	
	if is_user_blocked(user_id):
		await message.answer("⚠️ Siz bloklangansiz. Admin bilan bog'laning.")
		return
	
	payment_method = message.text
	
	await state.update_data(payment_method=payment_method)
	await state.set_state(TolovHolati.miqdor_kutilmoqda)
	
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text="10,000"),
				KeyboardButton(text="25,000")
			],
			[
				KeyboardButton(text="50,000"),
				KeyboardButton(text="100,000")
			],
			[
				KeyboardButton(text="250,000"),
				KeyboardButton(text="500,000")
			],
			[
				KeyboardButton(text=ORQAGA)
			]
		],
		resize_keyboard=True
	)
	
	method_name = {
		CLICK_TOLOV: "CLICK",
		UzCard: "UzCard",
		HumoCard: "HumoCard"
	}.get(payment_method, payment_method)
	
	await message.answer(
		f"💳 <b>{method_name} orqali to'lov</b>\n\n"
		f"💰 To'lov miqdorini tanlang yoki kiriting:\n"
		f"(Minimal: 5,000 UZS)",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.message(TolovHolati.miqdor_kutilmoqda)
async def amount_handler(message: Message, state: FSMContext):
	if message.text == ORQAGA:
		await balance_refill_handler(message, state)
		return
	
	try:
		amount = int(message.text.replace(",", "").replace(" ", ""))
		if amount < 5000:
			await message.answer("⚠️ Minimal to'lov miqdori 5,000 UZS.")
			return
		if amount > 10000000:
			await message.answer("⚠️ Maksimal to'lov miqdori 10,000,000 UZS.")
			return
	except ValueError:
		await message.answer("⚠️ Noto'g'ri miqdor. Faqat raqam kiriting.")
		return
	
	state_data = await state.get_data()
	payment_method = state_data.get('payment_method')
	
	await state.update_data(amount=amount)
	await state.set_state(TolovHolati.tolov_kutilmoqda)
	
	method_name = {
		CLICK_TOLOV: "CLICK",
		UzCard: "UzCard",
		HumoCard: "HumoCard"
	}.get(payment_method, payment_method)
	
	image_urls = {
		CLICK_TOLOV: "https://marketing.uz/uz/uploads/articles/1222/article-original.jpg",
		UzCard: "https://roobotmee.uz/img/ksjdns.png",
		HumoCard: "https://roobotmee.uz/img/hdusafd3sajhjkasd.png"
	}
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga", callback_data="back_to_amount"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_payment")
			]
		]
	)
	
	try:
		await bot.send_invoice(
			chat_id=message.chat.id,
			title=f"💰 {method_name} orqali hisobni to'ldirish",
			description=f"Hisobingizni {amount:,} UZS ga to'ldirish",
			payload=f"balance_refill_{amount}_{method_name.lower()}",
			provider_token=PAYMENT_TOKEN,
			currency="UZS",
			prices=[
				LabeledPrice(label=f"Hisobni to'ldirish", amount=amount * 100),
			],
			start_parameter="balance_refill",
			provider_data=None,
			photo_url=image_urls.get(payment_method, image_urls[UzCard]),
			photo_size=512,
			photo_width=512,
			photo_height=512,
			need_name=False,
			need_phone_number=False,
			need_email=False,
			need_shipping_address=False,
			send_phone_number_to_provider=False,
			send_email_to_provider=False,
			is_flexible=False,
			disable_notification=False,
			protect_content=False,
			reply_to_message_id=None,
			allow_sending_without_reply=True,
			request_timeout=15,
			reply_markup=inline_keyboard
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, keyinroq urinib ko'ring."
		)
		await state.clear()

@router.callback_query(F.data == "back_to_amount")
async def back_to_amount_callback(callback: CallbackQuery, state: FSMContext):
	await callback.message.delete()
	
	state_data = await state.get_data()
	payment_method = state_data.get('payment_method')
	
	keyboard = ReplyKeyboardMarkup(
		keyboard=[
			[
				KeyboardButton(text="10,000"),
				KeyboardButton(text="25,000")
			],
			[
				KeyboardButton(text="50,000"),
				KeyboardButton(text="100,000")
			],
			[
				KeyboardButton(text="250,000"),
				KeyboardButton(text="500,000")
			],
			[
				KeyboardButton(text=ORQAGA)
			]
		],
		resize_keyboard=True
	)
	
	method_name = {
		CLICK_TOLOV: "CLICK",
		UzCard: "UzCard",
		HumoCard: "HumoCard"
	}.get(payment_method, payment_method)
	
	await callback.message.answer(
		f"💳 <b>{method_name} orqali to'lov</b>\n\n"
		f"💰 To'lov miqdorini tanlang yoki kiriting:\n"
		f"(Minimal: 5,000 UZS)",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	
	await state.set_state(TolovHolati.miqdor_kutilmoqda)
	await callback.answer()

@router.callback_query(F.data == "cancel_payment")
async def cancel_payment_callback(callback: CallbackQuery, state: FSMContext):
	await callback.message.delete()
	await state.clear()
	
	user_id = callback.from_user.id
	user = get_user(user_id)
	
	if user:
		await show_main_menu(callback.message, user)
	
	await callback.answer("To'lov bekor qilindi")

async def main():
	"""Bot ishga tushirish"""
	try:
		create_tables()
		logging.info("Database tables created successfully")
		
		# YANGI: Admin jadvallarini yaratish
		admin.create_bot_status_table()
		
		await dp.start_polling(bot)
	except Exception as e:
		
		logging.exception(f"Error starting bot: {e}")

if __name__ == "__main__":
	asyncio.run(main())
 
 
 