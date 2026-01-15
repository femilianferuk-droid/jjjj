import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ParseMode
from aiogram.utils import executor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получение токена из переменных окружения
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("Токен бота не найден! Установите переменную окружения TELEGRAM_BOT_TOKEN")

# ID администратора
ADMIN_ID = 7973988177

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Цены
ACCOUNT_PRICES = {
    "США": 35,
    "РОССИЯ": 200,
    "КАЗАХСТАН": 200,
    "ИНДИЯ": 30
}

RENT_PRICES = {
    "США": 2  # руб/час
}

BROADCAST_PRICE = 3  # руб/час

# Хранилище данных
class DataStorage:
    def __init__(self):
        self.users_file = "users.json"
        self.stats_file = "stats.json"
        self.load_data()
    
    def load_data(self):
        try:
            with open(self.users_file, 'r', encoding='utf-8') as f:
                self.users = json.load(f)
        except FileNotFoundError:
            self.users = {}
        
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                self.stats = json.load(f)
        except FileNotFoundError:
            self.stats = {
                "total_users": 0,
                "total_revenue": 0,
                "accounts_sold": 0,
                "rent_hours": 0,
                "broadcast_hours": 0
            }
    
    def save_data(self):
        with open(self.users_file, 'w', encoding='utf-8') as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2)
        
        with open(self.stats_file, 'w', encoding='utf-8') as f:
            json.dump(self.stats, f, ensure_ascii=False, indent=2)
    
    def get_user(self, user_id: int):
        if str(user_id) not in self.users:
            return None
        return self.users[str(user_id)]
    
    def create_user(self, user_id: int, username: str = ""):
        user_data = {
            "user_id": user_id,
            "username": username,
            "balance": 0,
            "purchases": [],
            "rents": [],
            "broadcasts": [],
            "created_at": datetime.now().isoformat()
        }
        self.users[str(user_id)] = user_data
        
        # Обновляем статистику
        self.stats["total_users"] = len(self.users)
        self.save_data()
        return user_data
    
    def update_user(self, user_id: int, updates: dict):
        if str(user_id) in self.users:
            self.users[str(user_id)].update(updates)
            self.save_data()
    
    def add_purchase(self, user_id: int, account_type: str, quantity: int, total_price: int):
        purchase = {
            "type": "account",
            "account_type": account_type,
            "quantity": quantity,
            "price": total_price,
            "date": datetime.now().isoformat()
        }
        
        if str(user_id) in self.users:
            if "purchases" not in self.users[str(user_id)]:
                self.users[str(user_id)]["purchases"] = []
            self.users[str(user_id)]["purchases"].append(purchase)
            
            # Обновляем статистику
            self.stats["accounts_sold"] += quantity
            self.stats["total_revenue"] += total_price
            self.save_data()

# Инициализация хранилища
storage_db = DataStorage()

# Классы состояний
class BuyStates(StatesGroup):
    choosing_account_type = State()
    choosing_quantity = State()

class RentStates(StatesGroup):
    choosing_hours = State()

class BroadcastStates(StatesGroup):
    choosing_hours = State()

class AdminStates(StatesGroup):
    broadcast_message = State()

# Клавиатуры
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🛒 Купить аккаунты", callback_data="buy_accounts"),
        InlineKeyboardButton("⏳ Аренда аккаунтов", callback_data="rent_accounts"),
        InlineKeyboardButton("📢 Рассылка", callback_data="broadcast"),
        InlineKeyboardButton("💰 Мой баланс", callback_data="balance"),
        InlineKeyboardButton("👑 Админ панель", callback_data="admin_panel")
    )
    return keyboard

def get_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton("📢 Сделать рассылку", callback_data="admin_broadcast"),
        InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")
    )
    return keyboard

def get_account_types_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for country, price in ACCOUNT_PRICES.items():
        buttons.append(InlineKeyboardButton(
            f"{country} - {price}₽", 
            callback_data=f"account_{country}"
        ))
    keyboard.add(*buttons)
    keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return keyboard

def get_payment_keyboard(payment_type: str, item_id: str = ""):
    """Создает клавиатуру с кнопкой оплаты"""
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{payment_type}_{item_id}"),
        InlineKeyboardButton("⬅️ Назад", callback_data="main_menu")
    )
    return keyboard

def get_back_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return keyboard

# Обработчики команд
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    
    user = storage_db.get_user(user_id)
    if not user:
        user = storage_db.create_user(user_id, username)
    
    welcome_text = (
        "🐵 *Monkey Number*\n\n"
        "Добро пожаловать в лучший магазин Telegram аккаунтов!\n\n"
        "✨ *Наши услуги:*\n"
        "• Покупка аккаунтов разных стран\n"
        "• Аренда аккаунтов\n"
        "• Рассылка сообщений\n\n"
        "Выберите действие:"
    )
    
    await message.answer(welcome_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_main_keyboard())

@dp.message_handler(commands=['admin'])
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        admin_text = "👑 *Админ панель*\n\nВыберите действие:"
        await message.answer(admin_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    else:
        await message.answer("⛔ У вас нет доступа к админ панели!")

# Обработчики callback-запросов
@dp.callback_query_handler(lambda c: c.data == 'main_menu')
async def process_main_menu(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="🐵 *Monkey Number*\n\nГлавное меню:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data == 'buy_accounts')
async def process_buy_accounts(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    text = (
        "🛒 *Покупка аккаунтов*\n\n"
        "Выберите страну аккаунта:\n\n"
        f"• США - {ACCOUNT_PRICES['США']}₽\n"
        f"• РОССИЯ - {ACCOUNT_PRICES['РОССИЯ']}₽\n"
        f"• КАЗАХСТАН - {ACCOUNT_PRICES['КАЗАХСТАН']}₽\n"
        f"• ИНДИЯ - {ACCOUNT_PRICES['ИНДИЯ']}₽"
    )
    
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_account_types_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data.startswith('account_'))
async def process_account_type(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id)
    
    country = callback_query.data.replace('account_', '')
    price = ACCOUNT_PRICES[country]
    
    async with state.proxy() as data:
        data['account_type'] = country
        data['account_price'] = price
    
    text = (
        f"🌍 *{country}*\n\n"
        f"Цена: *{price}₽* за 1 аккаунт\n\n"
        "Сколько аккаунтов вы хотите купить?\n"
        "Введите количество (1-100):"
    )
    
    await BuyStates.choosing_quantity.set()
    
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message_handler(state=BuyStates.choosing_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 100:
            await message.answer("❌ Введите число от 1 до 100")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    async with state.proxy() as data:
        account_type = data['account_type']
        price = data['account_price']
    
    total_price = quantity * price
    
    text = (
        f"📦 *Детали заказа*\n\n"
        f"• Страна: *{account_type}*\n"
        f"• Количество: *{quantity}*\n"
        f"• Цена за штуку: *{price}₽*\n"
        f"• Общая сумма: *{total_price}₽*\n\n"
        f"Для оплаты нажмите кнопку ниже:"
    )
    
    # Создаем уникальный ID для заказа
    order_id = f"account_{account_type}_{int(datetime.now().timestamp())}"
    
    # Сохраняем данные заказа во временном хранилище
    async with state.proxy() as data:
        data['quantity'] = quantity
        data['total_price'] = total_price
        data['order_id'] = order_id
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("account", order_id)
    )
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'rent_accounts')
async def process_rent_accounts(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    text = (
        "⏳ *Аренда аккаунтов*\n\n"
        f"Доступна только аренда аккаунтов *США*\n"
        f"Цена: *{RENT_PRICES['США']}₽/час*\n"
        f"Максимум: *20 часов*\n\n"
        "Введите количество часов (1-20):"
    )
    
    await RentStates.choosing_hours.set()
    
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message_handler(state=RentStates.choosing_hours)
async def process_rent_hours(message: types.Message, state: FSMContext):
    try:
        hours = int(message.text)
        if hours < 1 or hours > 20:
            await message.answer("❌ Введите число от 1 до 20")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    price_per_hour = RENT_PRICES['США']
    total_price = hours * price_per_hour
    
    text = (
        f"⏳ *Детали аренды*\n\n"
        f"• Страна: *США*\n"
        f"• Количество часов: *{hours}*\n"
        f"• Цена за час: *{price_per_hour}₽*\n"
        f"• Общая сумма: *{total_price}₽*\n\n"
        f"Для оплаты нажмите кнопку ниже:"
    )
    
    # Создаем уникальный ID для аренды
    rent_id = f"rent_USA_{int(datetime.now().timestamp())}"
    
    # Сохраняем данные аренды
    async with state.proxy() as data:
        data['hours'] = hours
        data['total_price'] = total_price
        data['rent_id'] = rent_id
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("rent", rent_id)
    )
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'broadcast')
async def process_broadcast(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    text = (
        "📢 *Рассылка сообщений*\n\n"
        f"Цена: *{BROADCAST_PRICE}₽/час*\n"
        f"Максимум: *24 часа*\n\n"
        "Введите количество часов (1-24):"
    )
    
    await BroadcastStates.choosing_hours.set()
    
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message_handler(state=BroadcastStates.choosing_hours)
async def process_broadcast_hours(message: types.Message, state: FSMContext):
    try:
        hours = int(message.text)
        if hours < 1 or hours > 24:
            await message.answer("❌ Введите число от 1 до 24")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    total_price = hours * BROADCAST_PRICE
    
    text = (
        f"📢 *Детали рассылки*\n\n"
        f"• Количество часов: *{hours}*\n"
        f"• Цена за час: *{BROADCAST_PRICE}₽*\n"
        f"• Общая сумма: *{total_price}₽*\n\n"
        f"Для оплаты нажмите кнопку ниже:"
    )
    
    # Создаем уникальный ID для рассылки
    broadcast_id = f"broadcast_{int(datetime.now().timestamp())}"
    
    # Сохраняем данные рассылки
    async with state.proxy() as data:
        data['hours'] = hours
        data['total_price'] = total_price
        data['broadcast_id'] = broadcast_id
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("broadcast", broadcast_id)
    )
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == 'balance')
async def process_balance(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    user_id = callback_query.from_user.id
    user = storage_db.get_user(user_id)
    
    if user:
        balance = user.get('balance', 0)
        purchases_count = len(user.get('purchases', []))
        rents_count = len(user.get('rents', []))
        broadcasts_count = len(user.get('broadcasts', []))
        
        text = (
            f"💰 *Ваш баланс*\n\n"
            f"• Текущий баланс: *{balance}₽*\n\n"
            f"📊 *Статистика покупок:*\n"
            f"• Куплено аккаунтов: *{purchases_count}*\n"
            f"• Аренд: *{rents_count}*\n"
            f"• Рассылок: *{broadcasts_count}*"
        )
    else:
        text = "💰 *Ваш баланс*\n\n• Текущий баланс: *0₽*"
    
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text=text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

# Обработчик кнопки оплаты
@dp.callback_query_handler(lambda c: c.data.startswith('pay_'))
async def process_payment(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)
    
    # Показываем смайлик любви
    love_message = "❤️💕💖💗💓💘💝💞💟🥰😍😘💑"
    
    # Отправляем сообщение со смайликами
    await bot.send_message(
        callback_query.from_user.id,
        f"💳 *Оплата*\n\n"
        f"{love_message}\n\n"
        f"Спасибо за оплату! Ваш заказ обрабатывается!\n"
        f"Свяжитесь с администратором для получения товара.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Возвращаем в главное меню
    await bot.edit_message_text(
        chat_id=callback_query.from_user.id,
        message_id=callback_query.message.message_id,
        text="🐵 *Monkey Number*\n\nОплата успешно обработана! Свяжитесь с администратором.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard()
    )

# Админ функции
@dp.callback_query_handler(lambda c: c.data == 'admin_panel')
async def process_admin_panel(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await bot.answer_callback_query(callback_query.id)
        
        text = "👑 *Админ панель*\n\nВыберите действие:"
        
        await bot.edit_message_text(
            chat_id=callback_query.from_user.id,
            message_id=callback_query.message.message_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    else:
        await bot.answer_callback_query(callback_query.id, "⛔ Доступ запрещен!", show_alert=True)

@dp.callback_query_handler(lambda c: c.data == 'admin_stats')
async def process_admin_stats(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await bot.answer_callback_query(callback_query.id)
        
        stats = storage_db.stats
        
        text = (
            "📊 *Статистика Monkey Number*\n\n"
            f"• Всего пользователей: *{stats['total_users']}*\n"
            f"• Общая выручка: *{stats['total_revenue']}₽*\n"
            f"• Продано аккаунтов: *{stats['accounts_sold']}*\n"
            f"• Часов аренды: *{stats['rent_hours']}*\n"
            f"• Часов рассылки: *{stats['broadcast_hours']}*\n\n"
            f"📈 *Финансы:*\n"
            f"• Аккаунты: {sum(ACCOUNT_PRICES.values())}₽ за набор\n"
            f"• Аренда: {RENT_PRICES['США']}₽/час\n"
            f"• Рассылка: {BROADCAST_PRICE}₽/час"
        )
        
        await bot.edit_message_text(
            chat_id=callback_query.from_user.id,
            message_id=callback_query.message.message_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query_handler(lambda c: c.data == 'admin_broadcast')
async def process_admin_broadcast_start(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await bot.answer_callback_query(callback_query.id)
        
        text = "📢 *Админ рассылка*\n\nОтправьте сообщение для рассылки всем пользователям:"
        
        await AdminStates.broadcast_message.set()
        
        await bot.edit_message_text(
            chat_id=callback_query.from_user.id,
            message_id=callback_query.message.message_id,
            text=text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )

@dp.message_handler(state=AdminStates.broadcast_message)
async def process_admin_broadcast_message(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        users = storage_db.users
        sent_count = 0
        failed_count = 0
        
        # Отправляем сообщение всем пользователям
        for user_data in users.values():
            try:
                await bot.send_message(
                    chat_id=user_data['user_id'],
                    text=f"📢 *Сообщение от администратора*\n\n{message.text}",
                    parse_mode=ParseMode.MARKDOWN
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send broadcast to {user_data['user_id']}: {e}")
                failed_count += 1
        
        await message.answer(
            f"✅ Рассылка завершена!\n\n"
            f"• Успешно отправлено: *{sent_count}*\n"
            f"• Не удалось отправить: *{failed_count}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
        
        await state.finish()

# Обработчик для всех остальных сообщений
@dp.message_handler()
async def handle_other_messages(message: types.Message):
    if message.text.isdigit():
        # Если это число, проверяем состояния
        user_state = dp.current_state(user=message.from_user.id)
        state = await user_state.get_state()
        
        if state:
            # Если есть активное состояние, не обрабатываем здесь
            return
    
    # Для всех остальных сообщений показываем главное меню
    await cmd_start(message)

# Запуск бота
if __name__ == '__main__':
    logger.info("Бот Monkey Number запускается...")
    executor.start_polling(dp, skip_updates=True)
