import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database import get_all_wallets

logger = logging.getLogger(__name__)

def create_wallet_keyboard(wallets):
	"""Hamyonlar uchun klaviatura yaratish - TUZATILGAN"""
	try:
		logger.info(f"Creating wallet keyboard with {len(wallets) if wallets else 0} wallets")
		
		inline_keyboard = []
		
		inline_keyboard.extend([
			[
				InlineKeyboardButton(text="💳 UzCard [ Avto ]", callback_data="uzcard_payment"),
				InlineKeyboardButton(text="💳 HumoCard [ Avto ]", callback_data="humo_payment")
			],
			[
				InlineKeyboardButton(text="💳 CLICK [ Avto ]", callback_data="click_payment")
			]
		])
		
		if wallets and len(wallets) > 0:
			wallet_buttons = []
			for wallet in wallets:
				try:
					if len(wallet) >= 2:
						wallet_id = wallet[0]
						wallet_name = wallet[1]
						
						is_active = 1
						if len(wallet) >= 5:
							is_active = wallet[4]
						
						if is_active == 1:
							wallet_buttons.append(
								InlineKeyboardButton(text=f"💰 {wallet_name}",
								                     callback_data=f"wallet_payment_{wallet_id}")
							)
							logger.info(f"Added wallet button: {wallet_name} (ID: {wallet_id})")
						else:
							logger.info(f"Skipped inactive wallet: {wallet_name}")
					else:
						logger.warning(f"Invalid wallet structure: {wallet}")
				
				except Exception as e:
					logger.error(f"Error processing wallet {wallet}: {e}")
			
			for i in range(0, len(wallet_buttons), 2):
				row = wallet_buttons[i:i + 2]
				inline_keyboard.append(row)
			
			logger.info(f"Added {len(wallet_buttons)} wallet buttons to keyboard")
		else:
			logger.info("No wallets found for keyboard")
		
		inline_keyboard.append([
			InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")
		])
		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		logger.info(f"Wallet keyboard created successfully with {len(inline_keyboard)} rows")
		
		return markup
	
	except Exception as e:
		logger.error(f"Error creating wallet keyboard: {e}")
		return InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="💳 UzCard [ Avto ]", callback_data="uzcard_payment"),
					InlineKeyboardButton(text="💳 HumoCard [ Avto ]", callback_data="humo_payment")
				],
				[
					InlineKeyboardButton(text="💳 CLICK [ Avto ]", callback_data="click_payment")
				],
				[
					InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_main")
				]
			]
		)

def create_product_wallet_keyboard(product_id, wallets):
	"""Mahsulot uchun wallet klaviaturasi yaratish"""
	try:
		logger.info(
			f"Creating product wallet keyboard for product {product_id} with {len(wallets) if wallets else 0} wallets")
		inline_keyboard = []
		if wallets and len(wallets) > 0:
			wallet_buttons = []
			for wallet in wallets:
				try:
					if len(wallet) >= 2:
						wallet_id = wallet[0]
						wallet_name = wallet[1]
						
						is_active = 1
						if len(wallet) >= 5:
							is_active = wallet[4]
						
						if is_active == 1:
							wallet_buttons.append(
								InlineKeyboardButton(
									text=f"💰 {wallet_name}",
									callback_data=f"wallet_payment_product_{wallet_id}_{product_id}"
								)
							)
							logger.info(f"Added product wallet button: {wallet_name} (ID: {wallet_id})")
						else:
							logger.info(f"Skipped inactive wallet: {wallet_name}")
					else:
						logger.warning(f"Invalid wallet structure: {wallet}")
				
				except Exception as e:
					logger.error(f"Error processing wallet {wallet}: {e}")
			
			for i in range(0, len(wallet_buttons), 2):
				row = wallet_buttons[i:i + 2]
				inline_keyboard.append(row)
			
			logger.info(f"Added {len(wallet_buttons)} product wallet buttons to keyboard")
		else:
			logger.info("No wallets found for product keyboard, adding default wallet option")
			inline_keyboard.append([
				InlineKeyboardButton(text="💰 Wallet to'lov", callback_data=f"default_wallet_payment_{product_id}")
			])
		
		inline_keyboard.append([
			InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}")
		])
		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		logger.info(f"Product wallet keyboard created successfully with {len(inline_keyboard)} rows")
		
		return markup
	
	except Exception as e:
		logger.error(f"Error creating product wallet keyboard: {e}")
		return InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="💰 Wallet to'lov", callback_data=f"default_wallet_payment_{product_id}")
				],
				[
					InlineKeyboardButton(text="🔙 Ortga qaytish", callback_data=f"back_to_product_{product_id}")
				]
			]
		)
