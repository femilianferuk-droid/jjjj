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
    SuccessfulPayment, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Роутер
router = Router()

# Состояния FSM
class UserForm(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_deposit_confirmation = State()
    waiting_for_withdraw_item = State()
    waiting_for_withdraw_quantity = State()

class AdminForm(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_balance_change = State()
    waiting_for_balance_type = State()
    waiting_for_broadcast = State()

# Конфигурация
ADMIN_CHAT_ID = 7973988177
CASE_PRICE = 30
GAME_PRICE = 8
MIN_DEPOSIT = 8
MAX_DEPOSIT = 1000

# Призы для кейса с их стоимостью в звездах
CASE_PRIZES = {
    "heart": {"name": "❤️ Сердечко", "chance": 80.0, "value": 15, "emoji": "❤️"},
    "bear": {"name": "🧸 Мишка", "chance": 80.0, "value": 15, "emoji": "🧸"},
    "rose": {"name": "🌹 Роза", "chance": 15.0, "value": 25, "emoji": "🌹"},
    "ring": {"name": "💍 Кольцо", "chance": 4.99, "value": 100, "emoji": "💍"},
    "calendar": {"name": "📅 Desk Calendar", "chance": 0.01, "value": 300, "emoji": "📅"}
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
        user_id_str = str(user_id)
        if user_id_str not in self.users:
            self.users[user_id_str] = {
                "balance": 0,
                "inventory": [],
                "total_spent": 0,
                "total_won": 0,
                "total_deposited": 0,
                "joined_date": datetime.now().isoformat(),
                "username": "",
                "full_name": "",
                "withdrawn_items": []
            }
        return self.users[user_id_str]
    
    def update_balance(self, user_id: int, amount: int, update_stats: bool = False):
        user = self.get_user(user_id)
        user["balance"] += amount
        
        if update_stats:
            if amount > 0:
                user["total_deposited"] += amount
            elif amount < 0:
                user["total_spent"] += abs(amount)
        
        self.save_data()
        return user["balance"]
    
    def add_to_inventory(self, user_id: int, item: str):
        user = self.get_user(user_id)
        user["inventory"].append({
            "item": item,
            "date": datetime.now().isoformat(),
            "withdrawn": False
        })
        self.save_data()
    
    def get_inventory(self, user_id: int) -> List:
        user = self.get_user(user_id)
        return user["inventory"]
    
    def get_inventory_grouped(self, user_id: int) -> Dict:
        user = self.get_user(user_id)
        inventory = user["inventory"]
        grouped = {}
        
        for item in inventory:
            if not item.get("withdrawn", False):
                item_name = item["item"]
                if item_name in grouped:
                    grouped[item_name]["count"] += 1
                    grouped[item_name]["items"].append(item)
                else:
                    grouped[item_name] = {
                        "count": 1,
                        "items": [item],
                        "emoji": self.get_item_emoji(item_name)
                    }
        
        return grouped
    
    def get_item_emoji(self, item_name: str) -> str:
        for prize_id, prize_info in CASE_PRIZES.items():
            if prize_info["name"] == item_name:
                return prize_info["emoji"]
        return "🎁"
    
    def withdraw_item(self, user_id: int, item_name: str, quantity: int = 1) -> List:
        user = self.get_user(user_id)
        inventory = user["inventory"]
        withdrawn_items = []
        
        count = 0
        for item in inventory:
            if item["item"] == item_name and not item.get("withdrawn", False):
                item["withdrawn"] = True
                withdrawn_items.append(item)
                count += 1
                if count >= quantity:
                    break
        
        self.save_data()
        return withdrawn_items
    
    def update_user_info(self, user_id: int, username: str, full_name: str):
        user = self.get_user(user_id)
        user["username"] = username
        user["full_name"] = full_name
        self.save_data()
    
    def get_all_users(self) -> Dict:
        return self.users
    
    def set_balance(self, user_id: int, new_balance: int):
        user = self.get_user(user_id)
        old_balance = user["balance"]
        user["balance"] = new_balance
        self.save_data()
        return old_balance, new_balance

# Инициализация хранилища
user_data = UserData()

# Стилизованные клавиатуры с синим дизайном
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="🎮 Мини-игры", callback_data="minigames")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cases_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎒 Открыть БОМЖ КЕЙС (30 ⭐)", callback_data="open_bum_case")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_minigames_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚽️ Играть в футбол (8 ⭐)", callback_data="game_football")],
        [InlineKeyboardButton(text="🏀 Играть в баскетбол (8 ⭐)", callback_data="game_basketball")],
        [InlineKeyboardButton(text="🎯 Играть в дартс (8 ⭐)", callback_data="game_darts")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_profile_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton(text="🎒 Мой инвентарь", callback_data="inventory")],
        [InlineKeyboardButton(text="📊 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_deposit_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="💎 8 ⭐", callback_data="deposit_8"),
         InlineKeyboardButton(text="💎 50 ⭐", callback_data="deposit_50")],
        [InlineKeyboardButton(text="💎 100 ⭐", callback_data="deposit_100"),
         InlineKeyboardButton(text="💎 500 ⭐", callback_data="deposit_500")],
        [InlineKeyboardButton(text="💎 1000 ⭐", callback_data="deposit_1000")],
        [InlineKeyboardButton(text="✏️ Своя сумма", callback_data="custom_deposit")],
        [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_inventory_keyboard(inventory_items: Dict) -> InlineKeyboardMarkup:
    keyboard = []
    for item_name, item_data in inventory_items.items():
        emoji = item_data["emoji"]
        count = item_data["count"]
        keyboard.append([InlineKeyboardButton(
            text=f"{emoji} {item_name} ×{count}", 
            callback_data=f"withdraw_{item_name}"
        )])
    
    keyboard.append([InlineKeyboardButton(text="🔙 В профиль", callback_data="profile")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_withdraw_quantity_keyboard(item_name: str, max_quantity: int) -> InlineKeyboardMarkup:
    keyboard = []
    
    # Быстрые кнопки количества
    if max_quantity >= 1:
        keyboard.append([InlineKeyboardButton(text="1 шт.", callback_data=f"withdraw_qty_{item_name}_1")])
    if max_quantity >= 3:
        keyboard.append([InlineKeyboardButton(text="3 шт.", callback_data=f"withdraw_qty_{item_name}_3")])
    if max_quantity >= 5:
        keyboard.append([InlineKeyboardButton(text="5 шт.", callback_data=f"withdraw_qty_{item_name}_5")])
    if max_quantity >= 10:
        keyboard.append([InlineKeyboardButton(text="10 шт.", callback_data=f"withdraw_qty_{item_name}_10")])
    
    keyboard.append([InlineKeyboardButton(text="✏️ Другое количество", callback_data=f"custom_qty_{item_name}")])
    keyboard.append([InlineKeyboardButton(text="🔙 В инвентарь", callback_data="inventory")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_keyboard(target: str = "main_menu") -> InlineKeyboardMarkup:
    text = "🔙 В меню" if target == "main_menu" else f"🔙 Назад"
    keyboard = [[InlineKeyboardButton(text=text, callback_data=target)]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [[KeyboardButton(text="❌ Отмена")]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика бота", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👤 Найти пользователя", callback_data="admin_find_user")],
        [InlineKeyboardButton(text="💰 Изменить баланс", callback_data="admin_change_balance")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📥 Экспорт данных", callback_data="admin_export")],
        [InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_back_keyboard() -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="🔙 Админ панель", callback_data="admin_panel")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_balance_change_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="➕ Пополнить", callback_data="balance_add"),
            InlineKeyboardButton(text="➖ Списать", callback_data="balance_subtract")
        ],
        [InlineKeyboardButton(text="🎯 Установить точную сумму", callback_data="balance_set_exact")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Стилизованные сообщения с синим дизайном
def format_message(text: str, emoji: str = "💎") -> str:
    return f"{emoji} {text}"

def format_header(text: str) -> str:
    return f"🔷 *{text}*\n"

def format_success(text: str) -> str:
    return f"✅ {text}"

def format_error(text: str) -> str:
    return f"❌ {text}"

def format_info(text: str) -> str:
    return f"ℹ️ {text}"

# Обработчики команд
@router.message(CommandStart())
async def cmd_start(message: Message):
    # Обновление информации о пользователе
    user_data.update_user_info(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name
    )
    
    await message.answer(
        "🎰 *Добро пожаловать в Blue Casino Bot!*\n\n"
        "✨ Здесь вы можете открывать кейсы и играть в мини-игры!\n\n"
        "💎 Для начала пополните баланс звёздами.",
        parse_mode="Markdown",
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
        await message.answer("⛔ У вас нет доступа к админ-панели!")
        return
    
    await message.answer(
        "🛠️ *Админ-панель Blue Casino*",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

# Обработчики callback'ов
@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    if callback.from_user.id == ADMIN_CHAT_ID:
        await callback.message.edit_text(
            "🎰 *Главное меню Blue Casino*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )
    else:
        await callback.message.edit_text(
            "🎰 *Главное меню Blue Casino*",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

@router.callback_query(F.data == "cases")
async def show_cases(callback: CallbackQuery):
    await callback.message.edit_text(
        format_header("Открытие кейсов") +
        "\n🎁 *Доступные кейсы:*\n\n"
        "🎒 *БОМЖ КЕЙС* - 30 ⭐\n"
        "▫️ Содержит различные ценные призы!\n"
        "▫️ Попробуй удачу и получи дорогой подарок!\n\n"
        "🔹 *Ценности призов в звездах:*\n"
        "❤️ Сердечко/🧸 Мишка - 15 ⭐\n"
        "🌹 Роза - 25 ⭐\n"
        "💍 Кольцо - 100 ⭐\n"
        "📅 Desk Calendar - 300 ⭐",
        parse_mode="Markdown",
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
        count = int(prize_info["chance"] * 100)
        prizes_pool.extend([prize_id] * count)
    
    # Выбор приза
    chosen_prize_id = random.choice(prizes_pool)
    prize_info = CASE_PRIZES[chosen_prize_id]
    
    # Обновление баланса и инвентаря
    user_data.update_balance(user_id, -CASE_PRICE, update_stats=True)
    user_data.add_to_inventory(user_id, prize_info["name"])
    
    # Обновление статистики
    user["total_won"] += prize_info["value"]
    user_data.save_data()
    
    # Стилизованное сообщение о выигрыше
    prize_value_text = f"💎 Стоимость: {prize_info['value']} ⭐"
    if prize_info["value"] >= 100:
        prize_value_text = f"🔥 Стоимость: {prize_info['value']} ⭐ (КРУПНЫЙ ВЫИГРЫШ!)"
    
    await callback.message.edit_text(
        format_header("🎉 ПОЗДРАВЛЯЕМ!") +
        f"\n🎁 *Вы открыли БОМЖ КЕЙС!*\n\n"
        f"{prize_info['emoji']} *Ваш приз:* {prize_info['name']}\n"
        f"{prize_value_text}\n\n"
        f"💰 *Ваш баланс:* {user['balance']} ⭐",
        parse_mode="Markdown",
        reply_markup=get_cases_keyboard()
    )
    
    # Уведомление админа о большом выигрыше
    if prize_info["chance"] <= 5:
        await callback.bot.send_message(
            ADMIN_CHAT_ID,
            f"🎰 *Крупный выигрыш!*\n"
            f"👤 Пользователь: {callback.from_user.full_name} (ID: {user_id})\n"
            f"🎁 Приз: {prize_info['name']}\n"
            f"💎 Стоимость: {prize_info['value']} ⭐",
            parse_mode="Markdown"
        )

@router.callback_query(F.data == "minigames")
async def show_minigames(callback: CallbackQuery):
    await callback.message.edit_text(
        format_header("Мини-игры") +
        "\n🎮 *Доступные игры:*\n\n"
        "⚽️ *Футбол* - 8 ⭐ за попытку\n"
        "🏀 *Баскетбол* - 8 ⭐ за попытку\n"
        "🎯 *Дартс* - 8 ⭐ за попытку\n\n"
        "🎁 *За попадание вы получаете:*\n"
        "❤️ Сердечко или 🧸 Мишку (15 ⭐ каждый)!",
        parse_mode="Markdown",
        reply_markup=get_minigames_keyboard()
    )

@router.callback_query(F.data.startswith("game_"))
async def play_minigame(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    game_type = callback.data.split("_")[1]
    
    game_names = {
        "football": "⚽️ Футбол",
        "basketball": "🏀 Баскетбол", 
        "darts": "🎯 Дартс"
    }
    game_name = game_names.get(game_type, game_type.upper())
    
    if user["balance"] < GAME_PRICE:
        await callback.answer("❌ Недостаточно звёзд для игры!", show_alert=True)
        return
    
    # Обновление баланса
    user_data.update_balance(user_id, -GAME_PRICE, update_stats=True)
    
    # Симуляция игры (50% шанс на победу)
    if random.random() < 0.5:
        prize = random.choice(["❤️ Сердечко", "🧸 Мишка"])
        prize_value = 15
        
        user_data.add_to_inventory(user_id, prize)
        user["total_won"] += prize_value
        
        result_text = (
            format_header("🎯 ПОПАДАНИЕ!") +
            f"\n🎮 *Игра:* {game_name}\n"
            f"🎁 *Вы выиграли:* {prize}\n"
            f"💎 *Стоимость:* {prize_value} ⭐\n\n"
            f"💰 *Ваш баланс:* {user['balance']} ⭐"
        )
    else:
        result_text = (
            format_header("❌ ПРОМАХ") +
            f"\n🎮 *Игра:* {game_name}\n"
            f"💸 *Потрачено:* {GAME_PRICE} ⭐\n\n"
            f"💰 *Ваш баланс:* {user['balance']} ⭐\n"
            f"🔄 *Попробуйте ещё раз!*"
        )
    
    user_data.save_data()
    
    await callback.message.edit_text(
        result_text,
        parse_mode="Markdown",
        reply_markup=get_minigames_keyboard()
    )

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    inventory_count = len([item for item in user["inventory"] if not item.get("withdrawn", False)])
    
    await callback.message.edit_text(
        format_header("Ваш профиль") +
        f"\n🆔 *ID:* `{user_id}`\n"
        f"👤 *Имя:* {user.get('full_name', 'Не указано')}\n"
        f"💎 *Баланс:* {user['balance']} ⭐\n"
        f"🎒 *Инвентарь:* {inventory_count} предметов\n"
        f"💰 *Всего пополнено:* {user['total_deposited']} ⭐\n"
        f"🏆 *Всего выиграно:* {user['total_won']} ⭐",
        parse_mode="Markdown",
        reply_markup=get_profile_keyboard()
    )

@router.callback_query(F.data == "deposit")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        format_header("Пополнение баланса") +
        f"\n💰 *Выберите сумму для пополнения*\n"
        f"(от {MIN_DEPOSIT} до {MAX_DEPOSIT} звёзд):\n\n"
        f"⚠️ *Внимание:* Платежи обрабатываются через Telegram Stars",
        parse_mode="Markdown",
        reply_markup=get_deposit_keyboard()
    )

@router.callback_query(F.data == "custom_deposit")
async def custom_deposit(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        format_header("Своя сумма") +
        f"\n✏️ *Введите сумму для пополнения*\n"
        f"(от {MIN_DEPOSIT} до {MAX_DEPOSIT} звёзд):\n\n"
        f"*Пример:* 150",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("deposit")
    )
    
    await state.set_state(UserForm.waiting_for_deposit_amount)

@router.message(UserForm.waiting_for_deposit_amount)
async def process_custom_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        
        if amount < MIN_DEPOSIT:
            await message.answer(
                format_error(f"Сумма должна быть не меньше {MIN_DEPOSIT} звёзд!") +
                "\n\nПопробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        if amount > MAX_DEPOSIT:
            await message.answer(
                format_error(f"Сумма должна быть не больше {MAX_DEPOSIT} звёзд!") +
                "\n\nПопробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.update_data(deposit_amount=amount)
        await state.set_state(UserForm.waiting_for_deposit_confirmation)
        
        await message.answer(
            format_success(f"Сумма {amount} ⭐ принята!") +
            "\n\n*Подтвердите создание платежа:*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_custom_deposit")],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="deposit")]
                ]
            )
        )
        
    except ValueError:
        await message.answer(
            format_error("Пожалуйста, введите число!") +
            f"\n\n*Пример:* 150 (от {MIN_DEPOSIT} до {MAX_DEPOSIT}):",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        await message.answer(
            format_error(f"Ошибка: {str(e)}") +
            "\nПопробуйте ещё раз:",
            reply_markup=get_cancel_keyboard()
        )

@router.callback_query(F.data == "confirm_custom_deposit", UserForm.waiting_for_deposit_confirmation)
async def confirm_custom_deposit(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get("deposit_amount")
    
    if not amount:
        await callback.answer("❌ Ошибка: сумма не найдена", show_alert=True)
        await state.clear()
        return
    
    # Правильный расчет суммы для платежа (1:1)
    price_amount = amount
    
    # Создание платежа
    prices = [LabeledPrice(label=f"Пополнение баланса на {amount} ⭐", amount=price_amount)]
    
    try:
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
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка создания платежа: {str(e)}")
    
    await state.clear()

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
    
    # Правильный расчет суммы для платежа (1:1)
    price_amount = amount
    
    # Создание платежа
    prices = [LabeledPrice(label=f"Пополнение баланса на {amount} ⭐", amount=price_amount)]
    
    try:
        await callback.bot.send_invoice(
            chat_id=callback.from_user.id,
            title=f"Пополнение баланса на {amount} ⭐",
            description=f"Пополнение игрового баланса на {amount} Telegram Stars",
            payload=f"deposit_{amount}_{callback.from_user.id}",
            provider_token="",  # Токен будет настроен в хостинге
            currency="XTR",
            prices=prices,
            start_parameter=f"deposit_{amount}",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            is_flexible=False
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка создания платежа: {str(e)}")
    
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
            new_balance = user_data.update_balance(user_id, amount, update_stats=True)
            
            # Уведомление пользователя
            await message.answer(
                format_success("Платёж успешно обработан!") +
                f"\n\n💰 *Зачислено:* {amount} ⭐\n"
                f"💎 *Текущий баланс:* {new_balance} ⭐\n\n"
                f"🎰 *Приятной игры!*",
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
            )
            
            # Уведомление админа
            await message.bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 *Новое пополнение!*\n"
                f"👤 Пользователь: {message.from_user.full_name} (ID: {user_id})\n"
                f"💸 Сумма: {amount} ⭐\n"
                f"💳 ID платежа: {payment.telegram_payment_charge_id}\n"
                f"💎 Новый баланс: {new_balance} ⭐",
                parse_mode="Markdown"
            )

@router.callback_query(F.data == "inventory")
async def show_inventory(callback: CallbackQuery):
    user_id = callback.from_user.id
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if not inventory_grouped:
        await callback.message.edit_text(
            format_header("Мой инвентарь") +
            "\n🎒 *Ваш инвентарь пуст*\n\n"
            "🎁 Откройте кейсы или играйте в мини-игры, чтобы получить призы!",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard("profile")
        )
        return
    
    inventory_text = format_header("Мой инвентарь") + "\n🎒 *Ваши предметы:*\n\n"
    
    total_value = 0
    for item_name, item_data in inventory_grouped.items():
        count = item_data["count"]
        emoji = item_data["emoji"]
        
        # Находим стоимость предмета
        item_value = 0
        for prize_id, prize_info in CASE_PRIZES.items():
            if prize_info["name"] == item_name:
                item_value = prize_info["value"]
                break
        
        total_value += item_value * count
        
        inventory_text += f"{emoji} *{item_name}* ×{count}\n"
        inventory_text += f"   💰 Стоимость: {item_value} ⭐ за шт.\n"
        inventory_text += f"   📦 Всего: {item_value * count} ⭐\n\n"
    
    inventory_text += f"💰 *Общая стоимость инвентаря:* {total_value} ⭐\n\n"
    inventory_text += "👉 *Нажмите на предмет, чтобы вывести его*"
    
    await callback.message.edit_text(
        inventory_text,
        parse_mode="Markdown",
        reply_markup=get_inventory_keyboard(inventory_grouped)
    )

@router.callback_query(F.data.startswith("withdraw_"))
async def start_withdraw_item(callback: CallbackQuery, state: FSMContext):
    # Проверяем, не является ли это callback'ом с количеством
    if callback.data.startswith("withdraw_qty_"):
        return
    
    # Это выбор предмета для вывода
    item_name = callback.data.replace("withdraw_", "")
    
    user_id = callback.from_user.id
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if item_name not in inventory_grouped:
        await callback.answer("❌ Предмет не найден в инвентаре!", show_alert=True)
        return
    
    max_quantity = inventory_grouped[item_name]["count"]
    
    # Находим эмодзи для предмета
    item_emoji = ""
    for prize_id, prize_info in CASE_PRIZES.items():
        if prize_info["name"] == item_name:
            item_emoji = prize_info["emoji"]
            break
    
    await state.update_data(withdraw_item_name=item_name)
    await state.set_state(UserForm.waiting_for_withdraw_item)
    
    await callback.message.edit_text(
        format_header("Вывод предмета") +
        f"\n{item_emoji} *Выбран предмет:* {item_name}\n"
        f"📦 *Доступно в инвентаре:* {max_quantity} шт.\n\n"
        f"*Выберите количество для вывода:*",
        parse_mode="Markdown",
        reply_markup=get_withdraw_quantity_keyboard(item_name, max_quantity)
    )

@router.callback_query(F.data.startswith("withdraw_qty_"))
async def withdraw_with_quantity(callback: CallbackQuery, state: FSMContext):
    # Формат: withdraw_qty_ITEM_NAME_QUANTITY
    parts = callback.data.split("_")
    if len(parts) >= 4:
        item_name = "_".join(parts[2:-1])  # На случай, если в названии предмета есть подчеркивания
        quantity = int(parts[-1])
        
        await process_withdraw_item(callback, item_name, quantity, state)

@router.callback_query(F.data.startswith("custom_qty_"))
async def custom_withdraw_quantity(callback: CallbackQuery, state: FSMContext):
    item_name = callback.data.replace("custom_qty_", "")
    
    user_id = callback.from_user.id
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if item_name not in inventory_grouped:
        await callback.answer("❌ Предмет не найден в инвентаре!", show_alert=True)
        return
    
    max_quantity = inventory_grouped[item_name]["count"]
    
    await state.update_data(withdraw_item_name=item_name)
    await state.set_state(UserForm.waiting_for_withdraw_quantity)
    
    await callback.message.edit_text(
        format_header("Свое количество") +
        f"\n✏️ *Введите количество для вывода*\n"
        f"(от 1 до {max_quantity} шт.):\n\n"
        f"*Пример:* 3",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("inventory")
    )

@router.message(UserForm.waiting_for_withdraw_quantity)
async def process_custom_quantity(message: Message, state: FSMContext):
    try:
        quantity = int(message.text.strip())
        
        data = await state.get_data()
        item_name = data.get("withdraw_item_name")
        
        if not item_name:
            await message.answer("❌ Ошибка: предмет не найден")
            await state.clear()
            return
        
        user_id = message.from_user.id
        inventory_grouped = user_data.get_inventory_grouped(user_id)
        
        if item_name not in inventory_grouped:
            await message.answer("❌ Предмет не найден в инвентаре!")
            await state.clear()
            return
        
        max_quantity = inventory_grouped[item_name]["count"]
        
        if quantity < 1:
            await message.answer("❌ Количество должно быть не меньше 1!")
            return
        
        if quantity > max_quantity:
            await message.answer(f"❌ У вас есть только {max_quantity} шт. этого предмета!")
            return
        
        # Выполняем вывод
        await process_withdraw_item_message(message, item_name, quantity, state)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        await state.clear()

async def process_withdraw_item(callback: CallbackQuery, item_name: str, quantity: int, state: FSMContext):
    user_id = callback.from_user.id
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if item_name not in inventory_grouped:
        await callback.answer("❌ Предмет не найден в инвентаре!", show_alert=True)
        return
    
    max_quantity = inventory_grouped[item_name]["count"]
    
    if quantity > max_quantity:
        await callback.answer(f"❌ У вас есть только {max_quantity} шт. этого предмета!", show_alert=True)
        return
    
    # Выполняем вывод
    withdrawn_items = user_data.withdraw_item(user_id, item_name, quantity)
    
    # Находим эмодзи и стоимость предмета
    item_emoji = ""
    item_value = 0
    for prize_id, prize_info in CASE_PRIZES.items():
        if prize_info["name"] == item_name:
            item_emoji = prize_info["emoji"]
            item_value = prize_info["value"]
            break
    
    # Отправляем предметы пользователю
    for i, item in enumerate(withdrawn_items):
        # Отправляем стикер или текст в зависимости от предмета
        gift_message = f"{item_emoji} *{item_name}*"
        
        if i == 0:  # Первое сообщение
            await callback.bot.send_message(
                user_id,
                format_success(f"Предмет успешно выведен!") +
                f"\n\n{item_emoji} *{item_name}*\n"
                f"📦 Количество: {quantity} шт.\n"
                f"💰 Общая стоимость: {item_value * quantity} ⭐\n\n"
                f"🎁 *Ваш подарок отправлен в чат!*",
                parse_mode="Markdown"
            )
        
        # Отправляем сам "подарок" - в реальном боте здесь можно отправить стикер или другое медиа
        await callback.bot.send_message(
            user_id,
            f"🎁 *Ваш подарок #{i+1}:*\n{gift_message}",
            parse_mode="Markdown"
        )
    
    # Обновляем сообщение с инвентарем
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if not inventory_grouped:
        await callback.message.edit_text(
            format_header("Мой инвентарь") +
            "\n🎒 *Ваш инвентарь пуст*\n\n"
            "🎁 Откройте кейсы или играйте в мини-игры, чтобы получить призы!",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard("profile")
        )
    else:
        inventory_text = format_header("Мой инвентарь") + "\n🎒 *Ваши предметы:*\n\n"
        
        total_value = 0
        for item_name_inv, item_data in inventory_grouped.items():
            count = item_data["count"]
            emoji = item_data["emoji"]
            
            # Находим стоимость предмета
            item_value_inv = 0
            for prize_id, prize_info in CASE_PRIZES.items():
                if prize_info["name"] == item_name_inv:
                    item_value_inv = prize_info["value"]
                    break
            
            total_value += item_value_inv * count
            
            inventory_text += f"{emoji} *{item_name_inv}* ×{count}\n"
            inventory_text += f"   💰 Стоимость: {item_value_inv} ⭐ за шт.\n"
            inventory_text += f"   📦 Всего: {item_value_inv * count} ⭐\n\n"
        
        inventory_text += f"💰 *Общая стоимость инвентаря:* {total_value} ⭐\n\n"
        inventory_text += "👉 *Нажмите на предмет, чтобы вывести его*"
        
        await callback.message.edit_text(
            inventory_text,
            parse_mode="Markdown",
            reply_markup=get_inventory_keyboard(inventory_grouped)
        )
    
    await state.clear()

async def process_withdraw_item_message(message: Message, item_name: str, quantity: int, state: FSMContext):
    user_id = message.from_user.id
    withdrawn_items = user_data.withdraw_item(user_id, item_name, quantity)
    
    # Находим эмодзи и стоимость предмета
    item_emoji = ""
    item_value = 0
    for prize_id, prize_info in CASE_PRIZES.items():
        if prize_info["name"] == item_name:
            item_emoji = prize_info["emoji"]
            item_value = prize_info["value"]
            break
    
    # Отправляем предметы пользователю
    for i, item in enumerate(withdrawn_items):
        gift_message = f"{item_emoji} *{item_name}*"
        
        if i == 0:
            await message.answer(
                format_success(f"Предмет успешно выведен!") +
                f"\n\n{item_emoji} *{item_name}*\n"
                f"📦 Количество: {quantity} шт.\n"
                f"💰 Общая стоимость: {item_value * quantity} ⭐\n\n"
                f"🎁 *Ваш подарок отправлен в чат!*",
                parse_mode="Markdown"
            )
        
        # Отправляем сам "подарок"
        await message.answer(
            f"🎁 *Ваш подарок #{i+1}:*\n{gift_message}",
            parse_mode="Markdown"
        )
    
    # Показываем обновленный инвентарь
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    if not inventory_grouped:
        await message.answer(
            format_header("Мой инвентарь") +
            "\n🎒 *Ваш инвентарь пуст*\n\n"
            "🎁 Откройте кейсы или играйте в мини-игры, чтобы получить призы!",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard("profile")
        )
    else:
        await message.answer(
            "✅ Вывод завершен!",
            reply_markup=get_inventory_keyboard(inventory_grouped)
        )
    
    await state.clear()

@router.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    inventory_grouped = user_data.get_inventory_grouped(user_id)
    
    # Подсчитываем статистику по предметам
    prize_stats = {}
    total_inventory_value = 0
    
    for item_name, item_data in inventory_grouped.items():
        count = item_data["count"]
        
        # Находим стоимость предмета
        item_value = 0
        for prize_id, prize_info in CASE_PRIZES.items():
            if prize_info["name"] == item_name:
                item_value = prize_info["value"]
                break
        
        total_inventory_value += item_value * count
        prize_stats[item_name] = count
    
    stats_text = format_header("Моя статистика") + "\n"
    stats_text += f"🎁 *Всего предметов:* {sum(prize_stats.values())}\n"
    stats_text += f"💰 *Пополнено:* {user['total_deposited']} ⭐\n"
    stats_text += f"🏆 *Выиграно:* {user['total_won']} ⭐\n"
    stats_text += f"💎 *Текущий баланс:* {user['balance']} ⭐\n"
    stats_text += f"📦 *Стоимость инвентаря:* {total_inventory_value} ⭐\n"
    stats_text += f"📅 *Дата регистрации:* {user['joined_date'][:10]}\n"
    
    if prize_stats:
        stats_text += "\n🎯 *Статистика призов:*\n"
        for prize, count in prize_stats.items():
            # Находим эмодзи для предмета
            item_emoji = ""
            for prize_id, prize_info in CASE_PRIZES.items():
                if prize_info["name"] == prize:
                    item_emoji = prize_info["emoji"]
                    break
            
            stats_text += f"▫️ {item_emoji} {prize}: {count} шт.\n"
    
    await callback.message.edit_text(
        stats_text,
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("profile")
    )

# Админ обработчики (убрана автоподгрузка при /start для админа)
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🛠️ *Админ-панель Blue Casino*",
        parse_mode="Markdown",
        reply_markup=get_admin_keyboard()
    )

# Остальной код админ-панели остается таким же, как в предыдущей версии
# [Админ-обработчики из предыдущего кода остаются без изменений]

# Основная функция
async def main():
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
