# Token Burner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask web app that burns ¥2000 of Alibaba Cloud Bailian API tokens across 5 days with real-time monitoring.

**Architecture:** Single Flask backend (`app.py`) serving a dashboard HTML page. Backend manages concurrent API calls to Bailian via DashScope SDK, pushes real-time stats via SSE. SQLite persists burn history. Chart.js renders trend charts.

**Tech Stack:** Python Flask, DashScope SDK, SQLite, Chart.js, SSE

---

### Task 1: Project scaffold and dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.0
dashscope>=1.20
```

- [ ] **Step 2: Create .gitignore**

```
burner.db
__pycache__/
*.pyc
.superpowers/
```

- [ ] **Step 3: Create directory structure**

```bash
mkdir -p templates static
```

- [ ] **Step 4: Commit**

```bash
git init
git add -A
git commit -m "chore: initial project scaffold"
```

---

### Task 2: Flask app skeleton with config and models API

**Files:**
- Create: `app.py`
- Create: `templates/index.html`

- [ ] **Step 1: Write Flask app with config and models endpoints**

```python
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
```

- [ ] **Step 2: Write basic index.html template**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Burner</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f1a; color: #e0e0e0; min-height: 100vh; }
        .container { max-width: 900px; margin: 0 auto; padding: 20px; }
        h1 { font-size: 24px; margin-bottom: 20px; color: #fff; }
        .card { background: #1a1a2e; border-radius: 12px; padding: 20px; margin-bottom: 16px; border: 1px solid #2a2a3e; }
        .card-title { font-size: 12px; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .stat { text-align: center; }
        .stat-value { font-size: 24px; font-weight: bold; color: #fff; }
        .stat-label { font-size: 11px; color: #888; margin-top: 4px; }
        .stat-value.green { color: #4ade80; }
        .stat-value.orange { color: #f97316; }
        .stat-value.red { color: #ef4444; }
        .stat-value.blue { color: #60a5fa; }
        .progress-bar { height: 10px; background: #2a2a3e; border-radius: 5px; overflow: hidden; margin-top: 8px; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #f97316, #ef4444); border-radius: 5px; transition: width 1s ease; }
        .form-row { display: flex; gap: 12px; margin-bottom: 12px; align-items: end; }
        .form-group { flex: 1; }
        .form-group label { display: block; font-size: 12px; color: #888; margin-bottom: 4px; }
        .form-group input, .form-group select { width: 100%; padding: 8px 12px; background: #2a2a3e; border: 1px solid #3a3a4e; border-radius: 6px; color: #fff; font-size: 14px; }
        .form-group input:focus, .form-group select:focus { outline: none; border-color: #60a5fa; }
        .btn { padding: 10px 24px; border: none; border-radius: 6px; font-size: 14px; font-weight: bold; cursor: pointer; transition: all 0.2s; }
        .btn:hover { opacity: 0.85; }
        .btn-primary { background: #3b82f6; color: #fff; }
        .btn-success { background: #22c55e; color: #fff; }
        .btn-danger { background: #ef4444; color: #fff; }
        .btn-secondary { background: #4b5563; color: #fff; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        #chart-canvas { width: 100% !important; height: 250px !important; }
        .status-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .status-badge.running { background: #166534; color: #4ade80; }
        .status-badge.stopped { background: #451a1a; color: #f87171; }
        .status-badge.done { background: #1e3a1e; color: #4ade80; }
        .hidden { display: none; }
        #error-msg { background: #451a1a; color: #fca5a5; padding: 8px 16px; border-radius: 6px; margin-bottom: 12px; }
        .btn-row { display: flex; gap: 8px; margin-top: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 Token Burner</h1>
        <div id="error-msg" class="hidden"></div>

        <!-- Config -->
        <div class="card">
            <div class="card-title">配置</div>
            <div class="form-row">
                <div class="form-group" style="flex: 3;">
                    <label>百炼 API Key</label>
                    <input type="password" id="api-key" placeholder="sk-...">
                </div>
                <button class="btn btn-secondary" onclick="fetchModels()" style="margin-bottom: 0;">获取模型列表</button>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>模型</label>
                    <select id="model">
                        <option value="qwen-max">Qwen-Max (¥20-60/百万token)</option>
                        <option value="qwen-plus">Qwen-Plus (¥2-6/百万token)</option>
                        <option value="qwen-turbo">Qwen-Turbo (¥0.8-2/百万token)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>并发数</label>
                    <input type="number" id="concurrency" value="10" min="1" max="200">
                </div>
                <div class="form-group">
                    <label>目标金额 (¥)</label>
                    <input type="number" id="target-amount" value="2000" min="1" step="100">
                </div>
            </div>
            <button class="btn btn-success" id="btn-start" onclick="startBurn()">🔥 开始烧钱</button>
            <button class="btn btn-danger hidden" id="btn-stop" onclick="stopBurn()">⏹ 停止</button>
        </div>

        <!-- Stats -->
        <div class="card">
            <div class="card-title">实时状态 <span id="status-badge" class="status-badge stopped">已停止</span></div>
            <div class="stats" id="stats">
                <div class="stat"><div class="stat-value orange" id="cost-display">¥0.00</div><div class="stat-label">已消耗</div></div>
                <div class="stat"><div class="stat-value blue" id="tokens-display">0</div><div class="stat-label">总 Token</div></div>
                <div class="stat"><div class="stat-value green" id="rate-display">0/min</div><div class="stat-label">消耗速率</div></div>
                <div class="stat"><div class="stat-value" id="uptime-display">00:00:00</div><div class="stat-label">运行时间</div></div>
            </div>
            <div style="margin-top: 12px;">
                <div style="display: flex; justify-content: space-between; font-size: 12px; color: #888;">
                    <span id="progress-text">¥0.00 / ¥2000</span>
                    <span id="progress-pct">0%</span>
                </div>
                <div class="progress-bar"><div class="progress-fill" id="progress-fill" style="width: 0%;"></div></div>
            </div>
        </div>

        <!-- Chart -->
        <div class="card">
            <div class="card-title">消耗趋势 (近24小时)</div>
            <canvas id="chart-canvas"></canvas>
        </div>
    </div>

    <script>
        let chart = null;
        const BASE = '';

        function showError(msg) {
            const el = document.getElementById('error-msg');
            el.textContent = msg;
            el.classList.remove('hidden');
        }

        function hideError() { document.getElementById('error-msg').classList.add('hidden'); }

        async function api(path, opts = {}) {
            const res = await fetch(BASE + path, opts);
            return res.json();
        }

        async function fetchModels() {
            const key = document.getElementById('api-key').value;
            if (!key) { showError('请先输入 API Key'); return; }
            await api('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({api_key: key}) });
            const data = await api('/api/models');
            const sel = document.getElementById('model');
            if (data.models && data.models.length) {
                sel.innerHTML = data.models.map(m => `<option value="${m.model_id}">${m.name || m.model_id}</option>`).join('');
                hideError();
            } else {
                showError('获取模型列表失败: ' + (data.error || 'unknown error'));
            }
        }

        async function startBurn() {
            const key = document.getElementById('api-key').value;
            const model = document.getElementById('model').value;
            const concurrency = document.getElementById('concurrency').value;
            const target = document.getElementById('target-amount').value;
            hideError();
            await api('/api/config', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({api_key: key, model, concurrency: parseInt(concurrency), target_amount: parseFloat(target)}) });
            const data = await api('/api/start', { method: 'POST' });
            if (data.status === 'ok') {
                document.getElementById('btn-start').classList.add('hidden');
                document.getElementById('btn-stop').classList.remove('hidden');
            } else {
                showError(data.error || '启动失败');
            }
        }

        async function stopBurn() {
            await api('/api/stop', { method: 'POST' });
            document.getElementById('btn-start').classList.remove('hidden');
            document.getElementById('btn-stop').classList.add('hidden');
        }

        function formatNumber(n) {
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return n.toString();
        }

        // SSE listener
        function connectSSE() {
            const evtSource = new EventSource(BASE + '/api/events');
            evtSource.onmessage = (e) => {
                const d = JSON.parse(e.data);
                document.getElementById('cost-display').textContent = '¥' + d.total_cost.toFixed(2);
                document.getElementById('tokens-display').textContent = formatNumber(d.total_tokens);
                document.getElementById('rate-display').textContent = d.rate_per_min + '/min';
                document.getElementById('uptime-display').textContent = d.uptime_str;
                document.getElementById('progress-text').textContent = '¥' + d.total_cost.toFixed(2) + ' / ¥' + d.target_amount.toFixed(0);
                document.getElementById('progress-pct').textContent = d.progress_pct + '%';
                document.getElementById('progress-fill').style.width = d.progress_pct + '%';
                const badge = document.getElementById('status-badge');
                if (d.running) { badge.textContent = '运行中'; badge.className = 'status-badge running'; }
                else if (d.done) { badge.textContent = '已完成'; badge.className = 'status-badge done'; }
                else { badge.textContent = '已停止'; badge.className = 'status-badge stopped'; }

                if (d.done) {
                    document.getElementById('btn-start').classList.remove('hidden');
                    document.getElementById('btn-stop').classList.add('hidden');
                }

                // Update chart
                if (chart && d.history) {
                    chart.data.labels = d.history.map(h => h.t);
                    chart.data.datasets[0].data = d.history.map(h => h.tokens);
                    chart.data.datasets[1].data = d.history.map(h => h.cost);
                    chart.update('none');
                }
            };
        }

        async function initChart() {
            const ctx = document.getElementById('chart-canvas').getContext('2d');
            chart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [
                    { label: 'Token', data: [], borderColor: '#60a5fa', backgroundColor: 'rgba(96,165,250,0.1)', yAxisID: 'y', fill: true, tension: 0.3 },
                    { label: '费用 ¥', data: [], borderColor: '#f97316', backgroundColor: 'rgba(249,115,22,0.1)', yAxisID: 'y1', fill: true, tension: 0.3 }
                ]},
                options: {
                    responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { labels: { color: '#888', font: { size: 11 } } } },
                    scales: {
                        x: { ticks: { color: '#666', maxTicksLimit: 12, font: { size: 10 } }, grid: { color: '#2a2a3e' } },
                        y: { position: 'left', ticks: { color: '#60a5fa', font: { size: 10 } }, grid: { color: '#2a2a3e' }, title: { display: true, text: 'Token', color: '#60a5fa' } },
                        y1: { position: 'right', ticks: { color: '#f97316', font: { size: 10 } }, grid: { display: false }, title: { display: true, text: '费用 ¥', color: '#f97316' } }
                    }
                }
            });
        }

        // Load saved config on page load
        async function loadStatus() {
            const s = await api('/api/status');
            if (!s.error) {
                document.getElementById('cost-display').textContent = '¥' + (s.total_cost || 0).toFixed(2);
                document.getElementById('tokens-display').textContent = formatNumber(s.total_tokens || 0);
                document.getElementById('progress-text').textContent = '¥' + (s.total_cost || 0).toFixed(2) + ' / ¥' + (s.target_amount || 2000).toFixed(0);
                document.getElementById('progress-pct').textContent = (s.progress_pct || 0) + '%';
                document.getElementById('progress-fill').style.width = (s.progress_pct || 0) + '%';
                document.getElementById('concurrency').value = s.concurrency || 10;
                // Set model select
                if (s.model) document.getElementById('model').value = s.model;
                if (s.running) {
                    document.getElementById('btn-start').classList.add('hidden');
                    document.getElementById('btn-stop').classList.remove('hidden');
                }
            }
        }

        initChart();
        loadStatus();
        connectSSE();
    </script>
</body>
</html>
```

- [ ] **Step 2: Run the app and verify it starts**

```bash
cd /home/neo/study/claude-demo/burn-tokens
pip install -r requirements.txt
python app.py &
sleep 2
curl -s http://127.0.0.1:5000/api/status | python -m json.tool
```

Expected: JSON with running=false, total_tokens=0, total_cost=0

- [ ] **Step 3: Commit**

```bash
git add app.py templates/index.html requirements.txt .gitignore
git commit -m "feat: flask app skeleton with config/models API and dashboard UI"
```

---

### Task 3: Token burner engine (start/stop + concurrent API calls)

**Files:**
- Modify: `app.py` (add burner engine)

- [ ] **Step 1: Add burner engine to app.py**

Add the following before `if __name__ == '__main__':`:

```python
import random
import dashscope
from dashscope import Generation

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
```

- [ ] **Step 2: Verify app still starts without errors**

```bash
kill $(lsof -t -i:5000) 2>/dev/null; sleep 1
python app.py &
sleep 2
curl -s http://127.0.0.1:5000/api/status | python -m json.tool
```

Expected: No import errors, JSON response

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add token burner engine with concurrent API calls"
```

---

### Task 4: SSE event stream and history API

**Files:**
- Modify: `app.py` (add SSE endpoint + history)

- [ ] **Step 1: Add SSE and history endpoints**

Add before `if __name__ == '__main__':`:

```python
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
```

- [ ] **Step 2: Verify SSE endpoint works**

```bash
kill $(lsof -t -i:5000) 2>/dev/null; sleep 1
python app.py &
sleep 2
curl -s -N --max-time 3 http://127.0.0.1:5000/api/events 2>/dev/null || true
```

Expected: SSE data lines starting with `data: {`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add SSE event stream and history API"
```

---

### Task 5: Frontend interactivity and live chart

**Files:**
- Modify: `templates/index.html`

- [ ] **Step 1: Verify the complete frontend works**

The index.html has already been written with all frontend logic. Let's verify the full app runs:

```bash
kill $(lsof -t -i:5000) 2>/dev/null; sleep 1
cd /home/neo/study/claude-demo/burn-tokens
python app.py &
```

Then open http://127.0.0.1:5000 in a browser and verify:
- Page loads without console errors
- Config panel visible with API Key input, model selector
- Status shows "已停止"
- Chart area visible
- Can type API Key and click "获取模型列表"

- [ ] **Step 2: Commit**

```bash
git add templates/index.html
git commit -m "feat: complete dashboard with live updates and chart"
```

---

### Task 6: Error handling, model switching, and edge cases

**Files:**
- Modify: `app.py`

- [ ] **Step 1: Add model switching support during runtime**

Modify the `set_config` endpoint to handle model switching while running:

```python
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
```

This already supports model switching - the burner reads `state['model']` on each new request batch.

- [ ] **Step 2: Add target reached auto-stop in burner_worker**

The burner already checks `state['total_cost'] >= state['target_amount']` in the loop. Let's add a final notification mechanism:

In the `generate()` function of `/api/events`, the `done` flag is already computed:
```python
done = not running and total_cost >= target if not running else False
```

This will cause the frontend to show "已完成" status.

- [ ] **Step 3: Add retry logic with exponential backoff**

Modify the `send_request` function in burner_worker:

```python
def send_request():
    if stop_event.is_set():
        return
    max_retries = 3
    for attempt in range(max_retries):
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
                return  # Success - exit retry loop
            elif resp.status_code in (429, 503):
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                time.sleep(1)
                return  # Non-retryable error
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                time.sleep(1)
```

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: add retry logic and model switching support"
```

---

### Task 7: Final integration test and verification

- [ ] **Step 1: Kill any existing processes and restart fresh**

```bash
kill $(lsof -t -i:5000) 2>/dev/null; sleep 1
rm -f burner.db
python app.py &
sleep 2
```

- [ ] **Step 2: Verify all API endpoints respond correctly**

```bash
# Status endpoint
curl -s http://127.0.0.1:5000/api/status | python -m json.tool

# Config endpoint
curl -s -X POST http://127.0.0.1:5000/api/config \
  -H 'Content-Type: application/json' \
  -d '{"api_key": "test-key", "model": "qwen-max", "concurrency": 10, "target_amount": 2000}' | python -m json.tool

# Models endpoint
curl -s http://127.0.0.1:5000/api/models | python -m json.tool

# History endpoint
curl -s http://127.0.0.1:5000/api/history | python -m json.tool

# SSE endpoint (3 second sample)
timeout 3 curl -s -N http://127.0.0.1:5000/api/events 2>/dev/null || true
```

- [ ] **Step 3: Open in browser**

```bash
echo "Open http://127.0.0.1:5000 in your browser and verify the dashboard loads"
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: final integration fixes"
```
