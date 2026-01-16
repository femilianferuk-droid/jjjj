import logging
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.enums import ParseMode

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
# ВАЖНО: При развертывании на хостинге нужно будет указать токен
# BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
BOT_TOKEN = "ЗАМЕНИТЕ_НА_ВАШ_ТОКЕН"  # Токен нужно будет заменить
ADMIN_ID = 7973988177  # ID администратора

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния для FSM
class UserStates(StatesGroup):
    waiting_for_message = State()
    admin_waiting_for_reply = State()

# === КЛАВИАТУРЫ ===
# Главное меню для пользователей
def get_user_main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📨 Написать продавцу")],
            [KeyboardButton(text="❓ Помощь")]
        ],
        resize_keyboard=True
    )
    return keyboard

# Клавиатура отмены
def get_cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    return keyboard

# Клавиатура для админа (кнопка ответа)
def get_admin_reply_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton(text="👁️ Просмотрено", callback_data=f"seen_{user_id}")
        ]
    ])
    return keyboard

# Клавиатура для админа (отмена ответа)
def get_admin_cancel_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отменить ответ")]],
        resize_keyboard=True
    )
    return keyboard

# === ОБРАБОТЧИКИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Добро пожаловать!\n\n"
        "Это бот для связи с продавцом. "
        "Используйте кнопку ниже, чтобы отправить сообщение."
    )
    
    await message.answer(welcome_text, reply_markup=get_user_main_menu())

@dp.message(lambda message: message.text == "📨 Написать продавцу")
async def write_to_seller(message: types.Message, state: FSMContext):
    """Начало диалога с продавцом"""
    instruction = (
        "✍️ Напишите ваше сообщение продавцу.\n"
        "Оно будет отправлено администратору.\n\n"
        "Используйте кнопку '❌ Отмена', если передумали."
    )
    
    await state.set_state(UserStates.waiting_for_message)
    await message.answer(instruction, reply_markup=get_cancel_keyboard())

@dp.message(lambda message: message.text == "❓ Помощь")
async def show_help(message: types.Message):
    """Показ справки"""
    help_text = (
        "ℹ️ **Помощь по боту**\n\n"
        "1. Нажмите '📨 Написать продавцу'\n"
        "2. Введите ваше сообщение\n"
        "3. Администратор получит уведомление\n"
        "4. Дождитесь ответа\n\n"
        "Администратор ответит вам в этом же чате."
    )
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@dp.message(lambda message: message.text == "❌ Отмена")
async def cancel_operation(message: types.Message, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.clear()
    await message.answer("❌ Операция отменена", reply_markup=get_user_main_menu())

@dp.message(UserStates.waiting_for_message)
async def process_user_message(message: types.Message, state: FSMContext):
    """Обработка сообщения от пользователя"""
    try:
        # Формируем информацию о пользователе
        username = f"@{message.from_user.username}" if message.from_user.username else "нет"
        user_info = (
            f"👤 **Новое сообщение от пользователя**\n"
            f"ID: `{message.from_user.id}`\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: {username}\n"
            f"---\n"
        )
        
        # Отправляем сообщение админу
        if message.text:
            await bot.send_message(
                ADMIN_ID,
                f"{user_info}📝 Сообщение:\n{message.text}",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
            await message.answer(
                "✅ Ваше сообщение отправлено продавцу! Ожидайте ответа.",
                reply_markup=get_user_main_menu()
            )
        
        elif message.photo:
            # Для фото отправляем отдельно текст и фото
            await bot.send_message(
                ADMIN_ID,
                f"{user_info}📷 Фото от пользователя",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
            await bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id
            )
            await message.answer(
                "✅ Ваше фото отправлено продавцу! Ожидайте ответа.",
                reply_markup=get_user_main_menu()
            )
        
        elif message.document:
            await bot.send_message(
                ADMIN_ID,
                f"{user_info}📎 Документ от пользователя",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
            await bot.send_document(
                ADMIN_ID,
                message.document.file_id
            )
            await message.answer(
                "✅ Ваш документ отправлен продавцу! Ожидайте ответа.",
                reply_markup=get_user_main_menu()
            )
        else:
            await message.answer(
                "❌ Поддерживаются только текст, фото и документы.",
                reply_markup=get_user_main_menu()
            )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения админу: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения. Попробуйте позже.",
            reply_markup=get_user_main_menu()
        )
        await state.clear()

# === ОБРАБОТЧИКИ ДЛЯ АДМИНА ===
@dp.callback_query(lambda c: c.data and c.data.startswith('reply_'))
async def process_admin_reply(callback_query: types.CallbackQuery, state: FSMContext):
    """Админ нажал кнопку 'Ответить'"""
    user_id = int(callback_query.data.split('_')[1])
    
    # Сохраняем ID пользователя для ответа
    await state.update_data(reply_to=user_id)
    await state.set_state(UserStates.admin_waiting_for_reply)
    
    await callback_query.message.answer(
        f"✍️ Введите ответ для пользователя (ID: {user_id}):",
        reply_markup=get_admin_cancel_keyboard()
    )
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data and c.data.startswith('seen_'))
async def process_admin_seen(callback_query: types.CallbackQuery):
    """Админ пометил сообщение как просмотренное"""
    await callback_query.answer("✅ Помечено как просмотренное")
    
    # Можно удалить кнопки или изменить сообщение
    try:
        await callback_query.message.edit_reply_markup(
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👁️ Просмотрено", callback_data="already_seen")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка при изменении клавиатуры: {e}")

@dp.message(lambda message: message.text == "❌ Отменить ответ")
async def cancel_admin_reply(message: types.Message, state: FSMContext):
    """Админ отменяет ответ"""
    await state.clear()
    await message.answer("❌ Ответ отменен")

@dp.message(UserStates.admin_waiting_for_reply)
async def process_admin_reply_message(message: types.Message, state: FSMContext):
    """Обработка ответа от админа"""
    data = await state.get_data()
    user_id = data.get('reply_to')
    
    if user_id:
        try:
            # Отправляем ответ пользователю
            reply_text = (
                f"📩 **Ответ от продавца:**\n\n"
                f"{message.text}\n\n"
                f"_Чтобы ответить, просто напишите новое сообщение._"
            )
            
            await bot.send_message(user_id, reply_text, parse_mode=ParseMode.MARKDOWN)
            
            # Подтверждение админу
            await message.answer(
                f"✅ Ответ отправлен пользователю (ID: {user_id})"
            )
            
            # Логируем в чат админа
            await bot.send_message(
                ADMIN_ID,
                f"📤 Вы отправили ответ пользователю ID: {user_id}\n"
                f"Сообщение: {message.text[:50]}..."
            )
            
        except Exception as e:
            logger.error(f"Ошибка при отправке ответа пользователю: {e}")
            await message.answer(
                f"❌ Не удалось отправить ответ пользователю. "
                f"Возможно, он заблокировал бота."
            )
    
    await state.clear()

# Обработчик всех остальных сообщений
@dp.message()
async def handle_other_messages(message: types.Message):
    """Обработка прочих сообщений"""
    if message.from_user.id == ADMIN_ID:
        # Сообщения от админа вне состояния
        if message.text not in ["❌ Отменить ответ"]:
            await message.answer("Используйте кнопки в сообщениях от пользователей для ответа")
    else:
        # Предложение пользователям написать продавцу
        if message.text not in ["📨 Написать продавцу", "❓ Помощь", "❌ Отмена"]:
            await message.answer(
                "Чтобы написать продавцу, нажмите кнопку '📨 Написать продавцу'",
                reply_markup=get_user_main_menu()
            )

# === ЗАПУСК БОТА ===
async def main():
    logger.info("Бот запускается...")
    
    # Информация о конфигурации
    print("=" * 50)
    print("КОНФИГУРАЦИЯ БОТА:")
    print(f"1. ID администратора: {ADMIN_ID}")
    print("2. Токен бота: НЕ ЗАДАН (нужно заменить в коде)")
    print("=" * 50)
    print("\nПЕРЕД ЗАПУСКОМ:")
    print("1. Создайте бота через @BotFather")
    print("2. Получите токен")
    print("3. Замените 'ЗАМЕНИТЕ_НА_ВАШ_ТОКЕН' на ваш токен")
    print("4. Настройте хостинг")
    print("=" * 50)
    
    # Запуск бота
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
