# 📊 VXN/VIX 与美股指数相关性实时分析工具

实时获取 VXN、纳斯达克、VIX、标普500 指数数据，多时间窗口 Pearson 相关性分析，集成飞书机器人与每日推送。

## ✨ 功能特性

- **实时数据获取**：每次查询从 Yahoo Finance 拉取最新行情（≤10 分钟缓存）
- **多时间窗口分析**：1个月/3个月/6个月/1年/2年/5年 Pearson 相关系数 + P值
- **滚动相关系数**：30天滚动窗口 + 历史分位数（25%/50%/75%）
- **飞书机器人**：对话框 `/corr` 命令实时查询，卡片消息返回
- **每日推送**：北京时间 09:00 自动推送分析结果 + 图表
- **Web 仪表板**：交互式 Plotly 图表、自定义回测日期、CSV 下载
- **暗色主题**：适配飞书内置浏览器（移动端 + PC 端）

## 🚀 快速开始

### 1. 前置条件

- Python 3.9+
- 飞书开发者账号（[开放平台](https://open.feishu.cn/)）
- 可公开访问的域名（用于飞书事件订阅回调）

### 2. 安装依赖

```bash
git clone <your-repo-url>
cd vxn-vix-correlation
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入飞书应用凭证
```

必填项：
| 变量 | 说明 | 获取方式 |
|------|------|---------|
| `FEISHU_APP_ID` | 应用 App ID | 飞书开放平台 → 应用详情 → 凭证与基础信息 |
| `FEISHU_APP_SECRET` | 应用 Secret | 同上 |
| `FEISHU_VERIFICATION_TOKEN` | 事件订阅 Token | 飞书开放平台 → 事件订阅 |
| `BASE_URL` | 外网可访问的服务 URL | 部署后分配（Railway/Render 等） |
| `FEISHU_PUSH_CHAT_IDS` | 推送目标 chat_id | 群聊中添加机器人后获取 |

### 4. 启动服务

```bash
python run.py
# 服务运行在 http://localhost:8000
```

## 📡 API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/correlation` | GET | 返回最新分析结果（JSON），支持 `?force_refresh=true` |
| `/correlation/chart` | GET | 返回滚动相关系数图表（HTML），支持 `?pair=&window=&start_date=&end_date=` |
| `/correlation/data.csv` | GET | 下载相关系数数据 CSV |
| `/dashboard` | GET | Web 交互式仪表板 |
| `/webhook` | POST | 飞书事件回调地址 |
| `/health` | GET | 健康检查 |

### /correlation 响应示例

```json
{
  "success": true,
  "last_update": "2024-06-15 (latest trading day)",
  "prices": {
    "VXN": {"close": 22.5, "date": "2024-06-14"},
    "IXIC": {"close": 17689.3, "date": "2024-06-14"}
  },
  "correlations": {
    "vxn_ixic": {
      "1个月": {"correlation": -0.7234, "p_value": 0.0002, "n_samples": 21}
    }
  },
  "summary": "过去1个月 VXN-纳斯达克 相关系数 -0.72（强负相关）...",
  "chart_base64": "iVBORw0KGgo...",
  "dashboard_url": "https://your-app.railway.app/dashboard"
}
```

## 🏗️ 飞书应用配置

### 1. 创建自建应用

1. 登录 [飞书开放平台](https://open.feishu.cn/)
2. 点击「创建企业自建应用」
3. 填写应用名称和描述
4. 获取 `App ID` 和 `App Secret`

### 2. 启用机器人能力

1. 进入「添加应用能力」→ 启用「机器人」
2. 配置机器人名称和头像
3. 无需额外权限配置（机器人基础权限默认开通）

### 3. 配置事件订阅

1. 进入「事件订阅」→ 「配置事件」
2. 请求网址 URL 填入：`https://your-domain.com/webhook`
3. 添加事件：`im.message.receive_v1`（接收消息）
4. 保存后飞书会发送验证请求，确保服务已启动

### 4. 配置权限

进入「权限管理」，添加以下权限：
- `im:message` - 获取与发送单聊、群组消息
- `im:message.p2p_msg:readonly` - 读取用户发给机器人的单聊消息
- `im:message.group_msg:readonly` - 读取群组中的消息
- `im:message:send_as_bot` - 以机器人身份发送消息
- `im:resource` - 获取图片等资源（用于上传图表）

### 5. 发布应用

1. 点击「创建版本」→ 填写版本号和说明
2. 提交审核（自建应用通常无需审核）
3. 审核通过后点击「发布」

### 6. 获取 Chat ID

**方法一：通过 API 获取群聊列表**
```bash
curl -X POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal \
  -H "Content-Type: application/json" \
  -d '{"app_id": "YOUR_APP_ID", "app_secret": "YOUR_APP_SECRET"}'

# 用返回的 token 获取群聊列表
curl -H "Authorization: Bearer YOUR_TOKEN" \
  "https://open.feishu.cn/open-apis/im/v1/chats"
```

**方法二：在群聊中 @机器人 发消息，查看 webhook 日志**
服务会记录收到的 chat_id。

找到目标 chat_id 后填入 `.env` 中的 `FEISHU_PUSH_CHAT_IDS`。

## ☁️ 部署到云服务

### Railway

1. Fork 或上传代码到 GitHub
2. 在 [Railway](https://railway.app/) 中新建项目，关联仓库
3. 在 Railway 设置中添加环境变量（复制 .env.example 内容）
4. 部署！Railway 自动分配 `BASE_URL`
5. 将 `BASE_URL` 加 `/webhook` 填入飞书事件订阅地址

### Render

1. 在 [Render](https://render.com/) 新建 Web Service
2. 关联 GitHub 仓库
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python run.py`
5. 在 Environment 中添加所有环境变量
6. Render 分配 `*.onrender.com` 域名，设为 `BASE_URL`

### 阿里云函数计算 + 云托管

1. 使用 Docker 镜像部署
2. 构建镜像: `docker build -t vxn-vix-correlation .`
3. 推送到阿里云容器镜像服务
4. 在云托管中创建服务，选择镜像
5. 配置环境变量，设置端口 8000
6. 域名绑定后设置 `BASE_URL`

### Docker 本地部署

```bash
docker build -t vxn-vix-correlation .
docker run -d \
  --name vxn-correlation \
  -p 8000:8000 \
  --env-file .env \
  vxn-vix-correlation
```

## 🧪 测试

### 测试 API

```bash
# 健康检查
curl http://localhost:8000/health

# 获取相关性分析
curl http://localhost:8000/correlation | python -m json.tool

# 强制刷新
curl "http://localhost:8000/correlation?force_refresh=true" | python -m json.tool

# 打开仪表板
open http://localhost:8000/dashboard
```

### 测试飞书命令

在飞书中给机器人发消息：
- `/corr` - 触发相关性分析
- `相关性` - 中文命令
- `分析` - 简写命令
- `@机器人 corr` - @ 触发

### 测试每日推送

```bash
# 手动触发一次推送（需要先在 .env 中配置好）
python -c "
import asyncio
from app.scheduler import daily_push_task
asyncio.run(daily_push_task())
"
```

## 📂 项目结构

```
vxn-vix-correlation/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 主应用、Web 仪表板 HTML
│   ├── config.py        # 配置管理（环境变量）
│   ├── data.py          # 数据获取（yfinance + 缓存）
│   ├── analysis.py      # 相关性计算（Pearson + 滚动）
│   ├── charts.py        # Plotly 图表生成
│   ├── feishu_bot.py    # 飞书 API 客户端 + 卡片消息
│   └── scheduler.py     # 定时推送（APScheduler）
├── templates/
│   └── dashboard.html   # 仪表板模板（可选，不提供则用内联 HTML）
├── static/              # 静态文件
├── .cache/              # 数据缓存目录
├── .env.example         # 环境变量模板
├── requirements.txt     # Python 依赖
├── Dockerfile           # Docker 镜像
├── run.py               # 启动入口
└── README.md
```

## ⚠️ 注意事项

### 非交易日处理
- 美股周末及节假日无交易数据
- 系统自动检测最新交易日，返回最近交易日分析结果
- 推送消息会标注「数据日期: YYYY-MM-DD (最近交易日)」

### 数据源可用性
- 主数据源：Yahoo Finance (yfinance)，无需 API Key
- 备用数据源：Alpha Vantage（需免费注册获取 API Key）
- 国内访问 Yahoo Finance 可能不稳定，建议：
  - 配置代理：`.env` 中设置 `YFINANCE_PROXY`
  - 或注册 Alpha Vantage API Key 作为备用

### 频率限制
- Yahoo Finance 查询无硬性限制，但频繁请求可能被限
- Alpha Vantage 免费版限制：25 次/天（建议仅做备用）
- 本工具默认 10 分钟缓存，避免重复拉取完整历史

### 时区
- 美股交易时间：美东时间 9:30-16:00
- 每日推送：北京时间 09:00（对应美东晚上 21:00/20:00，当天数据已出）
- `/correlation` API 自动判断最新可用交易日

## 📄 数据代码说明

### 标的代码

| 名称 | Yahoo Finance | Alpha Vantage | 说明 |
|------|--------------|---------------|------|
| VXN | `^VXN` | `VXN` | CBOE 纳斯达克 100 波动率指数 |
| 纳斯达克 | `^IXIC` | `IXIC` | 纳斯达克综合指数 |
| VIX | `^VIX` | `VIX` | CBOE 标普 500 波动率指数 |
| 标普500 | `^GSPC` | `SPX` | 标普 500 指数 |

Yahoo Finance 上 VXN 波动率指数带 `^` 前缀；若数据为空，系统自动尝试去掉前缀重试。

### 相关性计算方法

- 使用**日对数收益率**计算 Pearson 相关系数（消除价格趋势影响）
- `ret = ln(close_t / close_{t-1})`
- 对齐两个标的的交易日后再计算
- P 值由 `scipy.stats.pearsonr` 计算

## 🔧 故障排除

### 数据源连接失败
```
RuntimeError: 无法获取 VXN (^VXN) 的数据
```
- 确认网络能访问 Yahoo Finance
- 设置 `ALPHA_VANTAGE_API_KEY` 启用备用数据源
- 设置 `YFINANCE_PROXY` 使用代理

### 飞书卡片不显示
- 确认 `FEISHU_APP_SECRET` 正确
- 检查机器人是否有发送消息权限
- 查看应用日志排查 API 调用错误

### 每日推送未触发
- 确认 `FEISHU_PUSH_CHAT_IDS` 已配置
- 检查服务时间是否正确
- 查看应用日志：搜索 `daily_push_task`

### 图表不显示
- 确认 `plotly` 和 `kaleido` 已安装（`pip install kaleido` 用于导出 PNG）
- Web 仪表板使用 CDN 加载 Plotly.js，需联网访问

## 📝 License

MIT
