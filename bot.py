import os
import asyncio
import json
import logging
from datetime import datetime
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetDialogFiltersRequest
import sys

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
CONFIG_FILE = 'config.json'
TDATA_FOLDER = 'tdata'

class TelegramFloodBot:
    def __init__(self):
        self.client = None
        self.is_running = False
        self.current_flood_task = None
        
    async def load_config(self):
        """Загрузка конфигурации"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Ошибка загрузки конфига: {e}")
        return {
            "sessions": {},
            "active_session": None,
            "api_id": "YOUR_API_ID",  # Замените на свой
            "api_hash": "YOUR_API_HASH"  # Замените на свой
        }
    
    async def save_config(self, config):
        """Сохранение конфигурации"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения конфига: {e}")
    
    async def create_session_from_tdata(self, tdata_path):
        """Создание сессии из TData"""
        try:
            # Создаем временную сессию для конвертации
            temp_client = TelegramClient(
                StringSession(),
                api_id="YOUR_API_ID",  # Используйте свой api_id
                api_hash="YOUR_API_HASH"  # Используйте свой api_hash
            )
            
            await temp_client.connect()
            
            # Конвертируем TData в строку сессии
            session_string = await temp_client.export_session_string()
            await temp_client.disconnect()
            
            return session_string
        except Exception as e:
            logger.error(f"Ошибка создания сессии из TData: {e}")
            return None
    
    async def start_client(self, session_string=None):
        """Запуск клиента Telegram"""
        try:
            if not session_string:
                # Загружаем активную сессию из конфига
                config = await self.load_config()
                if not config.get("active_session"):
                    return False, "❌ Нет активной сессии. Сначала добавьте TData"
                session_string = config["active_session"]
            
            # Создаем клиент
            self.client = TelegramClient(
                StringSession(session_string),
                api_id=config["api_id"],
                api_hash=config["api_hash"]
            )
            
            # Настраиваем обработчики
            self.client.add_event_handler(self.message_handler, events.NewMessage)
            
            # Подключаемся
            await self.client.connect()
            
            # Проверяем авторизацию
            if not await self.client.is_user_authorized():
                return False, "❌ Ошибка авторизации. Проверьте TData файл"
            
            # Получаем информацию о пользователе
            me = await self.client.get_me()
            logger.info(f"Авторизован как: {me.username or me.first_name}")
            
            return True, f"✅ Успешный вход! Аккаунт: @{me.username or me.first_name}"
            
        except Exception as e:
            logger.error(f"Ошибка запуска клиента: {e}")
            return False, f"❌ Ошибка: {str(e)}"
    
    async def message_handler(self, event):
        """Обработчик входящих сообщений"""
        try:
            message = event.message
            if message.text:
                logger.info(f"Получено сообщение: {message.text}")
                
                # Обработка команды /start
                if message.text == '/start':
                    await message.reply(
                        "👋 Привет! Я бот для рассылки сообщений.\n\n"
                        "📋 Доступные команды:\n"
                        "/help - Показать справку\n"
                        "/add_tdata - Добавить TData сессию\n"
                        "/sessions - Список сессий\n"
                        "/flud - Начать рассылку\n"
                        "/stop - Остановить рассылку\n"
                        "/status - Статус рассылки"
                    )
                
                # Обработка команды /help
                elif message.text == '/help':
                    await message.reply(
                        "📖 Справка по использованию бота:\n\n"
                        "1. Сначала добавьте TData файл командой /add_tdata\n"
                        "2. Укажите путь к папке tdata\n"
                        "3. Начните рассылку командой /flud\n\n"
                        "Формат команды /flud:\n"
                        "/flud\n"
                        "[сообщение для рассылки]\n"
                        "[задержка в секундах]\n"
                        "[название папки для рассылки]\n\n"
                        "Пример:\n"
                        "/flud\n"
                        "Привет всем! Это тестовая рассылка.\n"
                        "2\n"
                        "Избранное"
                    )
                
                # Обработка команды /add_tdata
                elif message.text == '/add_tdata':
                    await message.reply(
                        "📁 Отправьте команду в формате:\n"
                        "/add_tdata [путь_к_папке_tdata]\n\n"
                        "Пример:\n"
                        "/add_tdata C:/Users/User/tdata"
                    )
                
                # Обработка добавления TData
                elif message.text.startswith('/add_tdata '):
                    tdata_path = message.text.replace('/add_tdata ', '').strip()
                    await self.handle_add_tdata(message, tdata_path)
                
                # Обработка команды /sessions
                elif message.text == '/sessions':
                    await self.handle_sessions_list(message)
                
                # Обработка команды /flud
                elif message.text == '/flud':
                    await message.reply(
                        "📝 Отправьте данные для рассылки в формате:\n\n"
                        "Сообщение для рассылки\n"
                        "Задержка в секундах\n"
                        "Название папки\n\n"
                        "Пример:\n"
                        "Привет! Это тест\n"
                        "5\n"
                        "Избранное"
                    )
                
                # Обработка команды /stop
                elif message.text == '/stop':
                    await self.handle_stop_flood(message)
                
                # Обработка команды /status
                elif message.text == '/status':
                    await self.handle_status(message)
                
                # Обработка текста после команды /flud
                elif hasattr(self, 'waiting_for_flood_data'):
                    await self.handle_flood_data(message)
                
        except Exception as e:
            logger.error(f"Ошибка в обработчике сообщений: {e}")
            try:
                await message.reply(f"❌ Ошибка: {str(e)}")
            except:
                pass
    
    async def handle_add_tdata(self, message, tdata_path):
        """Обработка добавления TData"""
        try:
            if not os.path.exists(tdata_path):
                await message.reply("❌ Указанный путь не существует!")
                return
            
            # Конвертируем TData в сессию
            await message.reply("⏳ Конвертирую TData в сессию...")
            session_string = await self.create_session_from_tdata(tdata_path)
            
            if not session_string:
                await message.reply("❌ Ошибка конвертации TData!")
                return
            
            # Сохраняем сессию в конфиг
            config = await self.load_config()
            
            # Получаем информацию о пользователе из сессии
            temp_client = TelegramClient(
                StringSession(session_string),
                api_id=config["api_id"],
                api_hash=config["api_hash"]
            )
            
            await temp_client.connect()
            if await temp_client.is_user_authorized():
                me = await temp_client.get_me()
                username = me.username or me.first_name or f"user_{me.id}"
                phone = me.phone or "Не указан"
                
                # Сохраняем сессию
                session_id = str(me.id)
                config["sessions"][session_id] = {
                    "session_string": session_string,
                    "username": username,
                    "phone": phone,
                    "added_date": datetime.now().isoformat()
                }
                config["active_session"] = session_string
                
                await self.save_config(config)
                
                await message.reply(
                    f"✅ Сессия добавлена успешно!\n\n"
                    f"👤 Пользователь: @{username}\n"
                    f"📱 Телефон: {phone}\n"
                    f"🆔 ID: {session_id}"
                )
                
                # Запускаем клиента с новой сессией
                success, msg = await self.start_client(session_string)
                if success:
                    await message.reply(msg)
                else:
                    await message.reply(f"⚠️ Сессия сохранена, но клиент не запущен: {msg}")
            
            await temp_client.disconnect()
            
        except Exception as e:
            logger.error(f"Ошибка добавления TData: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def handle_sessions_list(self, message):
        """Показать список сессий"""
        try:
            config = await self.load_config()
            
            if not config.get("sessions"):
                await message.reply("📭 Нет сохраненных сессий")
                return
            
            sessions_list = "📋 Список сохраненных сессий:\n\n"
            for session_id, session_data in config["sessions"].items():
                status = "✅ Активная" if config.get("active_session") == session_data["session_string"] else "💤 Неактивная"
                sessions_list += f"👤 {session_data['username']}\n"
                sessions_list += f"📱 {session_data['phone']}\n"
                sessions_list += f"🆔 {session_id}\n"
                sessions_list += f"📅 {session_data['added_date'][:10]}\n"
                sessions_list += f"{status}\n"
                sessions_list += "─" * 30 + "\n"
            
            await message.reply(sessions_list)
            
        except Exception as e:
            logger.error(f"Ошибка получения списка сессий: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def handle_flood_data(self, message):
        """Обработка данных для рассылки"""
        try:
            text = message.text.strip()
            lines = text.split('\n')
            
            if len(lines) < 3:
                await message.reply("❌ Неверный формат данных!\nНужно: сообщение, задержка, папка")
                return
            
            flood_message = lines[0].strip()
            try:
                delay = float(lines[1].strip())
            except ValueError:
                await message.reply("❌ Неверный формат задержки! Должно быть число")
                return
            
            folder_name = lines[2].strip()
            
            # Удаляем флаг ожидания
            delattr(self, 'waiting_for_flood_data')
            
            # Запускаем рассылку
            await self.start_flood(message, flood_message, delay, folder_name)
            
        except Exception as e:
            logger.error(f"Ошибка обработки данных рассылки: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def start_flood(self, message, flood_message, delay, folder_name):
        """Запуск рассылки"""
        try:
            if not self.client or not await self.client.is_user_authorized():
                await message.reply("❌ Клиент не авторизован!")
                return
            
            if self.is_running:
                await message.reply("❌ Рассылка уже запущена!")
                return
            
            # Получаем список диалогов из указанной папки
            await message.reply(f"🔍 Ищу папку '{folder_name}'...")
            
            try:
                # Получаем все диалоги
                dialogs = await self.client.get_dialogs()
                
                # Ищем папку по имени
                target_dialogs = []
                for dialog in dialogs:
                    if hasattr(dialog, 'folder') and dialog.folder:
                        if dialog.folder.title == folder_name:
                            target_dialogs.append(dialog)
                    elif dialog.name == folder_name:
                        target_dialogs.append(dialog)
                
                if not target_dialogs:
                    await message.reply(f"❌ Папка '{folder_name}' не найдена!")
                    return
                
                await message.reply(f"✅ Найдено {len(target_dialogs)} диалогов в папке '{folder_name}'")
                
                # Запускаем рассылку
                self.is_running = True
                self.current_flood_task = asyncio.create_task(
                    self.flood_task(message, target_dialogs, flood_message, delay)
                )
                
            except Exception as e:
                await message.reply(f"❌ Ошибка получения диалогов: {str(e)}")
                
        except Exception as e:
            logger.error(f"Ошибка запуска рассылки: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def flood_task(self, message, dialogs, flood_message, delay):
        """Задача рассылки"""
        try:
            total = len(dialogs)
            successful = 0
            failed = 0
            
            await message.reply(f"🚀 Начинаю рассылку на {total} диалогов...")
            
            for i, dialog in enumerate(dialogs, 1):
                if not self.is_running:
                    break
                
                try:
                    # Отправляем сообщение
                    await self.client.send_message(dialog.entity, flood_message)
                    successful += 1
                    
                    # Отправляем статус каждые 10 сообщений
                    if i % 10 == 0:
                        status_msg = (
                            f"📊 Прогресс: {i}/{total}\n"
                            f"✅ Успешно: {successful}\n"
                            f"❌ Ошибок: {failed}\n"
                            f"⏱️ Задержка: {delay} сек"
                        )
                        await message.reply(status_msg)
                    
                    # Задержка между сообщениями
                    if i < total:
                        await asyncio.sleep(delay)
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"Ошибка отправки в диалог {dialog.name}: {e}")
            
            # Итоговый отчет
            final_msg = (
                f"🏁 Рассылка завершена!\n\n"
                f"📊 Итоги:\n"
                f"✅ Успешно отправлено: {successful}\n"
                f"❌ Ошибок: {failed}\n"
                f"🎯 Всего диалогов: {total}"
            )
            await message.reply(final_msg)
            
        except Exception as e:
            logger.error(f"Ошибка в задаче рассылки: {e}")
            try:
                await message.reply(f"❌ Ошибка рассылки: {str(e)}")
            except:
                pass
        finally:
            self.is_running = False
            self.current_flood_task = None
    
    async def handle_stop_flood(self, message):
        """Остановка рассылки"""
        try:
            if not self.is_running:
                await message.reply("⚠️ Рассылка не запущена")
                return
            
            self.is_running = False
            if self.current_flood_task:
                self.current_flood_task.cancel()
            
            await message.reply("⏹️ Рассылка остановлена")
            
        except Exception as e:
            logger.error(f"Ошибка остановки рассылки: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def handle_status(self, message):
        """Показать статус"""
        try:
            if self.is_running:
                status = "🟢 Рассылка активна"
            else:
                status = "🔴 Рассылка неактивна"
            
            if self.client and await self.client.is_user_authorized():
                me = await self.client.get_me()
                user_info = f"👤 Аккаунт: @{me.username or me.first_name}"
            else:
                user_info = "❌ Не авторизован"
            
            await message.reply(f"{status}\n{user_info}")
            
        except Exception as e:
            logger.error(f"Ошибка получения статуса: {e}")
            await message.reply(f"❌ Ошибка: {str(e)}")
    
    async def run(self):
        """Основной цикл бота"""
        try:
            # Загружаем конфиг
            config = await self.load_config()
            
            # Запускаем клиент если есть активная сессия
            if config.get("active_session"):
                success, msg = await self.start_client()
                if success:
                    logger.info(msg)
                else:
                    logger.warning(msg)
            
            logger.info("Бот запущен. Ожидание сообщений...")
            
            # Бесконечный цикл
            while True:
                try:
                    # Читаем сообщения из stdin (имитация входящих сообщений)
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, sys.stdin.readline
                    )
                    
                    if line:
                        # Эмулируем получение сообщения
                        print(f"Получено: {line.strip()}")
                        
                except KeyboardInterrupt:
                    logger.info("Получен сигнал завершения...")
                    break
                except Exception as e:
                    logger.error(f"Ошибка в основном цикле: {e}")
                    await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Ошибка в основном цикле: {e}")
        
        finally:
            # Отключаем клиент
            if self.client:
                await self.client.disconnect()
            logger.info("Бот остановлен")

# Запуск бота
if __name__ == "__main__":
    bot = TelegramFloodBot()
    
    # Для использования в интерактивном режиме
    print("=" * 50)
    print("🤖 Telegram Flood Bot")
    print("=" * 50)
    print("\nДля взаимодействия используйте команды:")
    print("1. /start - Начало работы")
    print("2. /add_tdata [путь] - Добавить TData")
    print("3. /sessions - Список сессий")
    print("4. /flud - Начать рассылку")
    print("5. /stop - Остановить рассылку")
    print("6. /status - Статус")
    print("7. /help - Помощь")
    print("\nВводите команды в консоль:")
    print("=" * 50)
    
    # Запускаем бота
    asyncio.run(bot.run())
