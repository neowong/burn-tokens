# Token Burner - 百炼 API Token 消耗监控应用

## 概述

一个用于消耗阿里云百炼 API Token 的 Web 应用，目标在 5 天内烧掉 ¥2000 的 token 费用，带实时监控仪表盘。

## 技术栈

| 组件 | 选择 |
|------|------|
| 后端 | Python Flask（单文件 app.py） |
| 前端 | 单页 HTML + Chart.js（templates/index.html） |
| 数据库 | SQLite（burner.db） |
| 实时通信 | SSE (Server-Sent Events) |
| 目标模型 | Qwen-Max（最贵，烧钱效率最高） |

## 架构

```
用户浏览器 (index.html)
    │ ▲
    │ │ HTTP REST + SSE
    ▼ │
Flask 后端 (app.py)
    │
    ├── 百炼 API (通过 DashScope SDK)
    └── SQLite (burner.db)
```

## 功能需求

### 1. API Key 与模型管理
- 用户输入百炼 API Key
- 点击「获取模型列表」调用百炼 ListModels API
- 下拉框选择模型（运行中也可切换）
- 配置存储在服务端内存，不暴露给前端

### 2. Token 消耗引擎
- 指定并发数发送请求到百炼 API
- 使用长文本 prompt 最大化 token 消耗（输入 + 输出双向烧）
- 支持运行中切换模型（新请求用新模型）
- 到达目标金额自动停止

### 3. 实时监控仪表盘
- 状态指示器（运行中/已停止/已完成）
- 实时统计数据：已消耗金额、已用 Token、平均速率
- 进度条：¥X / ¥2000
- 趋势图（Chart.js）：24 小时 token 消耗/费用双 Y 轴
- SSE 每秒推送更新

### 4. 数据持久化
- SQLite 存储每次 API 调用的记录
- 进程重启后从历史恢复，不重复计算
- 模型、金额等配置持久化

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/config | 设置 API Key |
| GET | /api/models | 获取模型列表 |
| POST | /api/start | 开始烧钱 |
| POST | /api/stop | 停止烧钱 |
| GET | /api/status | 当前状态+统计 |
| GET | /api/events | SSE 实时推送 |
| GET | /api/history | 历史数据（图表） |

## 数据模型

```sql
CREATE TABLE burn_records (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  model         TEXT NOT NULL,
  prompt_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  total_tokens  INTEGER NOT NULL,
  cost          REAL NOT NULL,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE config (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
```

## 烧钱策略

- **模型**: Qwen-Max（最贵，最大化消耗）
- **目标**: ¥2000 / 5 天 = ¥400/天
- **方法**: 高并发发送大量请求，每个请求携带长文本 prompt
- **定价**: 后端根据模型单价 × 实际用量实时计算

## 错误处理

| 场景 | 处理 |
|------|------|
| API Key 无效 | 前端提示，停止烧钱 |
| 余额不足 | 检测 403/429，暂停+告警 |
| 网络中断 | 指数退避重试，最多 3 次 |
| 目标达成 | 自动停止，前端通知 |
| 进程重启 | SQLite 恢复，不重复 |
| 切换模型 | 旧请求继续，新请求用新模型 |
