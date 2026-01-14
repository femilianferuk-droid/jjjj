import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
ADMIN_CHAT_ID = 7973988177  # ID администратора
SUPPORT_USERNAME = "@starfizovoi"  # Юзернейм поддержки
CARD_NUMBER = "2204120132703386"  # Номер карты для пополнения

# Хранилище данных (в реальном приложении используйте базу данных)
user_data_store = {}
pending_payments = {}

# Клавиатура главного меню
def main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='top_up')],
        [InlineKeyboardButton("🆘 Поддержка", callback_data='support')],
        [InlineKeyboardButton("💰 Баланс сайта", callback_data='site_balance')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для выбора суммы
def amount_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("10₽", callback_data='amount_10'),
            InlineKeyboardButton("50₽", callback_data='amount_50'),
            InlineKeyboardButton("100₽", callback_data='amount_100'),
        ],
        [
            InlineKeyboardButton("500₽", callback_data='amount_500'),
            InlineKeyboardButton("1000₽", callback_data='amount_1000'),
        ],
        [InlineKeyboardButton("💰 Другая сумма", callback_data='custom_amount')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для меню баланса сайта
def site_balance_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Указать ник на сайте", callback_data='set_site_nickname')],
        [InlineKeyboardButton("👤 Мой профиль", callback_data='my_profile')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='top_up')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# Клавиатура для админа (одобрить/отклонить)
def admin_decision_keyboard(payment_id):
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_{payment_id}'),
            InlineKeyboardButton("❌ Отклонить", callback_data=f'reject_{payment_id}')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        "Я бот для пополнения баланса.\n"
        "Выберите действие:"
    )
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=main_menu_keyboard())
    else:
        await update.callback_query.edit_message_text(welcome_text, reply_markup=main_menu_keyboard())

# Обработка нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'top_up':
        text = "💳 Выберите сумму для пополнения (от 10 до 1000₽):"
        await query.edit_message_text(text, reply_markup=amount_keyboard())
        
    elif query.data == 'support':
        text = f"🆘 Для связи с поддержкой:\n{SUPPORT_USERNAME}"
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif query.data == 'site_balance':
        balance = user_data_store.get(user_id, {}).get('balance', 0.0)
        site_nickname = user_data_store.get(user_id, {}).get('site_nickname', 'не указан')
        
        text = (
            f"💰 Ваш баланс на сайте: {balance}₽\n"
            f"👤 Ваш ник на сайте: {site_nickname}\n\n"
            f"Выберите действие:"
        )
        await query.edit_message_text(text, reply_markup=site_balance_keyboard())
        
    elif query.data == 'set_site_nickname':
        text = "📝 Введите ваш ник на сайте:"
        context.user_data['waiting_for_nickname'] = True
        await query.edit_message_text(text)
        
    elif query.data == 'my_profile':
        await show_profile(update, context)
        
    elif query.data == 'back_to_main':
        await start(update, context)
        
    elif query.data.startswith('amount_'):
        amount = int(query.data.split('_')[1])
        await process_payment_request(query, context, amount)
        
    elif query.data == 'custom_amount':
        text = "💰 Введите сумму для пополнения (от 10 до 1000₽):"
        context.user_data['waiting_for_amount'] = True
        await query.edit_message_text(text)
        
    elif query.data.startswith('approve_'):
        payment_id = query.data.split('_')[1]
        await approve_payment(update, context, payment_id)
        
    elif query.data.startswith('reject_'):
        payment_id = query.data.split('_')[1]
        await reject_payment(update, context, payment_id)

# Показать профиль пользователя
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user = query.from_user
    
    user_data = user_data_store.get(user_id, {})
    balance = user_data.get('balance', 0.0)
    site_nickname = user_data.get('site_nickname', 'не указан')
    
    text = (
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Имя в Telegram: {user.first_name}\n"
        f"📧 Username: @{user.username if user.username else 'не указан'}\n"
        f"💰 Баланс на сайте: *{balance}₽*\n"
        f"🎮 Ник на сайте: *{site_nickname}*\n\n"
        f"_Для смены ника используйте кнопку ниже_"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Изменить ник", callback_data='set_site_nickname')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='top_up')],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data='site_balance')]
    ]
    
    await query.edit_message_text(
        text, 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Команда /profile для быстрого доступа к профилю
async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    user_data = user_data_store.get(user_id, {})
    balance = user_data.get('balance', 0.0)
    site_nickname = user_data.get('site_nickname', 'не указан')
    
    text = (
        f"👤 *Ваш профиль*\n\n"
        f"🆔 ID: `{user_id}`\n"
        f"👤 Имя в Telegram: {user.first_name}\n"
        f"📧 Username: @{user.username if user.username else 'не указан'}\n"
        f"💰 Баланс на сайте: *{balance}₽*\n"
        f"🎮 Ник на сайте: *{site_nickname}*\n\n"
        f"_Для смены ника используйте кнопку ниже_"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Изменить ник", callback_data='set_site_nickname')],
        [InlineKeyboardButton("💳 Пополнить баланс", callback_data='top_up')],
        [InlineKeyboardButton("💰 Баланс сайта", callback_data='site_balance')],
        [InlineKeyboardButton("🏠 Главное меню", callback_data='back_to_main')]
    ]
    
    await update.message.reply_text(
        text, 
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработка ввода сообщений от пользователя
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text
    
    # Обработка ввода суммы для пополнения
    if 'waiting_for_amount' in context.user_data and context.user_data['waiting_for_amount']:
        try:
            amount = float(message_text)
            if amount < 10 or amount > 1000:
                await update.message.reply_text("❌ Сумма должна быть от 10 до 1000₽. Попробуйте снова:")
                return
            
            await process_payment_request(update, context, amount)
            context.user_data['waiting_for_amount'] = False
            
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите числовое значение (например: 150):")
    
    # Обработка ввода ника на сайте
    elif 'waiting_for_nickname' in context.user_data and context.user_data['waiting_for_nickname']:
        user_id = update.message.from_user.id
        
        # Сохраняем ник
        if user_id not in user_data_store:
            user_data_store[user_id] = {}
        
        user_data_store[user_id]['site_nickname'] = message_text
        context.user_data['waiting_for_nickname'] = False
        
        # Отправляем подтверждение
        await update.message.reply_text(
            f"✅ Ник успешно сохранен: *{message_text}*\n\n"
            "Теперь при пополнении баланса, средства будут зачислены на этот аккаунт.",
            parse_mode='Markdown',
            reply_markup=main_menu_keyboard()
        )
    
    # Обработка скриншотов оплаты
    elif update.message.photo:
        await handle_screenshot(update, context)

# Обработка запроса на пополнение
async def process_payment_request(update, context, amount):
    if isinstance(update, Update) and update.message:
        user = update.message.from_user
        chat_id = update.message.chat_id
        message_id = None
    else:
        query = update.callback_query
        user = query.from_user
        chat_id = query.message.chat_id
        message_id = query.message.message_id
    
    user_id = user.id
    
    # Проверяем, указан ли ник на сайте
    site_nickname = user_data_store.get(user_id, {}).get('site_nickname')
    if not site_nickname:
        text = (
            "❌ *Сначала укажите ваш ник на сайте!*\n\n"
            "Это необходимо для зачисления средств на правильный аккаунт."
        )
        
        keyboard = [
            [InlineKeyboardButton("📝 Указать ник", callback_data='set_site_nickname')],
            [InlineKeyboardButton("🔙 Назад", callback_data='top_up')]
        ]
        
        if message_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return
    
    payment_id = f"{user_id}_{datetime.now().timestamp()}"
    pending_payments[payment_id] = {
        'user_id': user_id,
        'username': user.username,
        'first_name': user.first_name,
        'site_nickname': site_nickname,
        'amount': amount,
        'status': 'waiting_for_payment'
    }
    
    text = (
        f"💳 *Запрос на пополнение {amount}₽*\n\n"
        f"👤 *Ваш ник на сайте:* {site_nickname}\n\n"
        f"*Инструкция по оплате:*\n"
        f"1️⃣ Переведите *{amount}₽* на карту:\n"
        f"`{CARD_NUMBER}`\n\n"
        f"2️⃣ После оплаты отправьте *скриншот чека* в этот чат.\n\n"
        f"⚠️ *Важно:*\n"
        f"• В комментарии к переводу укажите ваш ID: `{user_id}`\n"
        f"• Средства будут зачислены на ник: *{site_nickname}*"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Отменить", callback_data='top_up')]]
    
    if message_id:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Обработка скриншота
async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_id = user.id
    
    # Находим ожидающий платеж для этого пользователя
    payment_id = None
    payment_data = None
    
    for pid, data in pending_payments.items():
        if data['user_id'] == user_id and data['status'] == 'waiting_for_payment':
            payment_id = pid
            payment_data = data
            break
    
    if not payment_id:
        await update.message.reply_text(
            "❌ Сначала выберите сумму для пополнения!",
            reply_markup=main_menu_keyboard()
        )
        return
    
    # Обновляем статус платежа
    pending_payments[payment_id]['status'] = 'pending_admin_approval'
    pending_payments[payment_id]['screenshot_message_id'] = update.message.message_id
    
    # Отправляем уведомление пользователю
    await update.message.reply_text(
        "✅ Скриншот получен! Ожидайте подтверждения от администратора.\n"
        "Обычно это занимает несколько минут.",
        reply_markup=main_menu_keyboard()
    )
    
    # Отправляем уведомление админу
    admin_text = (
        f"🔄 *Новый запрос на пополнение!*\n\n"
        f"👤 *Пользователь:* {payment_data['first_name']} (@{payment_data['username']})\n"
        f"🆔 *ID:* `{payment_data['user_id']}`\n"
        f"🎮 *Ник на сайте:* {payment_data['site_nickname']}\n"
        f"💰 *Сумма:* {payment_data['amount']}₽\n"
        f"🆔 *ID платежа:* {payment_id}"
    )
    
    # Пересылаем скриншот админу
    await context.bot.send_photo(
        chat_id=ADMIN_CHAT_ID,
        photo=update.message.photo[-1].file_id,
        caption=admin_text,
        parse_mode='Markdown',
        reply_markup=admin_decision_keyboard(payment_id)
    )

# Одобрение платежа админом
async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: str):
    query = update.callback_query
    
    if payment_id not in pending_payments:
        await query.answer("Платеж не найден!", show_alert=True)
        return
    
    payment_data = pending_payments[payment_id]
    user_id = payment_data['user_id']
    site_nickname = payment_data['site_nickname']
    amount = payment_data['amount']
    
    # Обновляем баланс пользователя
    if user_id not in user_data_store:
        user_data_store[user_id] = {'balance': 0.0, 'site_nickname': site_nickname}
    
    user_data_store[user_id]['balance'] += amount
    
    # Уведомляем пользователя
    user_text = (
        f"✅ *Платеж подтвержден!*\n\n"
        f"💰 *Сумма:* {amount}₽\n"
        f"🎮 *Ник на сайте:* {site_nickname}\n"
        f"💵 *Баланс пополнен успешно!*\n"
        f"📊 *Текущий баланс:* {user_data_store[user_id]['balance']}₽"
    )
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=user_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {user_id}: {e}")
    
    # Уведомляем админа
    admin_update_text = (
        f"✅ *Платеж одобрен!*\n\n"
        f"🆔 *ID платежа:* {payment_id}\n"
        f"👤 *Пользователь:* {payment_data['first_name']}\n"
        f"🎮 *Ник на сайте:* {site_nickname}\n"
        f"💰 *Сумма:* {amount}₽\n"
        f"💳 *Новый баланс:* {user_data_store[user_id]['balance']}₽"
    )
    
    await query.edit_message_text(
        admin_update_text,
        parse_mode='Markdown'
    )
    
    # Удаляем из ожидающих
    del pending_payments[payment_id]

# Отклонение платежа админом
async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: str):
    query = update.callback_query
    
    if payment_id not in pending_payments:
        await query.answer("Платеж не найден!", show_alert=True)
        return
    
    payment_data = pending_payments[payment_id]
    site_nickname = payment_data['site_nickname']
    amount = payment_data['amount']
    
    # Уведомляем пользователя
    user_text = (
        f"❌ *Ваш запрос на пополнение отклонен!*\n\n"
        f"💰 *Сумма:* {amount}₽\n"
        f"🎮 *Ник на сайте:* {site_nickname}\n\n"
        f"ℹ️ *Возможные причины:*\n"
        f"• Неверный скриншот оплаты\n"
        f"• Несоответствие суммы\n"
        f"• Технические проблемы\n\n"
        f"📞 *Для уточнения деталей обратитесь в поддержку:* {SUPPORT_USERNAME}"
    )
    
    try:
        await context.bot.send_message(
            chat_id=payment_data['user_id'],
            text=user_text,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Не удалось отправить сообщение пользователю {payment_data['user_id']}: {e}")
    
    # Уведомляем админа
    await query.edit_message_text(
        f"❌ *Платеж отклонен!*\n"
        f"🆔 ID платежа: {payment_id}\n"
        f"👤 Пользователь уведомлен",
        parse_mode='Markdown'
    )
    
    # Удаляем из ожидающих
    del pending_payments[payment_id]

# Обработка неизвестных команд
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤔 Неизвестная команда. Используйте /start для начала работы.",
        reply_markup=main_menu_keyboard()
    )

# Основная функция
def main():
    # Получаем токен из переменной окружения
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    
    if not TOKEN:
        raise ValueError("Токен бота не найден! Установите переменную окружения TELEGRAM_BOT_TOKEN")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_screenshot))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Запускаем бота
    print("🤖 Бот запущен...")
    print(f"👑 Админ ID: {ADMIN_CHAT_ID}")
    print(f"💬 Поддержка: {SUPPORT_USERNAME}")
    print("⚡ Бот готов к работе!")
    
    # Исправленный запуск polling
    application.run_polling()

if __name__ == '__main__':
    main()
