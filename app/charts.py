"""Plotly 图表生成模块"""
import io
import base64
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots


# 配色
COLORS = {
    "vxn": "#FF6B6B",
    "ixic": "#4ECDC4",
    "vix": "#FF6B6B",
    "gspc": "#45B7D1",
    "vxn_ixic_corr": "#FF6B6B",
    "vix_gspc_corr": "#45B7D1",
    "bg": "#1a1a2e",
    "paper_bg": "#16213e",
    "text": "#e0e0e0",
    "grid": "#2a2a4a",
}

DARK_TEMPLATE = {
    "layout": {
        "paper_bgcolor": COLORS["paper_bg"],
        "plot_bgcolor": COLORS["bg"],
        "font": {"color": COLORS["text"]},
        "xaxis": {"gridcolor": COLORS["grid"], "zerolinecolor": COLORS["grid"]},
        "yaxis": {"gridcolor": COLORS["grid"], "zerolinecolor": COLORS["grid"]},
    }
}

pio.templates["dark_custom"] = go.layout.Template(**DARK_TEMPLATE)
pio.templates.default = "dark_custom"


def rolling_correlation_chart(
    df_vxn: pd.DataFrame,
    df_vix: pd.DataFrame,
    percentiles_vxn: dict,
    percentiles_vix: dict,
    as_base64: bool = True,
    height: int = 500,
) -> str:
    """
    生成滚动相关系数双图。
    返回 base64 PNG 字符串，或 Plotly HTML div。
    """
    if df_vxn.empty and df_vix.empty:
        return ""

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("VXN-纳斯达克 30日滚动相关系数", "VIX-标普500 30日滚动相关系数"),
    )

    # ── 上图：VXN-IXIC ──
    if not df_vxn.empty:
        fig.add_trace(
            go.Scatter(
                x=df_vxn["date"],
                y=df_vxn["correlation"],
                mode="lines",
                name="VXN-IXIC 滚动相关",
                line=dict(color=COLORS["vxn_ixic_corr"], width=1.5),
            ),
            row=1, col=1,
        )

        # 添加分位线
        for key, label, color in [
            ("q25", "25%分位", "#FFD93D"),
            ("q50", "50%分位", "#C0C0C0"),
            ("q75", "75%分位", "#FFD93D"),
        ]:
            if key in percentiles_vxn and percentiles_vxn[key] is not None:
                fig.add_hline(
                    y=percentiles_vxn[key],
                    line_dash="dash",
                    line_color=color,
                    opacity=0.5,
                    row=1, col=1,
                    annotation_text=label,
                    annotation_position="right",
                )

        # 零线
        fig.add_hline(y=0, line_dash="dot", line_color="#666", opacity=0.3, row=1, col=1)

        # 标注当前值
        if percentiles_vxn.get("current") is not None:
            fig.add_annotation(
                x=df_vxn["date"].iloc[-1],
                y=percentiles_vxn["current"],
                text=f"当前: {percentiles_vxn['current']:.3f}",
                showarrow=True,
                arrowhead=2,
                ax=40,
                ay=-30,
                font=dict(color=COLORS["vxn_ixic_corr"], size=11),
                row=1, col=1,
            )

    # ── 下图：VIX-GSPC ──
    if not df_vix.empty:
        fig.add_trace(
            go.Scatter(
                x=df_vix["date"],
                y=df_vix["correlation"],
                mode="lines",
                name="VIX-GSPC 滚动相关",
                line=dict(color=COLORS["vix_gspc_corr"], width=1.5),
            ),
            row=2, col=1,
        )

        for key, label, color in [
            ("q25", "25%分位", "#FFD93D"),
            ("q50", "50%分位", "#C0C0C0"),
            ("q75", "75%分位", "#FFD93D"),
        ]:
            if key in percentiles_vix and percentiles_vix[key] is not None:
                fig.add_hline(
                    y=percentiles_vix[key],
                    line_dash="dash",
                    line_color=color,
                    opacity=0.5,
                    row=2, col=1,
                )

        fig.add_hline(y=0, line_dash="dot", line_color="#666", opacity=0.3, row=2, col=1)

        if percentiles_vix.get("current") is not None:
            fig.add_annotation(
                x=df_vix["date"].iloc[-1],
                y=percentiles_vix["current"],
                text=f"当前: {percentiles_vix['current']:.3f}",
                showarrow=True,
                arrowhead=2,
                ax=40,
                ay=-30,
                font=dict(color=COLORS["vix_gspc_corr"], size=11),
                row=2, col=1,
            )

    fig.update_layout(
        height=height,
        hovermode="x unified",
        showlegend=False,
        margin=dict(l=40, r=40, t=50, b=30),
    )

    fig.update_xaxes(rangeslider_visible=False)
    fig.update_yaxes(title_text="相关系数", row=1, col=1)
    fig.update_yaxes(title_text="相关系数", row=2, col=1)

    if as_base64:
        try:
            img_bytes = fig.to_image(format="png", scale=2)
            return base64.b64encode(img_bytes).decode("utf-8")
        except (ValueError, ImportError) as e:
            # Kaleido 不可用时，返回 HTML
            import logging
            logging.getLogger(__name__).warning(f"PNG 导出失败 (kaleido 不可用): {e}，返回 HTML")
            return fig.to_html(full_html=False, include_plotlyjs="cdn")

    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def correlation_heatmap_chart(corr_data: dict) -> str:
    """生成相关性热力图（可选）"""
    # 简化版：返回 HTML div
    windows = list(corr_data.get("vxn_ixic", {}).keys())
    vxn_vals = [corr_data["vxn_ixic"].get(w, {}).get("correlation", None) for w in windows]
    vix_vals = [corr_data["vix_gspc"].get(w, {}).get("correlation", None) for w in windows]

    fig = go.Figure()

    if vxn_vals:
        fig.add_trace(go.Bar(
            y=windows,
            x=vxn_vals,
            name="VXN-纳斯达克",
            orientation="h",
            marker_color=COLORS["vxn_ixic_corr"],
            text=[f"{v:.3f}" if v is not None else "N/A" for v in vxn_vals],
            textposition="outside",
            textfont=dict(color=COLORS["text"]),
        ))

    if vix_vals:
        fig.add_trace(go.Bar(
            y=windows,
            x=vix_vals,
            name="VIX-标普500",
            orientation="h",
            marker_color=COLORS["vix_gspc_corr"],
            text=[f"{v:.3f}" if v is not None else "N/A" for v in vix_vals],
            textposition="outside",
            textfont=dict(color=COLORS["text"]),
        ))

    fig.update_layout(
        barmode="group",
        height=350,
        title="多时间窗口相关系数对比",
        xaxis_title="相关系数",
        xaxis=dict(range=[-1.1, 1.1]),
        margin=dict(l=40, r=80, t=50, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def price_chart(data: dict, days: int = 90) -> str:
    """生成价格走势图"""
    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=("VXN 波动率指数", "纳斯达克综合指数", "VIX 波动率指数", "标普500"),
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )

    pairs = [
        ("VXN", 1, 1, COLORS["vxn"]),
        ("IXIC", 1, 2, COLORS["ixic"]),
        ("VIX", 2, 1, COLORS["vix"]),
        ("GSPC", 2, 2, COLORS["gspc"]),
    ]

    for name, row, col, color in pairs:
        df = data.get(name, {}).get("history", pd.DataFrame())
        if not df.empty:
            df_tail = df.tail(days)
            fig.add_trace(
                go.Scatter(
                    x=df_tail.index,
                    y=df_tail["Close"],
                    mode="lines",
                    name=name,
                    line=dict(color=color, width=1.5),
                ),
                row=row, col=col,
            )

    fig.update_layout(
        height=600,
        showlegend=False,
        margin=dict(l=40, r=40, t=50, b=30),
    )

    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def interactive_rolling_chart(
    df_vxn: pd.DataFrame, df_vix: pd.DataFrame,
    start_date: str = "", end_date: str = "",
) -> str:
    """生成交互式滚动相关图（用于 Web 仪表板）"""
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=(
            "VXN-纳斯达克 滚动相关系数",
            "VIX-标普500 滚动相关系数"
        ),
    )

    if not df_vxn.empty:
        fig.add_trace(
            go.Scatter(
                x=df_vxn["date"], y=df_vxn["correlation"],
                mode="lines", name="VXN-IXIC",
                line=dict(color=COLORS["vxn_ixic_corr"], width=1.5),
                hovertemplate="日期: %{x}<br>相关系数: %{y:.4f}<extra></extra>",
            ),
            row=1, col=1,
        )
        fig.add_hline(y=0, line_dash="dot", line_color="#666", row=1, col=1)

    if not df_vix.empty:
        fig.add_trace(
            go.Scatter(
                x=df_vix["date"], y=df_vix["correlation"],
                mode="lines", name="VIX-GSPC",
                line=dict(color=COLORS["vix_gspc_corr"], width=1.5),
                hovertemplate="日期: %{x}<br>相关系数: %{y:.4f}<extra></extra>",
            ),
            row=2, col=1,
        )
        fig.add_hline(y=0, line_dash="dot", line_color="#666", row=2, col=1)

    title_parts = ["滚动相关系数"]
    if start_date or end_date:
        title_parts.append(f"({start_date} ~ {end_date})")

    fig.update_layout(
        height=600,
        hovermode="x unified",
        title=" ".join(title_parts),
        margin=dict(l=40, r=40, t=60, b=30),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    fig.update_xaxes(rangeslider_visible=True, row=2, col=1)

    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            "scrollZoom": True,
            "toImageButtonOptions": {
                "format": "png",
                "filename": "rolling_correlation",
                "height": 800,
                "width": 1200,
            },
        },
    )
