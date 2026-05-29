"""定时任务 — 每日自动推送"""
import asyncio
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import PUSH_HOUR, PUSH_MINUTE, PUSH_TIMEZONE, FEISHU_PUSH_CHAT_IDS, BASE_URL
from .data import fetch_all_data
from .analysis import analyze_correlations, compute_rolling_correlation, compute_percentiles
from .charts import rolling_correlation_chart
from .feishu_bot import FeishuClient, build_daily_push_card

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=PUSH_TIMEZONE)


async def daily_push_task():
    """每日推送任务：获取最新数据 → 分析 → 生成图表 → 推送飞书消息"""
    logger.info("开始每日推送任务...")
    chat_ids = [c.strip() for c in FEISHU_PUSH_CHAT_IDS.split(",") if c.strip()]

    if not chat_ids:
        logger.warning("未配置推送目标 (FEISHU_PUSH_CHAT_IDS)，跳过推送")
        return

    client = FeishuClient()

    try:
        # 1. 获取最新数据（实时拉取）
        logger.info("拉取最新行情数据...")
        data = fetch_all_data(force_refresh=True)

        # 2. 分析
        logger.info("计算相关性...")
        corr_data = analyze_correlations(data)

        # 3. 生成滚动相关图表
        df_vxn = compute_rolling_correlation(data, "vxn_ixic")
        df_vix = compute_rolling_correlation(data, "vix_gspc")
        pct_vxn = compute_percentiles(df_vxn)
        pct_vix = compute_percentiles(df_vix)

        chart_b64 = rolling_correlation_chart(df_vxn, df_vix, pct_vxn, pct_vix, as_base64=True)

        # 4. 上传图片到飞书（仅当图表是 base64 编码时）
        import base64 as b64
        image_key = ""
        if chart_b64 and not chart_b64.startswith("<"):  # 不是 HTML
            try:
                image_bytes = b64.b64decode(chart_b64)
                image_key = await client.upload_image(image_bytes)
                logger.info(f"图片上传成功: {image_key}")
            except Exception as e:
                logger.error(f"图片上传失败: {e}，将不包含图片")

        # 5. 构建推送卡片
        dashboard_url = f"{BASE_URL}/dashboard" if BASE_URL else ""
        update_time = data.get("last_update", datetime.now().strftime("%Y-%m-%d"))

        card_content = build_daily_push_card(
            corr_data, image_key, update_time, dashboard_url
        )

        # 6. 推送到每个目标
        for chat_id in chat_ids:
            try:
                result = await client.send_message(
                    receive_id=chat_id,
                    msg_type="interactive",
                    content=card_content,
                )
                logger.info(f"推送成功 [{chat_id}]: {result}")
            except Exception as e:
                logger.error(f"推送失败 [{chat_id}]: {e}")

        logger.info("每日推送任务完成")

    except Exception as e:
        logger.error(f"每日推送任务异常: {e}", exc_info=True)


def start_scheduler():
    """启动定时任务调度器"""
    trigger = CronTrigger(
        hour=PUSH_HOUR,
        minute=PUSH_MINUTE,
        timezone=PUSH_TIMEZONE,
    )
    scheduler.add_job(
        daily_push_task,
        trigger=trigger,
        id="daily_push",
        name="每日相关性分析推送",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"定时任务已启动: 每天 {PUSH_HOUR:02d}:{PUSH_MINUTE:02d} ({PUSH_TIMEZONE}) 推送"
    )


def stop_scheduler():
    """停止调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
