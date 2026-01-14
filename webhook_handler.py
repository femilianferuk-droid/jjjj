from flask import Flask, request, jsonify
import sqlite3
import json
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/webhook/<int:user_id>', methods=['POST'])
def handle_webhook(user_id):
    """Обработка сообщений от клиентского бота"""
    try:
        data = request.json
        
        # Получаем конфигурацию бота из БД
        conn = sqlite3.connect('configs.db')
        c = conn.cursor()
        c.execute('''SELECT config_json FROM bot_configs 
                    WHERE user_id = ? AND status = 'active' 
                    ORDER BY id DESC LIMIT 1''',
                 (user_id,))
        
        result = c.fetchone()
        if not result:
            return jsonify({"status": "error", "message": "Bot not found"}), 404
        
        config = json.loads(result[0])
        template_config = config.get('config', {})
        
        # Обработка входящего сообщения
        message_text = data.get('message', {}).get('text', '')
        
        # Проверяем авто-ответы
        auto_replies = template_config.get('auto_replies', {})
        reply_text = auto_replies.get(message_text.lower())
        
        if reply_text:
            response = {
                "method": "sendMessage",
                "chat_id": data['message']['chat']['id'],
                "text": reply_text
            }
            return jsonify(response)
        
        # Стандартный ответ
        welcome_msg = template_config.get('welcome_message', 'Бот активирован!')
        response = {
            "method": "sendMessage",
            "chat_id": data['message']['chat']['id'],
            "text": welcome_msg
        }
        
        conn.close()
        return jsonify(response)
        
    except Exception as e:
        logging.error(f"Webhook error: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
