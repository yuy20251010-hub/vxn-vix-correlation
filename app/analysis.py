"""相关性分析模块 — Pearson 系数 + 滚动相关性 + 解读"""
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
from scipy import stats


# ── 时间窗口定义 ──
WINDOWS = {
    "1个月": 21,       # ~21 trading days
    "3个月": 63,
    "6个月": 126,
    "1年": 252,
    "2年": 504,
    "5年": 1260,
}

WINDOW_LABELS = list(WINDOWS.keys())


def _get_history_for_window(df: pd.DataFrame, trading_days: int) -> pd.Series:
    """从 DataFrame 中取最近 N 个交易日的收盘价"""
    if df.empty:
        return pd.Series(dtype=float)
    closes = df["Close"].dropna()
    if len(closes) < trading_days:
        return closes  # 数据量不足时返回全部
    return closes.iloc[-trading_days:]


def _align_and_correlate(
    series1: pd.Series, series2: pd.Series
) -> Tuple[float, float, int]:
    """
    对齐两个 Series 的日期，计算 Pearson 相关系数和 p 值。
    返回 (correlation, p_value, n_samples)
    """
    # 取交集日期
    common_idx = series1.index.intersection(series2.index)
    if len(common_idx) < 5:
        return float("nan"), float("nan"), 0

    s1 = series1.loc[common_idx]
    s2 = series2.loc[common_idx]

    # 计算收益率（日对数收益率）以消除趋势影响
    ret1 = np.log(s1 / s1.shift(1)).dropna()
    ret2 = np.log(s2 / s2.shift(1)).dropna()

    # 收益率相关性
    common_idx_ret = ret1.index.intersection(ret2.index)
    r1 = ret1.loc[common_idx_ret]
    r2 = ret2.loc[common_idx_ret]

    if len(r1) < 5:
        return float("nan"), float("nan"), 0

    corr, p_val = stats.pearsonr(r1, r2)
    return round(corr, 4), round(p_val, 4), len(r1)


def _correlation_strength(corr: float) -> str:
    """解读相关性强度"""
    if np.isnan(corr):
        return "数据不足"
    abs_c = abs(corr)
    if abs_c >= 0.8:
        strength = "极强"
    elif abs_c >= 0.6:
        strength = "强"
    elif abs_c >= 0.4:
        strength = "中等"
    elif abs_c >= 0.2:
        strength = "弱"
    else:
        strength = "极弱"
    direction = "正相关" if corr > 0 else "负相关"
    return f"{strength}{direction}"


def analyze_correlations(data: dict) -> dict:
    """
    主分析函数：计算各时间窗口的相关系数。
    返回：
    {
        "vxn_ixic": {
            "1个月": {"correlation": 0.72, "p_value": 0.001, "n": 21},
            ...
        },
        "vix_gspc": {...},
        "last_update": "2024-01-15",
        "summary_text": "简短解读...",
        "recent_table": pd.DataFrame,
    }
    """
    vxn_hist = data.get("VXN", {}).get("history", pd.DataFrame())
    ixic_hist = data.get("IXIC", {}).get("history", pd.DataFrame())
    vix_hist = data.get("VIX", {}).get("history", pd.DataFrame())
    gspc_hist = data.get("GSPC", {}).get("history", pd.DataFrame())

    result = {
        "vxn_ixic": {},
        "vix_gspc": {},
        "last_update": data.get("last_update", "Unknown"),
    }

    # ── 各窗口相关性 ──
    for label, days in WINDOWS.items():
        # VXN vs IXIC
        vxn_series = _get_history_for_window(vxn_hist, days)
        ixic_series = _get_history_for_window(ixic_hist, days)
        corr, p, n = _align_and_correlate(vxn_series, ixic_series)
        result["vxn_ixic"][label] = {
            "correlation": corr,
            "p_value": p,
            "n_samples": n,
        }

        # VIX vs GSPC
        vix_series = _get_history_for_window(vix_hist, days)
        gspc_series = _get_history_for_window(gspc_hist, days)
        corr, p, n = _align_and_correlate(vix_series, gspc_series)
        result["vix_gspc"][label] = {
            "correlation": corr,
            "p_value": p,
            "n_samples": n,
        }

    # ── 生成简短解读 ──
    vxn_1m = result["vxn_ixic"].get("1个月", {})
    vix_1m = result["vix_gspc"].get("1个月", {})

    c1 = vxn_1m.get("correlation", float("nan"))
    c2 = vix_1m.get("correlation", float("nan"))

    parts = []
    if not np.isnan(c1):
        parts.append(
            f"过去1个月 VXN-纳斯达克 相关系数 {c1:.2f}（{_correlation_strength(c1)}），"
        )
        # 与 3 个月对比
        vxn_3m = result["vxn_ixic"].get("3个月", {}).get("correlation", float("nan"))
        if not np.isnan(vxn_3m):
            delta = c1 - vxn_3m
            parts.append(f"较3个月前{'上升' if delta > 0 else '下降'}{abs(delta):.2f}")

    parts.append("；")

    if not np.isnan(c2):
        parts.append(
            f"VIX-标普500 相关系数 {c2:.2f}（{_correlation_strength(c2)}）"
        )
        vix_3m = result["vix_gspc"].get("3个月", {}).get("correlation", float("nan"))
        if not np.isnan(vix_3m):
            delta = c2 - vix_3m
            parts.append(f"，较3个月前{'上升' if delta > 0 else '下降'}{abs(delta):.2f}")

    # 市场解读
    if not np.isnan(c1) and not np.isnan(c2):
        if c2 < -0.6:
            parts.append("。VIX 负相关性较强，市场避险情绪明显；")
        elif c2 > -0.3:
            parts.append("。VIX 负相关性减弱，市场风险偏好回升；")

        if abs(c1) > abs(c2):
            parts.append("纳斯达克波动率指数相关性更强。")
        elif abs(c2) > abs(c1):
            parts.append("标普波动率指数相关性更强。")
        else:
            parts.append("两个波动率指数相关性相当。")

    result["summary_text"] = "".join(parts)

    return result


def compute_rolling_correlation(
    data: dict,
    pair: str = "vxn_ixic",
    window: int = 30,
    lookback_years: int = 1,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    计算滚动相关系数。
    pair: "vxn_ixic" 或 "vix_gspc"
    window: 滚动窗口（交易日数）
    lookback_years: 回看年数
    """
    if pair == "vxn_ixic":
        s1 = data.get("VXN", {}).get("history", pd.DataFrame())
        s2 = data.get("IXIC", {}).get("history", pd.DataFrame())
        name = "VXN-纳斯达克"
    else:
        s1 = data.get("VIX", {}).get("history", pd.DataFrame())
        s2 = data.get("GSPC", {}).get("history", pd.DataFrame())
        name = "VIX-标普500"

    if s1.empty or s2.empty:
        return pd.DataFrame()

    close1 = s1["Close"].dropna()
    close2 = s2["Close"].dropna()

    # 日期过滤
    if start_date:
        start_dt = pd.Timestamp(start_date)
        close1 = close1[close1.index >= start_dt]
        close2 = close2[close2.index >= start_dt]
    if end_date:
        end_dt = pd.Timestamp(end_date)
        close1 = close1[close1.index <= end_dt]
        close2 = close2[close2.index <= end_dt]

    # 对数收益率
    ret1 = np.log(close1 / close1.shift(1)).dropna()
    ret2 = np.log(close2 / close2.shift(1)).dropna()

    # 取交集
    common_idx = ret1.index.intersection(ret2.index)
    ret1 = ret1.loc[common_idx]
    ret2 = ret2.loc[common_idx]

    if len(ret1) < window:
        return pd.DataFrame()

    # 滚动相关系数
    rolling_corr = ret1.rolling(window=window).corr(ret2)

    df = pd.DataFrame({
        "date": common_idx,
        "correlation": rolling_corr.values,
    })
    df = df.dropna()
    df["pair"] = name

    return df


def compute_percentiles(rolling_df: pd.DataFrame) -> dict:
    """计算滚动相关系数的分位数"""
    if rolling_df.empty:
        return {}
    corr_vals = rolling_df["correlation"].dropna()
    return {
        "current": round(float(corr_vals.iloc[-1]), 4) if len(corr_vals) > 0 else None,
        "q25": round(float(corr_vals.quantile(0.25)), 4),
        "q50": round(float(corr_vals.quantile(0.50)), 4),
        "q75": round(float(corr_vals.quantile(0.75)), 4),
        "min": round(float(corr_vals.min()), 4),
        "max": round(float(corr_vals.max()), 4),
    }
