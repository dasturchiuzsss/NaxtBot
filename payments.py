import logging
import asyncio
from datetime import datetime
from aiogram import Bot, Router, F
from aiogram.types import (
	Message, LabeledPrice, PreCheckoutQuery, ContentType,
	InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
	ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import PAYMENT_TOKEN, ADMINS
from database import (
	get_user, update_balance, add_transaction, get_wallet,
	add_pending_payment, update_payment_status, get_all_payment_methods,
	get_payment_method, get_all_wallets
)
from utils import create_wallet_keyboard

router = Router()

# FIXED PAYMENT AMOUNT - Barcha to'lovlar uchun qat'iy summa
FIXED_PAYMENT_AMOUNT = 50000

class TolovHolati(StatesGroup):
	tolov_kutilmoqda = State()
	tolov_usuli_kutilmoqda = State()
	hamyon_tanlash = State()
	chek_kutilmoqda = State()
	summa_kutilmoqda = State()
	wallet_chek_kutilmoqda = State()

# PRODUCT PAYMENT HANDLERS - MUKAMMAL TIZIM

def create_product_payment_keyboard(product_id):
	"""
	Mahsulot uchun admin tomonidan qo'shilgan to'lov tugmalarini yaratish
	"""
	inline_keyboard = []
	
	# Admin tomonidan qo'shilgan to'lov usullarini olish
	payment_methods = get_all_payment_methods()
	
	# Auto payment tugmalari - admin qo'shgan
	if payment_methods:
		payment_buttons = []
		for method in payment_methods:
			method_id, method_name = method[0], method[1]
			payment_buttons.append(
				InlineKeyboardButton(
					text=f"💳 {method_name} [ Avto ]",
					callback_data=f"auto_payment_product_{method_id}_{product_id}"
				)
			)
		
		# Payment tugmalarini 2 tadan qilib joylashtirish
		for i in range(0, len(payment_buttons), 2):
			row = payment_buttons[i:i + 2]
			inline_keyboard.append(row)
	
	# Admin tomonidan qo'shilgan hamyonlarni olish
	wallets = get_all_wallets()
	
	# Hamyon tugmalari - admin qo'shgan
	if wallets:
		wallet_buttons = []
		for wallet in wallets:
			wallet_id, wallet_name, card_number, full_name, is_active = wallet
			if is_active:  # Faqat faol hamyonlar
				wallet_buttons.append(
					InlineKeyboardButton(
						text=f"💰 {wallet_name}",
						callback_data=f"wallet_payment_product_{wallet_id}_{product_id}"
					)
				)
		
		# Hamyon tugmalarini 2 tadan qilib joylashtirish
		for i in range(0, len(wallet_buttons), 2):
			row = wallet_buttons[i:i + 2]
			inline_keyboard.append(row)
	
	# Agar admin tugmalar qo'shmagan bo'lsa, default tugmalarni ko'rsatish
	if not wallets and not payment_methods:
		inline_keyboard.extend([
			[
				InlineKeyboardButton(text="💳 UzCard [ Avto ]", callback_data=f"uzcard_payment_product_{product_id}"),
				InlineKeyboardButton(text="💳 HumoCard [ Avto ]", callback_data=f"humo_payment_product_{product_id}")
			],
			[
				InlineKeyboardButton(text="💳 CLICK [ Avto ]", callback_data=f"click_payment_product_{product_id}"),
				InlineKeyboardButton(text="💰 Wallet", callback_data=f"default_wallet_payment_{product_id}")
			]
		])
	
	# Qo'shimcha tugmalar
	inline_keyboard.extend([
		[
			InlineKeyboardButton(text="🔧 Admin bilan bog'lanish", callback_data=f"contact_admin_{product_id}")
		],
		[
			InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
			InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_product_order_{product_id}")
		]
	])
	
	return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)

@router.callback_query(F.data.startswith("auto_payment_product_"))
async def auto_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Product uchun auto payment - admin qo'shgan to'lov usuli"""
	parts = callback.data.split("_")
	method_id = int(parts[3])
	product_id = parts[4]
	
	method = get_payment_method(method_id)
	if not method:
		await callback.answer("⚠️ To'lov usuli topilmadi.")
		return
	
	from tovar import get_product
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
	image_url = method[3]
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="💳 To'lovni boshlash", pay=True)
			],
			[
				InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}"),
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"cancel_product_order_{product_id}")
			]
		]
	)
	
	try:
		bot = callback.bot
		invoice_message = await bot.send_invoice(
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
		
		asyncio.create_task(
			delete_invoice_after_timeout(
				bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				method_name
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

@router.callback_query(F.data.startswith("contact_admin_"))
async def contact_admin_callback(callback: CallbackQuery):
	"""Admin bilan bog'lanish"""
	product_id = callback.data.split("_")[2]
	
	# Birinchi adminning ID sini olish
	admin_id = ADMINS[0] if ADMINS else None
	
	if admin_id:
		admin_link = f"tg://user?id={admin_id}"
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="💬 Admin bilan yozishish", url=admin_link)
				],
				[
					InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}")
				]
			]
		)
		
		await callback.message.edit_text(
			"🔧 <b>Admin bilan bog'lanish</b>\n\n"
			"Savollaringiz bo'lsa yoki yordam kerak bo'lsa, admin bilan bog'laning.\n\n"
			"Pastdagi tugmani bosing:",
			reply_markup=inline_keyboard,
			parse_mode="HTML"
		)
	else:
		await callback.answer("⚠️ Admin ma'lumotlari topilmadi.")
	
	await callback.answer()

# Default payment methods for products (fallback)
@router.callback_query(F.data.startswith("uzcard_payment_product_"))
async def uzcard_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle UzCard payment for product - default method"""
	product_id = callback.data.split("_")[3]
	
	from tovar import get_product
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
		invoice_message = await callback.bot.send_invoice(
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
		
		asyncio.create_task(
			delete_invoice_after_timeout(
				callback.bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"UzCard"
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

# Similar handlers for HumoCard and CLICK...
@router.callback_query(F.data.startswith("humo_payment_product_"))
async def humo_payment_product_callback(callback: CallbackQuery, state: FSMContext):
	"""Handle HumoCard payment for product - default method"""
	product_id = callback.data.split("_")[3]
	
	from tovar import get_product
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
		invoice_message = await callback.bot.send_invoice(
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
		
		asyncio.create_task(
			delete_invoice_after_timeout(
				callback.bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"HumoCard"
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
	"""Handle CLICK payment for product - default method"""
	product_id = callback.data.split("_")[3]
	
	from tovar import get_product
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
		invoice_message = await callback.bot.send_invoice(
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
		
		asyncio.create_task(
			delete_invoice_after_timeout(
				callback.bot,
				callback.message.chat.id,
				invoice_message.message_id,
				callback.from_user.id,
				"CLICK"
			)
		)
	except Exception as e:
		logging.exception(f"❌ To'lov yuborishda xato: {e}")
		await callback.message.answer(
			"⚠️ Telegram to'lovlari bilan bog'liq muammo yuzaga keldi. Iltimos, boshqa to'lov usulini tanlang."
		)
		await state.clear()
	
	await callback.answer()

async def delete_invoice_after_timeout(bot, chat_id, message_id, user_id, payment_method, timeout=300):
	"""Delete invoice message after timeout"""
	await asyncio.sleep(timeout)
	
	try:
		await bot.delete_message(chat_id=chat_id, message_id=message_id)
		await bot.send_message(
			chat_id=user_id,
			text=f"⏱️ {payment_method} orqali to'lov vaqti tugadi.\n\n"
			     f"💡 To'lovni qayta amalga oshirish uchun tovar linkini qayta oching."
		)
	except Exception as e:
		logging.error(f"Error deleting invoice message: {e}")

# Export the payment keyboard creation function
__all__ = ['router', 'create_product_payment_keyboard']
