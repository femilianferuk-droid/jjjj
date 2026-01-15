import os
import asyncio
import logging
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, 
    LabeledPrice, PreCheckoutQuery, SuccessfulPayment,
    Message, CallbackQuery
)
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
import aiohttp
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация из переменных окружения
API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SMMWAY_API_KEY = os.getenv('SMMWAY_API_KEY', 'FjypaNPpdFqTXdwTbTwXLiwMC6GcPzyZ2nMwjrH0AsRzhsgAJlp1sY7iK6vU')
SMMWAY_API_URL = 'https://smmway.com/api/v2'

# Проверка токена
if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не найден в переменных окружения!")

# Повышение цен на 20%
PRICE_MULTIPLIER = 1.2

# Telegram Stars курс: 1 звезда = 1 рубль
STARS_PER_RUB = 1

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния FSM
class OrderState(StatesGroup):
    waiting_for_link = State()
    waiting_for_quantity = State()
    waiting_for_payment = State()

# Кэш для услуг
services_cache = {}
categories_cache = {}
cache_time = None
CACHE_DURATION = 300  # 5 минут

# Хранилище заказов (в production используйте БД)
user_orders = {}
active_orders = {}

# ========== Вспомогательные функции ==========

async def get_smmway_services() -> Dict:
    """Получение списка услуг с кэшированием"""
    global cache_time
    
    if cache_time and (datetime.now() - cache_time).seconds < CACHE_DURATION:
        return services_cache
    
    async with aiohttp.ClientSession() as session:
        params = {'key': SMMWAY_API_KEY, 'action': 'services'}
        try:
            async with session.get(SMMWAY_API_URL, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        services_cache.clear()
                        categories_cache.clear()
                        
                        # Организуем услуги по категориям
                        for service in data:
                            category = str(service.get('category', 'Другие'))
                            if category not in services_cache:
                                services_cache[category] = []
                                categories_cache[category] = service.get('category_name', category)
                            
                            # Рассчитываем цену с наценкой 20%
                            original_price = float(service.get('rate', 0))
                            adjusted_price = round(original_price * PRICE_MULTIPLIER, 2)
                            
                            service_info = {
                                'id': int(service.get('service')),
                                'name': service.get('name'),
                                'category': category,
                                'rate': adjusted_price,  # Цена с наценкой за 1000
                                'min': int(service.get('min', 1)),
                                'max': int(service.get('max', 10000)),
                                'original_price': original_price,
                                'type': service.get('type', 'default')
                            }
                            services_cache[category].append(service_info)
                        
                        cache_time = datetime.now()
                        logger.info(f"Загружено {len(data)} услуг из {len(services_cache)} категорий")
                        return services_cache
                    else:
                        logger.error(f"Некорректный ответ от API: {data}")
                else:
                    logger.error(f"Ошибка API: {response.status}")
        except Exception as e:
            logger.error(f"Ошибка при получении услуг: {e}")
    
    # Возвращаем кэш, даже если он устарел, в случае ошибки
    return services_cache or {}

async def get_smmway_balance() -> float:
    """Получение баланса из SmmWay"""
    async with aiohttp.ClientSession() as session:
        params = {'key': SMMWAY_API_KEY, 'action': 'balance'}
        try:
            async with session.get(SMMWAY_API_URL, params=params, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data.get('balance', 0))
                else:
                    logger.error(f"Ошибка получения баланса: {response.status}")
        except Exception as e:
            logger.error(f"Ошибка при получении баланса: {e}")
    return 0

async def create_smmway_order(service_id: int, quantity: int, link: str) -> Dict:
    """Создание заказа в SmmWay"""
    async with aiohttp.ClientSession() as session:
        params = {
            'key': SMMWAY_API_KEY,
            'action': 'add',
            'service': service_id,
            'quantity': quantity,
            'link': link
        }
        try:
            async with session.post(SMMWAY_API_URL, data=params, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    logger.error(f"Ошибка создания заказа: {response.status}")
                    return {"error": f"HTTP {response.status}"}
        except Exception as e:
            logger.error(f"Ошибка при создании заказа: {e}")
            return {"error": str(e)}

async def get_smmway_order_status(order_id: int) -> Dict:
    """Получение статуса заказа"""
    async with aiohttp.ClientSession() as session:
        params = {
            'key': SMMWAY_API_KEY,
            'action': 'status',
            'order': order_id
        }
        try:
            async with session.get(SMMWAY_API_URL, params=params, timeout=10) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
    return {}

async def create_invoice(chat_id: int, amount_rub: float, service_name: str, order_id: str) -> bool:
    """Создание счета для оплаты через Telegram Stars"""
    try:
        # Конвертируем рубли в звезды (1 рубль = 1 звезда)
        stars_amount = int(amount_rub * STARS_PER_RUB)
        
        # Создаем чек
        prices = [LabeledPrice(label=service_name, amount=stars_amount)]
        
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"💎 Оплата услуги: {service_name}",
            description=f"Накрутка {service_name}\nСумма: {amount_rub:.2f}₽",
            provider_token="",  # Для Telegram Stars оставляем пустым
            currency="XTR",  # Код валюты для Telegram Stars
            prices=prices,
            payload=order_id,  # Используем order_id как payload
            start_parameter="smmway_payment",
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False,
            protect_content=False,
            request_timeout=15
        )
        return True
    except Exception as e:
        logger.error(f"Ошибка создания счета: {e}")
        return False

async def calculate_order_price(service_rate: float, quantity: int) -> float:
    """Расчет стоимости заказа"""
    price_per_unit = service_rate / 1000  # Цена за 1 единицу
    total = price_per_unit * quantity
    return round(total, 2)

# ========== Команды бота ==========

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Команда /start"""
    welcome_text = """
🎉 <b>Добро пожаловать в SMMWay Bot!</b>

🤖 <b>Я помогу вам с накруткой во всех социальных сетях:</b>
• Instagram • TikTok • YouTube • Telegram
• VK • Facebook • Twitter • Одноклассники

💰 <b>Цены на 20% выше чем на сайте SmmWay</b>
💫 <b>Оплата через Telegram Stars</b> (1₽ = 1 звезда)

📋 <b>Доступные команды:</b>
/services - 📊 Посмотреть все услуги
/balance - 💰 Узнать баланс бота
/myorders - 📦 Мои заказы
/help - ❓ Помощь и инструкция

💎 <b>Для начала работы нажмите /services</b>
    """
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(text="📊 Все услуги", callback_data="show_services"))
    keyboard.add(InlineKeyboardButton(text="💰 Баланс", callback_data="show_balance"))
    keyboard.add(InlineKeyboardButton(text="📦 Мои заказы", callback_data="my_orders"))
    keyboard.add(InlineKeyboardButton(text="❓ Помощь", callback_data="show_help"))
    
    await message.answer(welcome_text, reply_markup=keyboard.as_markup())

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Команда /help"""
    help_text = """
❓ <b>Инструкция по использованию бота:</b>

1. 🛒 <b>Выбор услуги:</b>
   - Используйте /services для просмотра категорий
   - Выберите нужную категорию
   - Выберите конкретную услугу

2. 💰 <b>Оплата:</b>
   - Оплата происходит через Telegram Stars
   - 1 российский рубль = 1 звезда
   - После выбора услуги бот создаст счет

3. 📦 <b>Создание заказа:</b>
   - После оплаты укажите ссылку на аккаунт/пост
   - Укажите количество (в пределах минимального и максимального)
   - Заказ автоматически создается в системе

4. ⏱️ <b>Статус заказа:</b>
   - Заказы начинаются в течение 5-30 минут
   - Скорость выполнения зависит от услуги
   - Гарантия качества от SmmWay

⚠️ <b>Важно:</b>
- Все платежи защищены Telegram
- Возврат средств только при невозможности выполнения заказа
- Ссылка должна быть публичной и доступной

📞 <b>Поддержка:</b> Для вопросов обращайтесь к администратору.
    """
    await message.answer(help_text)

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    """Команда /balance"""
    try:
        balance = await get_smmway_balance()
        balance_text = f"""
💰 <b>Баланс системы:</b> <code>{balance:.2f}₽</code>

💡 Баланс используется для обработки ваших заказов.
Все платежи проходят через безопасную систему Telegram Stars.

📊 <b>Ваши данные:</b>
ID: <code>{message.from_user.id}</code>
Имя: {message.from_user.full_name}
        """
        await message.answer(balance_text)
    except Exception as e:
        logger.error(f"Ошибка в команде balance: {e}")
        await message.answer("⚠️ Не удалось получить баланс. Попробуйте позже.")

@dp.message(Command("services"))
async def cmd_services(message: types.Message):
    """Показать категории услуг"""
    await show_categories(message)

@dp.message(Command("myorders"))
async def cmd_myorders(message: types.Message):
    """Показать заказы пользователя"""
    user_id = message.from_user.id
    orders = user_orders.get(user_id, [])
    
    if not orders:
        await message.answer("📭 У вас пока нет заказов.")
        return
    
    text = "📦 <b>Ваши заказы:</b>\n\n"
    for i, order in enumerate(orders[-10:], 1):  # Показываем последние 10 заказов
        status = "✅ Оплачен" if order.get('paid') else "⏳ Ожидает оплаты"
        text += f"{i}. {order.get('service_name', 'Неизвестно')}\n"
        text += f"   Сумма: {order.get('amount', 0):.2f}₽\n"
        text += f"   Статус: {status}\n"
        if order.get('smmway_order_id'):
            text += f"   ID заказа: {order.get('smmway_order_id')}\n"
        text += "\n"
    
    await message.answer(text)

# ========== Callback обработчики ==========

@dp.callback_query(F.data == "show_services")
async def callback_show_services(callback: types.CallbackQuery):
    await show_categories(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "show_balance")
async def callback_show_balance(callback: types.CallbackQuery):
    await cmd_balance(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "my_orders")
async def callback_my_orders(callback: types.CallbackQuery):
    await cmd_myorders(callback.message)
    await callback.answer()

@dp.callback_query(F.data == "show_help")
async def callback_show_help(callback: types.CallbackQuery):
    await cmd_help(callback.message)
    await callback.answer()

@dp.callback_query(F.data.startswith("category_"))
async def callback_category(callback: types.CallbackQuery):
    """Обработка выбора категории"""
    category_id = callback.data.replace("category_", "")
    services = await get_smmway_services()
    
    if not services or category_id not in services:
        await callback.answer("Категория не найдена")
        return
    
    category_services = services[category_id]
    category_name = categories_cache.get(category_id, category_id)
    
    keyboard = InlineKeyboardBuilder()
    
    # Добавляем услуги категории
    for service in category_services[:30]:  # Ограничиваем 30 услугами
        service_name = service['name']
        if len(service_name) > 25:
            service_name = service_name[:22] + "..."
        
        # Цена за 1000
        price_per_k = service['rate']
        
        btn_text = f"{service_name} - {price_per_k}₽/1000"
        keyboard.row(InlineKeyboardButton(
            text=btn_text,
            callback_data=f"service_{service['id']}"
        ))
    
    # Кнопка назад
    keyboard.row(InlineKeyboardButton(
        text="🔙 Назад к категориям",
        callback_data="back_to_categories"
    ))
    
    text = f"<b>📁 {category_name}</b>\n\nВыберите услугу (цена указана за 1000 единиц):"
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    except:
        await callback.message.answer(text, reply_markup=keyboard.as_markup())
    
    await callback.answer()

@dp.callback_query(F.data == "back_to_categories")
async def callback_back_to_categories(callback: types.CallbackQuery):
    """Возврат к списку категорий"""
    await show_categories(callback.message, edit=True)
    await callback.answer()

@dp.callback_query(F.data.startswith("service_"))
async def callback_service(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора услуги"""
    service_id = int(callback.data.replace("service_", ""))
    
    # Ищем услугу
    services = await get_smmway_services()
    service_info = None
    
    for category in services.values():
        for service in category:
            if service['id'] == service_id:
                service_info = service
                break
        if service_info:
            break
    
    if not service_info:
        await callback.answer("Услуга не найдена")
        return
    
    # Сохраняем информацию об услуге в состоянии
    await state.update_data(
        service_id=service_id,
        service_name=service_info['name'],
        service_rate=service_info['rate'],
        min_quantity=service_info['min'],
        max_quantity=service_info['max']
    )
    
    # Формируем информацию об услуге
    text = f"""
<b>🛒 {service_info['name']}</b>

💰 <b>Цена:</b> <code>{service_info['rate']}₽</code> за 1000 единиц
📊 <b>Количество:</b> от {service_info['min']} до {service_info['max']}
🏷️ <b>Категория:</b> {categories_cache.get(service_info['category'], service_info['category'])}

💡 <b>Цена на сайте SmmWay:</b> {service_info['original_price']}₽
🎯 <b>Наша цена (с наценкой 20%):</b> {service_info['rate']}₽

<b>Для заказа нажмите кнопку ниже</b>
    """
    
    keyboard = InlineKeyboardBuilder()
    keyboard.add(InlineKeyboardButton(
        text="🛒 Заказать эту услугу",
        callback_data=f"start_order_{service_id}"
    ))
    keyboard.add(InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"category_{service_info['category']}"
    ))
    
    try:
        await callback.message.edit_text(text, reply_markup=keyboard.as_markup())
    except:
        await callback.message.answer(text, reply_markup=keyboard.as_markup())
    
    await callback.answer()

@dp.callback_query(F.data.startswith("start_order_"))
async def callback_start_order(callback: types.CallbackQuery, state: FSMContext):
    """Начало оформления заказа"""
    service_id = int(callback.data.replace("start_order_", ""))
    
    # Получаем данные услуги
    services = await get_smmway_services()
    service_info = None
    
    for category in services.values():
        for service in category:
            if service['id'] == service_id:
                service_info = service
                break
        if service_info:
            break
    
    if not service_info:
        await callback.answer("Услуга не найдена")
        return
    
    # Сохраняем в состоянии
    await state.update_data(
        service_id=service_id,
        service_name=service_info['name'],
        service_rate=service_info['rate'],
        min_quantity=service_info['min'],
        max_quantity=service_info['max']
    )
    
    # Просим ссылку
    text = f"""
<b>📝 Оформление заказа: {service_info['name']}</b>

Пожалуйста, отправьте мне <b>ссылку</b> на:
• Аккаунт (для подписчиков)
• Пост (для лайков, комментариев, просмотров)
• Видео (для просмотров YouTube/TikTok)
• Канал (для подписчиков Telegram)

Примеры:
https://instagram.com/username
https://t.me/channelname
https://youtube.com/watch?v=...
https://vk.com/wall-12345_67890

<b>Отправьте ссылку сейчас:</b>
    """
    
    await state.set_state(OrderState.waiting_for_link)
    
    try:
        await callback.message.edit_text(text)
    except:
        await callback.message.answer(text)
    
    await callback.answer()

@dp.message(OrderState.waiting_for_link)
async def process_link(message: Message, state: FSMContext):
    """Обработка ссылки от пользователя"""
    link = message.text.strip()
    
    # Простая валидация ссылки
    if not (link.startswith('http://') or link.startswith('https://')):
        await message.answer("⚠️ Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://")
        return
    
    # Сохраняем ссылку
    await state.update_data(link=link)
    
    # Получаем данные об услуге
    data = await state.get_data()
    min_qty = data.get('min_quantity', 100)
    max_qty = data.get('max_quantity', 10000)
    service_name = data.get('service_name', 'Услуга')
    service_rate = data.get('service_rate', 10)
    
    # Просим количество
    text = f"""
<b>📊 Укажите количество:</b>

Услуга: {service_name}
Ссылка: {link[:50]}...

<b>Минимальное количество:</b> {min_qty}
<b>Максимальное количество:</b> {max_qty}

💰 <b>Цена:</b> {service_rate}₽ за 1000 единиц

<b>Пример расчета:</b>
1000 единиц = {service_rate}₽
5000 единиц = {service_rate * 5}₽
10000 единиц = {service_rate * 10}₽

<b>Введите количество числом:</b>
    """
    
    await state.set_state(OrderState.waiting_for_quantity)
    await message.answer(text)

@dp.message(OrderState.waiting_for_quantity)
async def process_quantity(message: Message, state: FSMContext):
    """Обработка количества от пользователя"""
    try:
        quantity = int(message.text.strip())
        
        # Получаем данные
        data = await state.get_data()
        min_qty = data.get('min_quantity', 100)
        max_qty = data.get('max_quantity', 10000)
        service_name = data.get('service_name', 'Услуга')
        service_rate = data.get('service_rate', 10)
        link = data.get('link', '')
        service_id = data.get('service_id')
        
        # Проверяем диапазон
        if quantity < min_qty:
            await message.answer(f"⚠️ Минимальное количество: {min_qty}")
            return
        if quantity > max_qty:
            await message.answer(f"⚠️ Максимальное количество: {max_qty}")
            return
        
        # Рассчитываем стоимость
        price_per_unit = service_rate / 1000
        total_price = round(price_per_unit * quantity, 2)
        
        # Сохраняем данные
        await state.update_data(
            quantity=quantity,
            total_price=total_price
        )
        
        # Создаем временный заказ
        order_id = f"{message.from_user.id}_{int(datetime.now().timestamp())}"
        
        # Показываем подтверждение
        text = f"""
<b>✅ Подтверждение заказа:</b>

Услуга: {service_name}
Ссылка: {link[:50]}...
Количество: {quantity} единиц
Цена за 1000: {service_rate}₽

💰 <b>Итого к оплате:</b> {total_price}₽
⭐ <b>Telegram Stars:</b> {int(total_price * STARS_PER_RUB)} звезд

<b>Для оплаты нажмите кнопку ниже:</b>
        """
        
        keyboard = InlineKeyboardBuilder()
        keyboard.add(InlineKeyboardButton(
            text=f"💎 Оплатить {total_price}₽",
            callback_data=f"create_payment_{order_id}"
        ))
        keyboard.add(InlineKeyboardButton(
            text="❌ Отменить",
            callback_data="cancel_order"
        ))
        
        # Сохраняем заказ во временное хранилище
        user_id = message.from_user.id
        if user_id not in user_orders:
            user_orders[user_id] = []
        
        order_data = {
            'order_id': order_id,
            'service_id': service_id,
            'service_name': service_name,
            'link': link,
            'quantity': quantity,
            'amount': total_price,
            'created_at': datetime.now().isoformat(),
            'paid': False,
            'user_id': user_id
        }
        
        user_orders[user_id].append(order_data)
        active_orders[order_id] = order_data
        await state.update_data(order_id=order_id)
        
        await message.answer(text, reply_markup=keyboard.as_markup())
        
    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите число")
    except Exception as e:
        logger.error(f"Ошибка обработки количества: {e}")
        await message.answer("⚠️ Произошла ошибка. Попробуйте снова.")

@dp.callback_query(F.data.startswith("create_payment_"))
async def callback_create_payment(callback: types.CallbackQuery, state: FSMContext):
    """Создание платежа"""
    order_id = callback.data.replace("create_payment_", "")
    
    if order_id not in active_orders:
        await callback.answer("Заказ не найден")
        return
    
    order_data = active_orders[order_id]
    
    # Создаем счет
    success = await create_invoice(
        chat_id=callback.from_user.id,
        amount_rub=order_data['amount'],
        service_name=order_data['service_name'],
        order_id=order_id
    )
    
    if success:
        await state.set_state(OrderState.waiting_for_payment)
        await state.update_data(order_id=order_id)
        await callback.answer("Счет создан. Проверьте чат с ботом.")
    else:
        await callback.answer("Ошибка создания счета")

@dp.callback_query(F.data == "cancel_order")
async def callback_cancel_order(callback: types.CallbackQuery, state: FSMContext):
    """Отмена заказа"""
    await state.clear()
    await callback.message.edit_text("❌ Заказ отменен.")
    await callback.answer()

# ========== Обработка платежей ==========

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    """Обработка предварительного запроса на оплату"""
    order_id = pre_checkout_query.invoice_payload
    
    if order_id not in active_orders:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False, 
                                           error_message="Заказ не найден")
        return
    
    order_data = active_orders[order_id]
    
    # Проверяем, не оплачен ли уже заказ
    if order_data.get('paid'):
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False,
                                           error_message="Заказ уже оплачен")
        return
    
    # Все проверки пройдены
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def process_successful_payment(message: Message):
    """Обработка успешного платежа"""
    payment = message.successful_payment
    order_id = payment.invoice_payload
    
    if order_id not in active_orders:
        await message.answer("⚠️ Ошибка: заказ не найден")
        return
    
    order_data = active_orders[order_id]
    
    # Помечаем как оплаченный
    order_data['paid'] = True
    order_data['payment_id'] = payment.telegram_payment_charge_id
    order_data['paid_at'] = datetime.now().isoformat()
    
    # Обновляем в user_orders
    user_id = message.from_user.id
    for i, order in enumerate(user_orders.get(user_id, [])):
        if order['order_id'] == order_id:
            user_orders[user_id][i] = order_data
            break
    
    # Создаем заказ в SmmWay
    smmway_result = await create_smmway_order(
        service_id=order_data['service_id'],
        quantity=order_data['quantity'],
        link=order_data['link']
    )
    
    # Формируем ответ
    text = f"""
✅ <b>Оплата успешно принята!</b>

💰 Сумма: {order_data['amount']}₽
🛒 Услуга: {order_data['service_name']}
🔗 Ссылка: {order_data['link'][:50]}...
📊 Количество: {order_data['quantity']}

"""
    
    if smmway_result and 'order' in smmway_result:
        order_data['smmway_order_id'] = smmway_result['order']
        text += f"📦 <b>ID заказа SmmWay:</b> {smmway_result['order']}\n"
        text += f"🔄 <b>Статус:</b> В обработке\n\n"
        text += f"Заказ принят в работу. Начнется в течение 5-30 минут."
    else:
        text += f"⚠️ <b>Внимание:</b> Заказ создан, но возникла ошибка синхронизации с SmmWay.\n"
        text += f"Администратор проверит ваш заказ вручную.\n\n"
    
    text += f"\n<b>Спасибо за покупку!</b>"
    
    await message.answer(text)
    
    # Очищаем активные заказы (можно оставить для истории)
    # del active_orders[order_id]

# ========== Вспомогательные функции интерфейса ==========

async def show_categories(message: Message, edit: bool = False):
    """Показать список категорий"""
    services = await get_smmway_services()
    
    if not services:
        text = "⚠️ <b>Не удалось загрузить услуги. Попробуйте позже.</b>"
        if edit:
            try:
                await message.edit_text(text)
            except:
                await message.answer(text)
        else:
            await message.answer(text)
        return
    
    keyboard = InlineKeyboardBuilder()
    
    # Создаем кнопки категорий
    for category_id, category_services in services.items():
        category_name = categories_cache.get(category_id, category_id)
        services_count = len(category_services)
        
        # Обрезаем длинные названия
        if len(category_name) > 20:
            display_name = category_name[:17] + "..."
        else:
            display_name = category_name
            
        btn_text = f"{display_name} ({services_count})"
        
        keyboard.row(InlineKeyboardButton(
            text=btn_text,
            callback_data=f"category_{category_id}"
        ))
    
    # Кнопка обновления
    keyboard.row(InlineKeyboardButton(
        text="🔄 Обновить список",
        callback_data="refresh_services"
    ))
    
    keyboard.row(InlineKeyboardButton(
        text="💰 Баланс",
        callback_data="show_balance"
    ))
    
    text = "<b>📁 Выберите категорию услуг:</b>"
    
    if edit:
        try:
            await message.edit_text(text, reply_markup=keyboard.as_markup())
        except:
            await message.answer(text, reply_markup=keyboard.as_markup())
    else:
        await message.answer(text, reply_markup=keyboard.as_markup())

@dp.callback_query(F.data == "refresh_services")
async def callback_refresh_services(callback: types.CallbackQuery):
    """Обновление списка услуг"""
    global cache_time
    cache_time = None  # Сбрасываем кэш
    
    await callback.answer("Обновляем список услуг...")
    await show_categories(callback.message, edit=True)

# ========== Запуск бота ==========

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск SMMWay бота...")
    
    # Проверяем подключение к API
    try:
        services = await get_smmway_services()
        if services:
            logger.info(f"Бот успешно подключился к SmmWay API. Категорий: {len(services)}")
        else:
            logger.warning("Не удалось загрузить услуги. Проверьте API ключ.")
        
        balance = await get_smmway_balance()
        logger.info(f"Баланс SmmWay: {balance:.2f}₽")
        
    except Exception as e:
        logger.error(f"Ошибка при проверке API: {e}")
    
    # Запускаем бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
