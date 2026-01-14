import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, LabeledPrice, PreCheckoutQuery, SuccessfulPayment, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Роутер для обработки команд
router = Router()

# ID администратора для уведомлений
ADMIN_ID = 7973988177  # Ваш ID

# Создаем клавиатуру с кнопкой "Донат"
def get_main_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🎁 Сделать донат", callback_data="donate")
    keyboard.button(text="ℹ️ О боте", callback_data="about")
    return keyboard.as_markup()

# Создаем клавиатуру для оплаты
def get_payment_keyboard(payload: str):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="💳 Оплатить 10 Stars", pay=True)
    keyboard.button(text="↩️ Назад", callback_data="back_to_main")
    return keyboard.as_markup()

# Клавиатура для админа
def get_admin_keyboard(user_id: int):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="👤 Написать пользователю", url=f"tg://user?id={user_id}")
    return keyboard.as_markup()

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    welcome_text = (
        "👋 Привет!\n\n"
        "Это бот для приема донатов через Telegram Stars.\n"
        "Нажмите кнопку ниже, чтобы поддержать проект!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())

# Обработчик нажатия на кнопку "Донат"
@router.callback_query(F.data == "donate")
async def process_donate(callback_query):
    await callback_query.answer()
    
    # Создаем уникальный payload с timestamp
    timestamp = int(datetime.now().timestamp())
    payload = f"donation_{callback_query.from_user.id}_{timestamp}"
    
    await callback_query.message.answer_invoice(
        title="Донат на развитие проекта",
        description="Ваша поддержка поможет развивать проект дальше!\n\nСумма: 10 Telegram Stars",
        provider_token="",  # Оставляем пустым для Telegram Stars
        currency="XTR",  # Валюта Telegram Stars
        prices=[LabeledPrice(label="Донат 10 Stars", amount=10)],  # 10 Stars
        payload=payload,
        reply_markup=get_payment_keyboard(payload),
        need_name=False,
        need_phone_number=False,
        need_email=False,
        need_shipping_address=False,
        is_flexible=False
    )

# Обработчик возврата в главное меню
@router.callback_query(F.data == "back_to_main")
async def process_back(callback_query):
    await callback_query.answer()
    await callback_query.message.edit_text(
        "👋 Привет!\n\n"
        "Это бот для приема донатов через Telegram Stars.\n"
        "Нажмите кнопку ниже, чтобы поддержать проект!",
        reply_markup=get_main_keyboard()
    )

# Обработчик информации о боте
@router.callback_query(F.data == "about")
async def process_about(callback_query):
    await callback_query.answer()
    about_text = (
        "🤖 О боте:\n\n"
        "Этот бот принимает донаты через Telegram Stars.\n"
        "Telegram Stars — это внутренняя валюта Telegram.\n\n"
        "Минимальный донат: 10 Stars\n\n"
        "Спасибо за поддержку! ❤️"
    )
    await callback_query.message.edit_text(
        about_text,
        reply_markup=InlineKeyboardBuilder()
            .button(text="↩️ Назад", callback_data="back_to_main")
            .as_markup()
    )

# Обработчик предварительного запроса оплаты
@router.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

# Обработчик успешной оплаты
@router.message(F.successful_payment)
async def process_successful_payment(message: Message, bot: Bot):
    # Уведомляем пользователя
    user = message.from_user
    await message.answer(
        f"✅ Спасибо за донат, {user.first_name}!\n\n"
        f"Вы успешно поддержали проект на 10 Telegram Stars!\n"
        f"Ваша поддержка очень важна для нас! ❤️",
        reply_markup=get_main_keyboard()
    )
    
    # Уведомляем администратора
    try:
        admin_text = (
            f"🎉 Новый донат!\n\n"
            f"👤 Пользователь: {user.first_name} {user.last_name or ''}\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Username: @{user.username if user.username else 'нет'}\n"
            f"💰 Сумма: 10 Telegram Stars\n"
            f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🎯 Payload: {message.successful_payment.invoice_payload}"
        )
        
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=admin_text,
            reply_markup=get_admin_keyboard(user.id)
        )
        logger.info(f"Уведомление отправлено администратору {ADMIN_ID}")
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомления админу: {e}")

# Основная функция запуска бота
async def main():
    # Получаем токен бота из переменных окружения
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    bot_token = os.getenv("BOT_TOKEN")
    
    if not bot_token:
        logger.error("BOT_TOKEN не найден в переменных окружения!")
        return
    
    # Создаем бота и диспетчер
    bot = Bot(token=bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    
    # Запускаем бота
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
