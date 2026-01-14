import asyncio
import random
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, LabeledPrice, PreCheckoutQuery,
    SuccessfulPayment, InlineQuery, InlineQueryResultArticle,
    InputTextMessageContent
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Роутер
router = Router()

# Состояния FSM
class Form(StatesGroup):
    waiting_for_amount = State()

# Конфигурация
ADMIN_CHAT_ID = 7973988177
CASE_PRICE = 30
GAME_PRICE = 8

# Призы для кейса
CASE_PRIZES = {
    "heart": {"name": "❤️ Сердечко", "chance": 80.0, "value": 5},
    "bear": {"name": "🧸 Мишка", "chance": 80.0, "value": 5},
    "rose": {"name": "🌹 Роза", "chance": 15.0, "value": 50},
    "ring": {"name": "💍 Кольцо", "chance": 4.99, "value": 200},
    "calendar": {"name": "📅 Desk Calendar", "chance": 0.01, "value": 1000}
}

# Хранилище данных пользователей
class UserData:
    def __init__(self):
        self.users = {}
        self.load_data()
    
    def load_data(self):
        try:
            with open('users_data.json', 'r', encoding='utf-8') as f:
                self.users = json.load(f)
        except FileNotFoundError:
            self.users = {}
    
    def save_data(self):
        with open('users_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.users, f, ensure_ascii=False, indent=2)
    
    def get_user(self, user_id: int):
        if str(user_id) not in self.users:
            self.users[str(user_id)] = {
                "balance": 0,
                "inventory": [],
                "total_spent": 0,
                "total_won": 0,
                "joined_date": datetime.now().isoformat()
            }
        return self.users[str(user_id)]
    
    def update_balance(self, user_id: int, amount: int):
        user = self.get_user(user_id)
        user["balance"] += amount
        self.save_data()
    
    def add_to_inventory(self, user_id: int, item: str):
        user = self.get_user(user_id)
        user["inventory"].append({
            "item": item,
            "date": datetime.now().isoformat()
        })
        self.save_data()
    
    def get_inventory(self, user_id: int) -> List:
        user = self.get_user(user_id)
        return user["inventory"]

# Инициализация хранилища
user_data = UserData()

# Основные клавиатуры
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="🎮 Мини-игры", callback_data="minigames")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cases_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎒 БОМЖ КЕЙС (30 звёзд)", callback_data="open_bum_case")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_minigames_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚽️ Футбол", callback_data="game_football")],
        [InlineKeyboardButton(text="🏀 Баскетбол", callback_data="game_basketball")],
        [InlineKeyboardButton(text="🎯 Дартс", callback_data="game_darts")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton(text="🎒 Инвентарь", callback_data="inventory")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="8 ⭐", callback_data="deposit_8"),
         InlineKeyboardButton(text="50 ⭐", callback_data="deposit_50")],
        [InlineKeyboardButton(text="100 ⭐", callback_data="deposit_100"),
         InlineKeyboardButton(text="500 ⭐", callback_data="deposit_500")],
        [InlineKeyboardButton(text="1000 ⭐", callback_data="deposit_1000")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_to_profile_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Обработчики команд
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "🎰 Добро пожаловать в Casino Bot!\n\n"
        "✨ Здесь вы можете открывать кейсы и играть в мини-игры!\n\n"
        "💎 Для начала пополните баланс звёздами.",
        reply_markup=get_main_keyboard()
    )
    # Уведомление админа
    if message.from_user.id != ADMIN_CHAT_ID:
        await message.bot.send_message(
            ADMIN_CHAT_ID,
            f"👤 Новый пользователь:\n"
            f"ID: {message.from_user.id}\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username}"
        )

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    total_users = len(user_data.users)
    total_balance = sum(user["balance"] for user in user_data.users.values())
    
    await message.answer(
        f"📊 Статистика бота:\n"
        f"👥 Пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance} ⭐\n"
        f"💸 Пополнений: {sum(user['total_spent'] for user in user_data.users.values())} ⭐"
    )

# Обработчики callback'ов
@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎰 Главное меню Casino Bot",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "cases")
async def show_cases(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎁 Выберите кейс для открытия:\n\n"
        "🎒 БОМЖ КЕЙС - 30 ⭐\n"
        "▫️ Шансы выигрыша:\n"
        f"❤️ Сердечко/🧸 Мишка - {CASE_PRIZES['heart']['chance']}%\n"
        f"🌹 Роза - {CASE_PRIZES['rose']['chance']}%\n"
        f"💍 Кольцо - {CASE_PRIZES['ring']['chance']}%\n"
        f"📅 Desk Calendar - {CASE_PRIZES['calendar']['chance']}%",
        reply_markup=get_cases_keyboard()
    )

@router.callback_query(F.data == "open_bum_case")
async def open_bum_case(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    if user["balance"] < CASE_PRICE:
        await callback.answer("❌ Недостаточно звёзд для открытия кейса!", show_alert=True)
        return
    
    # Список призов с учетом вероятностей
    prizes_pool = []
    for prize_id, prize_info in CASE_PRIZES.items():
        count = int(prize_info["chance"] * 100)  # Умножаем на 100 для точности
        prizes_pool.extend([prize_id] * count)
    
    # Выбор приза
    chosen_prize_id = random.choice(prizes_pool)
    prize_info = CASE_PRIZES[chosen_prize_id]
    
    # Обновление баланса и инвентаря
    user_data.update_balance(user_id, -CASE_PRICE)
    user_data.add_to_inventory(user_id, prize_info["name"])
    
    # Обновление статистики
    user["total_spent"] += CASE_PRICE
    user["total_won"] += prize_info["value"]
    user_data.save_data()
    
    # Сообщение о выигрыше
    await callback.message.edit_text(
        f"🎉 Поздравляем! Вы открыли БОМЖ КЕЙС!\n\n"
        f"🎁 Ваш приз: {prize_info['name']}\n"
        f"💰 Стоимость: {prize_info['value']} ⭐\n\n"
        f"💎 Ваш баланс: {user['balance']} ⭐",
        reply_markup=get_cases_keyboard()
    )
    
    # Уведомление админа о большом выигрыше
    if prize_info["chance"] <= 5:  # Редкие выигрыши
        await callback.bot.send_message(
            ADMIN_CHAT_ID,
            f"🎰 Крупный выигрыш!\n"
            f"👤 Пользователь: {callback.from_user.full_name} (ID: {user_id})\n"
            f"🎁 Приз: {prize_info['name']}\n"
            f"📊 Шанс: {prize_info['chance']}%"
        )

@router.callback_query(F.data == "minigames")
async def show_minigames(callback: CallbackQuery):
    await callback.message.edit_text(
        "🎮 Выберите мини-игру:\n\n"
        "⚽️ Футбол - 8 ⭐ за попытку\n"
        "🏀 Баскетбол - 8 ⭐ за попытку\n"
        "🎯 Дартс - 8 ⭐ за попытку\n\n"
        "🎁 За попадание вы получаете:\n"
        "❤️ Сердечко или 🧸 Мишку!",
        reply_markup=get_minigames_keyboard()
    )

@router.callback_query(F.data.startswith("game_"))
async def play_minigame(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    game_type = callback.data.split("_")[1]
    
    if user["balance"] < GAME_PRICE:
        await callback.answer("❌ Недостаточно звёзд для игры!", show_alert=True)
        return
    
    # Обновление баланса
    user_data.update_balance(user_id, -GAME_PRICE)
    user["total_spent"] += GAME_PRICE
    
    # Симуляция игры (50% шанс на победу)
    if random.random() < 0.5:  # 50% шанс выиграть
        # Случайный приз
        prize = random.choice(["❤️ Сердечко", "🧸 Мишка"])
        prize_value = 5
        
        # Добавление в инвентарь
        user_data.add_to_inventory(user_id, prize)
        user["total_won"] += prize_value
        
        result_text = (
            f"🎯 Попадание! 🎯\n\n"
            f"🎮 Игра: {game_type.upper()}\n"
            f"🎁 Вы выиграли: {prize}\n"
            f"💰 Стоимость: {prize_value} ⭐\n\n"
            f"💎 Ваш баланс: {user['balance']} ⭐"
        )
    else:
        result_text = (
            f"❌ Промах!\n\n"
            f"🎮 Игра: {game_type.upper()}\n"
            f"💸 Потрачено: {GAME_PRICE} ⭐\n\n"
            f"💎 Ваш баланс: {user['balance']} ⭐\n"
            f"🔄 Попробуйте ещё раз!"
        )
    
    user_data.save_data()
    
    await callback.message.edit_text(
        result_text,
        reply_markup=get_minigames_keyboard()
    )

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    inventory_count = len(user["inventory"])
    
    await callback.message.edit_text(
        f"👤 Ваш профиль\n\n"
        f"🆔 ID: {user_id}\n"
        f"💎 Баланс: {user['balance']} ⭐\n"
        f"🎒 Инвентарь: {inventory_count} предметов\n"
        f"💰 Всего пополнено: {user['total_spent']} ⭐\n"
        f"🏆 Всего выиграно: {user['total_won']} ⭐",
        reply_markup=get_profile_keyboard()
    )

@router.callback_query(F.data == "deposit")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "💰 Пополнение баланса\n\n"
        "Выберите сумму для пополнения:\n"
        "⚠️ Внимание: Платежи обрабатываются через Telegram Stars",
        reply_markup=get_deposit_keyboard()
    )

@router.callback_query(F.data.startswith("deposit_"))
async def create_payment(callback: CallbackQuery):
    amounts = {
        "deposit_8": 8,
        "deposit_50": 50,
        "deposit_100": 100,
        "deposit_500": 500,
        "deposit_1000": 1000
    }
    
    amount = amounts.get(callback.data)
    if not amount:
        await callback.answer("❌ Ошибка выбора суммы", show_alert=True)
        return
    
    # Создание платежа через Telegram Stars
    prices = [LabeledPrice(label="Пополнение баланса", amount=amount * 100)]  # в копейках
    
    await callback.bot.send_invoice(
        chat_id=callback.from_user.id,
        title=f"Пополнение баланса на {amount} ⭐",
        description=f"Пополнение игрового баланса на {amount} Telegram Stars",
        payload=f"deposit_{amount}_{callback.from_user.id}",
        provider_token="",  # Токен будет настроен в хостинге
        currency="XTR",  # Telegram Stars
        prices=prices,
        start_parameter=f"deposit_{amount}",
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )
    await callback.answer()

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.bot.answer_pre_checkout_query(
        pre_checkout_query_id=pre_checkout_query.id,
        ok=True
    )

@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payment = message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith("deposit_"):
        parts = payload.split("_")
        if len(parts) >= 3:
            amount = int(parts[1])
            user_id = int(parts[2])
            
            # Обновление баланса
            user_data.update_balance(user_id, amount)
            user = user_data.get_user(user_id)
            user["total_spent"] += amount
            user_data.save_data()
            
            # Уведомление пользователя
            await message.answer(
                f"✅ Платёж успешно обработан!\n"
                f"💰 Зачислено: {amount} ⭐\n"
                f"💎 Текущий баланс: {user['balance']} ⭐\n\n"
                f"🎰 Приятной игры!",
                reply_markup=get_main_keyboard()
            )
            
            # Уведомление админа
            await message.bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 Новое пополнение!\n"
                f"👤 Пользователь: {message.from_user.full_name} (ID: {user_id})\n"
                f"💸 Сумма: {amount} ⭐\n"
                f"💳 ID платежа: {payment.telegram_payment_charge_id}"
            )

@router.callback_query(F.data == "inventory")
async def show_inventory(callback: CallbackQuery):
    user_id = callback.from_user.id
    inventory = user_data.get_inventory(user_id)
    
    if not inventory:
        await callback.message.edit_text(
            "🎒 Ваш инвентарь пуст\n\n"
            "🎁 Откройте кейсы или играйте в мини-игры, чтобы получить призы!",
            reply_markup=get_back_to_profile_keyboard()
        )
        return
    
    # Группировка предметов
    item_counts = {}
    for item in inventory:
        item_name = item["item"]
        item_counts[item_name] = item_counts.get(item_name, 0) + 1
    
    inventory_text = "🎒 Ваш инвентарь:\n\n"
    for item_name, count in item_counts.items():
        inventory_text += f"{item_name} ×{count}\n"
    
    await callback.message.edit_text(
        inventory_text,
        reply_markup=get_back_to_profile_keyboard()
    )

@router.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    # Статистика по призам
    prize_stats = {}
    for item in user["inventory"]:
        item_name = item["item"]
        prize_stats[item_name] = prize_stats.get(item_name, 0) + 1
    
    stats_text = f"📊 Ваша статистика:\n\n"
    stats_text += f"🎁 Всего предметов: {len(user['inventory'])}\n"
    stats_text += f"💰 Пополнено: {user['total_spent']} ⭐\n"
    stats_text += f"🏆 Выиграно: {user['total_won']} ⭐\n"
    
    if prize_stats:
        stats_text += "\n🎯 Статистика призов:\n"
        for prize, count in prize_stats.items():
            stats_text += f"▫️ {prize}: {count} шт.\n"
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_back_to_profile_keyboard()
    )

@router.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    help_text = (
        "❓ Помощь по боту:\n\n"
        "🎰 Этот бот - игровая платформа с кейсами и мини-играми\n\n"
        "🎁 **Кейсы:**\n"
        "▫️ Открывайте кейсы, чтобы получать призы\n"
        "▫️ Каждый кейс имеет разные шансы на выигрыш\n\n"
        "🎮 **Мини-игры:**\n"
        "▫️ Играйте в классические игры Telegram\n"
        "▫️ За победу получайте призы\n\n"
        "💰 **Пополнение баланса:**\n"
        "▫️ Баланс пополняется через Telegram Stars\n"
        "▫️ Доступны суммы от 8 до 1000 звёзд\n\n"
        "📞 **Поддержка:**\n"
        "▫️ По вопросам пишите @ваш_админ"
    )
    
    await callback.message.edit_text(
        help_text,
        reply_markup=get_main_keyboard()
    )

# Основная функция
async def main():
    # Токен бота будет получен из переменных окружения
    import os
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    if not BOT_TOKEN:
        logger.error("Не задан BOT_TOKEN в переменных окружения!")
        return
    
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
