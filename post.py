import logging
import asyncio
from aiogram import Router, F
from aiogram.types import (
	Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
	ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Import ADMINS directly from config.py
from config import ADMINS
from database import create_connection

router = Router()

class PostState(StatesGroup):
	selecting_post_type = State()
	waiting_for_post_text = State()
	waiting_for_post_image = State()
	waiting_for_post_video = State()
	waiting_for_post_button_text = State()
	waiting_for_post_button_url = State()
	waiting_for_more_buttons = State()
	waiting_for_confirmation = State()

@router.callback_query(F.data == "create_post")
async def create_post_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(PostState.selecting_post_type)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🖼 Rasmli post", callback_data="post_with_image")
			],
			[
				InlineKeyboardButton(text="🎥 Videoli post", callback_data="post_with_video")
			],
			[
				InlineKeyboardButton(text="📝 Matnli post", callback_data="post_text_only")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await callback.message.edit_text(
		"📝 <b>Post yaratish</b>\n\n"
		"Post turini tanlang:",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data == "post_with_image")
async def post_with_image_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(post_type="image")
	await state.set_state(PostState.waiting_for_post_text)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await callback.message.edit_text(
		"📝 <b>Rasmli post yaratish</b>\n\n"
		"Post uchun caption kiriting (HTML formatida yozishingiz mumkin):",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data == "post_with_video")
async def post_with_video_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(post_type="video")
	await state.set_state(PostState.waiting_for_post_text)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await callback.message.edit_text(
		"📝 <b>Videoli post yaratish</b>\n\n"
		"Post uchun caption kiriting (HTML formatida yozishingiz mumkin):",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data == "post_text_only")
async def post_text_only_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(post_type="text")
	await state.set_state(PostState.waiting_for_post_text)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await callback.message.edit_text(
		"📝 <b>Matnli post yaratish</b>\n\n"
		"Post matnini kiriting (HTML formatida yozishingiz mumkin):",
		reply_markup=inline_keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.message(PostState.waiting_for_post_text)
async def process_post_text(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	post_text = message.text or message.caption or ""
	
	if not post_text:
		await message.answer("⚠️ Post matni bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(post_text=post_text)
	
	state_data = await state.get_data()
	post_type = state_data.get("post_type", "text")
	
	if post_type == "image":
		await state.set_state(PostState.waiting_for_post_image)
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
				]
			]
		)
		
		await message.answer(
			"🖼 Post uchun rasm yuboring:",
			reply_markup=inline_keyboard
		)
	elif post_type == "video":
		await state.set_state(PostState.waiting_for_post_video)
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
				]
			]
		)
		
		await message.answer(
			"🎥 Post uchun video yuboring:",
			reply_markup=inline_keyboard
		)
	else:
		# For text-only posts, go directly to button question
		await ask_for_button(message, state)

@router.message(PostState.waiting_for_post_image, F.photo)
async def process_post_image(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	photo_file_id = message.photo[-1].file_id
	await state.update_data(post_image=photo_file_id, post_video=None)
	
	await ask_for_button(message, state)

@router.message(PostState.waiting_for_post_video, F.video)
async def process_post_video(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	video_file_id = message.video.file_id
	await state.update_data(post_video=video_file_id, post_image=None)
	
	await ask_for_button(message, state)

@router.message(PostState.waiting_for_post_image)
async def invalid_image(message: Message):
	await message.answer("⚠️ Iltimos, rasm yuboring.")

@router.message(PostState.waiting_for_post_video)
async def invalid_video(message: Message):
	await message.answer("⚠️ Iltimos, video yuboring.")

async def ask_for_button(message, state: FSMContext):
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ Ha", callback_data="add_button"),
				InlineKeyboardButton(text="❌ Yo'q", callback_data="no_buttons")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await message.answer(
		"🔘 Post uchun tugma qo'shmoqchimisiz?",
		reply_markup=inline_keyboard
	)

@router.callback_query(F.data == "add_button")
async def add_button_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	# Initialize buttons array if it doesn't exist
	state_data = await state.get_data()
	if "buttons" not in state_data:
		await state.update_data(buttons=[])
	
	await state.set_state(PostState.waiting_for_post_button_text)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await callback.message.edit_text(
		"🔘 Tugma uchun nom kiriting:",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "no_buttons")
async def no_buttons_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(buttons=[])
	await show_post_preview(callback.message, state)
	await callback.answer()

@router.message(PostState.waiting_for_post_button_text)
async def process_post_button_text(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	button_text = message.text
	
	if not button_text:
		await message.answer("⚠️ Tugma matni bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	await state.update_data(current_button_text=button_text)
	await state.set_state(PostState.waiting_for_post_button_url)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	await message.answer(
		"🔗 Tugma uchun URL manzilini kiriting:\n\n"
		"Masalan: https://t.me/example",
		reply_markup=inline_keyboard
	)

@router.message(PostState.waiting_for_post_button_url)
async def process_post_button_url(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	button_url = message.text
	
	if not button_url:
		await message.answer("⚠️ URL manzil bo'sh bo'lishi mumkin emas. Iltimos, qaytadan kiriting:")
		return
	
	if not button_url.startswith(("http://", "https://", "t.me/")):
		button_url = "https://" + button_url
	
	state_data = await state.get_data()
	current_button_text = state_data.get("current_button_text")
	buttons = state_data.get("buttons", [])
	
	buttons.append({"text": current_button_text, "url": button_url})
	await state.update_data(buttons=buttons)
	
	await state.set_state(PostState.waiting_for_more_buttons)
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ Ha", callback_data="add_button"),
				InlineKeyboardButton(text="❌ Yo'q", callback_data="no_more_buttons")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
			]
		]
	)
	
	# Show current buttons
	buttons_text = "🔘 Qo'shilgan tugmalar:\n"
	for i, btn in enumerate(buttons, 1):
		buttons_text += f"{i}. {btn['text']} - {btn['url']}\n"
	
	await message.answer(
		f"{buttons_text}\n"
		"Yana tugma qo'shmoqchimisiz?",
		reply_markup=inline_keyboard
	)

@router.callback_query(F.data == "no_more_buttons")
async def no_more_buttons_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await show_post_preview(callback.message, state)
	await callback.answer()

async def show_post_preview(message, state: FSMContext):
	state_data = await state.get_data()
	post_text = state_data.get("post_text", "")
	post_type = state_data.get("post_type", "text")
	post_image = state_data.get("post_image")
	post_video = state_data.get("post_video")
	buttons = state_data.get("buttons", [])
	
	inline_keyboard = []
	
	# Add all buttons from the state
	row = []
	for i, btn in enumerate(buttons):
		row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
		
		# Create a new row after every 2 buttons
		if (i + 1) % 2 == 0 or i == len(buttons) - 1:
			inline_keyboard.append(row)
			row = []
	
	# Add control buttons
	inline_keyboard.append([
		InlineKeyboardButton(text="✅ Yuborish", callback_data="send_post"),
		InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_post_creation")
	])
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
	
	await state.set_state(PostState.waiting_for_confirmation)
	
	preview_text = f"📝 <b>Post ko'rinishi:</b>\n\n{post_text}"
	
	if post_type == "image" and post_image:
		await message.answer_photo(
			photo=post_image,
			caption=preview_text,
			reply_markup=markup,
			parse_mode="HTML"
		)
	elif post_type == "video" and post_video:
		await message.answer_video(
			video=post_video,
			caption=preview_text,
			reply_markup=markup,
			parse_mode="HTML"
		)
	else:
		await message.answer(
			preview_text,
			reply_markup=markup,
			parse_mode="HTML"
		)

@router.callback_query(F.data == "send_post")
async def send_post_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	state_data = await state.get_data()
	post_text = state_data.get("post_text", "")
	post_type = state_data.get("post_type", "text")
	post_image = state_data.get("post_image")
	post_video = state_data.get("post_video")
	buttons = state_data.get("buttons", [])
	
	# Create inline keyboard with user-defined buttons
	inline_keyboard = []
	row = []
	for i, btn in enumerate(buttons):
		row.append(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
		
		# Create a new row after every 2 buttons
		if (i + 1) % 2 == 0 or i == len(buttons) - 1:
			inline_keyboard.append(row)
			row = []
	
	markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard) if inline_keyboard else None
	
	# Get all users from database
	conn = create_connection()
	if not conn:
		await callback.answer("⚠️ Ma'lumotlar bazasiga ulanishda xatolik yuz berdi.")
		return
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT id FROM users")
		users = cursor.fetchall()
		
		# Send a new message instead of editing the current one
		status_message = await callback.message.answer(
			"📤 Post yuborilmoqda...\n\n"
			f"Jami foydalanuvchilar: {len(users)} ta"
		)
		
		sent_count = 0
		error_count = 0
		
		for user in users:
			user_id = user[0]
			try:
				if post_type == "image" and post_image:
					await callback.bot.send_photo(
						chat_id=user_id,
						photo=post_image,
						caption=post_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				elif post_type == "video" and post_video:
					await callback.bot.send_video(
						chat_id=user_id,
						video=post_video,
						caption=post_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				else:
					await callback.bot.send_message(
						chat_id=user_id,
						text=post_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				sent_count += 1
				
				# Add delay to avoid flood limits
				await asyncio.sleep(0.05)
			except Exception as e:
				logging.error(f"Error sending post to user {user_id}: {e}")
				error_count += 1
		
		# Update the status message with results
		await status_message.edit_text(
			f"✅ Post yuborish yakunlandi!\n\n"
			f"✅ Yuborildi: {sent_count} ta\n"
			f"❌ Xatoliklar: {error_count} ta",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
					]
				]
			)
		)
	except Exception as e:
		logging.exception(f"Error sending post: {e}")
		# Send a new message with the error
		await callback.message.answer(
			f"❌ Post yuborishda xatolik yuz berdi: {e}",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="🔙 Admin paneli", callback_data="back_to_admin")
					]
				]
			)
		)
	finally:
		conn.close()
		await state.clear()
	
	await callback.answer()

@router.callback_query(F.data == "cancel_post_creation")
async def cancel_post_creation_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	
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
	await callback.answer("❌ Post yaratish bekor qilindi.")
