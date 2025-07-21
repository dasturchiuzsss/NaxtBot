import logging
import asyncio
import uuid
import time
import json
import re
import math
from datetime import datetime
from aiogram import Router, F
from aiogram.types import (
	Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
	ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMINS, BOT_TOKEN,  BOT_USERNAME , ORDER_CHANNEL, DEFAULT_PRODUCT_PRICE, PRODUCT_CHANNEL, TASDIQID
from database import create_connection, get_user, update_balance, add_transaction, get_all_wallets, get_setting, \
	update_setting, get_wallet, get_all_payment_methods
from utils import create_wallet_keyboard

import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = Router()

FIXED_PAYMENT_AMOUNT = 50000
PRODUCTS_PER_PAGE = 10

def get_google_sheets_credentials():
	return {

	# google malumoti
		
	}

class ProductState(StatesGroup):
	selecting_product_type = State()
	waiting_for_product_name = State()
	waiting_for_product_description = State()
	waiting_for_product_price = State()
	waiting_for_uzum_link = State()
	waiting_for_product_image = State()
	waiting_for_product_video = State()
	waiting_for_product_confirmation = State()
	
	editing_product = State()
	waiting_for_edit_name = State()
	waiting_for_edit_description = State()
	waiting_for_edit_price = State()
	waiting_for_edit_uzum_link = State()
	waiting_for_edit_image = State()
	waiting_for_edit_video = State()
	waiting_for_edit_category = State()
	waiting_for_edit_brand = State()
	waiting_for_edit_warranty = State()
	
	waiting_for_sheets_url = State()
	
	waiting_for_customer_name = State()
	waiting_for_customer_phone = State()
	waiting_for_customer_location = State()
	confirming_customer_info = State()

payment_data_storage = {}

def create_products_table():
	conn = create_connection()
	if not conn:
		logger.error("Database connection failed in create_products_table")
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL,
                uzum_link TEXT,
                image_file_id TEXT,
                video_file_id TEXT,
                product_type TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sales_count INTEGER DEFAULT 0,
                total_revenue REAL DEFAULT 0,
                last_sold TIMESTAMP,
                category TEXT DEFAULT 'Umumiy',
                tags TEXT,
                discount_percent REAL DEFAULT 0,
                stock_quantity INTEGER DEFAULT -1,
                min_order_quantity INTEGER DEFAULT 1,
                max_order_quantity INTEGER DEFAULT -1,
                weight REAL DEFAULT 0,
                dimensions TEXT,
                warranty_months INTEGER DEFAULT 0,
                brand TEXT,
                model TEXT,
                color TEXT,
                material TEXT,
                origin_country TEXT DEFAULT 'Uzbekistan',
                is_featured INTEGER DEFAULT 0,
                sort_order INTEGER DEFAULT 0,
                seo_title TEXT,
                seo_description TEXT,
                seo_keywords TEXT
            )
        ''')
		
		new_columns = [
			('uzum_link', 'TEXT'),
			('last_sold', 'TIMESTAMP'),
			('category', 'TEXT DEFAULT "Umumiy"'),
			('tags', 'TEXT'),
			('discount_percent', 'REAL DEFAULT 0'),
			('stock_quantity', 'INTEGER DEFAULT -1'),
			('min_order_quantity', 'INTEGER DEFAULT 1'),
			('max_order_quantity', 'INTEGER DEFAULT -1'),
			('weight', 'REAL DEFAULT 0'),
			('dimensions', 'TEXT'),
			('warranty_months', 'INTEGER DEFAULT 0'),
			('brand', 'TEXT'),
			('model', 'TEXT'),
			('color', 'TEXT'),
			('material', 'TEXT'),
			('origin_country', 'TEXT DEFAULT "Uzbekistan"'),
			('is_featured', 'INTEGER DEFAULT 0'),
			('sort_order', 'INTEGER DEFAULT 0'),
			('seo_title', 'TEXT'),
			('seo_description', 'TEXT'),
			('seo_keywords', 'TEXT')
		]
		
		for column_name, column_type in new_columns:
			try:
				cursor.execute(f'ALTER TABLE products ADD COLUMN {column_name} {column_type}')
			except Exception:
				pass
		
		cursor.execute('''
            CREATE TABLE IF NOT EXISTS product_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                product_price REAL NOT NULL DEFAULT 0,
                paid_amount REAL NOT NULL DEFAULT 0,
                remaining_amount REAL NOT NULL DEFAULT 0,
                payment_method TEXT NOT NULL,
                sale_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                customer_name TEXT,
                customer_phone TEXT,
                customer_location TEXT,
                status TEXT DEFAULT 'completed',
                admin_notes TEXT,
                quantity INTEGER DEFAULT 1,
                unit_price REAL DEFAULT 0,
                discount_amount REAL DEFAULT 0,
                tax_amount REAL DEFAULT 0,
                shipping_cost REAL DEFAULT 0,
                tracking_number TEXT,
                delivery_date TIMESTAMP,
                delivery_status TEXT DEFAULT 'pending',
                rating INTEGER DEFAULT 0,
                review TEXT,
                refund_amount REAL DEFAULT 0,
                refund_reason TEXT,
                refund_date TIMESTAMP,
                FOREIGN KEY (product_id) REFERENCES products (product_id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
		
		sales_columns = [
			('product_price', 'REAL DEFAULT 0'),
			('paid_amount', 'REAL DEFAULT 0'),
			('remaining_amount', 'REAL DEFAULT 0'),
			('status', 'TEXT DEFAULT "completed"'),
			('admin_notes', 'TEXT'),
			('quantity', 'INTEGER DEFAULT 1'),
			('unit_price', 'REAL DEFAULT 0'),
			('discount_amount', 'REAL DEFAULT 0'),
			('tax_amount', 'REAL DEFAULT 0'),
			('shipping_cost', 'REAL DEFAULT 0'),
			('tracking_number', 'TEXT'),
			('delivery_date', 'TIMESTAMP'),
			('delivery_status', 'TEXT DEFAULT "pending"'),
			('rating', 'INTEGER DEFAULT 0'),
			('review', 'TEXT'),
			('refund_amount', 'REAL DEFAULT 0'),
			('refund_reason', 'TEXT'),
			('refund_date', 'TIMESTAMP')
		]
		
		for column_name, column_type in sales_columns:
			try:
				cursor.execute(f'ALTER TABLE product_sales ADD COLUMN {column_name} {column_type}')
			except Exception:
				pass
		
		conn.commit()
		logger.info("Products tables created successfully with all enhancements")
		return True
	
	except Exception as e:
		logger.error(f"Error creating products tables: {e}")
		conn.rollback()
		return False
	finally:
		conn.close()

def add_product(product_id, name, description, price, uzum_link, image_file_id, video_file_id, product_type,
                created_by, category='Umumiy', **kwargs):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		base_fields = [
			'product_id', 'name', 'description', 'price', 'uzum_link',
			'image_file_id', 'video_file_id', 'product_type', 'created_by', 'category'
		]
		base_values = [product_id, name, description, price, uzum_link,
		               image_file_id, video_file_id, product_type, created_by, category]
		
		extra_fields = []
		extra_values = []
		
		allowed_fields = [
			'tags', 'discount_percent', 'stock_quantity', 'min_order_quantity',
			'max_order_quantity', 'weight', 'dimensions', 'warranty_months',
			'brand', 'model', 'color', 'material', 'origin_country',
			'is_featured', 'sort_order', 'seo_title', 'seo_description', 'seo_keywords'
		]
		
		for field in allowed_fields:
			if field in kwargs:
				extra_fields.append(field)
				extra_values.append(kwargs[field])
		
		all_fields = base_fields + extra_fields
		all_values = base_values + extra_values
		
		placeholders = ', '.join(['?'] * len(all_fields))
		fields_str = ', '.join(all_fields)
		
		cursor.execute(f'''
            INSERT INTO products ({fields_str})
            VALUES ({placeholders})
        ''', all_values)
		
		conn.commit()
		logger.info(f"Product added successfully: {product_id}")
		return True
	except Exception as e:
		logger.error(f"Error adding product: {e}")
		return False
	finally:
		conn.close()

def get_product(product_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
		product = cursor.fetchone()
		return product
	except Exception as e:
		logger.error(f"Error getting product: {e}")
		return None
	finally:
		conn.close()

def get_all_products(search_query=None, status_filter=None, sort_by="created_at", sort_order="DESC", limit=None,
                     offset=0):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		query = "SELECT * FROM products WHERE 1=1"
		params = []
		
		if search_query:
			query += " AND (name LIKE ? OR description LIKE ? OR tags LIKE ? OR brand LIKE ?)"
			search_param = f"%{search_query}%"
			params.extend([search_param, search_param, search_param, search_param])
		
		if status_filter is not None:
			query += " AND is_active = ?"
			params.append(status_filter)
		
		valid_sort_columns = [
			"created_at", "name", "price", "sales_count", "total_revenue",
			"last_sold", "sort_order", "category", "is_featured"
		]
		if sort_by in valid_sort_columns:
			query += f" ORDER BY {sort_by} {sort_order}"
		else:
			query += " ORDER BY is_featured DESC, sort_order ASC, created_at DESC"
		
		if limit:
			query += f" LIMIT {limit}"
			if offset:
				query += f" OFFSET {offset}"
		
		cursor.execute(query, params)
		products = cursor.fetchall()
		return products
	except Exception as e:
		logger.error(f"Error getting products: {e}")
		return []
	finally:
		conn.close()

def update_product_status(product_id, is_active):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("UPDATE products SET is_active = ? WHERE product_id = ?", (is_active, product_id))
		conn.commit()
		return True
	except Exception as e:
		logger.error(f"Error updating product status: {e}")
		return False
	finally:
		conn.close()

def update_product_info(product_id, **kwargs):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		updates = []
		params = []
		
		allowed_fields = [
			'name', 'description', 'price', 'uzum_link', 'category', 'tags',
			'discount_percent', 'stock_quantity', 'min_order_quantity',
			'max_order_quantity', 'weight', 'dimensions', 'warranty_months',
			'brand', 'model', 'color', 'material', 'origin_country',
			'is_featured', 'sort_order', 'seo_title', 'seo_description', 'seo_keywords',
			'image_file_id', 'video_file_id'
		]
		
		for field in allowed_fields:
			if field in kwargs and kwargs[field] is not None:
				updates.append(f"{field} = ?")
				params.append(kwargs[field])
		
		if updates:
			query = f"UPDATE products SET {', '.join(updates)} WHERE product_id = ?"
			params.append(product_id)
			cursor.execute(query, params)
			conn.commit()
			logger.info(f"Product updated successfully: {product_id}")
			return True
		
		return False
	except Exception as e:
		logger.error(f"Error updating product info: {e}")
		return False
	finally:
		conn.close()

def delete_product_permanently(product_id):
	conn = create_connection()
	if not conn:
		return False
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("DELETE FROM product_sales WHERE product_id = ?", (product_id,))
		cursor.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
		
		conn.commit()
		logger.info(f"Product deleted permanently: {product_id}")
		return True
	except Exception as e:
		logger.error(f"Error deleting product permanently: {e}")
		return False
	finally:
		conn.close()

def duplicate_product(product_id):
	conn = create_connection()
	if not conn:
		return None
	
	cursor = conn.cursor()
	
	try:
		cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
		original = cursor.fetchone()
		
		if not original:
			return None
		
		new_product_id = str(uuid.uuid4())[:8]
		new_name = f"{original[2]} (nusxa)"
		
		cursor.execute('''
            INSERT INTO products (
                product_id, name, description, price, uzum_link, image_file_id,
                video_file_id, product_type, is_active, created_by, category,
                tags, discount_percent, stock_quantity, min_order_quantity,
                max_order_quantity, weight, dimensions, warranty_months,
                brand, model, color, material, origin_country, is_featured,
                sort_order, seo_title, seo_description, seo_keywords
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
			new_product_id, new_name, original[3], original[4], original[5],
			original[6], original[7], original[8], original[10], original[15],
			original[16], original[17], original[18], original[19], original[20],
			original[21], original[22], original[23], original[24], original[25],
			original[26], original[27], original[28], 0, original[30],
			original[31], original[32], original[33]
		))
		
		conn.commit()
		logger.info(f"Product duplicated: {product_id} -> {new_product_id}")
		return new_product_id
	except Exception as e:
		logger.error(f"Error duplicating product: {e}")
		return None
	finally:
		conn.close()

def record_sale(product_id, user_id, product_price, payment_method, customer_name=None, customer_phone=None,
                customer_location=None, **kwargs):
	conn = create_connection()
	if not conn:
		logger.error("Database connection failed in record_sale")
		return False
	
	cursor = conn.cursor()
	
	try:
		paid_amount = kwargs.get('paid_amount', FIXED_PAYMENT_AMOUNT)
		remaining_amount = product_price - paid_amount
		quantity = kwargs.get('quantity', 1)
		unit_price = product_price / quantity if quantity > 0 else product_price
		
		cursor.execute("PRAGMA table_info(product_sales)")
		columns = [column[1] for column in cursor.fetchall()]
		logger.info(f"Product_sales table columns: {columns}")
		
		required_columns = [
			('status', 'TEXT DEFAULT "completed"'),
			('product_price', 'REAL DEFAULT 0'),
			('paid_amount', 'REAL DEFAULT 0'),
			('remaining_amount', 'REAL DEFAULT 0'),
			('quantity', 'INTEGER DEFAULT 1'),
			('unit_price', 'REAL DEFAULT 0')
		]
		
		for column_name, column_type in required_columns:
			if column_name not in columns:
				logger.info(f"Adding {column_name} column to product_sales table")
				cursor.execute(f'ALTER TABLE product_sales ADD COLUMN {column_name} {column_type}')
				conn.commit()
		
		cursor.execute('''
            INSERT INTO product_sales (
                product_id, user_id, product_price, paid_amount, remaining_amount,
                payment_method, customer_name, customer_phone, customer_location,
                status, quantity, unit_price
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (product_id, user_id, product_price, paid_amount, remaining_amount,
		      payment_method, customer_name, customer_phone, customer_location,
		      'completed', quantity, unit_price))
		
		cursor.execute('''
            UPDATE products
            SET sales_count = sales_count + ?,
                total_revenue = total_revenue + ?,
                last_sold = CURRENT_TIMESTAMP
            WHERE product_id = ?
        ''', (quantity, paid_amount, product_id))
		
		cursor.execute('''
            UPDATE products
            SET stock_quantity = CASE
                WHEN stock_quantity > 0 THEN stock_quantity - ?
                ELSE stock_quantity
            END
            WHERE product_id = ? AND stock_quantity > 0
        ''', (quantity, product_id))
		
		conn.commit()
		logger.info(f"Sale recorded successfully: product_id={product_id}, user_id={user_id}, amount={paid_amount}")
		return True
	
	except Exception as e:
		logger.error(f"Error recording sale: {e}")
		conn.rollback()
		return False
	finally:
		conn.close()

def get_product_statistics():
	conn = create_connection()
	if not conn:
		return {}
	
	cursor = conn.cursor()
	
	try:
		stats = {}
		
		cursor.execute("SELECT COUNT(*) FROM products")
		stats['total_products'] = cursor.fetchone()[0]
		
		cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 1")
		stats['active_products'] = cursor.fetchone()[0]
		
		cursor.execute("SELECT COUNT(*) FROM products WHERE is_active = 0")
		stats['inactive_products'] = cursor.fetchone()[0]
		
		cursor.execute("SELECT SUM(sales_count) FROM products")
		result = cursor.fetchone()[0]
		stats['total_sales'] = result if result else 0
		
		cursor.execute("SELECT SUM(total_revenue) FROM products")
		result = cursor.fetchone()[0]
		stats['total_revenue'] = result if result else 0
		
		return stats
	except Exception as e:
		logger.error(f"Error getting product statistics: {e}")
		return {}
	finally:
		conn.close()

def get_product_sales_history(product_id=None, user_id=None, limit=50):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		query = "SELECT * FROM product_sales WHERE 1=1"
		params = []
		
		if product_id:
			query += " AND product_id = ?"
			params.append(product_id)
		
		if user_id:
			query += " AND user_id = ?"
			params.append(user_id)
		
		query += " ORDER BY sale_date DESC"
		
		if limit:
			query += f" LIMIT {limit}"
		
		cursor.execute(query, params)
		sales = cursor.fetchall()
		return sales
	except Exception as e:
		logger.error(f"Error getting sales history: {e}")
		return []
	finally:
		conn.close()

def get_top_selling_products(limit=10):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
            SELECT * FROM products
            WHERE is_active = 1
            ORDER BY sales_count DESC, total_revenue DESC
            LIMIT ?
        ''', (limit,))
		products = cursor.fetchall()
		return products
	except Exception as e:
		logger.error(f"Error getting top selling products: {e}")
		return []
	finally:
		conn.close()

def search_products(query, limit=20):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		search_query = f"%{query}%"
		cursor.execute('''
            SELECT * FROM products
            WHERE is_active = 1 AND (
                name LIKE ? OR
                description LIKE ? OR
                tags LIKE ? OR
                brand LIKE ? OR
                category LIKE ?
            )
            ORDER BY
                CASE WHEN name LIKE ? THEN 1 ELSE 2 END,
                sales_count DESC
            LIMIT ?
        ''', (search_query, search_query, search_query, search_query, search_query, search_query, limit))
		products = cursor.fetchall()
		return products
	except Exception as e:
		logger.error(f"Error searching products: {e}")
		return []
	finally:
		conn.close()

def get_products_by_category(category, limit=20):
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
            SELECT * FROM products
            WHERE is_active = 1 AND category = ?
            ORDER BY is_featured DESC, sales_count DESC
            LIMIT ?
        ''', (category, limit))
		products = cursor.fetchall()
		return products
	except Exception as e:
		logger.error(f"Error getting products by category: {e}")
		return []
	finally:
		conn.close()

def get_all_categories():
	conn = create_connection()
	if not conn:
		return []
	
	cursor = conn.cursor()
	
	try:
		cursor.execute('''
            SELECT DISTINCT category, COUNT(*) as count
            FROM products
            WHERE is_active = 1
            GROUP BY category
            ORDER BY count DESC
        ''')
		categories = cursor.fetchall()
		return categories
	except Exception as e:
		logger.error(f"Error getting categories: {e}")
		return []
	finally:
		conn.close()

def test_google_sheets_connection():
	try:
		creds = Credentials.from_service_account_info(
			get_google_sheets_credentials(),
			scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
		)
		
		gc = gspread.authorize(creds)
		return True, "web-malumotlari@aqueous-argon-454316-h5.iam.gserviceaccount.com"
	except Exception as e:
		logger.error(f"Google Sheets connection test failed: {e}")
		return False, str(e)

def save_order_to_google_sheets(order_data, max_retries=3):
	for attempt in range(max_retries):
		try:
			sheets_url = get_setting("google_sheets_url", "")
			if not sheets_url:
				logger.warning("Google Sheets URL not configured")
				return False
			
			creds = Credentials.from_service_account_info(
				get_google_sheets_credentials(),
				scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
			)
			
			gc = gspread.authorize(creds)
			
			try:
				spreadsheet = gc.open_by_url(sheets_url)
				logger.info(f"Successfully opened spreadsheet: {spreadsheet.title}")
			except gspread.exceptions.SpreadsheetNotFound:
				logger.error(f"Spreadsheet not found at URL: {sheets_url}")
				return False
			except gspread.exceptions.NoValidUrlKeyFound:
				logger.error(f"Invalid Google Sheets URL: {sheets_url}")
				return False
			
			worksheet = spreadsheet.sheet1
			logger.info(f"Successfully accessed worksheet: {worksheet.title}")
			
			expected_headers = [
				"№", "Sana", "Ism", "Telefon", "Manzil", "Tovar", "Kategoriya",
				"Asosiy Narx", "To'langan", "Qolgan Qarz", "To'lov Usuli",
				"Username", "User ID", "Miqdor", "Chegirma", "Status", "Izohlar"
			]
			
			try:
				headers = worksheet.row_values(1)
				if not headers or len(headers) < len(expected_headers):
					if headers:
						worksheet.delete_rows(1)
					worksheet.insert_row(expected_headers, 1)
					logger.info("Headers updated in Google Sheets")
			except Exception as header_error:
				logger.error(f"Error handling headers: {header_error}")
				worksheet.append_row(expected_headers)
				logger.info("Headers added after error")
			
			try:
				all_values = worksheet.get_all_values()
				next_number = len(all_values)
			except:
				next_number = 1
			
			row_data = [
				next_number,
				order_data.get('sana', ''),
				order_data.get('mijoz_ismi', ''),
				order_data.get('telefon', ''),
				order_data.get('manzil', ''),
				order_data.get('tovar', ''),
				order_data.get('kategoriya', 'Umumiy'),
				order_data.get('asosiy_narx', ''),
				order_data.get('tolangan_summa', ''),
				order_data.get('qolgan_qarz', ''),
				order_data.get('tolov_usuli', ''),
				order_data.get('username', ''),
				order_data.get('user_id', ''),
				order_data.get('miqdor', '1'),
				order_data.get('chegirma', '0'),
				order_data.get('status', 'Completed'),
				order_data.get('izohlar', '')
			]
			
			worksheet.append_row(row_data)
			logger.info(f"Successfully added order data to Google Sheets: {order_data.get('user_id', 'Unknown')}")
			return True
		
		except Exception as e:
			logger.error(f"Attempt {attempt + 1} failed in save_order_to_google_sheets: {e}")
			if attempt == max_retries - 1:
				logger.error(f"All {max_retries} attempts failed for Google Sheets")
				return False
			
			time.sleep(2 ** attempt)
	
	return False

create_products_table()

async def show_product_with_payment_buttons(callback_or_message, product_id, is_callback=False):
	try:
		product = get_product(product_id)
		if not product or not product[9]:
			error_msg = "❌ Bu tovar mavjud emas yoki faol emas."
			if is_callback:
				await callback_or_message.answer(error_msg)
			else:
				await callback_or_message.answer(error_msg)
			return
		
		name = product[2]
		description = product[3]
		original_price = product[4]
		uzum_link = product[5]
		image_file_id = product[6]
		video_file_id = product[7]
		product_type = product[8]
		category = product[15] if len(product) > 15 and product[15] else 'Umumiy'
		brand = product[23] if len(product) > 23 and product[23] else None
		warranty_months = product[22] if len(product) > 22 and product[22] is not None else 0
		
		logger.info(f"Creating payment buttons for product {product_id}: {name}")
		
		try:
			wallets = get_all_wallets()
			payment_methods = get_all_payment_methods()
			
			logger.info(f"Database query results:")
			logger.info(f"- Wallets: {len(wallets) if wallets else 0}")
			logger.info(f"- Payment methods: {len(payment_methods) if payment_methods else 0}")
		
		except Exception as e:
			logger.error(f"Error getting wallets/payment methods: {e}")
			wallets = []
			payment_methods = []
		
		inline_keyboard = []
		
		wallet_buttons = []
		if wallets:
			for wallet in wallets:
				try:
					wallet_id, wallet_name, card_number, full_name, is_active = wallet
					if is_active:
						wallet_buttons.append(
							InlineKeyboardButton(
								text=f"💰 {wallet_name}",
								callback_data=f"wallet_payment_product_{wallet_id}_{product_id}"
							)
						)
						logger.info(f"Added wallet button: {wallet_name} (ID: {wallet_id})")
				except Exception as e:
					logger.error(f"Error processing wallet {wallet}: {e}")
		
		for i in range(0, len(wallet_buttons), 2):
			row = wallet_buttons[i:i + 2]
			inline_keyboard.append(row)
		
		if payment_methods and len(payment_methods) > 0:
			logger.info("Adding admin payment methods")
			payment_buttons = []
			for method in payment_methods:
				try:
					method_id, method_name = method[0], method[1]
					payment_buttons.append(
						InlineKeyboardButton(text=f"💳 {method_name} [ Avto ]",
						                     callback_data=f"auto_payment_product_{method_id}_{product_id}")
					)
					logger.info(f"Added payment method: {method_name} (ID: {method_id})")
				except Exception as e:
					logger.error(f"Error processing payment method {method}: {e}")
			
			for i in range(0, len(payment_buttons), 2):
				row = payment_buttons[i:i + 2]
				inline_keyboard.append(row)
		else:
			logger.info("Adding default payment methods")
			inline_keyboard.extend([
				[
					InlineKeyboardButton(text="💳 UzCard [ Avto ]",
					                     callback_data=f"uzcard_payment_product_{product_id}"),
					InlineKeyboardButton(text="💳 HumoCard [ Avto ]",
					                     callback_data=f"humo_payment_product_{product_id}")
				],
				[
					InlineKeyboardButton(text="💳 CLICK [ Avto ]",
					                     callback_data=f"click_payment_product_{product_id}")
				]
			])
		
		if not wallet_buttons:
			logger.info("No admin wallets found, adding default wallet option")
			inline_keyboard.append([
				InlineKeyboardButton(text="💰 Wallet to'lov",
				                     callback_data=f"default_wallet_payment_{product_id}")
			])
		
		if uzum_link and uzum_link.strip():
			inline_keyboard.append([
				InlineKeyboardButton(text="🛒 Uzum Nasiya", url=uzum_link)
			])
		


		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		
		product_text = f"🛍 <b>{name}</b>\n\n"
		product_text += f"{description}\n\n"
		
		if category and category != 'Umumiy':
			product_text += f"📂 <b>Kategoriya:</b> {category}\n"
		
		if brand:
			product_text += f"🏷 <b>Brend:</b> {brand}\n"
		
		if warranty_months and warranty_months > 0:
			product_text += f"🛡 <b>Kafolat:</b> {warranty_months} oy\n"
		
		product_text += f"\n💰 <b>Asosiy narx:</b> {original_price:,} UZS\n"
		product_text += f"💳 <b>To'lov summasi:</b> {FIXED_PAYMENT_AMOUNT:,} UZS\n\n"
		
		remaining_debt = original_price - FIXED_PAYMENT_AMOUNT
		if remaining_debt > 0:
			product_text += f"📋 <b>Qolgan qarz:</b> {remaining_debt:,} UZS\n\n"
		elif remaining_debt < 0:
			product_text += f"🎁 <b>Chegirma:</b> {abs(remaining_debt):,} UZS\n\n"
		else:
			product_text += "✅ <b>To'liq to'lov</b>\n\n"
		
		product_text += "👇 To'lov usulini tanlang:"
		
		logger.info(f"Product buttons created successfully: {len(inline_keyboard)} rows")
		
		if is_callback:
			try:
				if product_type == "image" and image_file_id:
					await callback_or_message.message.answer_photo(
						photo=image_file_id,
						caption=product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				elif product_type == "video" and video_file_id:
					await callback_or_message.message.answer_video(
						video=video_file_id,
						caption=product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				else:
					await callback_or_message.message.answer(
						product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
			except Exception as e:
				logger.error(f"Error sending product via callback: {e}")
				await callback_or_message.message.answer(
					product_text,
					reply_markup=markup,
					parse_mode="HTML"
				)
		else:
			try:
				if product_type == "image" and image_file_id:
					await callback_or_message.answer_photo(
						photo=image_file_id,
						caption=product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				elif product_type == "video" and video_file_id:
					await callback_or_message.answer_video(
						video=video_file_id,
						caption=product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
				else:
					await callback_or_message.answer(
						product_text,
						reply_markup=markup,
						parse_mode="HTML"
					)
			except Exception as e:
				logger.error(f"Error sending product via message: {e}")
				await callback_or_message.answer(
					product_text,
					reply_markup=markup,
					parse_mode="HTML"
				)
		
		logger.info(f"Product {product_id} displayed successfully")
	
	except Exception as e:
		logger.error(f"Error in show_product_with_payment_buttons: {e}")
		import traceback
		logger.error(f"Traceback: {traceback.format_exc()}")
		error_msg = "❌ Tovarni ko'rsatishda xatolik yuz berdi."
		if is_callback:
			await callback_or_message.answer(error_msg)
		else:
			await callback_or_message.answer(error_msg)

async def show_all_products(message_or_callback, page=1, is_callback=False):
	try:
		products = get_all_products(status_filter=1, sort_by="is_featured", sort_order="DESC")
		total_products = len(products)
		
		if total_products == 0:
			text = (
				"📋 <b>TOVARLAR BOSHQARUVI</b>\n"
				"---------------------------------------------\n\n"
				"❌ Hozircha faol tovarlar mavjud emas.\n\n"
				"🔄 Tez orada yangi tovarlar qo'shiladi!"
			)
			
			keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="back_to_main")]
				]
			)
			
			if is_callback:
				await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
			else:
				await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")
			return
		
		start_index = (page - 1) * PRODUCTS_PER_PAGE
		end_index = start_index + PRODUCTS_PER_PAGE
		page_products = products[start_index:end_index]
		
		total_pages = math.ceil(total_products / PRODUCTS_PER_PAGE)
		
		text = "📋 <b>TOVARLAR BOSHQARUVI</b>\n"
		text += "---------------------------------------------\n\n"
		
		for i, product in enumerate(page_products, start=start_index + 1):
			name = product[2]
			text += f"{i}. {name}\n"
		
		text += f"\n📄 Sahifa: {page}/{total_pages}\n"
		text += f"📊 Jami: {total_products} ta tovar\n\n"
		text += "---------------------------------------------\n\n"
		text += "👇 Bu bo'lim orqali siz tovarlarni boshqara olmaysiz shunchaki ularni korishinigz va yangi tovar qoshishinigz mumkin \n📦Tovarlarni boshqarish uchun Tovarlar royxati bolimiga oting  "
		
		inline_keyboard = []
		
		number_buttons = []
		for i, product in enumerate(page_products, start=1):
			product_id = product[1]
			number_buttons.append(
				InlineKeyboardButton(
					text=str(i),
					callback_data=f"show_product_{product_id}"
				)
			)
		
		for i in range(0, len(number_buttons), 5):
			row = number_buttons[i:i + 5]
			inline_keyboard.append(row)
		
		nav_buttons = []
		if page > 1:
			nav_buttons.append(
				InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"products_page_{page - 1}")
			)
		
		if total_pages > 1:
			nav_buttons.append(
				InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="current_page")
			)
		
		if page < total_pages:
			nav_buttons.append(
				InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"products_page_{page + 1}")
			)
		
		if nav_buttons:
			inline_keyboard.append(nav_buttons)
		
		extra_buttons = [
			[
				InlineKeyboardButton(text="➕ Tovar qo'shish", callback_data="add_product"),
				InlineKeyboardButton(text="🔄 Yangilash", callback_data="show_all_products")
			],
			[
				InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
			]
		]
		
		inline_keyboard.extend(extra_buttons)
		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		
		if is_callback:
			await message_or_callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
		else:
			await message_or_callback.answer(text, reply_markup=markup, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing all products: {e}")
		error_text = (
			"❌ <b>Xatolik yuz berdi</b>\n\n"
			"Tovarlarni yuklashda muammo bo'ldi.\n"
			"Iltimos, qaytadan urinib ko'ring."
		)
		if is_callback:
			await message_or_callback.answer(error_text, parse_mode="HTML")
		else:
			await message_or_callback.answer(error_text, parse_mode="HTML")

async def show_manage_products(callback: CallbackQuery, page=1):
	"""Tovarlarni boshqarish (adminlar uchun)"""
	try:
		products = get_all_products(sort_by="created_at", sort_order="DESC")
		total_products = len(products)
		
		if total_products == 0:
			text = (
				"📋 <b>TOVARLARNI BOSHQARISH</b>\n"
				"---------------------------------------------\n\n"
				"❌ Hozircha tovarlar mavjud emas.\n\n"
				"➕ Yangi tovar qo'shish uchun tugmani bosing."
			)
			
			keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="➕ Tovar qo'shish", callback_data="add_product")
					],
					[
						InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
					]
				]
			)
			
			await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
			return
		
		start_index = (page - 1) * PRODUCTS_PER_PAGE
		end_index = start_index + PRODUCTS_PER_PAGE
		page_products = products[start_index:end_index]
		
		total_pages = math.ceil(total_products / PRODUCTS_PER_PAGE)
		
		text = "📋 <b>TOVARLARNI BOSHQARISH</b>\n"
		text += "---------------------------------------------\n\n"
		
		for i, product in enumerate(page_products, start=start_index + 1):
			name = product[2]
			price = product[4]
			is_active = product[9]
			sales_count = product[12]
			
			status_icon = "✅" if is_active else "❌"
			text += f"{i}. {status_icon} {name}\n"
			text += f"---------------------------------------------\n"
		
		text += f"📄 Sahifa: {page}/{total_pages}\n"
		text += f"📊 Jami: {total_products} ta tovar\n\n"
		text += f"---------------------------------------------\n"
		text += "👇 Tovarni tanlash uchun raqamini bosing:"
		
		inline_keyboard = []
		
		# Sahifadagi tovarlar uchun raqamli tugmalar
		number_buttons = []
		for i, product in enumerate(page_products, start=start_index + 1):
			product_id = product[1]
			number_buttons.append(
				InlineKeyboardButton(
					text=str(i),
					callback_data=f"manage_product_{product_id}"
				)
			)
		
		# Raqamli tugmalarni 5 tadan qatorga joylashtirish
		for i in range(0, len(number_buttons), 5):
			row = number_buttons[i:i + 5]
			inline_keyboard.append(row)
		
		# Navigatsiya tugmalari
		nav_buttons = []
		if page > 1:
			nav_buttons.append(
				InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"manage_page_{page - 1}")
			)
		
		if total_pages > 1:
			nav_buttons.append(
				InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="current_manage_page")
			)
		
		if page < total_pages:
			nav_buttons.append(
				InlineKeyboardButton(text="➡️ Keyingi", callback_data=f"manage_page_{page + 1}")
			)
		
		if nav_buttons:
			inline_keyboard.append(nav_buttons)
		
		# Qo'shimcha tugmalar
		extra_buttons = [
			[
				InlineKeyboardButton(text="➕ Yangi qo'shish", callback_data="add_product"),
				InlineKeyboardButton(text="🔄 Yangilash", callback_data="manage_products")
			],
			[
				InlineKeyboardButton(text="📊 Statistika", callback_data="product_statistics"),
				InlineKeyboardButton(text="🔍 Qidirish", callback_data="admin_search_products")
			],
			[
				InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
			]
		]
		
		inline_keyboard.extend(extra_buttons)
		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		
		await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing manage products: {e}")
		await callback.answer("❌ Xatolik yuz berdi")

async def show_product_management(callback: CallbackQuery, product_id: str):
	"""Tovar boshqaruvi menyusi"""
	try:
		product = get_product(product_id)
		if not product:
			await callback.answer("❌ Tovar topilmadi")
			return
		
		name = product[2]
		description = product[3]
		price = product[4]
		uzum_link = product[5] if len(product) > 5 else None
		is_active = product[9]
		sales_count = product[12]
		total_revenue = product[13]
		category = product[15] if len(product) > 15 else 'Umumiy'
		brand = product[23] if len(product) > 23 else None
		warranty_months = product[22] if len(product) > 22 else 0
		
		status_text = "✅ Faol" if is_active else "❌ Nofaol"
		
		text = f"🛍 <b>TOVAR BOSHQARUVI</b>\n"
		text += f"---------------------------------------------\n\n"
		text += f"📝 <b>Nom:</b> {name}\n"
		text += f"📂 <b>Kategoriya:</b> {category}\n"
		text += f"💰 <b>Narx:</b> {price:,.0f} UZS\n"
		text += f"📊 <b>Holat:</b> {status_text}\n"
		text += f"🛒 <b>Sotildi:</b> {sales_count} ta\n"
		text += f"💵 <b>Daromad:</b> {total_revenue:,.0f} UZS\n"
		
		if brand:
			text += f"🏷 <b>Brend:</b> {brand}\n"
		
		if warranty_months and warranty_months > 0:
			text += f"🛡 <b>Kafolat:</b> {warranty_months} oy\n"
		
		if uzum_link:
			text += f"🛒 <b>Uzum link:</b> Mavjud\n"
		
		text += f"\n📋 <b>Tavsif:</b>\n{description[:100]}{'...' if len(description) > 100 else ''}\n\n"
		text += f"🆔 <b>ID:</b> <code>{product_id}</code>"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="👁 Ko'rish", callback_data=f"view_product_{product_id}"),
					InlineKeyboardButton(text="✏️ Tahrirlash", callback_data=f"edit_product_{product_id}")
				],
				[
					InlineKeyboardButton(text="🔗 Taklif havolasi", callback_data=f"referral_link_{product_id}")
				],
				[
					InlineKeyboardButton(
						text="❌ O'chirish" if is_active else "✅ Faollashtirish",
						callback_data=f"toggle_product_{product_id}"
					),
					InlineKeyboardButton(text="📋 Nusxalash", callback_data=f"duplicate_product_{product_id}")
				],
				[
					InlineKeyboardButton(text="📊 Statistika", callback_data=f"product_stats_{product_id}"),
					InlineKeyboardButton(text="📺 Kanalga yuborish", callback_data=f"send_to_channel_{product_id}")
				],
				[
					InlineKeyboardButton(text="🗑 Butunlay o'chirish", callback_data=f"delete_product_{product_id}")
				],
				[
					InlineKeyboardButton(text="🔙 Orqaga", callback_data="manage_products")
				]
			]
		)
		
		await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing product management: {e}")
		await callback.answer("❌ Xatolik yuz berdi")

@router.callback_query(F.data.startswith("referral_link_"))
async def referral_link_callback(callback: CallbackQuery):
	"""Taklif havolasini ko'rsatish"""
	product_id = callback.data.split("_")[2]
	
	product = get_product(product_id)
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	product_name = product[2]
	bot_username = get_bot_username()
	referral_link = f"https://t.me/{bot_username}?start=product_{product_id}"
	
	text = f"🔗 <b>TAKLIF HAVOLASI</b>\n\n"
	text += f"📦 <b>Mahsulot:</b> {product_name}\n\n"
	text += f"🌐 <b>Havola:</b>\n<code>{referral_link}</code>\n\n"
	text += f"📋 <b>Qo'llanma:</b>\n"
	text += f"• Havolani nusxalang\n"
	text += f"• Do'stlaringiz bilan bo'lashing\n"
	text += f"• Ular havola orqali tovarni ko'rishlari mumkin\n\n"
	text += f"💡 <b>Maslahat:</b> Ijtimoiy tarmoqlarda, guruhlarda yoki shaxsiy xabarlarda ulashing!"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="📋 Nusxalash", callback_data=f"copy_link_{product_id}")
			],
			[
				InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"manage_product_{product_id}")
			]
		]
	)
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

def get_bot_username():
    """Get bot username, fallback if not available"""
    try:
        return BOT_USERNAME.replace('@', '') if BOT_USERNAME else 'yourbot'
    except:
        return 'yourbot'
    
    
@router.callback_query(F.data.startswith("copy_link_"))
async def copy_link_callback(callback: CallbackQuery):
	"""Havolani nusxalash"""
	product_id = callback.data.split("_")[2]
	bot_username = get_bot_username()
	referral_link = f"https://t.me/{bot_username}?start=product_{product_id}"
	
	await callback.answer(f"📋 Havola nusxalandi!\n{referral_link}", show_alert=True)
	
	
	
async def show_product_edit_menu(callback: CallbackQuery, product_id: str):
	try:
		product = get_product(product_id)
		if not product:
			await callback.answer("❌ Tovar topilmadi")
			return
		
		name = product[2]
		
		text = f"✏️ <b>TOVAR TAHRIRLASH</b>\n"
		text += f"---------------------------------------------\n\n"
		text += f"📝 <b>Tovar:</b> {name}\n"
		text += f"🆔 <b>ID:</b> <code>{product_id}</code>\n\n"
		text += f"👇 Nimani tahrirlashni xohlaysiz?"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="📝 Nom", callback_data=f"edit_name_{product_id}"),
					InlineKeyboardButton(text="📋 Tavsif", callback_data=f"edit_description_{product_id}")
				],
				[
					InlineKeyboardButton(text="💰 Narx", callback_data=f"edit_price_{product_id}"),
					InlineKeyboardButton(text="📂 Kategoriya", callback_data=f"edit_category_{product_id}")
				],
				[
					InlineKeyboardButton(text="🏷 Brend", callback_data=f"edit_brand_{product_id}"),
					InlineKeyboardButton(text="🛡 Kafolat", callback_data=f"edit_warranty_{product_id}")
				],
				[
					InlineKeyboardButton(text="🛒 Uzum link", callback_data=f"edit_uzum_link_{product_id}"),
					InlineKeyboardButton(text="🖼 Rasm", callback_data=f"edit_image_{product_id}")
				],
				[
					InlineKeyboardButton(text="🎥 Video", callback_data=f"edit_video_{product_id}")
				],
				[
					InlineKeyboardButton(text="💾 Saqlash va chiqish", callback_data=f"manage_product_{product_id}"),
					InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		
		await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing product edit menu: {e}")
		await callback.answer("❌ Xatolik yuz berdi")

async def show_product_statistics_detailed(callback: CallbackQuery):
	try:
		stats = get_product_statistics()
		top_products = get_top_selling_products(5)
		categories = get_all_categories()
		
		text = "📊 <b>TOVARLAR STATISTIKASI</b>\n"
		text += "---------------------------------------------\n\n"
		
		text += f"📦 <b>UMUMIY MA'LUMOTLAR:</b>\n"
		text += f"├ Jami tovarlar: <b>{stats.get('total_products', 0)}</b>\n"
		text += f"├ Faol tovarlar: <b>{stats.get('active_products', 0)}</b>\n"
		text += f"├ Nofaol tovarlar: <b>{stats.get('inactive_products', 0)}</b>\n"
		text += f"├ Jami sotish: <b>{stats.get('total_sales', 0)}</b> ta\n"
		text += f"└ Jami daromad: <b>{stats.get('total_revenue', 0):,.0f}</b> UZS\n\n"
		
		text += "---------------------------------------------\n\n"
		text += f"⏰ <b>Oxirgi yangilanish:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="📈 Batafsil hisobot", callback_data="detailed_report"),
					InlineKeyboardButton(text="📊 Eksport", callback_data="export_stats")
				],
				[
					InlineKeyboardButton(text="🔄 Yangilash", callback_data="product_statistics"),
					InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
				]
			]
		)
		
		await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing detailed statistics: {e}")
		await callback.answer("❌ Xatolik yuz berdi")

async def show_google_sheets_settings(callback: CallbackQuery):
	try:
		current_url = get_setting("google_sheets_url", "")
		connection_status, email = test_google_sheets_connection()
		
		text = "⚙️ <b>GOOGLE SHEETS SOZLAMALARI</b>\n"
		text += "---------------------------------------------\n\n"
		
		text += f"🔗 <b>Ulanish holati:</b> {'✅ Ulangan' if connection_status else '❌ Ulanmagan'}\n"
		text += f"📧 <b>Service Account:</b> {email}\n\n"
		
		if current_url:
			text += f"📊 <b>Joriy Google Sheets:</b>\n"
			text += f"🔗 {current_url[:50]}{'...' if len(current_url) > 50 else ''}\n\n"
		else:
			text += f"📊 <b>Google Sheets:</b> ❌ Sozlanmagan\n\n"
		
		text += f"ℹ️ <b>Ma'lumot:</b>\n"
		text += f"• Buyurtmalar avtomatik Google Sheets ga saqlanadi\n"
		text += f"• Sheets URL ni o'rnatish uchun pastdagi tugmani bosing\n"
		text += f"• Service Account email ni Sheets ga ulashing kerak"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔗 URL o'rnatish", callback_data="set_sheets_url"),
					InlineKeyboardButton(text="🧪 Ulanishni tekshirish", callback_data="test_sheets_connection")
				],
				[
					InlineKeyboardButton(text="📋 Namuna yaratish", callback_data="create_sample_sheet"),
					InlineKeyboardButton(text="🗑 URL o'chirish", callback_data="clear_sheets_url")
				],
				[
					InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
				]
			]
		)
		
		await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error showing Google Sheets settings: {e}")
		await callback.answer("❌ Xatolik yuz berdi")

async def send_product_to_channel(bot, product_id):
	try:
		if not PRODUCT_CHANNEL:
			logger.warning("PRODUCT_CHANNEL not configured")
			return False
		
		product = get_product(product_id)
		if not product:
			logger.error(f"Product not found: {product_id}")
			return False
		
		name = product[2]
		description = product[3]
		original_price = product[4]
		uzum_link = product[5]
		image_file_id = product[6]
		video_file_id = product[7]
		product_type = product[8]
		category = product[15] if len(product) > 15 and product[15] else 'Umumiy'
		brand = product[23] if len(product) > 23 and product[23] else None
		warranty_months = product[22] if len(product) > 22 and product[22] is not None else 0
		
		bot_info = await bot.get_me()
		bot_username = bot_info.username
		
		channel_text = f"🛍 <b>{name}</b>\n\n"
		channel_text += f"{description}\n\n"
		
		if category and category != 'Umumiy':
			channel_text += f"📂 <b>Kategoriya:</b> {category}\n"
		
		if brand:
			channel_text += f"🏷 <b>Brend:</b> {brand}\n"
		
		if warranty_months and warranty_months > 0:
			channel_text += f"🛡 <b>Kafolat:</b> {warranty_months} oy\n"
		
		channel_text += f"\n💰 <b>Narx:</b> {original_price:,} UZS\n"
		channel_text += f"💳 <b>Tolashingiz kerak </b> {FIXED_PAYMENT_AMOUNT:,}  UZS \n\n"
		
		remaining_debt = original_price - FIXED_PAYMENT_AMOUNT
		if remaining_debt > 0:
			channel_text += f"🎁 <b>Yetkazilgach:</b> {abs(remaining_debt):,} UZS\n"
		else:
			channel_text += "✅ <b>To'liq to'lov</b>\n"
		
		
		inline_keyboard = []
		
		inline_keyboard.append([
			InlineKeyboardButton(
				text="🛒 SOTIB OLISH",
				url=f"https://t.me/{bot_username}?start=product_{product_id}"
			)
		])
		

		
		
		markup = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
		
		if product_type == "image" and image_file_id:
			await bot.send_photo(
				chat_id=PRODUCT_CHANNEL,
				photo=image_file_id,
				caption=channel_text,
				reply_markup=markup,
				parse_mode="HTML"
			)
		elif product_type == "video" and video_file_id:
			await bot.send_video(
				chat_id=PRODUCT_CHANNEL,
				video=video_file_id,
				caption=channel_text,
				reply_markup=markup,
				parse_mode="HTML"
			)
		else:
			await bot.send_message(
				chat_id=PRODUCT_CHANNEL,
				text=channel_text,
				reply_markup=markup,
				parse_mode="HTML"
			)
		
		logger.info(f"Product {product_id} sent to channel {PRODUCT_CHANNEL} successfully")
		return True
	
	except Exception as e:
		logger.error(f"Error sending product to channel: {e}")
		return False

@router.message(Command("tovar"))
async def tovar_admin_panel(message: Message):
	if message.from_user.id not in ADMINS:
		await message.answer("⚠️ Bu buyruq faqat adminlar uchun.")
		return
	
	try:
		stats = get_product_statistics()
		
		text = "🛍 <b>TOVAR BOSHQARUV PANELI</b>\n"
		text += "---------------------------------------------\n\n"
		text += f"📊 <b>STATISTIKA:</b>\n"
		text += f"├ 📦 Jami tovarlar: <b>{stats.get('total_products', 0)}</b>\n"
		text += f"├ ✅ Faol tovarlar: <b>{stats.get('active_products', 0)}</b>\n"
		text += f"└ ❌ Nofaol tovarlar: <b>{stats.get('inactive_products', 0)}</b>\n\n"
		text += f"💰 <b>MOLIYA:</b>\n"
		text += f"├ 🛒 Jami sotish: <b>{stats.get('total_sales', 0)}</b> ta\n"
		text += f"└ 💵 Jami daromad: <b>{stats.get('total_revenue', 0):,.0f}</b> UZS\n\n"
		text += "👇 <b>Kerakli bo'limni tanlang:</b>"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="➕ Tovar qo'shish", callback_data="add_product"),
					InlineKeyboardButton(text="📋 Tovarlar ro'yxati", callback_data="manage_products")
				],
				[
					InlineKeyboardButton(text="👀 Faol tovarlar", callback_data="show_all_products"),
					InlineKeyboardButton(text="⚙️ Google Sheets", callback_data="product_settings")
				],
				[
					InlineKeyboardButton(text="📊 Statistika", callback_data="product_statistics"),
					InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_admin_panel")
				]
			]
		)
		
		await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error in tovar admin panel: {e}")
		await message.answer("❌ Admin panelni yuklashda xatolik yuz berdi.")

@router.callback_query(F.data == "show_all_products")
async def show_all_products_callback(callback: CallbackQuery):
	await show_all_products(callback, is_callback=True)
	await callback.answer()

@router.callback_query(F.data.startswith("products_page_"))
async def products_page_callback(callback: CallbackQuery):
	page = int(callback.data.split("_")[2])
	await show_all_products(callback, page=page, is_callback=True)
	await callback.answer()

@router.callback_query(F.data.startswith("show_product_"))
async def show_product_callback(callback: CallbackQuery):
	product_id = callback.data.split("_")[2]
	await show_product_with_payment_buttons(callback, product_id, is_callback=True)
	await callback.answer()

@router.callback_query(F.data == "manage_products")
async def manage_products_callback(callback: CallbackQuery):
	await show_manage_products(callback)
	await callback.answer()

@router.callback_query(F.data.startswith("manage_page_"))
async def manage_page_callback(callback: CallbackQuery):
	page = int(callback.data.split("_")[2])
	await show_manage_products(callback, page=page)
	await callback.answer()

@router.callback_query(F.data.startswith("manage_product_"))
async def manage_product_callback(callback: CallbackQuery):
	product_id = callback.data.split("_")[2]
	await show_product_management(callback, product_id)
	await callback.answer()

@router.callback_query(F.data.startswith("view_product_"))
async def view_product_callback(callback: CallbackQuery):
	product_id = callback.data.split("_")[2]
	await show_product_with_payment_buttons(callback, product_id, is_callback=True)
	await callback.answer()

@router.callback_query(F.data.startswith("edit_product_"))
async def edit_product_callback(callback: CallbackQuery):
	product_id = callback.data.split("_")[2]
	await show_product_edit_menu(callback, product_id)
	await callback.answer()

@router.callback_query(F.data.startswith("edit_name_"))
async def edit_name_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="name")
	await state.set_state(ProductState.waiting_for_edit_name)
	
	current_name = product[2]
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR NOMINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"📝 <b>Joriy nom:</b> {current_name}\n\n"
	text += f"✏️ <b>Yangi nomni kiriting:</b>\n"
	text += f"(Kamida 3 ta belgi)"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_name)
async def edit_name_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_name = message.text.strip()
	
	if len(new_name) < 3:
		await message.answer("⚠️ Tovar nomi kamida 3 ta belgidan iborat bo'lishi kerak.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, name=new_name)
	
	if success:
		await message.answer(f"✅ Tovar nomi yangilandi: {new_name}")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Nomni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("edit_description_"))
async def edit_description_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="description")
	await state.set_state(ProductState.waiting_for_edit_description)
	
	current_description = product[3]
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR TAVSIFINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"📝 <b>Joriy tavsif:</b>\n{current_description[:200]}{'...' if len(current_description) > 200 else ''}\n\n"
	text += f"✏️ <b>Yangi tavsifni kiriting:</b>\n"
	text += f"(Kamida 10 ta belgi)"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_description)
async def edit_description_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_description = message.text.strip()
	
	if len(new_description) < 10:
		await message.answer("⚠️ Tovar tavsifi kamida 10 ta belgidan iborat bo'lishi kerak.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, description=new_description)
	
	if success:
		await message.answer("✅ Tovar tavsifi yangilandi")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Tavsifni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("edit_price_"))
async def edit_price_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="price")
	await state.set_state(ProductState.waiting_for_edit_price)
	
	current_price = product[4]
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR NARXINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"💰 <b>Joriy narx:</b> {current_price:,.0f} UZS\n\n"
	text += f"✏️ <b>Yangi narxni kiriting (UZS):</b>\n"
	text += f"Masalan: 250000"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_price)
async def edit_price_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		new_price = float(message.text.strip().replace(",", "").replace(" ", ""))
		if new_price <= 0:
			await message.answer("⚠️ Narx musbat son bo'lishi kerak.")
			return
	except ValueError:
		await message.answer("⚠️ Noto'g'ri narx formati. Faqat raqam kiriting.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, price=new_price)
	
	if success:
		await message.answer(f"✅ Tovar narxi yangilandi: {new_price:,.0f} UZS")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Narxni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("edit_category_"))
async def edit_category_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="category")
	await state.set_state(ProductState.waiting_for_edit_category)
	
	current_category = product[15] if len(product) > 15 else 'Umumiy'
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR KATEGORIYASINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"📂 <b>Joriy kategoriya:</b> {current_category}\n\n"
	text += f"✏️ <b>Yangi kategoriyani kiriting:</b>\n"
	text += f"Masalan: Elektronika, Kiyim, Oziq-ovqat"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_category)
async def edit_category_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_category = message.text.strip()
	
	if len(new_category) < 2:
		await message.answer("⚠️ Kategoriya nomi kamida 2 ta belgidan iborat bo'lishi kerak.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, category=new_category)
	
	if success:
		await message.answer(f"✅ Tovar kategoriyasi yangilandi: {new_category}")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Kategoriyani yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("edit_brand_"))
async def edit_brand_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="brand")
	await state.set_state(ProductState.waiting_for_edit_brand)
	
	current_brand = product[23] if len(product) > 23 and product[23] else "Belgilanmagan"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🗑 Brendni o'chirish", callback_data=f"clear_brand_{product_id}")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR BRENDINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"🏷 <b>Joriy brend:</b> {current_brand}\n\n"
	text += f"✏️ <b>Yangi brendni kiriting:</b>\n"
	text += f"Masalan: Samsung, Apple, Nike"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_brand)
async def edit_brand_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_brand = message.text.strip()
	
	if len(new_brand) < 1:
		await message.answer("⚠️ Brend nomi bo'sh bo'lishi mumkin emas.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, brand=new_brand)
	
	if success:
		await message.answer(f"✅ Tovar brendi yangilandi: {new_brand}")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Brendni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("clear_brand_"))
async def clear_brand_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	
	success = update_product_info(product_id, brand=None)
	
	if success:
		await callback.answer("✅ Brend o'chirildi")
		await state.clear()
		await show_product_edit_menu(callback, product_id)
	else:
		await callback.answer("❌ Brendni o'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("edit_warranty_"))
async def edit_warranty_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="warranty")
	await state.set_state(ProductState.waiting_for_edit_warranty)
	
	current_warranty = product[22] if len(product) > 22 and product[22] else 0
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🗑 Kafolatni o'chirish", callback_data=f"clear_warranty_{product_id}")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR KAFOLATINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"🛡 <b>Joriy kafolat:</b> {current_warranty} oy\n\n"
	text += f"✏️ <b>Yangi kafolat muddatini kiriting (oy):</b>\n"
	text += f"Masalan: 12, 24, 36\n"
	text += f"0 - kafolatsiz"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_warranty)
async def edit_warranty_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		new_warranty = int(message.text.strip())
		if new_warranty < 0:
			await message.answer("⚠️ Kafolat muddati manfiy bo'lishi mumkin emas.")
			return
		if new_warranty > 120:
			await message.answer("⚠️ Kafolat muddati 120 oydan oshmasligi kerak.")
			return
	except ValueError:
		await message.answer("⚠️ Noto'g'ri format. Faqat raqam kiriting.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, warranty_months=new_warranty)
	
	if success:
		warranty_text = f"{new_warranty} oy" if new_warranty > 0 else "Kafolatsiz"
		await message.answer(f"✅ Tovar kafolati yangilandi: {warranty_text}")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Kafolatni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("clear_warranty_"))
async def clear_warranty_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	
	success = update_product_info(product_id, warranty_months=0)
	
	if success:
		await callback.answer("✅ Kafolat o'chirildi")
		await state.clear()
		await show_product_edit_menu(callback, product_id)
	else:
		await callback.answer("❌ Kafolatni o'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("edit_uzum_link_"))
async def edit_uzum_link_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[3]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="uzum_link")
	await state.set_state(ProductState.waiting_for_edit_uzum_link)
	
	current_link = product[5] if len(product) > 5 and product[5] else "Mavjud emas"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🗑 Linkni o'chirish", callback_data=f"clear_uzum_link_{product_id}")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>UZUM LINKINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"🛒 <b>Joriy link:</b> {current_link[:50]}{'...' if len(current_link) > 50 else ''}\n\n"
	text += f"✏️ <b>Yangi Uzum Nasiya linkini kiriting:</b>\n"
	text += f"https:// bilan boshlangan to'liq link"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_uzum_link)
async def edit_uzum_link_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_link = message.text.strip()
	
	if new_link and not (new_link.startswith("http://") or new_link.startswith("https://")):
		await message.answer("⚠️ Link http:// yoki https:// bilan boshlanishi kerak.")
		return
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, uzum_link=new_link)
	
	if success:
		await message.answer("✅ Uzum linki yangilandi")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Linkni yangilashda xatolik yuz berdi.")

@router.callback_query(F.data.startswith("clear_uzum_link_"))
async def clear_uzum_link_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[3]
	
	success = update_product_info(product_id, uzum_link=None)
	
	if success:
		await callback.answer("✅ Uzum linki o'chirildi")
		await state.clear()
		await show_product_edit_menu(callback, product_id)
	else:
		await callback.answer("❌ Linkni o'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("edit_image_"))
async def edit_image_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="image")
	await state.set_state(ProductState.waiting_for_edit_image)
	
	current_image = "Mavjud" if product[6] else "Mavjud emas"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🗑 Rasmni o'chirish", callback_data=f"clear_image_{product_id}")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR RASMINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"🖼 <b>Joriy rasm:</b> {current_image}\n\n"
	text += f"📸 <b>Yangi rasmni yuboring:</b>\n"
	text += f"Rasm formatida fayl yuboring"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_image, F.photo)
async def edit_image_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_image_id = message.photo[-1].file_id
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, image_file_id=new_image_id)
	
	if success:
		await message.answer("✅ Tovar rasmi yangilandi")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Rasmni yangilashda xatolik yuz berdi.")

@router.message(ProductState.waiting_for_edit_image)
async def edit_image_invalid_handler(message: Message):
	if message.from_user.id not in ADMINS:
		return
	
	await message.answer("⚠️ Iltimos, rasm formatida fayl yuboring.")

@router.callback_query(F.data.startswith("clear_image_"))
async def clear_image_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	
	success = update_product_info(product_id, image_file_id=None)
	
	if success:
		await callback.answer("✅ Rasm o'chirildi")
		await state.clear()
		await show_product_edit_menu(callback, product_id)
	else:
		await callback.answer("❌ Rasmni o'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("edit_video_"))
async def edit_video_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	await state.update_data(editing_product_id=product_id, editing_field="video")
	await state.set_state(ProductState.waiting_for_edit_video)
	
	current_video = "Mavjud" if product[7] else "Mavjud emas"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🗑 Videoni o'chirish", callback_data=f"clear_video_{product_id}")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data=f"edit_product_{product_id}")
			]
		]
	)
	
	text = f"✏️ <b>TOVAR VIDEOSINI TAHRIRLASH</b>\n"
	text += f"---------------------------------------------\n\n"
	text += f"🎥 <b>Joriy video:</b> {current_video}\n\n"
	text += f"📹 <b>Yangi videoni yuboring:</b>\n"
	text += f"Video formatida fayl yuboring"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_edit_video, F.video)
async def edit_video_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	new_video_id = message.video.file_id
	
	state_data = await state.get_data()
	product_id = state_data.get('editing_product_id')
	
	success = update_product_info(product_id, video_file_id=new_video_id)
	
	if success:
		await message.answer("✅ Tovar videosi yangilandi")
		await state.clear()
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔙 Tahrirlashga qaytish", callback_data=f"edit_product_{product_id}"),
					InlineKeyboardButton(text="📋 Boshqarish", callback_data=f"manage_product_{product_id}")
				]
			]
		)
		await message.answer("👇 Keyingi harakat:", reply_markup=keyboard)
	else:
		await message.answer("❌ Videoni yangilashda xatolik yuz berdi.")

@router.message(ProductState.waiting_for_edit_video)
async def edit_video_invalid_handler(message: Message):
	if message.from_user.id not in ADMINS:
		return
	
	await message.answer("⚠️ Iltimos, video formatida fayl yuboring.")

@router.callback_query(F.data.startswith("clear_video_"))
async def clear_video_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	
	success = update_product_info(product_id, video_file_id=None)
	
	if success:
		await callback.answer("✅ Video o'chirildi")
		await state.clear()
		await show_product_edit_menu(callback, product_id)
	else:
		await callback.answer("❌ Videoni o'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("toggle_product_"))
async def toggle_product_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	current_status = product[9]
	new_status = 0 if current_status else 1
	
	success = update_product_status(product_id, new_status)
	
	if success:
		status_text = "faollashtirildi" if new_status else "o'chirildi"
		await callback.answer(f"✅ Tovar {status_text}")
		await show_product_management(callback, product_id)
	else:
		await callback.answer("❌ Xatolik yuz berdi")

@router.callback_query(F.data.startswith("duplicate_product_"))
async def duplicate_product_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	new_product_id = duplicate_product(product_id)
	
	if new_product_id:
		await callback.answer(f"✅ Tovar nusxalandi: {new_product_id}")
		await show_product_management(callback, new_product_id)
	else:
		await callback.answer("❌ Nusxalashda xatolik yuz berdi")

@router.callback_query(F.data.startswith("delete_product_"))
async def delete_product_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	product = get_product(product_id)
	
	if not product:
		await callback.answer("❌ Tovar topilmadi")
		return
	
	name = product[2]
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="✅ Ha, o'chirish", callback_data=f"confirm_delete_{product_id}"),
				InlineKeyboardButton(text="❌ Yo'q", callback_data=f"manage_product_{product_id}")
			]
		]
	)
	
	text = f"⚠️ <b>OGOHLANTIRISHH!</b>\n\n"
	text += f"Siz <b>{name}</b> tovarini butunlay o'chirmoqchisiz.\n\n"
	text += f"❌ Bu amal qaytarib bo'lmaydi!\n"
	text += f"❌ Barcha sotish tarixi ham o'chadi!\n\n"
	text += f"Davom etishni xohlaysizmi?"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.callback_query(F.data.startswith("confirm_delete_"))
async def confirm_delete_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[2]
	success = delete_product_permanently(product_id)
	
	if success:
		await callback.answer("✅ Tovar butunlay o'chirildi")
		await show_manage_products(callback)
	else:
		await callback.answer("❌ O'chirishda xatolik yuz berdi")

@router.callback_query(F.data.startswith("send_to_channel_"))
async def send_to_channel_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_id = callback.data.split("_")[3]
	success = await send_product_to_channel(callback.bot, product_id)
	
	if success:
		await callback.answer("✅ Tovar kanalga yuborildi")
	else:
		await callback.answer("❌ Kanalga yuborishda xatolik yuz berdi")

@router.callback_query(F.data == "product_statistics")
async def product_statistics_callback(callback: CallbackQuery):
	await show_product_statistics_detailed(callback)
	await callback.answer()

@router.callback_query(F.data == "product_settings")
async def product_settings_callback(callback: CallbackQuery):
	await show_google_sheets_settings(callback)
	await callback.answer()

@router.callback_query(F.data == "set_sheets_url")
async def set_sheets_url_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.set_state(ProductState.waiting_for_sheets_url)
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="product_settings")
			]
		]
	)
	
	text = "🔗 <b>GOOGLE SHEETS URL O'RNATISH</b>\n"
	text += "---------------------------------------------\n\n"
	text += "📋 <b>Quyidagi qadamlarni bajaring:</b>\n\n"
	text += "1️⃣ Google Sheets da yangi jadval yarating\n"
	text += "2️⃣ Jadvalga quyidagi email ni ulashing:\n"
	text += "📧 <code>web-malumotlari@aqueous-argon-454316-h5.iam.gserviceaccount.com</code>\n"
	text += "3️⃣ Email ga 'Editor' huquqi bering\n"
	text += "4️⃣ Jadval URL ni pastga yuboring\n\n"
	text += "💡 <b>Namuna URL:</b>\n"
	text += "<code>https://docs.google.com/spreadsheets/d/1ABC.../edit</code>"
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	await callback.answer()

@router.message(ProductState.waiting_for_sheets_url)
async def sheets_url_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	url = message.text.strip()
	
	if not url.startswith("https://docs.google.com/spreadsheets/"):
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="product_settings")
				]
			]
		)
		await message.answer(
			"⚠️ Noto'g'ri URL format.\n"
			"Google Sheets URL ni to'g'ri kiriting.",
			reply_markup=keyboard
		)
		return
	
	update_setting("google_sheets_url", url)
	await state.clear()
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🧪 Ulanishni tekshirish", callback_data="test_sheets_connection"),
				InlineKeyboardButton(text="🔙 Sozlamalar", callback_data="product_settings")
			]
		]
	)
	
	await message.answer(
		"✅ <b>Google Sheets URL saqlandi!</b>\n\n"
		"🧪 Endi ulanishni tekshirib ko'ring.",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.callback_query(F.data == "test_sheets_connection")
async def test_sheets_connection_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await callback.answer("🔄 Tekshirilmoqda...")
	
	success, message_text = test_google_sheets_connection()
	
	if success:
		test_data = {
			'sana': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
			'mijoz_ismi': 'Test Mijoz',
			'telefon': '+998901234567',
			'manzil': 'Test manzil',
			'tovar': 'Test tovar',
			'kategoriya': 'Test',
			'asosiy_narx': '100,000 UZS',
			'tolangan_summa': '50,000 UZS',
			'qolgan_qarz': '50,000 UZS',
			'tolov_usuli': 'TEST',
			'username': '@test_user',
			'user_id': '123456789',
			'miqdor': '1',
			'chegirma': '0',
			'status': 'Test',
			'izohlar': 'Bu test ma\'lumoti'
		}
		
		sheets_success = save_order_to_google_sheets(test_data)
		
		if sheets_success:
			text = "✅ <b>ULANISH MUVAFFAQIYATLI!</b>\n\n"
			text += "📊 Google Sheets ga test ma'lumot yuborildi.\n"
			text += "📧 Service Account: Ulangan\n"
			text += "🔗 URL: To'g'ri\n"
			text += "✍️ Yozish huquqi: Mavjud"
		else:
			text = "⚠️ <b>QISMAN MUAMMO</b>\n\n"
			text += "📧 Service Account: ✅ Ulangan\n"
			text += "🔗 URL: ❌ Noto'g'ri yoki huquq yo'q\n\n"
			text += "🔧 Tekshiring:\n"
			text += "• URL to'g'ri ekanligini\n"
			text += "• Service Account ga Editor huquqi berilganligini"
	else:
		text = "❌ <b>ULANISH XATOSI!</b>\n\n"
		text += f"📧 Service Account: ❌ Xato\n"
		text += f"🔗 Xato: {message_text}"
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🔄 Qayta tekshirish", callback_data="test_sheets_connection"),
				InlineKeyboardButton(text="🔙 Sozlamalar", callback_data="product_settings")
			]
		]
	)
	
	await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

@router.callback_query(F.data == "clear_sheets_url")
async def clear_sheets_url_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	update_setting("google_sheets_url", "")
	await callback.answer("✅ URL o'chirildi")
	await show_google_sheets_settings(callback)

@router.callback_query(F.data == "current_page")
async def current_page_callback(callback: CallbackQuery):
	await callback.answer("📄 Siz hozir ushbu sahifadasiz", show_alert=False)

@router.callback_query(F.data == "current_manage_page")
async def current_manage_page_callback(callback: CallbackQuery):
	await callback.answer("📄 Siz hozir ushbu sahifadasiz", show_alert=False)

@router.callback_query(F.data == "add_product")
async def add_product_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="🖼 Rasm bilan", callback_data="add_product_image"),
				InlineKeyboardButton(text="🎥 Video bilan", callback_data="add_product_video")
			],
			[
				InlineKeyboardButton(text="📝 Matn", callback_data="add_product_text")
			],
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	
	await callback.message.edit_text(
		"📦 <b>YANGI TOVAR QO'SHISH</b>\n"
		"---------------------------------------------\n\n"
		"📝 <b>Tovar turini tanlang:</b>\n\n"
		"🖼 <b>Rasm bilan</b> - Tovar rasmini yuklash\n"
		"🎥 <b>Video bilan</b> - Tovar videosini yuklash\n"
		"📝 <b>Matn</b> - Faqat matn ko'rinishida\n\n"
		"👇 Kerakli turni tanlang:",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.callback_query(F.data == "cancel_add_product")
async def cancel_add_product_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.clear()
	await back_to_admin_panel_callback(callback)

@router.callback_query(F.data.startswith("add_product_"))
async def add_product_type_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	product_type = callback.data.split("_")[2]
	
	await state.update_data(product_type=product_type)
	await state.set_state(ProductState.waiting_for_product_name)
	
	type_names = {
		"image": "🖼 Rasm bilan",
		"video": "🎥 Video bilan",
		"text": "📝 Matn"
	}
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	
	await callback.message.edit_text(
		f"📦 <b>YANGI TOVAR QO'SHISH</b>\n"
		f"---------------------------------------------\n\n"
		f"📝 <b>Tanlangan tur:</b> {type_names.get(product_type, product_type)}\n\n"
		f"✏️ <b>Tovar nomini kiriting:</b>\n"
		f"(Kamida 3 ta belgi)",
		reply_markup=keyboard,
		parse_mode="HTML"
	)
	await callback.answer()

@router.message(ProductState.waiting_for_product_name)
async def product_name_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	product_name = message.text.strip()
	
	if len(product_name) < 3:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer("⚠️ Tovar nomi kamida 3 ta belgidan iborat bo'lishi kerak.", reply_markup=keyboard)
		return
	
	await state.update_data(product_name=product_name)
	await state.set_state(ProductState.waiting_for_product_description)
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	
	await message.answer(
		f"✅ <b>Tovar nomi:</b> {product_name}\n\n"
		f"📝 <b>Tovar tavsifini kiriting:</b>\n"
		f"(Kamida 10 ta belgi)",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.message(ProductState.waiting_for_product_description)
async def product_description_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	description = message.text.strip()
	
	if len(description) < 10:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer("⚠️ Tovar tavsifi kamida 10 ta belgidan iborat bo'lishi kerak.", reply_markup=keyboard)
		return
	
	await state.update_data(product_description=description)
	await state.set_state(ProductState.waiting_for_product_price)
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	
	await message.answer(
		f"✅ <b>Tavsif qabul qilindi.</b>\n\n"
		f"💰 <b>Tovar narxini kiriting (UZS):</b>\n"
		f"Masalan: 150000",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.message(ProductState.waiting_for_product_price)
async def product_price_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	try:
		price = float(message.text.strip().replace(",", "").replace(" ", ""))
		if price <= 0:
			keyboard = InlineKeyboardMarkup(
				inline_keyboard=[
					[
						InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
					]
				]
			)
			await message.answer("⚠️ Narx musbat son bo'lishi kerak.", reply_markup=keyboard)
			return
	except ValueError:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer("⚠️ Noto'g'ri narx formati. Faqat raqam kiriting.", reply_markup=keyboard)
		return
	
	await state.update_data(product_price=price)
	await state.set_state(ProductState.waiting_for_uzum_link)
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	
	await message.answer(
		f"✅ <b>Narx:</b> {price:,.0f} UZS\n\n"
		f"🛒 <b>Uzum Nasiya havolasini kiriting:</b>\n"
		f"(Majburiy)",
		reply_markup=keyboard,
		parse_mode="HTML"
	)

@router.callback_query(F.data == "skip_uzum_link")
async def skip_uzum_link_callback(callback: CallbackQuery, state: FSMContext):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	await state.update_data(uzum_link=None)
	
	state_data = await state.get_data()
	product_type = state_data.get('product_type')
	
	if product_type == "image":
		await state.set_state(ProductState.waiting_for_product_image)
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await callback.message.edit_text(
			"🖼 <b>Tovar rasmini yuboring:</b>\n"
			"Rasm formatida fayl yuboring.",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	elif product_type == "video":
		await state.set_state(ProductState.waiting_for_product_video)
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await callback.message.edit_text(
			"🎥 <b>Tovar videosini yuboring:</b>\n"
			"Video formatida fayl yuboring.",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	else:
		await finalize_product_creation(callback.message, state)
	
	await callback.answer()

@router.message(ProductState.waiting_for_uzum_link)
async def uzum_link_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	uzum_link = message.text.strip()
	
	if uzum_link and not (uzum_link.startswith("http://") or uzum_link.startswith("https://")):
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer("⚠️ Havola http:// yoki https:// bilan boshlanishi kerak.", reply_markup=keyboard)
		return
	
	await state.update_data(uzum_link=uzum_link)
	
	state_data = await state.get_data()
	product_type = state_data.get('product_type')
	
	if product_type == "image":
		await state.set_state(ProductState.waiting_for_product_image)
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer(
			"🖼 <b>Tovar rasmini yuboring:</b>\n"
			"Rasm formatida fayl yuboring.",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	elif product_type == "video":
		await state.set_state(ProductState.waiting_for_product_video)
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
				]
			]
		)
		await message.answer(
			"🎥 <b>Tovar videosini yuboring:</b>\n"
			"Video formatida fayl yuboring.",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	else:
		await finalize_product_creation(message, state)

@router.message(ProductState.waiting_for_product_image, F.photo)
async def product_image_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	image_file_id = message.photo[-1].file_id
	await state.update_data(image_file_id=image_file_id)
	
	await finalize_product_creation(message, state)

@router.message(ProductState.waiting_for_product_image)
async def product_image_invalid_handler(message: Message):
	if message.from_user.id not in ADMINS:
		return
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	await message.answer("⚠️ Iltimos, rasm formatida fayl yuboring.", reply_markup=keyboard)

@router.message(ProductState.waiting_for_product_video, F.video)
async def product_video_handler(message: Message, state: FSMContext):
	if message.from_user.id not in ADMINS:
		return
	
	video_file_id = message.video.file_id
	await state.update_data(video_file_id=video_file_id)
	
	await finalize_product_creation(message, state)

@router.message(ProductState.waiting_for_product_video)
async def product_video_invalid_handler(message: Message):
	if message.from_user.id not in ADMINS:
		return
	
	keyboard = InlineKeyboardMarkup(
		inline_keyboard=[
			[
				InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_add_product")
			]
		]
	)
	await message.answer("⚠️ Iltimos, video formatida fayl yuboring.", reply_markup=keyboard)

async def finalize_product_creation(message: Message, state: FSMContext):
	state_data = await state.get_data()
	
	product_id = str(uuid.uuid4())[:8]
	product_name = state_data.get('product_name')
	product_description = state_data.get('product_description')
	product_price = state_data.get('product_price')
	uzum_link = state_data.get('uzum_link')
	product_type = state_data.get('product_type')
	image_file_id = state_data.get('image_file_id')
	video_file_id = state_data.get('video_file_id')
	
	success = add_product(
		product_id=product_id,
		name=product_name,
		description=product_description,
		price=product_price,
		uzum_link=uzum_link,
		image_file_id=image_file_id,
		video_file_id=video_file_id,
		product_type=product_type,
		created_by=message.from_user.id
	)
	
	if success:
		await send_product_to_channel(message.bot, product_id)
		bot_username = get_bot_username()
		referral_link = f"https://t.me/{bot_username}?start=product_{product_id}"
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="➕ Yana qo'shish", callback_data="add_product"),
					InlineKeyboardButton(text="📋 Tovarlar", callback_data="show_all_products")
				],
				[
					InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
				]
			]
		)
		
		await message.answer(
			
			f"✅ <b>TOVAR MUVAFFAQIYATLI QO'SHILDI!</b>\n\n"
			f"📦 <b>ID:</b> {product_id}\n"
			f"📝 <b>Nom:</b> {product_name}\n"
			f"💰 <b>Narx:</b> {product_price:,.0f} UZS\n"
			f"📺 <b>Kanal:</b> {'✅ Yuborildi' if PRODUCT_CHANNEL else '❌ Sozlanmagan'}\n\n"
			f"🎉 Tovar faol holatda va sotishga tayyor!  \n\n 🔗 Havolani nusxlaash : \n --------------------------------------------- \n <code>{referral_link}</code> --------------------------------------------- \n\n 🔗 Taklif linkini " ,
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	else:
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="🔄 Qaytadan urinish", callback_data="add_product"),
					InlineKeyboardButton(text="🔙 Admin panel", callback_data="back_to_admin_panel")
				]
			]
		)
		
		await message.answer(
			"❌ <b>XATOLIK!</b>\n\n"
			"Tovarni qo'shishda muammo yuz berdi.\n"
			"Iltimos, qaytadan urinib ko'ring.",
			reply_markup=keyboard,
			parse_mode="HTML"
		)
	
	await state.clear()
	


	

@router.callback_query(F.data == "back_to_admin_panel")
async def back_to_admin_panel_callback(callback: CallbackQuery):
	if callback.from_user.id not in ADMINS:
		await callback.answer("⚠️ Bu funksiya faqat adminlar uchun.")
		return
	
	try:
		stats = get_product_statistics()
		
		text = "🛍 <b>TOVAR BOSHQARUV PANELI</b>\n"
		text += "---------------------------------------------\n\n"
		text += f"📊 <b>STATISTIKA:</b>\n"
		text += f"├ 📦 Jami tovarlar: <b>{stats.get('total_products', 0)}</b>\n"
		text += f"├ ✅ Faol tovarlar: <b>{stats.get('active_products', 0)}</b>\n"
		text += f"└ ❌ Nofaol tovarlar: <b>{stats.get('inactive_products', 0)}</b>\n\n"
		text += f"💰 <b>MOLIYA:</b>\n"
		text += f"├ 🛒 Jami sotish: <b>{stats.get('total_sales', 0)}</b> ta\n"
		text += f"└ 💵 Jami daromad: <b>{stats.get('total_revenue', 0):,.0f}</b> UZS\n\n"
		text += "👇 <b>Kerakli bo'limni tanlang:</b>"
		
		keyboard = InlineKeyboardMarkup(
			inline_keyboard=[
				[
					InlineKeyboardButton(text="➕ Tovar qo'shish", callback_data="add_product"),
					InlineKeyboardButton(text="📋 Tovarlar ro'yxati", callback_data="manage_products")
				],
				[
					InlineKeyboardButton(text="👀 Faol tovarlar", callback_data="show_all_products"),
					InlineKeyboardButton(text="⚙️ Google Sheets", callback_data="product_settings")
				],
				[
					InlineKeyboardButton(text="📊 Statistika", callback_data="product_statistics"),
					InlineKeyboardButton(text="🔄 Yangilash", callback_data="refresh_admin_panel")
				]
			]
		)
		
		await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
	
	except Exception as e:
		logger.error(f"Error in back_to_admin_panel: {e}")
		await callback.answer("❌ Admin panelni yuklashda xatolik yuz berdi.")
	
	await callback.answer()

@router.callback_query(F.data == "refresh_admin_panel")
async def refresh_admin_panel_callback(callback: CallbackQuery):
	await back_to_admin_panel_callback(callback)
