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
                "full_name": ""
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
            "date": datetime.now().isoformat()
        })
        self.save_data()
    
    def get_inventory(self, user_id: int) -> List:
        user = self.get_user(user_id)
        return user["inventory"]
    
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

# Основные клавиатуры
def get_main_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="🎁 Кейсы", callback_data="cases")],
        [InlineKeyboardButton(text="🎮 Мини-игры", callback_data="minigames")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")]
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
        [InlineKeyboardButton(text="📝 Своя сумма", callback_data="custom_deposit")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="profile")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_back_keyboard(target: str = "main_menu") -> InlineKeyboardMarkup:
    keyboard = [[InlineKeyboardButton(text="🔙 Назад", callback_data=target)]]
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

# Обработчики команд
@router.message(CommandStart())
async def cmd_start(message: Message):
    # Обновление информации о пользователе
    user_data.update_user_info(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name
    )
    
    if message.from_user.id == ADMIN_CHAT_ID:
        # Админ меню
        await message.answer(
            "🛠️ Добро пожаловать в админ-панель!",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "🎰 Добро пожаловать в Casino Bot!\n\n"
            "✨ Здесь вы можете открывать кейсы и играть в мини-игры!\n\n"
            "💎 Для начала пополните баланс звёздами.",
            reply_markup=get_main_keyboard()
        )
        # Уведомление админа
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
        "🛠️ Админ-панель",
        reply_markup=get_admin_keyboard()
    )

# Обработчики callback'ов
@router.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    if callback.from_user.id == ADMIN_CHAT_ID:
        await callback.message.edit_text(
            "🛠️ Админ-панель",
            reply_markup=get_admin_keyboard()
        )
    else:
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
    
    # Сообщение о выигрыше
    await callback.message.edit_text(
        f"🎉 Поздравляем! Вы открыли БОМЖ КЕЙС!\n\n"
        f"🎁 Ваш приз: {prize_info['name']}\n"
        f"💰 Стоимость: {prize_info['value']} ⭐\n\n"
        f"💎 Ваш баланс: {user['balance']} ⭐",
        reply_markup=get_cases_keyboard()
    )
    
    # Уведомление админа о большом выигрыше
    if prize_info["chance"] <= 5:
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
    user_data.update_balance(user_id, -GAME_PRICE, update_stats=True)
    
    # Симуляция игры (50% шанс на победу)
    if random.random() < 0.5:
        prize = random.choice(["❤️ Сердечко", "🧸 Мишка"])
        prize_value = 5
        
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
        f"👤 Имя: {user.get('full_name', 'Не указано')}\n"
        f"💎 Баланс: {user['balance']} ⭐\n"
        f"🎒 Инвентарь: {inventory_count} предметов\n"
        f"💰 Всего пополнено: {user['total_deposited']} ⭐\n"
        f"🏆 Всего выиграно: {user['total_won']} ⭐",
        reply_markup=get_profile_keyboard()
    )

@router.callback_query(F.data == "deposit")
async def deposit_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        f"💰 Пополнение баланса\n\n"
        f"Выберите сумму для пополнения (от {MIN_DEPOSIT} до {MAX_DEPOSIT} звёзд):\n"
        f"⚠️ Внимание: Платежи обрабатываются через Telegram Stars",
        reply_markup=get_deposit_keyboard()
    )

@router.callback_query(F.data == "custom_deposit")
async def custom_deposit(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"📝 Введите сумму для пополнения (от {MIN_DEPOSIT} до {MAX_DEPOSIT} звёзд):\n\n"
        f"Пример: 150",
        reply_markup=get_back_keyboard("deposit")
    )
    
    await state.set_state(UserForm.waiting_for_deposit_amount)

@router.message(UserForm.waiting_for_deposit_amount)
async def process_custom_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        
        if amount < MIN_DEPOSIT:
            await message.answer(
                f"❌ Сумма должна быть не меньше {MIN_DEPOSIT} звёзд!\n"
                f"Попробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        if amount > MAX_DEPOSIT:
            await message.answer(
                f"❌ Сумма должна быть не больше {MAX_DEPOSIT} звёзд!\n"
                f"Попробуйте ещё раз:",
                reply_markup=get_cancel_keyboard()
            )
            return
        
        await state.update_data(deposit_amount=amount)
        await state.set_state(UserForm.waiting_for_deposit_confirmation)
        
        await message.answer(
            f"✅ Сумма {amount} ⭐ принята!\n\n"
            f"Подтвердите создание платежа:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_custom_deposit")],
                    [InlineKeyboardButton(text="❌ Отменить", callback_data="deposit")]
                ]
            )
        )
        
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, введите число!\n"
            f"Пример: 150 (от {MIN_DEPOSIT} до {MAX_DEPOSIT}):",
            reply_markup=get_cancel_keyboard()
        )
    except Exception as e:
        await message.answer(
            f"❌ Ошибка: {str(e)}\nПопробуйте ещё раз:",
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
    
    # ИСПРАВЛЕНО: Правильный расчет суммы для платежа
    # Telegram Stars использует минимальную единицу как копейки (1 звезда = 100 минимальных единиц)
    # Но в нашем случае мы хотим 1:1, поэтому просто используем amount
    price_amount = amount  # 1 звезда = 1 единица в нашем боте
    
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
    
    # ИСПРАВЛЕНО: Правильный расчет суммы для платежа
    price_amount = amount  # 1 звезда = 1 единица
    
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
                f"✅ Платёж успешно обработан!\n"
                f"💰 Зачислено: {amount} ⭐\n"
                f"💎 Текущий баланс: {new_balance} ⭐\n\n"
                f"🎰 Приятной игры!",
                reply_markup=get_main_keyboard()
            )
            
            # Уведомление админа
            await message.bot.send_message(
                ADMIN_CHAT_ID,
                f"💰 Новое пополнение!\n"
                f"👤 Пользователь: {message.from_user.full_name} (ID: {user_id})\n"
                f"💸 Сумма: {amount} ⭐\n"
                f"💳 ID платежа: {payment.telegram_payment_charge_id}\n"
                f"💎 Новый баланс: {new_balance} ⭐"
            )

@router.callback_query(F.data == "inventory")
async def show_inventory(callback: CallbackQuery):
    user_id = callback.from_user.id
    inventory = user_data.get_inventory(user_id)
    
    if not inventory:
        await callback.message.edit_text(
            "🎒 Ваш инвентарь пуст\n\n"
            "🎁 Откройте кейсы или играйте в мини-игры, чтобы получить призы!",
            reply_markup=get_back_keyboard("profile")
        )
        return
    
    item_counts = {}
    for item in inventory:
        item_name = item["item"]
        item_counts[item_name] = item_counts.get(item_name, 0) + 1
    
    inventory_text = "🎒 Ваш инвентарь:\n\n"
    for item_name, count in item_counts.items():
        inventory_text += f"{item_name} ×{count}\n"
    
    await callback.message.edit_text(
        inventory_text,
        reply_markup=get_back_keyboard("profile")
    )

@router.callback_query(F.data == "stats")
async def show_stats(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = user_data.get_user(user_id)
    
    prize_stats = {}
    for item in user["inventory"]:
        item_name = item["item"]
        prize_stats[item_name] = prize_stats.get(item_name, 0) + 1
    
    stats_text = f"📊 Ваша статистика:\n\n"
    stats_text += f"🎁 Всего предметов: {len(user['inventory'])}\n"
    stats_text += f"💰 Пополнено: {user['total_deposited']} ⭐\n"
    stats_text += f"🏆 Выиграно: {user['total_won']} ⭐\n"
    stats_text += f"📅 Дата регистрации: {user['joined_date'][:10]}\n"
    
    if prize_stats:
        stats_text += "\n🎯 Статистика призов:\n"
        for prize, count in prize_stats.items():
            stats_text += f"▫️ {prize}: {count} шт.\n"
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_back_keyboard("profile")
    )

# Админ обработчики
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🛠️ Админ-панель\n\n"
        "Выберите действие:",
        reply_markup=get_admin_keyboard()
    )

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    users = user_data.get_all_users()
    total_users = len(users)
    total_balance = sum(user["balance"] for user in users.values())
    total_deposited = sum(user["total_deposited"] for user in users.values())
    total_won = sum(user["total_won"] for user in users.values())
    
    # Статистика за сегодня
    today = datetime.now().date().isoformat()
    today_users = sum(1 for user in users.values() if user["joined_date"][:10] == today)
    today_deposits = sum(user["total_deposited"] for user in users.values() if user["joined_date"][:10] == today)
    
    stats_text = (
        f"📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"👤 Новых сегодня: {today_users}\n"
        f"💰 Общий баланс: {total_balance} ⭐\n"
        f"💸 Всего пополнено: {total_deposited} ⭐\n"
        f"🏆 Всего выиграно: {total_won} ⭐\n"
        f"💎 Пополнений сегодня: {today_deposits} ⭐\n\n"
        f"📈 Чистая прибыль: {total_deposited - total_won} ⭐"
    )
    
    await callback.message.edit_text(
        stats_text,
        reply_markup=get_admin_back_keyboard()
    )

@router.callback_query(F.data == "admin_find_user")
async def admin_find_user(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔍 Поиск пользователя\n\n"
        "Введите ID пользователя или его username (без @):",
        reply_markup=get_admin_back_keyboard()
    )
    
    await state.set_state(AdminForm.waiting_for_user_id)

@router.message(AdminForm.waiting_for_user_id)
async def process_find_user(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    search_query = message.text.strip()
    users = user_data.get_all_users()
    
    found_users = []
    
    for user_id_str, user_data_info in users.items():
        user_id = int(user_id_str)
        
        # Поиск по ID
        if search_query.isdigit() and int(search_query) == user_id:
            found_users.append((user_id, user_data_info))
            break
        
        # Поиск по username
        username = user_data_info.get("username", "").lower()
        full_name = user_data_info.get("full_name", "").lower()
        
        if (search_query.lower() in username or 
            search_query.lower() in full_name or
            search_query.lower() in user_data_info.get("username", "").replace("@", "")):
            found_users.append((user_id, user_data_info))
    
    if not found_users:
        await message.answer(
            "❌ Пользователь не найден!\n"
            "Попробуйте ещё раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    if len(found_users) > 10:
        await message.answer(
            f"⚠️ Найдено слишком много пользователей ({len(found_users)})\n"
            f"Уточните запрос:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    response = f"🔍 Найдено пользователей: {len(found_users)}\n\n"
    
    for user_id, user_info in found_users[:10]:
        response += (
            f"🆔 ID: {user_id}\n"
            f"👤 Имя: {user_info.get('full_name', 'Не указано')}\n"
            f"📱 Username: @{user_info.get('username', 'Не указан')}\n"
            f"💎 Баланс: {user_info.get('balance', 0)} ⭐\n"
            f"💰 Пополнено: {user_info.get('total_deposited', 0)} ⭐\n"
            f"📅 Регистрация: {user_info.get('joined_date', 'Неизвестно')[:10]}\n"
            f"────────────────────\n"
        )
    
    await message.answer(
        response,
        reply_markup=get_admin_back_keyboard()
    )
    
    await state.clear()

@router.callback_query(F.data == "admin_change_balance")
async def admin_change_balance_start(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💰 Изменение баланса\n\n"
        "Введите ID пользователя:",
        reply_markup=get_admin_back_keyboard()
    )

@router.message(F.text, F.from_user.id == ADMIN_CHAT_ID)
async def handle_admin_text_input(message: Message, state: FSMContext):
    # Проверяем, находится ли пользователь в состоянии ожидания ID для изменения баланса
    current_state = await state.get_state()
    
    if current_state is None:
        # Если не в состоянии, проверяем, может быть это ID пользователя
        try:
            user_id = int(message.text.strip())
            user = user_data.get_user(user_id)
            
            await state.update_data(target_user_id=user_id)
            
            await message.answer(
                f"👤 Пользователь найден:\n\n"
                f"ID: {user_id}\n"
                f"Имя: {user.get('full_name', 'Не указано')}\n"
                f"Текущий баланс: {user.get('balance', 0)} ⭐\n\n"
                f"Выберите действие:",
                reply_markup=get_balance_change_keyboard()
            )
            
            await state.set_state(AdminForm.waiting_for_balance_type)
            
        except ValueError:
            # Если это не число, игнорируем
            pass
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
    elif current_state == AdminForm.waiting_for_balance_type:
        # Если мы уже в состоянии выбора типа операции, значит нужно установить точную сумму
        data = await state.get_data()
        user_id = data.get("target_user_id")
        
        try:
            new_balance = int(message.text.strip())
            
            if new_balance < 0:
                await message.answer("❌ Баланс не может быть отрицательным!")
                return
            
            old_balance, current_balance = user_data.set_balance(user_id, new_balance)
            
            # Уведомление пользователя
            try:
                await message.bot.send_message(
                    user_id,
                    f"💰 Ваш баланс был изменён администратором!\n\n"
                    f"📊 Старый баланс: {old_balance} ⭐\n"
                    f"💎 Новый баланс: {current_balance} ⭐"
                )
            except:
                pass  # Пользователь мог заблокировать бота
            
            await message.answer(
                f"✅ Баланс успешно изменён!\n\n"
                f"👤 Пользователь: {user_data.get_user(user_id).get('full_name', 'Не указано')} (ID: {user_id})\n"
                f"📊 Старый баланс: {old_balance} ⭐\n"
                f"💎 Новый баланс: {current_balance} ⭐",
                reply_markup=get_admin_back_keyboard()
            )
            
            await state.clear()
            
        except ValueError:
            await message.answer("❌ Пожалуйста, введите число!")
    elif current_state == AdminForm.waiting_for_balance_change:
        # Если мы в состоянии ожидания суммы для пополнения/списания
        data = await state.get_data()
        user_id = data.get("target_user_id")
        operation = data.get("operation")
        
        try:
            amount = int(message.text.strip())
            
            if amount <= 0:
                await message.answer("❌ Сумма должна быть положительной!")
                return
            
            user = user_data.get_user(user_id)
            old_balance = user["balance"]
            
            if operation == "balance_add":
                new_balance = user_data.update_balance(user_id, amount)
                operation_text = "пополнен"
            elif operation == "balance_subtract":
                if user["balance"] < amount:
                    await message.answer(
                        f"❌ Недостаточно средств на балансе!\n"
                        f"Текущий баланс: {old_balance} ⭐"
                    )
                    return
                new_balance = user_data.update_balance(user_id, -amount)
                operation_text = "списан"
            else:
                await message.answer("❌ Неизвестная операция!")
                await state.clear()
                return
            
            # Уведомление пользователя
            try:
                await message.bot.send_message(
                    user_id,
                    f"💰 Ваш баланс был изменён администратором!\n\n"
                    f"📝 Операция: {operation_text}\n"
                    f"💸 Сумма: {amount} ⭐\n"
                    f"📊 Старый баланс: {old_balance} ⭐\n"
                    f"💎 Новый баланс: {new_balance} ⭐"
                )
            except:
                pass
            
            await message.answer(
                f"✅ Баланс успешно изменён!\n\n"
                f"👤 Пользователь: {user.get('full_name', 'Не указано')} (ID: {user_id})\n"
                f"📝 Операция: {operation_text}\n"
                f"💸 Сумма: {amount} ⭐\n"
                f"📊 Старый баланс: {old_balance} ⭐\n"
                f"💎 Новый баланс: {new_balance} ⭐",
                reply_markup=get_admin_back_keyboard()
            )
            
            await state.clear()
            
        except ValueError:
            await message.answer("❌ Пожалуйста, введите число!")

@router.callback_query(F.data.in_(["balance_add", "balance_subtract", "balance_set_exact"]), AdminForm.waiting_for_balance_type)
async def select_balance_operation(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_CHAT_ID:
        return
    
    operation = callback.data
    data = await state.get_data()
    user_id = data.get("target_user_id")
    
    if not user_id:
        await callback.answer("❌ Ошибка: ID пользователя не найден", show_alert=True)
        await state.clear()
        return
    
    if operation == "balance_set_exact":
        # Установка точной суммы
        await callback.message.edit_text(
            f"🎯 Установка точной суммы баланса\n\n"
            f"Введите новую сумму баланса для пользователя (ID: {user_id}):\n\n"
            f"Пример: 500",
            reply_markup=get_admin_back_keyboard()
        )
        await state.set_state(AdminForm.waiting_for_balance_change)
        await state.update_data(operation="balance_set_exact")
    else:
        # Пополнение или списание
        await state.update_data(operation=operation)
        await state.set_state(AdminForm.waiting_for_balance_change)
        
        operation_text = "пополнения" if operation == "balance_add" else "списания"
        
        await callback.message.edit_text(
            f"💰 Введите сумму для {operation_text}:\n\n"
            f"Пример: 100",
            reply_markup=get_admin_back_keyboard()
        )

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 Рассылка сообщения\n\n"
        "Введите сообщение для рассылки всем пользователям:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel")]
            ]
        )
    )
    
    await state.set_state(AdminForm.waiting_for_broadcast)

@router.message(AdminForm.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_CHAT_ID:
        return
    
    broadcast_text = message.text
    users = user_data.get_all_users()
    total_users = len(users)
    successful = 0
    failed = 0
    
    progress_msg = await message.answer(f"📤 Начинаю рассылку... 0/{total_users}")
    
    for user_id_str in users:
        try:
            user_id = int(user_id_str)
            await message.bot.send_message(
                user_id,
                f"📢 Сообщение от администратора:\n\n{broadcast_text}"
            )
            successful += 1
        except Exception as e:
            failed += 1
        
        # Обновляем прогресс каждые 10 пользователей
        if (successful + failed) % 10 == 0:
            await progress_msg.edit_text(
                f"📤 Рассылка... {successful + failed}/{total_users}\n"
                f"✅ Успешно: {successful}\n"
                f"❌ Неудачно: {failed}"
            )
        
        # Небольшая задержка чтобы не спамить
        await asyncio.sleep(0.05)
    
    await progress_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"✅ Успешно отправлено: {successful}\n"
        f"❌ Не удалось отправить: {failed}\n"
        f"📊 Процент доставки: {successful/total_users*100:.1f}%"
    )
    
    await state.clear()

@router.callback_query(F.data == "admin_export")
async def admin_export(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_CHAT_ID:
        await callback.answer("⛔ Доступ запрещен!", show_alert=True)
        return
    
    try:
        # Создаем текстовый файл с данными
        users = user_data.get_all_users()
        
        export_text = "Экспорт данных пользователей\n\n"
        
        for user_id_str, user_info in users.items():
            export_text += (
                f"ID: {user_id_str}\n"
                f"Имя: {user_info.get('full_name', 'Не указано')}\n"
                f"Username: @{user_info.get('username', 'Не указан')}\n"
                f"Баланс: {user_info.get('balance', 0)} ⭐\n"
                f"Пополнено: {user_info.get('total_deposited', 0)} ⭐\n"
                f"Выиграно: {user_info.get('total_won', 0)} ⭐\n"
                f"Дата регистрации: {user_info.get('joined_date', 'Неизвестно')}\n"
                f"Предметов в инвентаре: {len(user_info.get('inventory', []))}\n"
                f"{'='*40}\n"
            )
        
        # Сохраняем во временный файл
        with open('users_export.txt', 'w', encoding='utf-8') as f:
            f.write(export_text)
        
        # Отправляем файл
        with open('users_export.txt', 'rb') as f:
            await callback.bot.send_document(
                chat_id=ADMIN_CHAT_ID,
                document=f,
                caption=f"📊 Экспорт данных пользователей\n👥 Всего пользователей: {len(users)}"
            )
        
        await callback.answer("✅ Экспорт завершен!", show_alert=True)
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка экспорта: {str(e)}", show_alert=True)

# Отмена действий
@router.message(F.text == "❌ Отмена")
async def cancel_action(message: Message, state: FSMContext):
    await state.clear()
    
    if message.from_user.id == ADMIN_CHAT_ID:
        await message.answer(
            "❌ Действие отменено",
            reply_markup=get_admin_keyboard()
        )
    else:
        await message.answer(
            "❌ Действие отменено",
            reply_markup=ReplyKeyboardRemove()
        )
        await message.answer(
            "🎰 Главное меню Casino Bot",
            reply_markup=get_main_keyboard()
        )

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
