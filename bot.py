import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
import asyncio

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
dp = Dispatcher(storage=storage)

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
                "broadcast_hours": 0,
                "last_update": datetime.now().isoformat()
            }
    
    def save_data(self):
        self.stats["last_update"] = datetime.now().isoformat()
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
            "created_at": datetime.now().isoformat(),
            "is_admin": (user_id == ADMIN_ID)
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
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🛒 Купить аккаунты", callback_data="buy_accounts"),
        InlineKeyboardButton(text="⏳ Аренда аккаунтов", callback_data="rent_accounts")
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="broadcast"),
        InlineKeyboardButton(text="💰 Мой баланс", callback_data="balance")
    )
    builder.row(
        InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel")
    )
    return builder.as_markup()

def get_admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu")
    )
    return builder.as_markup()

def get_account_types_keyboard():
    builder = InlineKeyboardBuilder()
    for country, price in ACCOUNT_PRICES.items():
        builder.button(text=f"{country} - {price}₽", callback_data=f"account_{country}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    return builder.as_markup()

def get_payment_keyboard(payment_type: str, item_id: str = ""):
    """Создает клавиатуру с кнопкой оплаты"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", callback_data=f"pay_{payment_type}_{item_id}"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    return builder.as_markup()

def get_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="main_menu"))
    return builder.as_markup()

# Обработчики команд
@dp.message(Command("start"))
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

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        admin_text = "👑 *Админ панель*\n\nВыберите действие:"
        await message.answer(admin_text, parse_mode=ParseMode.MARKDOWN, reply_markup=get_admin_keyboard())
    else:
        await message.answer("⛔ У вас нет доступа к админ панели!")

# Обработчики callback-запросов
@dp.callback_query(F.data == "main_menu")
async def process_main_menu(callback_query: types.CallbackQuery):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "🐵 *Monkey Number*\n\nГлавное меню:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard()
    )

@dp.callback_query(F.data == "buy_accounts")
async def process_buy_accounts(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    text = (
        "🛒 *Покупка аккаунтов*\n\n"
        "Выберите страну аккаунта:\n\n"
        f"• США - {ACCOUNT_PRICES['США']}₽\n"
        f"• РОССИЯ - {ACCOUNT_PRICES['РОССИЯ']}₽\n"
        f"• КАЗАХСТАН - {ACCOUNT_PRICES['КАЗАХСТАН']}₽\n"
        f"• ИНДИЯ - {ACCOUNT_PRICES['ИНДИЯ']}₽"
    )
    
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_account_types_keyboard()
    )

@dp.callback_query(F.data.startswith("account_"))
async def process_account_type(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    country = callback_query.data.replace('account_', '')
    price = ACCOUNT_PRICES[country]
    
    await state.update_data(account_type=country, account_price=price)
    
    text = (
        f"🌍 *{country}*\n\n"
        f"Цена: *{price}₽* за 1 аккаунт\n\n"
        "Сколько аккаунтов вы хотите купить?\n"
        "Введите количество (1-100):"
    )
    
    await state.set_state(BuyStates.choosing_quantity)
    
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message(BuyStates.choosing_quantity)
async def process_quantity(message: types.Message, state: FSMContext):
    try:
        quantity = int(message.text)
        if quantity < 1 or quantity > 100:
            await message.answer("❌ Введите число от 1 до 100")
            return
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число")
        return
    
    data = await state.get_data()
    account_type = data.get('account_type')
    price = data.get('account_price')
    
    if not account_type or not price:
        await message.answer("❌ Произошла ошибка. Попробуйте снова.")
        await state.clear()
        return
    
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
    
    # Сохраняем данные заказа
    await state.update_data(
        quantity=quantity, 
        total_price=total_price, 
        order_id=order_id
    )
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("account", order_id)
    )
    
    await state.clear()

@dp.callback_query(F.data == "rent_accounts")
async def process_rent_accounts(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    text = (
        "⏳ *Аренда аккаунтов*\n\n"
        f"Доступна только аренда аккаунтов *США*\n"
        f"Цена: *{RENT_PRICES['США']}₽/час*\n"
        f"Максимум: *20 часов*\n\n"
        "Введите количество часов (1-20):"
    )
    
    await state.set_state(RentStates.choosing_hours)
    
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message(RentStates.choosing_hours)
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
    await state.update_data(
        hours=hours, 
        total_price=total_price, 
        rent_id=rent_id
    )
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("rent", rent_id)
    )
    
    await state.clear()

@dp.callback_query(F.data == "broadcast")
async def process_broadcast(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    text = (
        "📢 *Рассылка сообщений*\n\n"
        f"Цена: *{BROADCAST_PRICE}₽/час*\n"
        f"Максимум: *24 часа*\n\n"
        "Введите количество часов (1-24):"
    )
    
    await state.set_state(BroadcastStates.choosing_hours)
    
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

@dp.message(BroadcastStates.choosing_hours)
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
    await state.update_data(
        hours=hours, 
        total_price=total_price, 
        broadcast_id=broadcast_id
    )
    
    await message.answer(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_payment_keyboard("broadcast", broadcast_id)
    )
    
    await state.clear()

@dp.callback_query(F.data == "balance")
async def process_balance(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
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
    
    await callback_query.message.edit_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_back_keyboard()
    )

# Обработчик кнопки оплаты
@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback_query: types.CallbackQuery):
    await callback_query.answer()
    
    # Показываем смайлик любви
    love_message = "❤️💕💖💗💓💘💝💞💟🥰😍😘💑"
    
    # Отправляем сообщение со смайликами
    await callback_query.message.answer(
        f"💳 *Оплата*\n\n"
        f"{love_message}\n\n"
        f"Спасибо за оплату! Ваш заказ обрабатывается!\n"
        f"Свяжитесь с администратором для получения товара.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Возвращаем в главное меню
    await callback_query.message.edit_text(
        "🐵 *Monkey Number*\n\nОплата успешно обработана! Свяжитесь с администратором.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_keyboard()
    )

# Админ функции
@dp.callback_query(F.data == "admin_panel")
async def process_admin_panel(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await callback_query.answer()
        
        text = "👑 *Админ панель*\n\nВыберите действие:"
        
        await callback_query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
    else:
        await callback_query.answer("⛔ Доступ запрещен!", show_alert=True)

@dp.callback_query(F.data == "admin_stats")
async def process_admin_stats(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await callback_query.answer()
        
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
            f"• Рассылка: {BROADCAST_PRICE}₽/час\n\n"
            f"🕐 Последнее обновление:\n"
            f"{stats.get('last_update', 'Нет данных')}"
        )
        
        await callback_query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )

@dp.callback_query(F.data == "admin_broadcast")
async def process_admin_broadcast_start(callback_query: types.CallbackQuery, state: FSMContext):
    user_id = callback_query.from_user.id
    if user_id == ADMIN_ID:
        await callback_query.answer()
        
        text = "📢 *Админ рассылка*\n\nОтправьте сообщение для рассылки всем пользователям:"
        
        await state.set_state(AdminStates.broadcast_message)
        
        await callback_query.message.edit_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_back_keyboard()
        )

@dp.message(AdminStates.broadcast_message)
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
        
        await state.clear()

# Обработчик для всех остальных сообщений
@dp.message()
async def handle_other_messages(message: types.Message):
    # Проверяем, есть ли активное состояние
    current_state = dp.fsm.get_context(bot, message.from_user.id, message.chat.id)
    state = await current_state.get_state()
    
    if not state:
        # Если нет активного состояния, показываем главное меню
        await cmd_start(message)

# Запуск бота
async def main():
    logger.info("Бот Monkey Number запускается...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
