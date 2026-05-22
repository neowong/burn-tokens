import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, Response, render_template
import random
import dashscope
from dashscope import Generation

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


# Long prompt text to maximize token consumption
LONG_PROMPT = """请详细分析以下内容，从多个角度进行深入探讨，包括历史背景、技术原理、应用场景、发展趋势等方面：

人工智能（Artificial Intelligence, AI）是计算机科学的一个分支，旨在创建能够模拟人类智能的系统。自1956年达特茅斯会议以来，AI已经经历了多次浪潮和寒冬。近年来，随着深度学习技术的突破，AI在自然语言处理、计算机视觉、语音识别等领域取得了显著进展。

大型语言模型（Large Language Models, LLMs）是当前AI领域最受关注的技术之一。这些模型通过在海量文本数据上进行预训练，学习了丰富的语言知识和推理能力。GPT系列、BERT、T5等模型的出现，彻底改变了自然语言处理的研究范式。

在应用层面，AI技术已经渗透到各行各业。医疗健康领域，AI辅助诊断系统可以帮助医生更准确地识别疾病；金融领域，AI算法用于风险控制和量化交易；教育领域，个性化学习系统根据学生特点定制教学方案；自动驾驶技术正在逐步改变交通运输行业。

然而，AI的发展也面临着诸多挑战。数据隐私、算法偏见、可解释性、安全性等问题亟待解决。此外，AI的广泛应用也可能对就业结构、社会公平产生深远影响。

未来，人工智能将继续朝着更强大、更可靠、更可控的方向发展。多模态AI、具身智能、神经符号系统等新兴方向值得持续关注。同时，AI治理框架的建立也将成为重要议题，以确保技术的健康发展造福全人类。请对以上内容进行全面分析，每一点都要详细展开，提供具体的案例和数据支持。"""


def calc_cost(model, prompt_tokens, output_tokens):
    prices = MODEL_PRICES.get(model, MODEL_PRICES['qwen-max'])
    input_cost = prompt_tokens * prices['input'] / 1_000_000
    output_cost = output_tokens * prices['output'] / 1_000_000
    return input_cost + output_cost


def burner_worker():
    """Background thread that sends concurrent requests to Bailian API."""
    stop_event = threading.Event()
    state['stop_event'] = stop_event
    state['running'] = True
    state['start_time'] = datetime.now()

    def send_request():
        if stop_event.is_set():
            return
        try:
            dashscope.api_key = state['api_key']
            resp = Generation.call(
                model=state['model'],
                prompt=LONG_PROMPT,
                max_tokens=4096,
                temperature=0.9,
                result_format='message'
            )
            if stop_event.is_set():
                return
            if resp.status_code == 200:
                usage = resp.get('usage', {})
                prompt_tokens = usage.get('input_tokens', 0) or usage.get('prompt_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                total_tokens = prompt_tokens + output_tokens
                cost = calc_cost(state['model'], prompt_tokens, output_tokens)

                conn = get_db()
                conn.execute(
                    'INSERT INTO burn_records (model, prompt_tokens, output_tokens, total_tokens, cost) VALUES (?, ?, ?, ?, ?)',
                    (state['model'], prompt_tokens, output_tokens, total_tokens, cost)
                )
                conn.commit()
                conn.close()

                state['total_tokens'] += total_tokens
                state['total_cost'] += cost
                save_config_key('total_tokens', state['total_tokens'])
                save_config_key('total_cost', state['total_cost'])
            else:
                time.sleep(1)
        except Exception:
            time.sleep(1)

    try:
        while not stop_event.is_set():
            if state['total_cost'] >= state['target_amount']:
                break
            # Check target every iteration
            threads = []
            for _ in range(state['concurrency']):
                if stop_event.is_set() or state['total_cost'] >= state['target_amount']:
                    break
                t = threading.Thread(target=send_request)
                t.start()
                threads.append(t)
                time.sleep(0.05)  # Small stagger to avoid thundering herd
            for t in threads:
                t.join(timeout=30)
    finally:
        state['running'] = False
        state['stop_event'] = None


@app.route('/api/start', methods=['POST'])
def start_burn():
    if state['running']:
        return jsonify({'status': 'error', 'error': 'Already running'})
    if not state['api_key']:
        return jsonify({'status': 'error', 'error': 'API Key not set'})
    state['total_tokens'] = 0
    state['total_cost'] = 0.0
    save_config_key('total_tokens', '0')
    save_config_key('total_cost', '0')
    # Clear old records
    conn = get_db()
    conn.execute('DELETE FROM burn_records')
    conn.commit()
    conn.close()

    state['burn_thread'] = threading.Thread(target=burner_worker, daemon=True)
    state['burn_thread'].start()
    return jsonify({'status': 'ok'})


@app.route('/api/stop', methods=['POST'])
def stop_burn():
    if state.get('stop_event'):
        state['stop_event'].set()
    state['running'] = False
    return jsonify({'status': 'ok'})


@app.route('/api/events')
def event_stream():
    def generate():
        last_cost = 0
        last_tokens = 0
        rate_window = []  # [(timestamp, tokens), ...]
        while True:
            running = state['running']
            total_cost = state['total_cost']
            total_tokens = state['total_tokens']
            target = state['target_amount']
            done = not running and total_cost >= target if not running else False

            # Calculate rate from recent history
            now = time.time()
            rate_window.append((now, total_tokens))
            # Keep last 60 seconds
            rate_window = [(t, tok) for t, tok in rate_window if now - t < 60]
            if len(rate_window) > 1:
                dt = rate_window[-1][0] - rate_window[0][0]
                dtok = rate_window[-1][1] - rate_window[0][1]
                rate = int(dtok / (dt / 60)) if dt > 0 else 0
            else:
                rate = 0

            # Uptime
            uptime = int(now - state['start_time'].timestamp()) if state['start_time'] else 0
            uptime_str = f"{uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}"

            # History for chart (last 24h, aggregated by hour)
            conn = get_db()
            rows = conn.execute('''
                SELECT strftime('%H:00', created_at) as hour,
                       SUM(total_tokens) as tokens,
                       SUM(cost) as cost
                FROM burn_records
                WHERE created_at > datetime('now', '-24 hours')
                GROUP BY strftime('%H', created_at)
                ORDER BY hour
            ''').fetchall()
            conn.close()
            history = [{'t': r['hour'], 'tokens': r['tokens'], 'cost': round(r['cost'], 4)} for r in rows]

            data = {
                'running': running,
                'done': done,
                'total_cost': round(total_cost, 4),
                'total_tokens': total_tokens,
                'target_amount': target,
                'progress_pct': round(min(total_cost / target * 100, 100), 1) if target > 0 else 0,
                'rate_per_min': rate,
                'uptime_str': uptime_str,
                'history': history,
            }
            yield f"data: {json.dumps(data)}\n\n"

            last_cost = total_cost
            last_tokens = total_tokens
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
    })


@app.route('/api/history')
def get_history():
    conn = get_db()
    rows = conn.execute('''
        SELECT strftime('%H:00', created_at) as hour,
               SUM(total_tokens) as tokens,
               SUM(cost) as cost
        FROM burn_records
        WHERE created_at > datetime('now', '-24 hours')
        GROUP BY strftime('%H', created_at)
        ORDER BY hour
    ''').fetchall()
    conn.close()
    return jsonify([{'t': r['hour'], 'tokens': r['tokens'], 'cost': round(r['cost'], 4)} for r in rows])


if __name__ == '__main__':
    init_db()
    load_config()
    app.run(debug=False, host='127.0.0.1', port=5000)
