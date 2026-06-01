"""FastAPI 主应用 — API 端点 + Web 仪表板服务"""
import io
import json
import logging
import base64
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    PORT, HOST, BASE_URL, BASE_DIR, STATIC_DIR,
    FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_VERIFICATION_TOKEN,
)
from .data import fetch_all_data, get_latest_prices, get_recent_table
from .analysis import (
    analyze_correlations,
    compute_rolling_correlation,
    compute_percentiles,
)
from .charts import (
    rolling_correlation_chart,
    correlation_heatmap_chart,
    price_chart,
    interactive_rolling_chart,
)
from .feishu_bot import (
    FeishuClient,
    build_correlation_card,
    build_simple_text_card,
    parse_command,
)
from .scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _clean_nan(obj):
    """递归清理 NaN/Inf 值，替换为 None"""
    import math
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


# ── 生命周期 ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    logger.info(f"服务启动: http://{HOST}:{PORT}")
    yield
    stop_scheduler()


app = FastAPI(
    title="VXN/VIX 相关性分析",
    description="实时获取 VXN、纳斯达克、VIX、标普500 指数数据并进行相关性分析",
    version="1.0.0",
    lifespan=lifespan,
)


# ── API 端点 ──

@app.get("/")
async def root():
    return {"service": "VXN/VIX Correlation Analysis", "status": "running", "version": "2.0.0", "vxn_source": "CBOE"}


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}


@app.get("/correlation")
async def get_correlation(force_refresh: bool = Query(False)):
    """
    获取最新相关性分析结果（JSON）。
    - force_refresh=true 强制跳过缓存重新拉取数据。
    """
    try:
        # 1. 获取数据
        data = fetch_all_data(force_refresh=force_refresh)

        # 2. 分析
        corr_data = analyze_correlations(data)

        # 3. 滚动相关
        df_vxn = compute_rolling_correlation(data, "vxn_ixic")
        df_vix = compute_rolling_correlation(data, "vix_gspc")
        pct_vxn = compute_percentiles(df_vxn)
        pct_vix = compute_percentiles(df_vix)

        # 4. 图表 base64
        chart_b64 = rolling_correlation_chart(df_vxn, df_vix, pct_vxn, pct_vix, as_base64=True)

        # 5. 最近 10 日表格
        recent_df = get_recent_table(data, days=10)

        # 6. 最新价格
        prices = get_latest_prices(data)

        result = {
            "success": True,
            "last_update": data.get("last_update"),
            "is_trading_day": data.get("is_trading_day", True),
            "data_fresh": data.get("data_fresh", True),
            "prices": prices,
            "correlations": corr_data,
            "rolling_correlation": {
                "vxn_ixic": pct_vxn,
                "vix_gspc": pct_vix,
            },
            "chart_base64": chart_b64,
            "recent_table": recent_df.to_dict(orient="records") if not recent_df.empty else [],
            "summary": corr_data.get("summary_text", ""),
            "dashboard_url": f"{BASE_URL}/dashboard" if BASE_URL else "/dashboard",
            "timestamp": datetime.now().isoformat(),
        }

        return JSONResponse(_clean_nan(result))

    except RuntimeError as e:
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": "数据获取失败，请稍后重试或检查数据源配置",
        }, status_code=503)
    except Exception as e:
        logger.error(f"相关性分析失败: {e}", exc_info=True)
        return JSONResponse({
            "success": False,
            "error": str(e),
        }, status_code=500)


@app.get("/correlation/chart")
async def get_correlation_chart(
    pair: str = Query("vxn_ixic", description="vxn_ixic 或 vix_gspc"),
    window: int = Query(30, ge=5, le=252),
    start_date: str = Query(""),
    end_date: str = Query(""),
):
    """获取滚动相关系数图（HTML）"""
    try:
        data = fetch_all_data()
        df = compute_rolling_correlation(
            data, pair, window=window,
            start_date=start_date or None,
            end_date=end_date or None,
        )
        # 也计算另一个 pair
        other_pair = "vix_gspc" if pair == "vxn_ixic" else "vxn_ixic"
        df_other = compute_rolling_correlation(
            data, other_pair, window=window,
            start_date=start_date or None,
            end_date=end_date or None,
        )

        if pair == "vxn_ixic":
            html = interactive_rolling_chart(df, df_other, start_date, end_date)
        else:
            html = interactive_rolling_chart(df_other, df, start_date, end_date)

        return HTMLResponse(
            f"<html><head><meta charset='utf-8'></head><body>{html}</body></html>"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/correlation/data.csv")
async def download_csv(
    pair: str = Query("vxn_ixic"),
    start_date: str = Query(""),
    end_date: str = Query(""),
):
    """下载相关系数数据为 CSV"""
    try:
        data = fetch_all_data()
        df = compute_rolling_correlation(
            data, pair,
            start_date=start_date or None,
            end_date=end_date or None,
        )
        if df.empty:
            raise HTTPException(status_code=404, detail="无数据")

        csv_content = df.to_csv(index=False)
        return PlainTextResponse(
            csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={pair}_correlation.csv"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 飞书 Webhook ──

@app.post("/webhook")
async def feishu_webhook(request: Request):
    """
    接收飞书事件回调。
    支持：
    - URL 验证（首次配置时）
    - 消息事件（用户发送命令）
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    # URL 验证
    if body.get("type") == "url_verification":
        token = body.get("token", "")
        challenge = body.get("challenge", "")
        # 验证 token
        if FEISHU_VERIFICATION_TOKEN and token != FEISHU_VERIFICATION_TOKEN:
            return JSONResponse({"error": "invalid token"}, status_code=403)
        return JSONResponse({"challenge": challenge})

    # 消息事件
    header = body.get("header", {})
    event_type = header.get("event_type", "")

    if event_type == "im.message.receive_v1":
        event = body.get("event", {})
        message = event.get("message", {})
        msg_type = message.get("message_type", "")
        msg_id = message.get("message_id", "")
        chat_id = message.get("chat_id", "")
        content_str = message.get("content", "{}")

        # 解析消息内容
        try:
            content_obj = json.loads(content_str)
            text = content_obj.get("text", "")
        except Exception:
            text = ""

        logger.info(f"收到消息: chat_id={chat_id}, text={text[:100]}")

        # 解析命令
        cmd = parse_command(text)
        if cmd != "correlation":
            # 不是目标命令，忽略
            return JSONResponse({"code": 0})

        # 异步处理：先回复"正在获取数据"，然后计算并返回结果
        client = FeishuClient()

        # 先回复确认
        await client.reply_message(
            msg_id,
            "text",
            json.dumps({"text": "⏳ 正在获取最新数据，请稍候..."}, ensure_ascii=False),
        )

        try:
            # 获取数据并分析
            data = fetch_all_data(force_refresh=True)
            corr_data = analyze_correlations(data)

            df_vxn = compute_rolling_correlation(data, "vxn_ixic")
            df_vix = compute_rolling_correlation(data, "vix_gspc")
            pct_vxn = compute_percentiles(df_vxn)
            pct_vix = compute_percentiles(df_vix)

            chart_b64 = rolling_correlation_chart(df_vxn, df_vix, pct_vxn, pct_vix, as_base64=True)

            # 上传图表（仅当是 base64 时）
            image_bytes_raw = base64.b64decode(chart_b64) if chart_b64 and not chart_b64.startswith("<") else None
            image_key = ""
            if image_bytes_raw:
                try:
                    image_key = await client.upload_image(image_bytes_raw)
                except Exception as e:
                    logger.error(f"上传图片失败: {e}")

            # 构建卡片
            update_time = data.get("last_update", "Unknown")
            card = build_correlation_card(corr_data, chart_b64, update_time)

            # 如果上传了图片，添加图片
            if image_key:
                elements = card.get("elements", [])
                # 在 action 前插入图片
                for i, el in enumerate(elements):
                    if el.get("tag") == "action":
                        img_el = {
                            "tag": "img",
                            "img_key": image_key,
                            "alt": {"tag": "plain_text", "content": "滚动相关系数"},
                            "mode": "fit_horizontal",
                            "preview": True,
                        }
                        elements.insert(i, {"tag": "hr"})
                        elements.insert(i, img_el)
                        break

            card_json = json.dumps(card, ensure_ascii=False)

            # 发送卡片回复
            await client.reply_message(msg_id, "interactive", card_json)

        except Exception as e:
            logger.error(f"处理分析请求失败: {e}", exc_info=True)
            await client.reply_message(
                msg_id,
                "text",
                json.dumps({
                    "text": f"❌ 分析失败: {str(e)}\n请检查数据源是否可用。"
                }, ensure_ascii=False),
            )

    return JSONResponse({"code": 0})


# ── Web 仪表板 ──

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    start_date: str = Query(""),
    end_date: str = Query(""),
    window: int = Query(30, ge=5, le=252),
):
    """Web 交互式仪表板"""
    from pathlib import Path
    template_path = BASE_DIR / "templates" / "dashboard.html"

    if template_path.exists():
        html = template_path.read_text(encoding="utf-8")
        # 替换占位符
        html = html.replace("{{WINDOW}}", str(window))
        html = html.replace("{{START_DATE}}", start_date)
        html = html.replace("{{END_DATE}}", end_date)
        return HTMLResponse(html)

    # 后备：内联 HTML
    return HTMLResponse(_dashboard_html())


# ── 静态文件 ──
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _dashboard_html() -> str:
    """内联仪表板 HTML（在模板未找到时使用）"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VXN/VIX 相关性分析仪表板</title>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f0f23; color: #e0e0e0;
            min-height: 100vh;
        }
        .header {
            background: linear-gradient(135deg, #1a1a3e 0%, #16213e 100%);
            padding: 20px 24px;
            border-bottom: 1px solid #2a2a4a;
        }
        .header h1 { font-size: 1.5em; font-weight: 600; }
        .header .subtitle { font-size: 0.85em; color: #888; margin-top: 4px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .controls {
            display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
            padding: 16px; background: #16213e; border-radius: 8px;
            margin-bottom: 20px;
        }
        .controls label { font-size: 0.9em; color: #aaa; }
        .controls input, .controls select {
            padding: 8px 12px; border-radius: 6px;
            border: 1px solid #2a2a4a; background: #0f0f23; color: #e0e0e0;
            font-size: 0.9em;
        }
        .controls button {
            padding: 8px 20px; border-radius: 6px; border: none;
            background: #4a90d9; color: white; cursor: pointer;
            font-size: 0.9em; font-weight: 500;
        }
        .controls button:hover { background: #5a9fe9; }
        .controls button.secondary {
            background: transparent; border: 1px solid #4a90d9; color: #4a90d9;
        }
        .summary-card {
            background: #16213e; border-radius: 8px; padding: 20px;
            margin-bottom: 20px; border-left: 3px solid #4a90d9;
        }
        .summary-card .update-time { font-size: 0.8em; color: #888; }
        .corr-table {
            width: 100%; border-collapse: collapse; margin: 16px 0;
            font-size: 0.9em;
        }
        .corr-table th, .corr-table td {
            padding: 10px 12px; text-align: center;
            border-bottom: 1px solid #2a2a4a;
        }
        .corr-table th { background: #1a1a3e; color: #aaa; font-weight: 500; }
        .corr-table td { font-variant-numeric: tabular-nums; }
        .positive { color: #4ecdc4; }
        .negative { color: #ff6b6b; }
        .chart-container {
            background: #16213e; border-radius: 8px; padding: 16px;
            margin-bottom: 20px;
        }
        .section-title {
            font-size: 1.1em; font-weight: 600;
            margin-bottom: 12px; padding-bottom: 8px;
            border-bottom: 1px solid #2a2a4a;
        }
        .tabs { display: flex; gap: 4px; margin-bottom: 16px; }
        .tab {
            padding: 8px 16px; border-radius: 6px 6px 0 0;
            cursor: pointer; background: #1a1a3e; border: none;
            color: #888; font-size: 0.9em;
        }
        .tab.active { background: #4a90d9; color: white; }
        .loading { text-align: center; padding: 40px; color: #888; }
        .error { color: #ff6b6b; padding: 20px; text-align: center; }
        .btn-csv {
            display: inline-block; padding: 6px 14px; border-radius: 4px;
            background: #2a2a4a; color: #aaa; text-decoration: none;
            font-size: 0.85em; margin-top: 8px;
        }
        .btn-csv:hover { background: #3a3a5a; }
        @media (max-width: 768px) {
            .controls { flex-direction: column; align-items: stretch; }
            .corr-table { font-size: 0.75em; }
            .corr-table th, .corr-table td { padding: 6px 4px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 VXN/VIX 与美股指数相关性分析</h1>
        <div class="subtitle" id="updateTime">正在加载...</div>
    </div>
    <div class="container">
        <!-- 摘要卡片 -->
        <div class="summary-card">
            <div id="summaryText">正在加载分析结果...</div>
        </div>

        <!-- 相关性表格 -->
        <div class="chart-container">
            <div class="section-title">📈 多时间窗口 Pearson 相关系数</div>
            <div class="tabs">
                <button class="tab active" onclick="showTable('vxn_ixic')">VXN-纳斯达克</button>
                <button class="tab" onclick="showTable('vix_gspc')">VIX-标普500</button>
            </div>
            <div id="tableContainer"></div>
        </div>

        <!-- 图表控制 -->
        <div class="controls">
            <label>起始日期:</label>
            <input type="date" id="startDate">
            <label>结束日期:</label>
            <input type="date" id="endDate">
            <label>滚动窗口:</label>
            <select id="windowSize">
                <option value="10">10天</option>
                <option value="20">20天</option>
                <option value="30" selected>30天</option>
                <option value="60">60天</option>
                <option value="90">90天</option>
            </select>
            <button onclick="loadCharts()">🔄 更新图表</button>
            <button class="secondary" onclick="downloadCSV()">📥 下载 CSV</button>
        </div>

        <!-- 滚动相关图 -->
        <div class="chart-container">
            <div class="section-title">📉 滚动相关系数</div>
            <div id="rollingChart" class="loading">加载中...</div>
        </div>

        <!-- 价格走势图 -->
        <div class="chart-container">
            <div class="section-title">💹 近期价格走势</div>
            <div id="priceChart" class="loading">加载中...</div>
        </div>
    </div>

    <script>
        let corrData = null;
        let currentPair = 'vxn_ixic';

        async function loadData() {
            try {
                const resp = await fetch('/correlation');
                corrData = await resp.json();
                if (!corrData.success) {
                    document.getElementById('summaryText').innerHTML =
                        '<span class="error">❌ ' + corrData.error + '</span>';
                    return;
                }
                renderSummary();
                renderTable(currentPair);
                loadCharts();
            } catch (err) {
                document.getElementById('summaryText').innerHTML =
                    '<span class="error">❌ 加载失败: ' + err.message + '</span>';
            }
        }

        function renderSummary() {
            document.getElementById('updateTime').textContent =
                '数据更新: ' + (corrData.last_update || 'Unknown');
            document.getElementById('summaryText').innerHTML =
                '<p>' + (corrData.summary || '无数据') + '</p>';

            if (corrData.recent_table && corrData.recent_table.length > 0) {
                let html = '<table class="corr-table"><thead><tr>' +
                    '<th>日期</th><th>VXN</th><th>纳斯达克</th><th>VIX</th><th>标普500</th>' +
                    '</tr></thead><tbody>';
                corrData.recent_table.slice(0, 10).forEach(row => {
                    html += '<tr>' +
                        '<td>' + (row['日期'] || '') + '</td>' +
                        '<td>' + (row['VXN'] != null ? row['VXN'] : '-') + '</td>' +
                        '<td>' + (row['IXIC'] != null ? row['IXIC'].toLocaleString() : '-') + '</td>' +
                        '<td>' + (row['VIX'] != null ? row['VIX'] : '-') + '</td>' +
                        '<td>' + (row['GSPC'] != null ? row['GSPC'].toLocaleString() : '-') + '</td>' +
                        '</tr>';
                });
                html += '</tbody></table>';
                document.getElementById('summaryText').innerHTML += html;
            }
        }

        function renderTable(pair) {
            if (!corrData || !corrData.correlations) return;
            const data = corrData.correlations[pair];
            if (!data) return;

            const windows = ['1个月', '3个月', '6个月', '1年', '2年', '5年'];
            let html = '<table class="corr-table"><thead><tr>' +
                '<th>时间窗口</th><th>相关系数</th><th>P 值</th><th>样本数</th><th>强度</th>' +
                '</tr></thead><tbody>';

            windows.forEach(w => {
                const d = data[w] || {};
                const c = d.correlation;
                const cssClass = c > 0 ? 'positive' : (c < 0 ? 'negative' : '');
                let strength = '';
                if (c != null && !isNaN(c)) {
                    const abs = Math.abs(c);
                    if (abs >= 0.8) strength = '极强';
                    else if (abs >= 0.6) strength = '强';
                    else if (abs >= 0.4) strength = '中等';
                    else if (abs >= 0.2) strength = '弱';
                    else strength = '极弱';
                    strength += c > 0 ? '正相关' : '负相关';
                }
                html += '<tr>' +
                    '<td>' + w + '</td>' +
                    '<td class="' + cssClass + '">' + (c != null ? c.toFixed(4) : 'N/A') + '</td>' +
                    '<td>' + (d.p_value != null ? d.p_value.toFixed(4) : 'N/A') + '</td>' +
                    '<td>' + (d.n_samples || 'N/A') + '</td>' +
                    '<td>' + strength + '</td>' +
                    '</tr>';
            });
            html += '</tbody></table>';

            // 添加分位数
            if (corrData.rolling_correlation && corrData.rolling_correlation[pair]) {
                const pct = corrData.rolling_correlation[pair];
                html += '<p style="margin-top:12px;font-size:0.85em;color:#aaa;">' +
                    '滚动相关系数分位数: ' +
                    '当前 <strong>' + (pct.current != null ? pct.current.toFixed(4) : 'N/A') + '</strong> | ' +
                    '25%: ' + (pct.q25 != null ? pct.q25.toFixed(4) : 'N/A') + ' | ' +
                    '50%: ' + (pct.q50 != null ? pct.q50.toFixed(4) : 'N/A') + ' | ' +
                    '75%: ' + (pct.q75 != null ? pct.q75.toFixed(4) : 'N/A') +
                    '</p>';
            }

            document.getElementById('tableContainer').innerHTML = html;
        }

        function showTable(pair) {
            currentPair = pair;
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            renderTable(pair);
        }

        async function loadCharts() {
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            const windowSize = document.getElementById('windowSize').value;

            // 加载滚动相关图
            const params = new URLSearchParams();
            params.set('pair', currentPair);
            params.set('window', windowSize);
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);

            try {
                const resp = await fetch('/correlation/chart?' + params.toString());
                const html = await resp.text();
                document.getElementById('rollingChart').innerHTML = html;
            } catch (err) {
                document.getElementById('rollingChart').innerHTML =
                    '<span class="error">加载图表失败</span>';
            }
        }

        function downloadCSV() {
            const startDate = document.getElementById('startDate').value;
            const endDate = document.getElementById('endDate').value;
            const params = new URLSearchParams();
            params.set('pair', currentPair);
            if (startDate) params.set('start_date', startDate);
            if (endDate) params.set('end_date', endDate);
            window.open('/correlation/data.csv?' + params.toString(), '_blank');
        }

        // 初始化
        document.getElementById('startDate').value = '';
        document.getElementById('endDate').value = '';
        loadData();
    </script>
</body>
</html>"""
