import logging
import json
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
ADMIN_ID = 7973988177  # Ваш Telegram ID

# Инициализация бота
# Токен будет передан при запуске через polling
bot = Bot(token="placeholder")  # Заполнитель, будет заменен
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Файл для хранения данных
DATA_FILE = 'buttons_data.json'

# Состояния для FSM
class AdminStates(StatesGroup):
    waiting_for_button_name = State()
    waiting_for_button_url = State()
    waiting_for_button_id_to_remove = State()
    waiting_for_button_id_to_edit = State()
    waiting_for_new_button_name = State()
    waiting_for_new_button_url = State()
    waiting_for_welcome_message = State()

# Функции для работы с данными
def load_data():
    """Загружаем данные из файла"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Если файла нет или он пустой, создаем структуру по умолчанию
        default_data = {
            "buttons": [],
            "welcome_message": "🌟 Добро пожаловать в бот-переходник!\n\nВыберите нужную кнопку ниже:"
        }
        save_data(default_data)
        return default_data

def save_data(data):
    """Сохраняем данные в файл"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def create_keyboard(buttons_data):
    """Создаем клавиатуру из данных"""
    if not buttons_data:
        return None
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Группируем кнопки по 2 в ряд
    for i in range(0, len(buttons_data), 2):
        row_buttons = []
        for j in range(2):
            if i + j < len(buttons_data):
                button = buttons_data[i + j]
                row_buttons.append(
                    InlineKeyboardButton(
                        text=button['name'], 
                        url=button['url']
                    )
                )
        keyboard.row(*row_buttons)
    
    return keyboard

# ========== ОБРАБОТЧИКИ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========

@dp.message_handler(commands=['start', 'help'])
async def send_welcome(message: types.Message):
    """Обработчик команды /start"""
    data = load_data()
    keyboard = create_keyboard(data['buttons'])
    
    await message.answer(
        data['welcome_message'],
        reply_markup=keyboard
    )

# ========== ОБРАБОТЧИКИ АДМИН-ПАНЕЛИ ==========

@dp.message_handler(commands=['admin'], user_id=ADMIN_ID)
async def admin_panel(message: types.Message):
    """Панель администратора"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("➕ Добавить кнопку", callback_data="add_button"),
        InlineKeyboardButton("✏️ Редактировать кнопку", callback_data="edit_button"),
        InlineKeyboardButton("❌ Удалить кнопку", callback_data="remove_button"),
        InlineKeyboardButton("📝 Изменить приветствие", callback_data="edit_welcome"),
        InlineKeyboardButton("📊 Просмотреть все кнопки", callback_data="view_buttons")
    )
    
    await message.answer("👑 Админ-панель:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "add_button", user_id=ADMIN_ID)
async def add_button_start(callback_query: types.CallbackQuery):
    """Начало добавления кнопки"""
    await AdminStates.waiting_for_button_name.set()
    await callback_query.message.answer("Введите название для новой кнопки:")
    await callback_query.answer()

@dp.message_handler(state=AdminStates.waiting_for_button_name, user_id=ADMIN_ID)
async def process_button_name(message: types.Message, state: FSMContext):
    """Получаем название кнопки"""
    async with state.proxy() as data:
        data['button_name'] = message.text
    
    await AdminStates.waiting_for_button_url.set()
    await message.answer("Теперь введите URL для кнопки (начинается с http:// или https://):")

@dp.message_handler(state=AdminStates.waiting_for_button_url, user_id=ADMIN_ID)
async def process_button_url(message: types.Message, state: FSMContext):
    """Получаем URL кнопки и сохраняем"""
    url = message.text
    if not url.startswith(('http://', 'https://')):
        await message.answer("URL должен начинаться с http:// или https://. Попробуйте еще раз:")
        return
    
    async with state.proxy() as data:
        button_data = load_data()
        new_button = {
            'id': len(button_data['buttons']) + 1,
            'name': data['button_name'],
            'url': url
        }
        button_data['buttons'].append(new_button)
        save_data(button_data)
    
    await state.finish()
    await message.answer(f"✅ Кнопка '{data['button_name']}' успешно добавлена!")

@dp.callback_query_handler(lambda c: c.data == "view_buttons", user_id=ADMIN_ID)
async def view_all_buttons(callback_query: types.CallbackQuery):
    """Просмотр всех кнопок"""
    data = load_data()
    
    if not data['buttons']:
        await callback_query.message.answer("📭 Список кнопок пуст.")
        return
    
    response = "📋 Список всех кнопок:\n\n"
    for i, button in enumerate(data['buttons'], 1):
        response += f"{i}. {button['name']}\n   🔗 {button['url']}\n\n"
    
    await callback_query.message.answer(response)
    await callback_query.answer()

@dp.callback_query_handler(lambda c: c.data == "remove_button", user_id=ADMIN_ID)
async def remove_button_start(callback_query: types.CallbackQuery):
    """Начало удаления кнопки"""
    data = load_data()
    
    if not data['buttons']:
        await callback_query.message.answer("📭 Список кнопок пуст.")
        await callback_query.answer()
        return
    
    response = "❌ Удаление кнопки\n\nВыберите ID кнопки для удаления:\n\n"
    for button in data['buttons']:
        response += f"{button['id']}. {button['name']}\n"
    
    await AdminStates.waiting_for_button_id_to_remove.set()
    await callback_query.message.answer(response)
    await callback_query.answer()

@dp.message_handler(state=AdminStates.waiting_for_button_id_to_remove, user_id=ADMIN_ID)
async def process_button_remove(message: types.Message, state: FSMContext):
    """Удаляем кнопку по ID"""
    try:
        button_id = int(message.text)
        data = load_data()
        
        # Ищем кнопку с таким ID
        button_to_remove = None
        for button in data['buttons']:
            if button['id'] == button_id:
                button_to_remove = button
                break
        
        if button_to_remove:
            data['buttons'].remove(button_to_remove)
            # Пересчитываем ID
            for i, button in enumerate(data['buttons'], 1):
                button['id'] = i
            save_data(data)
            await message.answer(f"✅ Кнопка '{button_to_remove['name']}' удалена!")
        else:
            await message.answer("❌ Кнопка с таким ID не найдена.")
    
    except ValueError:
        await message.answer("❌ Пожалуйста, введите числовой ID кнопки.")
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "edit_button", user_id=ADMIN_ID)
async def edit_button_start(callback_query: types.CallbackQuery):
    """Начало редактирования кнопки"""
    data = load_data()
    
    if not data['buttons']:
        await callback_query.message.answer("📭 Список кнопок пуст.")
        await callback_query.answer()
        return
    
    response = "✏️ Редактирование кнопки\n\nВыберите ID кнопки для редактирования:\n\n"
    for button in data['buttons']:
        response += f"{button['id']}. {button['name']}\n"
    
    await AdminStates.waiting_for_button_id_to_edit.set()
    await callback_query.message.answer(response)
    await callback_query.answer()

@dp.message_handler(state=AdminStates.waiting_for_button_id_to_edit, user_id=ADMIN_ID)
async def process_button_edit_id(message: types.Message, state: FSMContext):
    """Получаем ID кнопки для редактирования"""
    try:
        button_id = int(message.text)
        data = load_data()
        
        # Ищем кнопку с таким ID
        button_to_edit = None
        for button in data['buttons']:
            if button['id'] == button_id:
                button_to_edit = button
                break
        
        if button_to_edit:
            async with state.proxy() as state_data:
                state_data['edit_button_id'] = button_id
                state_data['edit_button'] = button_to_edit
            
            await AdminStates.waiting_for_new_button_name.set()
            await message.answer(
                f"Текущее название: {button_to_edit['name']}\n"
                f"Введите новое название (или отправьте '-' чтобы оставить без изменений):"
            )
        else:
            await message.answer("❌ Кнопка с таким ID не найдена.")
            await state.finish()
    
    except ValueError:
        await message.answer("❌ Пожалуйста, введите числовой ID кнопки.")
        await state.finish()

@dp.message_handler(state=AdminStates.waiting_for_new_button_name, user_id=ADMIN_ID)
async def process_edit_button_name(message: types.Message, state: FSMContext):
    """Получаем новое название кнопки"""
    new_name = message.text
    
    async with state.proxy() as data:
        if new_name != '-':
            data['new_button_name'] = new_name
        else:
            data['new_button_name'] = data['edit_button']['name']
    
    await AdminStates.waiting_for_new_button_url.set()
    await message.answer(
        f"Текущий URL: {data['edit_button']['url']}\n"
        f"Введите новый URL (или отправьте '-' чтобы оставить без изменений):"
    )

@dp.message_handler(state=AdminStates.waiting_for_new_button_url, user_id=ADMIN_ID)
async def process_edit_button_url(message: types.Message, state: FSMContext):
    """Получаем новый URL и сохраняем изменения"""
    new_url = message.text
    
    async with state.proxy() as data:
        button_id = data['edit_button_id']
        data_to_save = load_data()
        
        # Находим и обновляем кнопку
        for button in data_to_save['buttons']:
            if button['id'] == button_id:
                if new_url != '-':
                    if not new_url.startswith(('http://', 'https://')):
                        await message.answer("❌ URL должен начинаться с http:// или https://")
                        await state.finish()
                        return
                    button['url'] = new_url
                button['name'] = data['new_button_name']
                break
        
        save_data(data_to_save)
    
    await state.finish()
    await message.answer("✅ Кнопка успешно обновлена!")

@dp.callback_query_handler(lambda c: c.data == "edit_welcome", user_id=ADMIN_ID)
async def edit_welcome_message(callback_query: types.CallbackQuery):
    """Изменение приветственного сообщения"""
    data = load_data()
    
    await AdminStates.waiting_for_welcome_message.set()
    await callback_query.message.answer(
        f"Текущее приветственное сообщение:\n\n{data['welcome_message']}\n\n"
        f"Отправьте новое приветственное сообщение:"
    )
    await callback_query.answer()

@dp.message_handler(state=AdminStates.waiting_for_welcome_message, user_id=ADMIN_ID)
async def process_welcome_message(message: types.Message, state: FSMContext):
    """Сохраняем новое приветственное сообщение"""
    data = load_data()
    data['welcome_message'] = message.text
    save_data(data)
    
    await state.finish()
    await message.answer("✅ Приветственное сообщение обновлено!")

# ========== ЗАПУСК БОТА ==========

if __name__ == '__main__':
    print("Бот запускается...")
    print(f"Админ ID: {ADMIN_ID}")
    print("Используйте команду /start для начала работы")
    print("Используйте команду /admin для доступа к админ-панели")
    
    # Создаем файл данных если его нет
    load_data()
    
    executor.start_polling(dp, skip_updates=True)
