"""数据获取模块 — yfinance + 缓存 + 备用数据源"""
import time
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import yfinance as yf
import pandas as pd
import numpy as np

from .config import (
    SYMBOLS, SYMBOLS_ALT, DATA_CACHE_TTL, DATA_CACHE_DIR,
    YFINANCE_PROXY, ALPHA_VANTAGE_API_KEY,
)

# ── 缓存键生成 ──
def _cache_key(symbols: tuple, period: str) -> str:
    raw = f"{'|'.join(symbols)}_{period}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]

def _cache_path(cache_key: str) -> Path:
    return DATA_CACHE_DIR / f"data_{cache_key}.json"

# ── 缓存读写 ──
def _read_cache(cache_key: str) -> Optional[dict]:
    """读取缓存，过期返回 None"""
    p = _cache_path(cache_key)
    if not p.exists():
        return None
    try:
        raw = json.loads(p.read_text())
    except Exception:
        return None
    age = time.time() - raw.get("ts", 0)
    if age > DATA_CACHE_TTL:
        return None
    return raw

def _write_cache(cache_key: str, data: dict):
    p = _cache_path(cache_key)
    p.write_text(json.dumps(data, default=str, ensure_ascii=False))

# ── 获取最新交易日 ──
def _latest_trading_day() -> str:
    """返回最近一个美股交易日（美东，非周末/假日估算）"""
    now_et = datetime.now(timezone(timedelta(hours=-4)))  # EDT
    # 简单判断：周末回退到周五
    while now_et.weekday() >= 5:  # 5=Sat, 6=Sun
        now_et -= timedelta(days=1)
    # 如果美东时间在 9:30 之前，回退到前一天
    if now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30):
        now_et -= timedelta(days=1)
        while now_et.weekday() >= 5:
            now_et -= timedelta(days=1)
    return now_et.strftime("%Y-%m-%d")

# ── yfinance 获取 ──
def _fetch_yfinance(symbol: str, period: str, retries: int = 3) -> pd.DataFrame:
    """从 yfinance 拉取数据（支持重试）"""
    last_error = None
    for attempt in range(retries):
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, auto_adjust=True)
            if df.empty:
                # 再尝试一次，去掉 ^ 前缀
                alt_symbol = symbol.lstrip("^")
                ticker2 = yf.Ticker(alt_symbol)
                df = ticker2.history(period=period, auto_adjust=True)
            if not df.empty:
                return df
            last_error = f"返回空数据"
        except Exception as e:
            last_error = str(e)
            if "Rate limited" in last_error or "Too Many Requests" in last_error:
                wait = (attempt + 1) * 5  # 5s, 10s, 15s
                time.sleep(wait)
                continue
            break
    raise RuntimeError(f"获取 {symbol} 失败: {last_error}")

# ── CBOE 数据获取（VXN 主数据源，VIX/SPX 备用）──
CBOE_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices"

# CBOE 文件名映射
_CBOE_FILE_MAP = {
    "VXN": "VXN_History.csv",
    "VIX": "VIX_History.csv",
    "GSPC": "SPX_History.csv",
}

# CBOE CSV 列名映射: (close_column_name, has_ohlc)
_CBOE_FORMAT_MAP = {
    "VXN": ("CLOSE", True),   # DATE, OPEN, HIGH, LOW, CLOSE
    "VIX": ("CLOSE", True),   # DATE, OPEN, HIGH, LOW, CLOSE
    "GSPC": ("SPX", False),   # DATE, SPX (only close)
}


def _fetch_cboe(name: str, max_rows: int = None) -> pd.DataFrame:
    """从 CBOE 官网拉取历史数据。

    CBOE 提供 VXN/VIX/SPX 的完整历史 CSV。
    格式: DATE, OPEN, HIGH, LOW, CLOSE (VXN/VIX) 或 DATE, SPX (GSPC)

    Args:
        name: "VXN", "VIX", 或 "GSPC"
        max_rows: 保留最近 N 行（None = 全部）
    """
    import io

    filename = _CBOE_FILE_MAP.get(name)
    if not filename:
        return pd.DataFrame()

    try:
        import urllib.request
        url = f"{CBOE_URL}/{filename}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()

        # 解析 CSV
        if name == "GSPC":
            # SPX: DATE,SPX
            df = pd.read_csv(io.StringIO(raw), parse_dates=["DATE"], index_col="DATE")
            df.rename(columns={"SPX": "Close"}, inplace=True)
        else:
            # VXN/VIX: DATE,OPEN,HIGH,LOW,CLOSE
            df = pd.read_csv(io.StringIO(raw), parse_dates=["DATE"], index_col="DATE")
            # 只保留 Close
            df = df[["CLOSE"]].rename(columns={"CLOSE": "Close"})

        df = df.sort_index()
        if max_rows:
            df = df.iloc[-max_rows:]

        return df

    except Exception as e:
        raise RuntimeError(f"CBOE 获取 {name} 失败: {e}")


def _fetch_alpha_vantage(symbol: str, compact: bool = True) -> pd.DataFrame:
    """从 Alpha Vantage 拉取数据（备用）"""
    import httpx
    alt_symbol = SYMBOLS_ALT.get(symbol.strip("^"), symbol.strip("^"))
    function = "TIME_SERIES_DAILY"
    outputsize = "compact" if compact else "full"
    url = (
        f"https://www.alphavantage.co/query"
        f"?function={function}&symbol={alt_symbol}"
        f"&outputsize={outputsize}&apikey={ALPHA_VANTAGE_API_KEY}"
    )
    resp = httpx.get(url, timeout=15)
    data = resp.json()
    ts_key = "Time Series (Daily)"
    if ts_key not in data:
        return pd.DataFrame()
    records = []
    for date_str, values in data[ts_key].items():
        close = float(values.get("4. close", 0))
        records.append({"Date": date_str, "Close": close})
    df = pd.DataFrame(records)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
    return df

# ── 主数据获取函数 ──
def fetch_all_data(force_refresh: bool = False) -> dict:
    """
    获取四个标的最新数据。
    返回格式：
    {
        "VXN": {"latest_close": ..., "latest_date": ..., "history": pd.DataFrame},
        ...
        "IXIC": {...},
        "VIX": {...},
        "GSPC": {...},
        "last_update": "2024-01-15 16:00 EST",
        "is_trading_day": True,
        "data_fresh": True,
    }
    """
    periods = ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"]
    all_symbols = list(SYMBOLS.values())
    cache_key = _cache_key(tuple(all_symbols), "max")

    # 尝试读缓存
    if not force_refresh:
        cached = _read_cache(cache_key)
        if cached:
            # 检查跨天
            cache_day = cached.get("cache_day", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if cache_day == today:
                # 还原 DataFrame
                result = {}
                for name, sym in SYMBOLS.items():
                    if name in cached.get("data", {}):
                        d = cached["data"][name]
                        df = pd.DataFrame(d["history"])
                        if not df.empty and "Date" in df.columns:
                            df["Date"] = pd.to_datetime(df["Date"])
                            df = df.set_index("Date")
                        result[name] = {
                            "latest_close": d["latest_close"],
                            "latest_date": d["latest_date"],
                            "history": df,
                        }
                result["last_update"] = cached.get("last_update", "Unknown")
                result["data_fresh"] = True
                result["is_trading_day"] = cached.get("is_trading_day", True)
                return result

    # 实时拉取
    result = {}

    # ── Step 1: VXN 从 CBOE 获取 ──
    vxn_sym = SYMBOLS.get("VXN", "^VXN")
    df_vxn = pd.DataFrame()
    try:
        df_vxn = _fetch_cboe("VXN")
    except Exception:
        try:
            df_vxn = _fetch_yfinance(vxn_sym, "max")
        except Exception:
            pass

    if df_vxn.empty:
        raise RuntimeError(f"无法获取 VXN ({vxn_sym}) 的数据，所有数据源均不可用")

    result["VXN"] = {
        "latest_close": float(df_vxn["Close"].iloc[-1]),
        "latest_date": df_vxn.index[-1].strftime("%Y-%m-%d"),
        "history": df_vxn,
    }

    # ── Step 2: IXIC, VIX, GSPC 从 yfinance 批量获取 ──
    yf_symbols = []
    yf_names = []
    for name, sym in SYMBOLS.items():
        if name != "VXN":
            yf_symbols.append(sym)
            yf_names.append(name)

    # 批量请求，一次 HTTP 调用避免频率限制
    yf_data = {}
    try:
        raw = yf.download(
            tickers=" ".join(yf_symbols),
            period="max",
            interval="1d",
            progress=False,
            auto_adjust=True,
        )
        if raw is not None and not raw.empty:
            for i, sym in enumerate(yf_symbols):
                name = yf_names[i]
                try:
                    if ("Close", sym) in raw.columns:
                        series = raw[("Close", sym)].dropna()
                        df = pd.DataFrame({"Close": series})
                        df.index.name = "Date"
                        yf_data[name] = df
                except Exception:
                    pass
    except Exception:
        pass

    # 逐个补充失败的
    import logging
    _log = logging.getLogger(__name__)
    
    data_warnings = []
    for i, name in enumerate(yf_names):
        if name in yf_data:
            df = yf_data[name]
        else:
            sym = yf_symbols[i]
            df = pd.DataFrame()
            # 逐个重试
            try:
                df = _fetch_yfinance(sym, "max")
            except Exception:
                pass
            # CBOE 备用
            if df.empty and name in ("VIX", "GSPC"):
                try:
                    df = _fetch_cboe(name)
                except Exception:
                    pass

        if df.empty:
            _log.warning(f"无法获取 {name} ({yf_symbols[i]})，跳过")
            data_warnings.append(f"{name} 数据不可用")
            continue  # 跳过此 symbol，不阻塞其他数据

        result[name] = {
            "latest_close": float(df["Close"].iloc[-1]),
            "latest_date": df.index[-1].strftime("%Y-%m-%d"),
            "history": df,
        }
        time.sleep(0.5)

    # 数据新鲜度
    latest_trading_day = _latest_trading_day()
    latest_dates = [r["latest_date"] for r in result.values() if r["latest_date"] != "N/A"]
    data_latest = max(latest_dates) if latest_dates else "N/A"
    result["last_update"] = f"{data_latest} (latest trading day)"
    result["is_trading_day"] = (
        datetime.now().strftime("%Y-%m-%d") == latest_trading_day
    )
    result["data_fresh"] = data_latest >= _latest_trading_day()
    if data_warnings:
        result["warnings"] = data_warnings

    # 写入缓存
    cache_data = {}
    for name in SYMBOLS:
        df = result[name]["history"]
        hist_records = df.reset_index().to_dict(orient="records") if not df.empty else []
        cache_data[name] = {
            "latest_close": result[name]["latest_close"],
            "latest_date": result[name]["latest_date"],
            "history": hist_records,
        }
    _write_cache(cache_key, {
        "ts": time.time(),
        "cache_day": datetime.now().strftime("%Y-%m-%d"),
        "last_update": result["last_update"],
        "is_trading_day": result["is_trading_day"],
        "data": cache_data,
    })

    return result


def get_latest_prices(data: dict) -> dict:
    """提取最新价格摘要"""
    prices = {}
    for name in ["VXN", "IXIC", "VIX", "GSPC"]:
        if name in data:
            prices[name] = {
                "close": data[name]["latest_close"],
                "date": data[name]["latest_date"],
            }
    return prices


def get_recent_table(data: dict, days: int = 10) -> pd.DataFrame:
    """最近 N 个交易日的收盘价表格"""
    records = []
    # 收集所有日期
    all_dates = set()
    for name in ["VXN", "IXIC", "VIX", "GSPC"]:
        if name in data:
            df = data[name]["history"]
            if not df.empty:
                all_dates.update(df.index.strftime("%Y-%m-%d"))

    sorted_dates = sorted(all_dates, reverse=True)[:days]

    for d in sorted_dates:
        row = {"日期": d}
        for name in ["VXN", "IXIC", "VIX", "GSPC"]:
            if name in data:
                df = data[name]["history"]
                try:
                    val = df.loc[d, "Close"] if d in df.index else None
                    row[name] = round(float(val), 2) if val is not None else None
                except Exception:
                    row[name] = None
        records.append(row)

    return pd.DataFrame(records).sort_values("日期")
