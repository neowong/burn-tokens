import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, render_template

app = Flask(__name__)

DB_PATH = 'burner.db'

# In-memory state
state = {
    'api_key': None,
    'model': 'qwen-max',
    'target_amount': 2000.0,
    'concurrency': 10,
    'running': False,
    'total_tokens': 0,
    'total_cost': 0.0,
    'start_time': None,
    'burn_thread': None,
    'stop_event': None,
}

# Model pricing per 1M tokens (CNY)
MODEL_PRICES = {
    'qwen-max': {'input': 20.0, 'output': 60.0},
    'qwen-plus': {'input': 2.0, 'output': 6.0},
    'qwen-turbo': {'input': 0.8, 'output': 2.0},
    'deepseek-v3': {'input': 2.0, 'output': 8.0},
    'deepseek-r1': {'input': 4.0, 'output': 16.0},
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS burn_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            cost REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    ''')
    conn.commit()
    conn.close()


def load_config():
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM config').fetchall()
    conn.close()
    for row in rows:
        if row['key'] == 'api_key':
            state['api_key'] = row['value']
        elif row['key'] == 'model':
            state['model'] = row['value']
        elif row['key'] == 'target_amount':
            state['target_amount'] = float(row['value'])
        elif row['key'] == 'concurrency':
            state['concurrency'] = int(row['value'])
        elif row['key'] == 'total_tokens':
            state['total_tokens'] = int(row['value'])
        elif row['key'] == 'total_cost':
            state['total_cost'] = float(row['value'])


def save_config_key(key, value):
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/config', methods=['POST'])
def set_config():
    data = request.json
    if 'api_key' in data:
        state['api_key'] = data['api_key']
        save_config_key('api_key', data['api_key'])
    if 'model' in data:
        state['model'] = data['model']
        save_config_key('model', data['model'])
    if 'target_amount' in data:
        state['target_amount'] = float(data['target_amount'])
        save_config_key('target_amount', data['target_amount'])
    if 'concurrency' in data:
        state['concurrency'] = int(data['concurrency'])
        save_config_key('concurrency', data['concurrency'])
    return jsonify({'status': 'ok'})


@app.route('/api/models', methods=['GET'])
def list_models():
    if not state['api_key']:
        return jsonify({'error': 'API Key not set'}), 400
    try:
        from dashscope import Generation
        models = Generation.list_models(api_key=state['api_key'])
        result = [m for m in models if m.get('model_id') and 'qwen' in m.get('model_id', '').lower() or 'deepseek' in m.get('model_id', '').lower()]
        return jsonify({'models': result})
    except Exception as e:
        # Fallback: return known models with pricing
        fallback = [
            {'model_id': 'qwen-max', 'name': 'Qwen-Max (¥20-60/百万token)'},
            {'model_id': 'qwen-plus', 'name': 'Qwen-Plus (¥2-6/百万token)'},
            {'model_id': 'qwen-turbo', 'name': 'Qwen-Turbo (¥0.8-2/百万token)'},
        ]
        return jsonify({'models': fallback, 'fallback': True, 'error': str(e)})


@app.route('/api/status')
def get_status():
    return jsonify({
        'running': state['running'],
        'model': state['model'],
        'total_tokens': state['total_tokens'],
        'total_cost': round(state['total_cost'], 4),
        'target_amount': state['target_amount'],
        'progress_pct': round(min(state['total_cost'] / state['target_amount'] * 100, 100), 1) if state['target_amount'] > 0 else 0,
        'concurrency': state['concurrency'],
        'start_time': state['start_time'].isoformat() if state['start_time'] else None,
        'uptime_seconds': int((datetime.now() - state['start_time']).total_seconds()) if state['start_time'] else 0,
    })


if __name__ == '__main__':
    init_db()
    load_config()
    app.run(debug=False, host='127.0.0.1', port=5000)
