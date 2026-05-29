"""
缓存模块 — 10分钟短时缓存
特点:
- 同一天内多次请求复用缓存
- 跨天自动刷新
- 用户可强制刷新 (refresh=true)
"""
import logging
import time
from datetime import datetime
from typing import Dict, Optional, Any, Tuple

import pandas as pd

from src.config import config

logger = logging.getLogger(__name__)


class DataCache:
    """
    内存缓存, 存储拉取的数据和分析结果
    TTL: 默认 10 分钟
    跨天失效: 缓存日期与当前日期不一致时自动失效
    """

    def __init__(self):
        self._data: Optional[Dict[str, pd.DataFrame]] = None
        self._analysis_result: Optional[Dict[str, Any]] = None
        self._timestamp: float = 0.0
        self._cache_date: str = ""  # 缓存创建的日期 (北京时间)

    def _get_today_str(self) -> str:
        """获取北京时间今天的日期字符串"""
        return datetime.now().strftime("%Y-%m-%d")

    def _is_valid(self) -> bool:
        """检查缓存是否有效 (未过期 + 未跨天)"""
        if self._data is None:
            return False
        # 跨天检查
        if self._cache_date != self._get_today_str():
            logger.info("Cache invalidated: cross-day detected")
            return False
        # TTL 检查
        elapsed = time.time() - self._timestamp
        if elapsed > config.CACHE_TTL_SECONDS:
            logger.info(f"Cache expired: {elapsed:.0f}s > {config.CACHE_TTL_SECONDS}s")
            return False
        return True

    def get_data(self, force_refresh: bool = False) -> Tuple[Optional[Dict[str, pd.DataFrame]], bool]:
        """
        获取缓存的数据

        Returns:
            (data_dict, is_cached): 数据字典和是否是缓存命中
        """
        if not force_refresh and self._is_valid():
            logger.info("Cache HIT for raw data")
            return self._data, True
        return None, False

    def set_data(self, data: Dict[str, pd.DataFrame]):
        """设置数据缓存"""
        self._data = data
        self._timestamp = time.time()
        self._cache_date = self._get_today_str()
        logger.info(f"Data cached at {self._cache_date}")

    def get_analysis(self, force_refresh: bool = False) -> Tuple[Optional[Dict[str, Any]], bool]:
        """
        获取缓存的分析结果

        Returns:
            (result_dict, is_cached)
        """
        if not force_refresh and self._is_valid():
            logger.info("Cache HIT for analysis result")
            return self._analysis_result, True
        return None, False

    def set_analysis(self, result: Dict[str, Any]):
        """设置分析结果缓存"""
        self._analysis_result = result
        # 分析结果的 timestamp 和 date 沿用 data 缓存的
        # 但这里更新一下确保一致性
        if not self._timestamp or self._cache_date != self._get_today_str():
            self._timestamp = time.time()
            self._cache_date = self._get_today_str()
        logger.info(f"Analysis result cached at {self._cache_date}")

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存状态信息"""
        valid = self._is_valid()
        return {
            "is_cached": self._data is not None,
            "is_valid": valid,
            "cache_date": self._cache_date,
            "age_seconds": time.time() - self._timestamp if self._timestamp else 0,
            "ttl_seconds": config.CACHE_TTL_SECONDS,
        }

    def invalidate(self):
        """手动失效缓存"""
        self._data = None
        self._analysis_result = None
        self._timestamp = 0
        self._cache_date = ""
        logger.info("Cache manually invalidated")


# 全局缓存实例
cache = DataCache()
