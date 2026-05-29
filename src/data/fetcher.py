"""
数据获取模块
主数据源: yfinance (Yahoo Finance)
备用数据源: Alpha Vantage
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

import pandas as pd
import yfinance as yf
import httpx
import pytz

from src.config import config

logger = logging.getLogger(__name__)

# 美股交易时间段 (美东时间, 近似)
MARKET_OPEN_HOUR = 9
MARKET_CLOSE_HOUR = 16


def _get_us_eastern_now() -> datetime:
    """获取当前美东时间"""
    return datetime.now(pytz.timezone(config.TZ_US_EASTERN))


def is_market_closed_today() -> bool:
    """判断美股今天是否已收盘 (用于决定获取几天数据)"""
    now_et = _get_us_eastern_now()
    # 周末不交易
    if now_et.weekday() >= 5:
        return True
    # 美东时间 16:00 后视为收盘
    return now_et.hour >= MARKET_CLOSE_HOUR


def get_latest_trading_day() -> str:
    """
    获取最近一个交易日日期 (YYYY-MM-DD)
    如果今天已收盘(含周末), 返回今天; 否则返回昨天
    """
    now_et = _get_us_eastern_now()
    if is_market_closed_today():
        # 如果是周末, 回退到周五
        if now_et.weekday() == 5:  # 周六
            latest = now_et - timedelta(days=1)
        elif now_et.weekday() == 6:  # 周日
            latest = now_et - timedelta(days=2)
        else:
            latest = now_et
    else:
        # 今天还没收盘, 返回上一个交易日
        latest = now_et - timedelta(days=1)
        if latest.weekday() == 5:
            latest -= timedelta(days=1)
        elif latest.weekday() == 6:
            latest -= timedelta(days=2)

    return latest.strftime("%Y-%m-%d")


def fetch_from_yfinance(tickers: list, period: str = "5y") -> Optional[pd.DataFrame]:
    """
    从 Yahoo Finance 获取数据

    Args:
        tickers: 股票代码列表 (Yahoo Finance 格式)
        period: 数据周期 (1mo, 3mo, 6mo, 1y, 2y, 5y, max)

    Returns:
        DataFrame with columns: (Close, ticker) MultiIndex 或 None
    """
    try:
        logger.info(f"Fetching data from Yahoo Finance: {tickers}, period={period}")
        data = yf.download(
            tickers=" ".join(tickers),
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if data is None or data.empty:
            logger.warning(f"Yahoo Finance returned empty data for {tickers}")
            return None
        logger.info(f"Yahoo Finance: got {len(data)} rows for {list(data.columns)}")
        return data
    except Exception as e:
        logger.error(f"Yahoo Finance error: {e}")
        return None


def fetch_from_alpha_vantage(ticker: str, api_key: str = "") -> Optional[pd.Series]:
    """
    从 Alpha Vantage 获取单个股票数据 (备用)

    Args:
        ticker: 股票代码
        api_key: Alpha Vantage API key

    Returns:
        Series of Close prices 或 None
    """
    if not api_key:
        logger.warning("Alpha Vantage API key not configured")
        return None

    # Alpha Vantage 的代码映射
    av_ticker_map = {
        "^VXN": "VXN",      # VXN 在 Alpha Vantage 可能需要不同代码
        "^VIX": "VIX",
        "^IXIC": "IXIC",    # 纳斯达克综合指数在某些平台可能需要不同代码
        "^GSPC": "SPX",
    }
    av_symbol = av_ticker_map.get(ticker, ticker.replace("^", ""))

    try:
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": av_symbol,
            "apikey": api_key,
            "outputsize": "full",
        }
        resp = httpx.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if "Time Series (Daily)" not in data:
            logger.warning(f"Alpha Vantage: unexpected response for {ticker}: {data.keys()}")
            return None

        ts = data["Time Series (Daily)"]
        series = pd.Series(
            {date: float(v["4. close"]) for date, v in ts.items()},
            name=ticker,
        )
        series.index = pd.to_datetime(series.index)
        series = series.sort_index()
        logger.info(f"Alpha Vantage: got {len(series)} rows for {ticker}")
        return series
    except Exception as e:
        logger.error(f"Alpha Vantage error for {ticker}: {e}")
        return None


def fetch_all_data(
    use_cache: bool = True,
    force_refresh: bool = False,
) -> Dict[str, pd.DataFrame]:
    """
    获取所有四个指数的数据

    策略:
    1. 优先使用 yfinance 批量拉取 (速度快, 一次请求)
    2. 如果某个 ticker 在 yfinance 返回为空, 用 Alpha Vantage 补充
    3. 增量拉取: 先检查已有缓存, 只拉取缺失的日期

    Returns:
        {ticker_name: DataFrame with 'Close' column}
    """
    tickers_list = list(config.TICKERS.values())
    ticker_names = list(config.TICKERS.keys())

    result = {}

    # 确定拉取周期: 需要覆盖 5 年 (最长时间窗口)
    raw = fetch_from_yfinance(tickers_list, period="5y")

    if raw is not None:
        # yfinance 返回 MultiIndex columns: ('Close', '^VIX'), ('Close', '^GSPC')
        for i, ticker_val in enumerate(tickers_list):
            name = ticker_names[i]
            try:
                if ("Close", ticker_val) in raw.columns:
                    series = raw[("Close", ticker_val)].dropna()
                    df = pd.DataFrame({"Close": series})
                    df.index.name = "Date"
                    result[name] = df
                    logger.info(f"  {name} ({ticker_val}): {len(df)} days")
                else:
                    logger.warning(f"  {name} ({ticker_val}): no Close column in yfinance output")
            except Exception as e:
                logger.error(f"  {name} ({ticker_val}): error extracting from yfinance: {e}")

    # Alpha Vantage 补充缺失的 ticker
    for i, name in enumerate(ticker_names):
        if name not in result and config.ALPHA_VANTAGE_API_KEY:
            ticker_val = tickers_list[i]
            series = fetch_from_alpha_vantage(ticker_val, config.ALPHA_VANTAGE_API_KEY)
            if series is not None:
                result[name] = pd.DataFrame({"Close": series})
                result[name].index.name = "Date"

    return result


def get_data_freshness(data_dict: Dict[str, pd.DataFrame]) -> dict:
    """
    检查数据新鲜度

    Returns:
        {
            "latest_date": "YYYY-MM-DD",  # 所有 ticker 中最新的日期
            "is_fresh": bool,              # 是否在允许的延迟内
            "ticker_dates": {ticker: "YYYY-MM-DD"},
            "warnings": [str],
        }
    """
    if not data_dict:
        return {
            "latest_date": "N/A",
            "is_fresh": False,
            "ticker_dates": {},
            "warnings": ["No data available from any source"],
        }

    latest_dates = {}
    overall_latest = None

    for name, df in data_dict.items():
        if df.empty:
            latest_dates[name] = "N/A"
            continue
        last_date = df.index.max()
        if hasattr(last_date, "strftime"):
            date_str = last_date.strftime("%Y-%m-%d")
        else:
            date_str = str(last_date)[:10]
        latest_dates[name] = date_str
        if overall_latest is None or date_str > overall_latest:
            overall_latest = date_str

    # 检查新鲜度
    expected_latest = get_latest_trading_day()
    warnings = []

    if overall_latest is None:
        is_fresh = False
        warnings.append("No data available")
    else:
        delta = (
            datetime.strptime(expected_latest, "%Y-%m-%d")
            - datetime.strptime(overall_latest, "%Y-%m-%d")
        ).days
        is_fresh = delta <= config.MAX_DATA_STALENESS_DAYS
        if delta > 0:
            warnings.append(
                f"Data is {delta} day(s) behind expected latest trading day ({expected_latest})"
            )

    return {
        "latest_date": overall_latest or "N/A",
        "is_fresh": is_fresh,
        "ticker_dates": latest_dates,
        "warnings": warnings,
    }
