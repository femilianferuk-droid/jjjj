import logging
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === КОНФИГУРАЦИЯ ===
# ВАЖНО: При развертывании на хостинге нужно будет указать токен
# BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"
ADMIN_ID = 7973988177  # ID администратора

# Инициализация хранилища состояний
storage = MemoryStorage()
bot = Bot(token="ЗАМЕНИТЕ_НА_ВАШ_ТОКЕН")  # Токен нужно будет заменить
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# Состояния для FSM
class UserStates(StatesGroup):
    waiting_for_message = State()
    admin_waiting_for_reply = State()

# === КЛАВИАТУРЫ ===
# Главное меню для пользователей
def get_user_main_menu():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("📨 Написать продавцу")
    keyboard.add("❓ Помощь")
    return keyboard

# Клавиатура отмены
def get_cancel_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add("❌ Отмена")
    return keyboard

# Клавиатура для админа (кнопка ответа)
def get_admin_reply_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("💬 Ответить", callback_data=f"reply_{user_id}"),
        InlineKeyboardButton("👁️ Просмотрено", callback_data=f"seen_{user_id}")
    )
    return keyboard

# Клавиатура для админа (отмена ответа)
def get_admin_cancel_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("❌ Отменить ответ")
    return keyboard

# === ОБРАБОТЧИКИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ===
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    welcome_text = (
        "👋 Добро пожаловать!\n\n"
        "Это бот для связи с продавцом. "
        "Используйте кнопку ниже, чтобы отправить сообщение."
    )
    
    await message.answer(welcome_text, reply_markup=get_user_main_menu())

@dp.message_handler(text="📨 Написать продавцу")
async def write_to_seller(message: types.Message):
    """Начало диалога с продавцом"""
    instruction = (
        "✍️ Напишите ваше сообщение продавцу.\n"
        "Оно будет отправлено администратору.\n\n"
        "Используйте кнопку '❌ Отмена', если передумали."
    )
    
    await UserStates.waiting_for_message.set()
    await message.answer(instruction, reply_markup=get_cancel_keyboard())

@dp.message_handler(text="❓ Помощь")
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
    await message.answer(help_text, parse_mode="Markdown")

@dp.message_handler(text="❌ Отмена", state="*")
async def cancel_operation(message: types.Message, state: FSMContext):
    """Отмена текущей операции"""
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.finish()
    await message.answer("❌ Операция отменена", reply_markup=get_user_main_menu())

@dp.message_handler(state=UserStates.waiting_for_message, content_types=types.ContentTypes.ANY)
async def process_user_message(message: types.Message, state: FSMContext):
    """Обработка сообщения от пользователя"""
    try:
        # Формируем информацию о пользователе
        user_info = (
            f"👤 **Новое сообщение от пользователя**\n"
            f"ID: `{message.from_user.id}`\n"
            f"Имя: {message.from_user.full_name}\n"
            f"Username: @{message.from_user.username if message.from_user.username else 'нет'}\n"
            f"---\n"
        )
        
        # Отправляем сообщение админу
        if message.text:
            await bot.send_message(
                ADMIN_ID,
                f"{user_info}📝 Сообщение:\n{message.text}",
                parse_mode="Markdown",
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
        elif message.photo:
            await bot.send_photo(
                ADMIN_ID,
                message.photo[-1].file_id,
                caption=f"{user_info}📷 Фото от пользователя",
                parse_mode="Markdown",
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
        elif message.document:
            await bot.send_document(
                ADMIN_ID,
                message.document.file_id,
                caption=f"{user_info}📎 Документ от пользователя",
                parse_mode="Markdown",
                reply_markup=get_admin_reply_keyboard(message.from_user.id)
            )
        
        # Подтверждение пользователю
        await message.answer(
            "✅ Ваше сообщение отправлено продавцу! Ожидайте ответа.",
            reply_markup=get_user_main_menu()
        )
        
        await state.finish()
        
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения админу: {e}")
        await message.answer(
            "❌ Произошла ошибка при отправке сообщения. Попробуйте позже.",
            reply_markup=get_user_main_menu()
        )
        await state.finish()

# === ОБРАБОТЧИКИ ДЛЯ АДМИНА ===
@dp.callback_query_handler(lambda c: c.data.startswith('reply_'))
async def process_admin_reply(callback_query: types.CallbackQuery, state: FSMContext):
    """Админ нажал кнопку 'Ответить'"""
    user_id = int(callback_query.data.split('_')[1])
    
    # Сохраняем ID пользователя для ответа
    async with state.proxy() as data:
        data['reply_to'] = user_id
    
    await UserStates.admin_waiting_for_reply.set()
    
    await callback_query.message.answer(
        f"✍️ Введите ответ для пользователя (ID: {user_id}):",
        reply_markup=get_admin_cancel_keyboard()
    )
    
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data.startswith('seen_'))
async def process_admin_seen(callback_query: types.CallbackQuery):
    """Админ пометил сообщение как просмотренное"""
    await callback_query.answer("✅ Помечено как просмотренное")
    
    # Можно удалить кнопки или изменить сообщение
    try:
        await callback_query.message.edit_reply_markup(
            InlineKeyboardMarkup().add(
                InlineKeyboardButton("👁️ Просмотрено", callback_data="already_seen")
            )
        )
    except:
        pass

@dp.message_handler(text="❌ Отменить ответ", state=UserStates.admin_waiting_for_reply)
async def cancel_admin_reply(message: types.Message, state: FSMContext):
    """Админ отменяет ответ"""
    await state.finish()
    await message.answer("❌ Ответ отменен")

@dp.message_handler(state=UserStates.admin_waiting_for_reply, content_types=types.ContentTypes.TEXT)
async def process_admin_reply_message(message: types.Message, state: FSMContext):
    """Обработка ответа от админа"""
    async with state.proxy() as data:
        user_id = data.get('reply_to')
    
    if user_id:
        try:
            # Отправляем ответ пользователю
            reply_text = (
                f"📩 **Ответ от продавца:**\n\n"
                f"{message.text}\n\n"
                f"_Чтобы ответить, просто напишите новое сообщение._"
            )
            
            await bot.send_message(user_id, reply_text, parse_mode="Markdown")
            
            # Подтверждение админу
            await message.answer(
                f"✅ Ответ отправлен пользователю (ID: {user_id})",
                reply_markup=types.ReplyKeyboardRemove()
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
                f"Возможно, он заблокировал бота.",
                reply_markup=types.ReplyKeyboardRemove()
            )
    
    await state.finish()

# Обработчик всех остальных сообщений от пользователей
@dp.message_handler(content_types=types.ContentTypes.ANY)
async def handle_other_messages(message: types.Message):
    """Обработка прочих сообщений"""
    if message.from_user.id == ADMIN_ID:
        # Сообщения от админа вне состояния
        await message.answer("Используйте кнопки в сообщениях от пользователей для ответа")
    else:
        # Предложение пользователям написать продавцу
        if message.text not in ["📨 Написать продавцу", "❓ Помощь", "❌ Отмена"]:
            await message.answer(
                "Чтобы написать продавцу, нажмите кнопку '📨 Написать продавцу'",
                reply_markup=get_user_main_menu()
            )

# === ЗАПУСК БОТА ===
if __name__ == '__main__':
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
    print("4. Настройте хостинг (см. инструкцию ниже)")
    print("=" * 50)
    
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
