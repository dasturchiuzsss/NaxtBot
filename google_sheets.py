import gspread
from google.oauth2.service_account import Credentials
import logging
from datetime import datetime
import json
import os

SCOPES = [
	'https://www.googleapis.com/auth/spreadsheets',
	'https://www.googleapis.com/auth/drive'
]

GOOGLE_SHEETS_CREDENTIALS_FILE = "credentials.json"
SPREADSHEET_ID = "your_spreadsheet_id_here"
WORKSHEET_NAME = "Orders"

def get_google_sheets_client():
	try:
		if not os.path.exists(GOOGLE_SHEETS_CREDENTIALS_FILE):
			logging.error(f"Google Sheets credentials file not found: {GOOGLE_SHEETS_CREDENTIALS_FILE}")
			return None
		
		credentials = Credentials.from_service_account_file(
			GOOGLE_SHEETS_CREDENTIALS_FILE,
			scopes=SCOPES
		)
		client = gspread.authorize(credentials)
		return client
	except Exception as e:
		logging.error(f"Google Sheets client yaratishda xato: {e}")
		return None

def get_worksheet():
	try:
		client = get_google_sheets_client()
		if not client:
			return None
		
		spreadsheet = client.open_by_key(SPREADSHEET_ID)
		
		try:
			worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
		except gspread.WorksheetNotFound:
			worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=20)
			headers = [
				"Sana", "Ism", "Telefon", "Manzil", "Tovar",
				"Summa", "To'lov Usuli", "Username", "User ID",
				"Tovar ID", "Status", "Izoh"
			]
			worksheet.append_row(headers)
		
		return worksheet
	except Exception as e:
		logging.error(f"Worksheet olishda xato: {e}")
		return None

def save_order_to_sheets(order_data):
	try:
		worksheet = get_worksheet()
		if not worksheet:
			logging.error("Google Sheets worksheet topilmadi")
			return False
		
		sana = order_data.get('sana', datetime.now().strftime('%d.%m.%Y %H:%M'))
		ism = order_data.get('ism', '')
		telefon = order_data.get('telefon', '')
		manzil = order_data.get('manzil', '')
		tovar = order_data.get('tovar', '')
		summa = order_data.get('summa', 0)
		tolov_usuli = order_data.get('tolov_usuli', '')
		username = order_data.get('username', '')
		user_id = order_data.get('user_id', '')
		tovar_id = order_data.get('tovar_id', '')
		status = order_data.get('status', 'Yangi')
		izoh = order_data.get('izoh', '')
		
		row_data = [
			sana, ism, telefon, manzil, tovar,
			summa, tolov_usuli, username, user_id,
			tovar_id, status, izoh
		]
		
		worksheet.append_row(row_data)
		logging.info(f"Buyurtma Google Sheets ga saqlandi: User ID {user_id}")
		return True
	
	except Exception as e:
		logging.error(f"Google Sheets ga saqlashda xato: {e}")
		return False

def update_order_status(user_id, new_status, izoh=""):
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return False
		
		all_records = worksheet.get_all_records()
		
		for i, record in enumerate(all_records, start=2):
			if str(record.get('User ID', '')) == str(user_id):
				worksheet.update_cell(i, 11, new_status)
				if izoh:
					worksheet.update_cell(i, 12, izoh)
				logging.info(f"Buyurtma statusi yangilandi: User ID {user_id} -> {new_status}")
				return True
		
		logging.warning(f"Buyurtma topilmadi: User ID {user_id}")
		return False
	
	except Exception as e:
		logging.error(f"Status yangilashda xato: {e}")
		return False

def get_user_orders(user_id):
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return []
		
		all_records = worksheet.get_all_records()
		user_orders = []
		
		for record in all_records:
			if str(record.get('User ID', '')) == str(user_id):
				user_orders.append(record)
		
		return user_orders
	
	except Exception as e:
		logging.error(f"Foydalanuvchi buyurtmalarini olishda xato: {e}")
		return []

def get_all_orders():
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return []
		
		all_records = worksheet.get_all_records()
		return all_records
	
	except Exception as e:
		logging.error(f"Barcha buyurtmalarni olishda xato: {e}")
		return []

def search_orders_by_phone(phone_number):
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return []
		
		all_records = worksheet.get_all_records()
		matching_orders = []
		
		for record in all_records:
			if phone_number in str(record.get('Telefon', '')):
				matching_orders.append(record)
		
		return matching_orders
	
	except Exception as e:
		logging.error(f"Telefon bo'yicha qidirishda xato: {e}")
		return []

def get_orders_by_date_range(start_date, end_date):
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return []
		
		all_records = worksheet.get_all_records()
		filtered_orders = []
		
		for record in all_records:
			try:
				order_date_str = record.get('Sana', '')
				if order_date_str:
					order_date = datetime.strptime(order_date_str.split()[0], '%d.%m.%Y')
					if start_date <= order_date <= end_date:
						filtered_orders.append(record)
			except ValueError:
				continue
		
		return filtered_orders
	
	except Exception as e:
		logging.error(f"Sana bo'yicha filtrlashda xato: {e}")
		return []

def get_orders_statistics():
	try:
		worksheet = get_worksheet()
		if not worksheet:
			return {}
		
		all_records = worksheet.get_all_records()
		
		total_orders = len(all_records)
		total_amount = 0
		status_count = {}
		payment_methods = {}
		
		for record in all_records:
			try:
				summa = float(str(record.get('Summa', 0)).replace(',', ''))
				total_amount += summa
			except (ValueError, TypeError):
				pass
			
			status = record.get('Status', 'Noma\'lum')
			status_count[status] = status_count.get(status, 0) + 1
			
			payment_method = record.get('To\'lov Usuli', 'Noma\'lum')
			payment_methods[payment_method] = payment_methods.get(payment_method, 0) + 1
		
		return {
			'total_orders': total_orders,
			'total_amount': total_amount,
			'status_count': status_count,
			'payment_methods': payment_methods
		}
	
	except Exception as e:
		logging.error(f"Statistika olishda xato: {e}")
		return {}
