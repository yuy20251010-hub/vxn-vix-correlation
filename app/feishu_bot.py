"""飞书机器人集成 — 消息卡片、命令响应、消息推送"""
import time
import json
import hashlib
from typing import Optional, Dict, Any

import httpx

from .config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET, BASE_URL,
    FEISHU_PUSH_CHAT_IDS,
)


# ── 飞书 API 客户端 ──
class FeishuClient:
    """飞书 API 客户端，自动管理 tenant_access_token"""

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires: float = 0

    async def _ensure_token(self):
        """确保 token 有效"""
        if self._token and time.time() < self._token_expires - 60:
            return

        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        resp = httpx.post(url, json={
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET,
        }, timeout=10)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书认证失败: {data}")
        self._token = data["tenant_access_token"]
        self._token_expires = time.time() + data.get("expire", 7200)

    async def _headers(self) -> dict:
        await self._ensure_token()
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    async def send_message(self, receive_id: str, msg_type: str, content: str) -> dict:
        """发送消息到指定 chat_id 或 open_id"""
        headers = await self._headers()
        body = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": content,
        }

        # 判断 receive_id 类型
        if receive_id.startswith("oc_"):
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        elif len(receive_id) > 20:
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
        else:
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"

        resp = httpx.post(url, headers=headers, json=body, timeout=10)
        return resp.json()

    async def reply_message(self, message_id: str, msg_type: str, content: str) -> dict:
        """回复消息"""
        headers = await self._headers()
        body = {
            "msg_type": msg_type,
            "content": content,
        }
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
        resp = httpx.post(url, headers=headers, json=body, timeout=10)
        return resp.json()

    async def upload_image(self, image_bytes: bytes, image_type: str = "message") -> str:
        """上传图片，返回 image_key"""
        headers = {
            "Authorization": f"Bearer {self._token}",
        }
        await self._ensure_token()
        headers["Authorization"] = f"Bearer {self._token}"

        url = "https://open.feishu.cn/open-apis/im/v1/images"

        # multipart upload
        files = {
            "image_type": (None, image_type),
            "image": ("chart.png", image_bytes, "image/png"),
        }
        resp = httpx.post(url, headers={"Authorization": headers["Authorization"]}, files=files, timeout=15)
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"上传图片失败: {data}")
        return data["data"]["image_key"]


# ── 卡片消息构建 ──
def build_correlation_card(
    corr_data: dict,
    rolling_chart_base64: str,
    update_time: str,
) -> dict:
    """
    构建飞书卡片消息 JSON。
    返回飞书卡片 content 的 JSON 字符串。
    """
    vxn_row = corr_data.get("vxn_ixic", {})
    vix_row = corr_data.get("vix_gspc", {})

    # 构建表格的列
    windows = ["1个月", "3个月", "6个月", "1年", "2年", "5年"]

    # 相关性表格内容
    vxn_cells = []
    vix_cells = []
    for w in windows:
        v = vxn_row.get(w, {})
        c = v.get("correlation")
        vxn_cells.append(f"{c:.3f}" if c is not None and c == c else "N/A")  # NaN check

    for w in windows:
        v = vix_row.get(w, {})
        c = v.get("correlation")
        vix_cells.append(f"{c:.3f}" if c is not None and c == c else "N/A")

    # 使用飞书卡片模板
    dashboard_url = f"{BASE_URL}/dashboard" if BASE_URL else ""

    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": "📊 VXN/VIX 与美股指数相关性分析"
            },
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**数据更新**: {update_time}\n{corr_data.get('summary_text', '')}"
                }
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**📈 VXN — 纳斯达克 相关系数**"}
            },
            {
                "tag": "table",
                "columns": [
                    {"name": "窗口", "width": "auto"},
                    {"name": "1个月", "width": "auto"},
                    {"name": "3个月", "width": "auto"},
                    {"name": "6个月", "width": "auto"},
                    {"name": "1年", "width": "auto"},
                    {"name": "2年", "width": "auto"},
                    {"name": "5年", "width": "auto"},
                ],
                "rows": [
                    [
                        {"tag": "text", "text": "VXN-IXIC"},
                        *[{"tag": "text", "text": v} for v in vxn_cells],
                    ]
                ],
            },
            {"tag": "hr"},
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "**📉 VIX — 标普500 相关系数**"}
            },
            {
                "tag": "table",
                "columns": [
                    {"name": "窗口", "width": "auto"},
                    {"name": "1个月", "width": "auto"},
                    {"name": "3个月", "width": "auto"},
                    {"name": "6个月", "width": "auto"},
                    {"name": "1年", "width": "auto"},
                    {"name": "2年", "width": "auto"},
                    {"name": "5年", "width": "auto"},
                ],
                "rows": [
                    [
                        {"tag": "text", "text": "VIX-SPX"},
                        *[{"tag": "text", "text": v} for v in vix_cells],
                    ]
                ],
            },
            {"tag": "hr"},
        ],
    }

    # 如果有图表 base64，添加图片（通过 img_key 方式）
    # 注意：卡片消息中直接放 base64 可能不被支持，改用 image 元素
    # 这里先添加一个 markdown 提示，图片通过后续上传

    # 添加按钮
    actions = []
    if dashboard_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "🔗 查看完整仪表板"},
            "type": "primary",
            "url": dashboard_url,
        })
    actions.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "🔄 刷新数据"},
        "type": "default",
        "value": {"action": "refresh"},
    })

    card["elements"].append({"tag": "action", "actions": actions})
    card["elements"].append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "数据来源: Yahoo Finance | 基于日对数收益率计算 Pearson 相关系数"}]
    })

    return card


def build_simple_text_card(text: str) -> str:
    """构建简单文本卡片"""
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "📊 相关性分析"},
            "template": "blue",
        },
        "elements": [
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": text}
            }
        ],
    }
    return json.dumps(card, ensure_ascii=False)


def build_daily_push_card(
    corr_data: dict,
    chart_image_key: str,
    update_time: str,
    dashboard_url: str,
) -> str:
    """构建每日推送卡片（与实时卡片类似，但包含图片）"""
    card = build_correlation_card(corr_data, "", update_time)

    # 添加图表图片
    if chart_image_key:
        # 在 hr 之后插入图片元素
        img_element = {
            "tag": "img",
            "img_key": chart_image_key,
            "alt": {"tag": "plain_text", "content": "滚动相关系数图"},
            "mode": "fit_horizontal",
            "preview": True,
        }
        # 插入到 actions 之前
        elements = card["elements"]
        # 找到 action 位置
        for i, el in enumerate(elements):
            if el.get("tag") == "action":
                elements.insert(i, {"tag": "hr"})
                elements.insert(i, img_element)
                break

    # 更新按钮 URL
    for el in card["elements"]:
        if el.get("tag") == "action":
            for action in el.get("actions", []):
                if action.get("text", {}).get("content") == "🔗 查看完整仪表板":
                    action["url"] = dashboard_url

    return json.dumps(card, ensure_ascii=False)


# ── 命令解析 ──
def parse_command(text: str) -> Optional[str]:
    """解析用户输入，返回命令类型"""
    text = text.strip().lower()
    commands = ["/corr", "相关性", "分析", "corr", "/分析", "/相关性"]

    # 去掉 @mention
    if "@" in text:
        parts = text.split()
        text = " ".join([p for p in parts if not p.startswith("@")])

    for cmd in commands:
        if text == cmd or text.startswith(cmd):
            return "correlation"

    return None
