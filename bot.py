import logging
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import json
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Структура для хранения данных бота
@dataclass
class Button:
    text: str
    url: str

@dataclass
class BotConfig:
    welcome_message: str = "Добро пожаловать! Это бот-переходник. Выберите нужную кнопку ниже:"
    buttons: List[Button] = None
    
    def __post_init__(self):
        if self.buttons is None:
            self.buttons = []

class BotData:
    def __init__(self, filename: str = "bot_data.json"):
        self.filename = filename
        self.config = BotConfig()
        self.load_data()
    
    def load_data(self):
        """Загрузить данные из файла"""
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.config.welcome_message = data.get('welcome_message', self.config.welcome_message)
                    buttons_data = data.get('buttons', [])
                    self.config.buttons = [Button(**btn) for btn in buttons_data]
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
    
    def save_data(self):
        """Сохранить данные в файл"""
        try:
            data = {
                'welcome_message': self.config.welcome_message,
                'buttons': [asdict(btn) for btn in self.config.buttons]
            }
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения данных: {e}")

# Инициализация хранилища данных
bot_data = BotData()

# ID администратора (замените на ваш)
ADMIN_ID = 7973988177

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("⚙️ Админ панель", callback_data='admin_panel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 Привет, администратор!\n\n{bot_data.config.welcome_message}",
            reply_markup=reply_markup
        )
    else:
        # Показываем кнопки для обычных пользователей
        await show_buttons(update, context)

async def show_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать кнопки пользователю"""
    if not bot_data.config.buttons:
        message = bot_data.config.welcome_message + "\n\nКнопки пока не настроены администратором."
        await update.message.reply_text(message) if update.message else await update.callback_query.message.reply_text(message)
        return
    
    # Создаем клавиатуру с кнопками
    keyboard = []
    for btn in bot_data.config.buttons:
        keyboard.append([InlineKeyboardButton(btn.text, url=btn.url)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(bot_data.config.welcome_message, reply_markup=reply_markup)
    else:
        await update.callback_query.edit_message_text(
            bot_data.config.welcome_message,
            reply_markup=reply_markup
        )

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ панель"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("✏️ Изменить приветствие", callback_data='edit_welcome')],
        [InlineKeyboardButton("📝 Добавить кнопку", callback_data='add_button')],
        [InlineKeyboardButton("🗑️ Удалить кнопку", callback_data='remove_button')],
        [InlineKeyboardButton("📋 Список кнопок", callback_data='list_buttons')],
        [InlineKeyboardButton("👀 Предпросмотр", callback_data='preview')],
        [InlineKeyboardButton("💾 Сохранить", callback_data='save')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "⚙️ Админ панель:\n\n"
        f"Приветствие: {bot_data.config.welcome_message[:50]}...\n"
        f"Количество кнопок: {len(bot_data.config.buttons)}",
        reply_markup=reply_markup
    )

async def edit_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Редактирование приветственного сообщения"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "✏️ Отправьте новое приветственное сообщение:"
    )
    context.user_data['awaiting_welcome'] = True

async def add_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление новой кнопки"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "📝 Для добавления кнопки отправьте сообщение в формате:\n"
        "`Название кнопки|ссылка`\n\n"
        "Пример:\n"
        "`Мой сайт|https://example.com`",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_button'] = True

async def remove_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление кнопки"""
    query = update.callback_query
    await query.answer()
    
    if not bot_data.config.buttons:
        await query.edit_message_text("Нет кнопок для удаления.")
        return
    
    keyboard = []
    for i, btn in enumerate(bot_data.config.buttons):
        keyboard.append([InlineKeyboardButton(f"{i+1}. {btn.text}", callback_data=f'delete_{i}')])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🗑️ Выберите кнопку для удаления:",
        reply_markup=reply_markup
    )

async def delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удалить конкретную кнопку"""
    query = update.callback_query
    await query.answer()
    
    button_index = int(query.data.split('_')[1])
    
    if 0 <= button_index < len(bot_data.config.buttons):
        removed_btn = bot_data.config.buttons.pop(button_index)
        await query.edit_message_text(f"✅ Кнопка '{removed_btn.text}' удалена!")
        bot_data.save_data()
    else:
        await query.edit_message_text("❌ Ошибка: кнопка не найдена")
    
    await admin_panel(update, context)

async def list_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список всех кнопок"""
    query = update.callback_query
    await query.answer()
    
    if not bot_data.config.buttons:
        text = "📋 Список кнопок пуст."
    else:
        text = "📋 Список кнопок:\n\n"
        for i, btn in enumerate(bot_data.config.buttons):
            text += f"{i+1}. {btn.text}\n   {btn.url}\n\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data='admin_panel')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup)

async def preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Предпросмотр бота"""
    query = update.callback_query
    await query.answer()
    
    await show_buttons(update, context)

async def save_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохранение данных"""
    query = update.callback_query
    await query.answer()
    
    bot_data.save_data()
    await query.edit_message_text("✅ Данные сохранены!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстовых сообщений"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        # Для обычных пользователей показываем кнопки
        await show_buttons(update, context)
        return
    
    message_text = update.message.text
    
    if context.user_data.get('awaiting_welcome'):
        # Сохраняем новое приветствие
        bot_data.config.welcome_message = message_text
        context.user_data['awaiting_welcome'] = False
        await update.message.reply_text("✅ Приветствие обновлено!")
        await admin_panel(update, context)
    
    elif context.user_data.get('awaiting_button'):
        # Добавляем новую кнопку
        try:
            if '|' in message_text:
                btn_text, btn_url = message_text.split('|', 1)
                btn_text = btn_text.strip()
                btn_url = btn_url.strip()
                
                # Проверка URL
                if not btn_url.startswith(('http://', 'https://')):
                    btn_url = 'https://' + btn_url
                
                bot_data.config.buttons.append(Button(btn_text, btn_url))
                context.user_data['awaiting_button'] = False
                await update.message.reply_text(f"✅ Кнопка '{btn_text}' добавлена!")
                await admin_panel(update, context)
            else:
                await update.message.reply_text("❌ Неправильный формат. Используйте: `Название|ссылка`", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Ошибка: {str(e)}")
    
    else:
        # Любое другое сообщение от админа
        await update.message.reply_text("Для управления ботом используйте админ панель. /start")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка callback запросов"""
    query = update.callback_query
    callback_data = query.data
    
    if callback_data == 'admin_panel':
        await admin_panel(update, context)
    elif callback_data == 'edit_welcome':
        await edit_welcome(update, context)
    elif callback_data == 'add_button':
        await add_button(update, context)
    elif callback_data == 'remove_button':
        await remove_button(update, context)
    elif callback_data == 'list_buttons':
        await list_buttons(update, context)
    elif callback_data == 'preview':
        await preview(update, context)
    elif callback_data == 'save':
        await save_data(update, context)
    elif callback_data.startswith('delete_'):
        await delete_button(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}")

def main():
    """Запуск бота"""
    # Токен берется из переменной окружения
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        logger.error("Токен бота не найден! Установите переменную окружения TELEGRAM_BOT_TOKEN")
        return
    
    # Создаем приложение
    application = Application.builder().token(token).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
