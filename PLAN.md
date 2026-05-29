# VXN/VIX 与美股指数相关性实时分析工具 — 实施计划

> **目标:** 构建完整的飞书机器人+Web仪表板，实时分析VIX/VXN与标普500/纳斯达克的相关性

**架构:** Python 3.9+ FastAPI 后端 + Plotly 交互图表 + 飞书 Webhook 集成 + APScheduler 定时推送

**技术栈:** FastAPI, yfinance (主数据源), alpha-vantage (备用), pandas, scipy, plotly, APScheduler, lark-oapi

---

## 模块结构

```
vxn-vix-correlation/
├── src/
│   ├── __init__.py
│   ├── config.py              # 环境变量配置
│   ├── data/
│   │   ├── __init__.py
│   │   ├── fetcher.py         # 数据获取 (yfinance + Alpha Vantage)
│   │   └── cache.py           # 10分钟缓存层
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── correlation.py     # 相关性计算引擎
│   │   └── charts.py          # Plotly 图表生成
│   ├── bot/
│   │   ├── __init__.py
│   │   ├── feishu_handler.py  # 飞书消息处理
│   │   └── card_builder.py    # 消息卡片构建
│   └── api/
│       ├── __init__.py
│       ├── routes.py          # FastAPI 路由
│       └── scheduler.py       # 定时推送
├── templates/
│   └── dashboard.html         # Web 仪表板
├── static/
│   ├── css/dashboard.css
│   └── js/dashboard.js
├── config/
│   └── .env.example           # 环境变量示例
├── tests/
│   ├── test_fetcher.py
│   ├── test_correlation.py
│   └── test_api.py
├── scripts/
│   └── start.sh               # 启动脚本
├── Dockerfile
├── requirements.txt
├── README.md
└── main.py                    # 入口
```

## API 端点

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | /correlation | 返回最新相关性分析数据 (JSON) |
| GET | /correlation?refresh=true | 强制刷新数据 |
| GET | /dashboard | Web 仪表板 HTML |
| GET | /chart/rolling | 滚动相关系数图片 (PNG base64) |
| GET | /data/csv | 下载 CSV 数据 |
| POST | /webhook | 飞书事件回调 |
| GET | /health | 健康检查 |

## 数据流

```
飞书命令 → /webhook → 解析命令 → /correlation (内部调用)
                                        ↓
                               cache.get_or_fetch()
                                        ↓
                              yfinance.download() ← 10分钟缓存
                                        ↓
                              相关性计算 → JSON 响应
                                        ↓
                              构建飞书卡片 → 回复用户
```

## 实施步骤（按顺序）

### Phase 1: 基础设施
1. 创建项目结构 + requirements.txt
2. 配置模块 (环境变量)
3. FastAPI 应用骨架

### Phase 2: 数据层
4. 数据获取器 (yfinance 主 + Alpha Vantage 备用)
5. 缓存层 (10分钟 TTL + 跨天自动刷新)
6. 时区处理 (美东时间对齐)

### Phase 3: 分析引擎
7. Pearson 相关性 + p-value
8. 多时间窗口计算 (1M, 3M, 6M, 1Y, 2Y, 5Y)
9. 滚动相关系数 (30天窗口, 1年历史)
10. Plotly 图表生成

### Phase 4: Web 仪表板
11. 仪表板 HTML + JS
12. 自定义日期范围回测
13. CSV 下载

### Phase 5: 飞书集成
14. 飞书 Webhook 事件处理
15. 消息卡片构建
16. APScheduler 每日推送

### Phase 6: 部署
17. Dockerfile
18. README.md (含飞书配置步骤)
19. 启动脚本
20. 端到端测试
