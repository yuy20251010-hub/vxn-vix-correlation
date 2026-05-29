"""
配置模块 — 从环境变量加载所有配置
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
ENV_PATH = Path(__file__).parent.parent / "config" / ".env"
load_dotenv(ENV_PATH)


class Config:
    """全局配置"""

    # --- 数据源 ---
    ALPHA_VANTAGE_API_KEY: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")

    # --- 飞书 ---
    FEISHU_APP_ID: str = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET: str = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_VERIFICATION_TOKEN: str = os.getenv("FEISHU_VERIFICATION_TOKEN", "")
    FEISHU_ENCRYPT_KEY: str = os.getenv("FEISHU_ENCRYPT_KEY", "")
    FEISHU_PUSH_TARGETS: list = [
        t.strip()
        for t in os.getenv("FEISHU_PUSH_TARGETS", "").split(",")
        if t.strip()
    ]

    # --- 服务器 ---
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    BASE_URL: str = os.getenv("BASE_URL", f"http://localhost:{PORT}")

    # --- 定时推送 ---
    PUSH_CRON_HOUR: int = int(os.getenv("PUSH_CRON_HOUR", "9"))
    PUSH_CRON_MINUTE: int = int(os.getenv("PUSH_CRON_MINUTE", "0"))

    # --- 缓存 ---
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "600"))

    # --- 数据常量 ---
    # 股票/指数代码 (Yahoo Finance 格式)
    TICKERS = {
        "VXN": "^VXN",       # CBOE 纳斯达克波动率指数
        "IXIC": "^IXIC",     # 纳斯达克综合指数
        "VIX": "^VIX",       # CBOE 标普500波动率指数
        "GSPC": "^GSPC",     # 标普500指数
    }

    # 相关性分析的时间窗口
    CORRELATION_WINDOWS = {
        "1M": 21,     # ~1 个月交易日
        "3M": 63,     # ~3 个月
        "6M": 126,    # ~6 个月
        "1Y": 252,    # ~1 年
        "2Y": 504,    # ~2 年
        "5Y": 1260,   # ~5 年
    }

    # 滚动相关系数窗口
    ROLLING_WINDOW = 30     # 30 个交易日
    ROLLING_HISTORY = 252   # 1 年历史

    # 时区
    TZ_US_EASTERN = "America/New_York"
    TZ_BEIJING = "Asia/Shanghai"

    # 最新数据允许的最大延迟 (天) — 超过此值视为数据过期
    MAX_DATA_STALENESS_DAYS = 2


config = Config()
