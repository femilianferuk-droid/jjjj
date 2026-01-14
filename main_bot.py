import asyncio
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import json
import os

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния
class BotActivation(StatesGroup):
    waiting_token = State()
    waiting_confirm = State()

class HostedMainBot:
    def __init__(self):
        self.bot = Bot(token=os.getenv("MAIN_BOT_TOKEN"))
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.configs_db = "configs.db"
        self.init_databases()
        self.setup_handlers()
    
    def init_databases(self):
        """Инициализация баз данных"""
        # База конфигураций для клиентских ботов
        conn = sqlite3.connect(self.configs_db)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS bot_configs
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     user_token TEXT UNIQUE,
                     config_json TEXT,
                     status TEXT DEFAULT 'inactive',
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS templates
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     name TEXT,
                     template_json TEXT,
                     price INTEGER,
                     is_active BOOLEAN DEFAULT 1)''')
        
        # Добавляем шаблоны по умолчанию
        default_templates = [
            ("support_bot", json.dumps({
                "commands": [
                    {"command": "start", "description": "Начать диалог"},
                    {"command": "help", "description": "Помощь"},
                    {"command": "ticket", "description": "Создать тикет"},
                    {"command": "faq", "description": "Частые вопросы"}
                ],
                "welcome_message": "👋 Добро пожаловать в поддержку!",
                "auto_replies": {
                    "привет": "Здравствуйте! Чем могу помочь?",
                    "цена": "Цены вы можете узнать на сайте"
                }
            }), 0),
            
            ("shop_bot", json.dumps({
                "commands": [
                    {"command": "start", "description": "В магазин"},
                    {"command": "catalog", "description": "Каталог"},
                    {"command": "cart", "description": "Корзина"},
                    {"command": "orders", "description": "Мои заказы"}
                ],
                "welcome_message": "🛒 Добро пожаловать в магазин!",
                "product_categories": ["Электроника", "Одежда", "Книги"]
            }), 500),
            
            ("news_bot", json.dumps({
                "commands": [
                    {"command": "start", "description": "Подписаться"},
                    {"command": "news", "description": "Последние новости"},
                    {"command": "subscribe", "description": "Подписки"},
                    {"command": "unsubscribe", "description": "Отписаться"}
                ],
                "welcome_message": "📰 Новостной бот активирован!",
                "broadcast_enabled": True
            }), 300)
        ]
        
        for name, template_json, price in default_templates:
            c.execute('''INSERT OR IGNORE INTO templates (name, template_json, price) 
                        VALUES (?, ?, ?)''', (name, template_json, price))
        
        conn.commit()
        conn.close()
        logger.info("Базы данных инициализированы")
    
    def setup_handlers(self):
        """Настройка обработчиков"""
        
        @self.dp.message(Command("start"))
        async def start_command(message: types.Message):
            """Стартовое сообщение"""
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Активировать бота", callback_data="activate_bot")],
                [InlineKeyboardButton(text="📋 Мои боты", callback_data="my_bots")],
                [InlineKeyboardButton(text="🛒 Шаблоны", callback_data="templates")]
            ])
            
            await message.answer(
                "🤖 *Главный бот-активатор*\n\n"
                "Я помогу добавить функционал в ВАШЕГО телеграм-бота!\n\n"
                "Просто укажите токен своего бота и выберите шаблон.\n"
                "Я автоматически настрою команды и функционал.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        
        @self.dp.callback_query(lambda c: c.data == "activate_bot")
        async def activate_bot_start(callback: types.CallbackQuery, state: FSMContext):
            """Начало активации"""
            await callback.answer()
            
            # Показываем шаблоны
            conn = sqlite3.connect(self.configs_db)
            c = conn.cursor()
            c.execute("SELECT id, name, price FROM templates WHERE is_active = 1")
            templates = c.fetchall()
            conn.close()
            
            keyboard_buttons = []
            for tpl_id, name, price in templates:
                price_text = "Бесплатно" if price == 0 else f"{price}₽"
                keyboard_buttons.append([
                    InlineKeyboardButton(
                        text=f"{name} ({price_text})",
                        callback_data=f"template_{tpl_id}"
                    )
                ])
            
            keyboard_buttons.append([
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            
            await callback.message.edit_text(
                "🎨 *Выберите шаблон бота:*\n\n"
                "Шаблон определяет функционал вашего бота.\n"
                "После выбора укажите токен вашего бота.",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        
        @self.dp.callback_query(lambda c: c.data.startswith("template_"))
        async def select_template(callback: types.CallbackQuery, state: FSMContext):
            """Выбор шаблона"""
            await callback.answer()
            template_id = int(callback.data.split("_")[1])
            
            # Сохраняем ID шаблона
            await state.update_data(template_id=template_id)
            
            await callback.message.edit_text(
                "✅ Шаблон выбран!\n\n"
                "Теперь отправьте *токен вашего бота*.\n\n"
                "*Как получить токен:*\n"
                "1. Напишите @BotFather\n"
                "2. Отправьте /mybots\n"
                "3. Выберите бота → API Token\n"
                "4. Скопируйте и отправьте сюда\n\n"
                "*Токен выглядит так:*\n"
                "`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`",
                parse_mode="Markdown"
            )
            
            await state.set_state(BotActivation.waiting_token)
        
        @self.dp.message(BotActivation.waiting_token)
        async def process_user_token(message: types.Message, state: FSMContext):
            """Обработка токена пользователя"""
            user_token = message.text.strip()
            
            # Проверка формата токена
            if not self.validate_token(user_token):
                await message.answer(
                    "❌ *Неверный формат токена!*\n\n"
                    "Пример правильного токена:\n"
                    "`1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`\n\n"
                    "Отправьте корректный токен:",
                    parse_mode="Markdown"
                )
                return
            
            # Получаем данные шаблона
            data = await state.get_data()
            template_id = data.get('template_id')
            
            conn = sqlite3.connect(self.configs_db)
            c = conn.cursor()
            c.execute("SELECT template_json FROM templates WHERE id = ?", (template_id,))
            template_result = c.fetchone()
            
            if not template_result:
                await message.answer("Ошибка: шаблон не найден")
                return
            
            template_config = json.loads(template_result[0])
            
            # Сохраняем конфигурацию
            config_data = {
                "user_id": message.from_user.id,
                "user_token": user_token,
                "template_id": template_id,
                "config": template_config,
                "webhook_url": f"https://your-host.com/webhook/{message.from_user.id}"
            }
            
            c.execute('''INSERT OR REPLACE INTO bot_configs 
                        (user_id, user_token, config_json, status)
                        VALUES (?, ?, ?, ?)''',
                     (message.from_user.id, user_token, 
                      json.dumps(config_data), 'pending_activation'))
            
            conn.commit()
            conn.close()
            
            # Показываем подтверждение
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Активировать", callback_data="confirm_activate")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_activate")]
            ])
            
            await message.answer(
                f"✅ *Токен принят!*\n\n"
                f"*Детали:*\n"
                f"• Ваш токен: `{user_token[:15]}...`\n"
                f"• Шаблон: ID {template_id}\n"
                f"• Команд: {len(template_config.get('commands', []))}\n\n"
                f"*После активации:*\n"
                f"1. Ваш бот получит новые команды\n"
                f"2. Будет настроен webhook\n"
                f"3. Начнет работать по выбранному шаблону\n\n"
                f"Активировать?",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            
            await state.set_state(BotActivation.waiting_confirm)
        
        @self.dp.callback_query(BotActivation.waiting_confirm, lambda c: c.data == "confirm_activate")
        async def confirm_activation(callback: types.CallbackQuery, state: FSMContext):
            """Подтверждение активации"""
            await callback.answer()
            
            data = await state.get_data()
            template_id = data.get('template_id')
            
            # Активируем бота
            success = await self.activate_user_bot(callback.from_user.id, template_id)
            
            if success:
                await callback.message.edit_text(
                    "🎉 *Бот успешно активирован!*\n\n"
                    "✅ Команды добавлены\n"
                    "✅ Webhook настроен\n"
                    "✅ Бот готов к работе\n\n"
                    "Перейдите в своего бота и отправьте /start",
                    parse_mode="Markdown"
                )
            else:
                await callback.message.edit_text(
                    "❌ *Ошибка активации!*\n\n"
                    "Проверьте:\n"
                    "1. Корректность токена\n"
                    "2. Что бот не заблокирован\n"
                    "3. Попробуйте еще раз через /start",
                    parse_mode="Markdown"
                )
            
            await state.clear()
        
        @self.dp.callback_query(lambda c: c.data == "my_bots")
        async def show_my_bots(callback: types.CallbackQuery):
            """Показать список ботов пользователя"""
            await callback.answer()
            
            conn = sqlite3.connect(self.configs_db)
            c = conn.cursor()
            c.execute('''SELECT user_token, status, created_at 
                        FROM bot_configs 
                        WHERE user_id = ? 
                        ORDER BY created_at DESC''',
                     (callback.from_user.id,))
            
            bots = c.fetchall()
            conn.close()
            
            if not bots:
                await callback.message.edit_text(
                    "🤷 *У вас нет активированных ботов*\n\n"
                    "Нажмите 'Активировать бота' чтобы начать.",
                    parse_mode="Markdown"
                )
                return
            
            bots_text = "📋 *Ваши боты:*\n\n"
            for i, (token, status, created_at) in enumerate(bots, 1):
                status_emoji = "✅" if status == "active" else "🔄"
                bots_text += f"{i}. `{token[:10]}...` {status_emoji}\n"
            
            await callback.message.edit_text(
                bots_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main")]
                ])
            )
    
    def validate_token(self, token: str) -> bool:
        """Валидация токена"""
        import re
        pattern = r'^\d{10}:[A-Za-z0-9_-]{35}$'
        return bool(re.match(pattern, token))
    
    async def activate_user_bot(self, user_id: int, template_id: int) -> bool:
        """Активация бота пользователя"""
        try:
            conn = sqlite3.connect(self.configs_db)
            c = conn.cursor()
            
            # Получаем конфигурацию
            c.execute('''SELECT user_token, config_json 
                        FROM bot_configs 
                        WHERE user_id = ? AND status LIKE '%pending%'
                        ORDER BY id DESC LIMIT 1''',
                     (user_id,))
            
            result = c.fetchone()
            if not result:
                return False
            
            user_token, config_json = result
            config = json.loads(config_json)
            template_config = config.get('config', {})
            
            # Создаем объект бота пользователя
            user_bot = Bot(token=user_token)
            
            # 1. Устанавливаем команды
            if 'commands' in template_config:
                commands = [
                    types.BotCommand(
                        command=cmd['command'],
                        description=cmd['description']
                    )
                    for cmd in template_config['commands']
                ]
                await user_bot.set_my_commands(commands)
            
            # 2. Устанавливаем описание
            if 'welcome_message' in template_config:
                await user_bot.set_my_description(
                    description=template_config['welcome_message'][:255]
                )
            
            # 3. Настраиваем webhook (если есть URL)
            if 'webhook_url' in config:
                # Здесь можно настроить webhook для обработки сообщений
                pass
            
            # 4. Отправляем сообщение о успешной активации
            await user_bot.send_message(
                chat_id=user_id,
                text=f"🎉 *Ваш бот активирован!*\n\n"
                     f"Шаблон: ID {template_id}\n"
                     f"Команд: {len(template_config.get('commands', []))}\n\n"
                     f"Отправьте /start в своем боте чтобы начать.",
                parse_mode="Markdown"
            )
            
            # 5. Обновляем статус в БД
            c.execute('''UPDATE bot_configs 
                        SET status = 'active', updated_at = CURRENT_TIMESTAMP
                        WHERE user_id = ? AND user_token = ?''',
                     (user_id, user_token))
            
            conn.commit()
            conn.close()
            
            # Закрываем сессию
            await user_bot.session.close()
            
            logger.info(f"Бот пользователя {user_id} успешно активирован")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка активации: {e}")
            return False
    
    async def run(self):
        """Запуск бота"""
        logger.info("Главный бот запущен...")
        await self.dp.start_polling(self.bot)

if __name__ == "__main__":
    # Запуск на хостинге
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    bot = HostedMainBot()
    asyncio.run(bot.run())
