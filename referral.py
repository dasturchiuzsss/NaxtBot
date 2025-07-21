import logging
from aiogram import Router, F
from aiogram.types import (
	Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
	ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import BOT_TOKEN, ADMINS
from database import (
	get_user, get_user_referral_count, get_top_referrers,
	get_setting, update_setting, get_user_referrals
)

router = Router()

class ReferralSettingsState(StatesGroup):
	waiting_for_new_reward = State()

REFERRAL_BUTTON = "👥 Pul ishlash"
MY_REFERRALS_BUTTON = "👨‍👨‍👦 Referallarim"
TOP_REFERRALS_BUTTON = "🏆 TOP-10 "
BACK_BUTTON = "🔙 Orqaga"

REFERRAL_SETTINGS_BUTTON = "⚙️ Referal sozlamalari"
CHANGE_REWARD_BUTTON = "💰 Mukofot miqdorini o'zgartirish"

REFERRAL_IMAGE_URL = "https://roobotmee.uz/img/hdusafd3sajhjkasd.png"

@router.message(F.text == REFERRAL_BUTTON)
async def referral_program_handler(message: Message):
	user_id = message.from_user.id
	user = get_user(user_id)
	
	if not user:
		await message.answer("⚠️ Siz ro'yxatdan o'tmagansiz. /start buyrug'ini yuboring.")
		return
	
	bot_id = user[3]
	referral_count = get_user_referral_count(user_id)
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	bot_username = (await message.bot.get_me()).username
	invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="♻️ Ulashish (Oddiy)",
					url=f"https://t.me/share/url?url={invite_link}&text=🤖 Telegram orqali pul ishlash uchun ajoyib bot! 💰 Har bir taklif qilgan do'stingiz uchun {reward_uzb} so'm olasiz."
				)
			],
			[
				InlineKeyboardButton(text=MY_REFERRALS_BUTTON, callback_data="my_referrals") , InlineKeyboardButton(text=TOP_REFERRALS_BUTTON, callback_data="top_referrals")
			],

			[
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_main")
			]
		]
	)
	
	try:
		await message.answer_photo(
			photo=REFERRAL_IMAGE_URL,
			caption=f"🔴 Sizning taklif havolangiz:\n\n"
			        f"{invite_link}\n\n"
			        f"Sizning referallaringiz: {referral_count} ta\n\n"
			        f"Sizga har bir taklif qilgan o'zbek referalingiz uchun {reward_uzb} so'm\n"
			        f"boshqa davlat referali uchun esa {reward_foreign} so'm beriladi (Feyk yani\n"
			        f"yolg'on reklama block bo'lishga sabab bo'ladi)\n\n"
			        f"👤 ID raqam: {bot_id}",
			reply_markup=inline_keyboard
		)
	except Exception as e:
		logging.error(f"Error sending referral image: {e}")
		await message.answer(
			f"🔴 Sizning taklif havolangiz:\n\n"
			f"{invite_link}\n\n"
			f"Sizning referallaringiz: {referral_count} ta\n\n"
			f"Sizga har bir taklif qilgan o'zbek referalingiz uchun {reward_uzb} so'm\n"
			f"boshqa davlat referali uchun esa {reward_foreign} so'm beriladi (Feyk yani\n"
			f"yolg'on reklama block bo'lishga sabab bo'ladi)\n\n"
			f"👤 ID raqam: {bot_id}",
			reply_markup=inline_keyboard
		)

@router.callback_query(F.data == "my_referrals")
async def my_referrals_callback(callback: CallbackQuery):
	user_id = callback.from_user.id
	user = get_user(user_id)
	
	if not user:
		await callback.answer("⚠️ Siz ro'yxatdan o'tmagansiz.")
		return
	
	referral_count = get_user_referral_count(user_id)
	referrals = get_user_referrals(user_id)
	
	reward_uzb = float(get_setting("referral_reward_uzb", "100"))
	total_earnings = referral_count * reward_uzb
	
	message_text = f"👨‍👨‍👦 Mening referallarim\n\n"
	message_text += f"Jami referallar soni: {referral_count} ta\n"
	message_text += f"Jami ishlagan pul: {total_earnings} so'm\n\n"
	
	if referrals:
		message_text += "Referallaringiz ro'yxati:\n"
		for i, referral in enumerate(referrals, 1):
			ref_username = referral[1] if referral[1] else "username yo'q"
			ref_full_name = referral[2]
			message_text += f"{i}. {ref_full_name} (@{ref_username})\n"
	else:
		message_text += "Hozircha sizda referallar yo'q. Do'stlaringizni taklif qiling!"
	
	try:
		if callback.message.photo:
			await callback.message.edit_caption(
				caption=message_text,
				reply_markup=InlineKeyboardMarkup(
					inline_keyboard=[
						[
							InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
						]
					]
				)
			)
		else:
			await callback.message.edit_text(
				message_text,
				reply_markup=InlineKeyboardMarkup(
					inline_keyboard=[
						[
							InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
						]
					]
				)
			)
	except Exception as e:
		logging.error(f"Error editing message: {e}")
		await callback.message.answer(
			message_text,
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
					]
				]
			)
		)
	await callback.answer()

@router.callback_query(F.data == "top_referrals")
async def top_referrals_callback(callback: CallbackQuery):
	top_referrers = get_top_referrers(10)
	
	if not top_referrers:
		await callback.message.edit_text(
			"🏆 TOP-10 referal reyting:\n\n"
			"Hozircha hech kim referal orqali foydalanuvchi taklif qilmagan.",
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
					]
				]
			)
		)
		await callback.answer()
		return
	
	message_text = "🏆 TOP-10 referal reyting:\n\n"
	
	for i, referrer in enumerate(top_referrers, 1):
		user_id, username, full_name, referral_count = referrer
		display_name = username if username else full_name
		message_text += f"{i}. {display_name} - {referral_count} ta referal\n"
	
	try:
		if callback.message.photo:
			await callback.message.edit_caption(
				caption=message_text,
				reply_markup=InlineKeyboardMarkup(
					inline_keyboard=[
						[
							InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
						]
					]
				)
			)
		else:
			await callback.message.edit_text(
				message_text,
				reply_markup=InlineKeyboardMarkup(
					inline_keyboard=[
						[
							InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
						]
					]
				)
			)
	except Exception as e:
		logging.error(f"Error editing message: {e}")
		await callback.message.answer(
			message_text,
			reply_markup=InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral")
					]
				]
			)
		)
	await callback.answer()

@router.callback_query(F.data == "back_to_referral")
async def back_to_referral_callback(callback: CallbackQuery):
	user_id = callback.from_user.id
	user = get_user(user_id)
	
	if not user:
		await callback.answer("⚠️ Siz ro'yxatdan o'tmagansiz.")
		return
	
	bot_id = user[3]
	referral_count = get_user_referral_count(user_id)
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	bot_username = (await callback.bot.get_me()).username
	invite_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(
					text="♻️ Ulashish (Oddiy)",
					url=f"https://t.me/share/url?url={invite_link}&text=🤖 Telegram orqali pul ishlash uchun ajoyib bot! 💰 Har bir taklif qilgan do'stingiz uchun {reward_uzb} so'm olasiz."
				)
			],
			[
				InlineKeyboardButton(text=MY_REFERRALS_BUTTON, callback_data="my_referrals") , InlineKeyboardButton(text=TOP_REFERRALS_BUTTON, callback_data="top_referrals")
			],

			[
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_main")
			]
		]
	)
	
	try:
		await callback.message.delete()
	except Exception as e:
		logging.error(f"Error deleting message: {e}")
	
	try:
		await callback.bot.send_photo(
			chat_id=callback.from_user.id,
			photo=REFERRAL_IMAGE_URL,
			caption=f"🔴 Sizning taklif havolangiz:\n\n"
			        f"{invite_link}\n\n"
			        f"Sizning referallaringiz: {referral_count} ta\n\n"
			        f"Sizga har bir taklif qilgan o'zbek referalingiz uchun {reward_uzb} so'm\n"
			        f"boshqa davlat referali uchun esa {reward_foreign} so'm beriladi (Feyk yani\n"
			        f"yolg'on reklama block bo'lishga sabab bo'ladi)\n\n"
			        f"👤 ID raqam: {bot_id}",
			reply_markup=inline_keyboard
		)
	except Exception as e:
		logging.error(f"Error sending referral image: {e}")
		await callback.bot.send_message(
			chat_id=callback.from_user.id,
			text=f"🔴 Sizning taklif havolangiz:\n\n"
			     f"{invite_link}\n\n"
			     f"Sizning referallaringiz: {referral_count} ta\n\n"
			     f"Sizga har bir taklif qilgan o'zbek referalingiz uchun {reward_uzb} so'm\n"
			     f"boshqa davlat referali uchun esa {reward_foreign} so'm beriladi (Feyk yani\n"
			     f"yolg'on reklama block bo'lishga sabab bo'ladi)\n\n"
			     f"👤 ID raqam: {bot_id}",
			reply_markup=inline_keyboard
		)
	
	await callback.answer()

@router.message(F.text == REFERRAL_SETTINGS_BUTTON)
async def referral_settings_handler(message: Message):
	user_id = message.from_user.id
	
	if user_id not in ADMINS:
		return
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text=CHANGE_REWARD_BUTTON, callback_data="change_referral_reward")
			],
			[
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_admin")
			]
		]
	)
	
	await message.answer(
		f"⚙️ Referal sozlamalari\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm",
		reply_markup=inline_keyboard
	)

@router.callback_query(F.data == "change_referral_reward")
async def change_referral_reward_callback(callback: CallbackQuery):
	user_id = callback.from_user.id
	
	if user_id not in ADMINS:
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
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_referral_settings")
			]
		]
	)
	
	await callback.message.edit_text(
		f"💰 Mukofot miqdorini o'zgartirish\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm\n\n"
		f"Qaysi mukofot miqdorini o'zgartirmoqchisiz?",
		reply_markup=inline_keyboard
	)
	await callback.answer()

@router.callback_query(F.data == "change_reward_uzb")
async def change_reward_uzb_callback(callback: CallbackQuery, state: FSMContext):
	user_id = callback.from_user.id
	
	if user_id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(reward_type="referral_reward_uzb")
	await state.set_state(ReferralSettingsState.waiting_for_new_reward)
	
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
	user_id = callback.from_user.id
	
	if user_id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(reward_type="referral_reward_foreign")
	await state.set_state(ReferralSettingsState.waiting_for_new_reward)
	
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

@router.message(ReferralSettingsState.waiting_for_new_reward)
async def process_new_reward(message: Message, state: FSMContext):
	user_id = message.from_user.id
	
	if user_id not in ADMINS:
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
		
		inline_keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text=CHANGE_REWARD_BUTTON, callback_data="change_referral_reward")
				],
				[
					InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_admin")
				]
			]
		)
		
		reward_type_text = "O'zbek referallari" if reward_type == "referral_reward_uzb" else "Boshqa davlat referallari"
		
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
	user_id = callback.from_user.id
	
	if user_id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text=CHANGE_REWARD_BUTTON, callback_data="change_referral_reward")
			],
			[
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"⚙️ Referal sozlamalari\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm",
		reply_markup=inline_keyboard
	)
	await callback.answer("❌ Mukofot miqdorini o'zgartirish bekor qilindi.")

@router.callback_query(F.data == "back_to_referral_settings")
async def back_to_referral_settings_callback(callback: CallbackQuery):
	user_id = callback.from_user.id
	
	if user_id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	reward_uzb = get_setting("referral_reward_uzb", "100")
	reward_foreign = get_setting("referral_reward_foreign", "80")
	
	inline_keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text=CHANGE_REWARD_BUTTON, callback_data="change_referral_reward")
			],
			[
				InlineKeyboardButton(text=BACK_BUTTON, callback_data="back_to_admin")
			]
		]
	)
	
	await callback.message.edit_text(
		f"⚙️ Referal sozlamalari\n\n"
		f"Hozirgi mukofot miqdorlari:\n"
		f"- O'zbek referallari uchun: {reward_uzb} so'm\n"
		f"- Boshqa davlat referallari uchun: {reward_foreign} so'm",
		reply_markup=inline_keyboard
	)
	await callback.answer()