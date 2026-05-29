"""应用配置 - 所有配置通过环境变量注入"""
import os
from pathlib import Path

# ── 项目路径 ──
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
DATA_CACHE_DIR = BASE_DIR / ".cache"
DATA_CACHE_DIR.mkdir(exist_ok=True)

# ── 数据源配置 ──
# Yahoo Finance 无需 API Key，但国内可能需要代理
YFINANCE_PROXY = os.getenv("YFINANCE_PROXY", "")  # e.g. "http://127.0.0.1:7890"
# Alpha Vantage 备用数据源
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
# 数据缓存时间（秒）
DATA_CACHE_TTL = int(os.getenv("DATA_CACHE_TTL", "600"))  # 10 分钟

# ── 飞书应用配置 ──
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_VERIFICATION_TOKEN = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")
# 每日推送目标：支持 chat_id 或用逗号分隔的多个 chat_id
FEISHU_PUSH_CHAT_IDS = os.getenv("FEISHU_PUSH_CHAT_IDS", "")

# ── 每日推送时间 ──
PUSH_HOUR = int(os.getenv("PUSH_HOUR", "9"))
PUSH_MINUTE = int(os.getenv("PUSH_MINUTE", "0"))
PUSH_TIMEZONE = os.getenv("PUSH_TIMEZONE", "Asia/Shanghai")

# ── 服务器配置 ──
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
BASE_URL = os.getenv("BASE_URL", "")  # 外网可访问的 URL，用于卡片链接

# ── 行情标的代码 ──
SYMBOLS = {
    "VXN": "^VXN",      # CBOE Nasdaq-100 Volatility Index
    "IXIC": "^IXIC",    # Nasdaq Composite
    "VIX": "^VIX",      # CBOE S&P 500 Volatility Index
    "GSPC": "^GSPC",    # S&P 500
}
# 备用代码（某些数据源格式不同）
SYMBOLS_ALT = {
    "VXN": "VXN",       # Alpha Vantage / Investing.com 格式
    "IXIC": "IXIC",
    "VIX": "VIX",
    "GSPC": "SPX",
}
