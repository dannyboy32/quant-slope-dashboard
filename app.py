import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as gr

# 1. 页面配置
st.set_page_config(page_title="MA Slope Dashboard", layout="wide")

# 2. 左侧配置栏 (Sidebar)
st.sidebar.header("Configuration")
ticker = st.sidebar.text_input("Ticker", value="QQQ").upper()
date_range = st.sidebar.selectbox("Date range", ["1Y", "3Y", "5Y", "10Y"], index=2)
ma_input = st.sidebar.text_input("MA periods (comma-separated)", value="20, 50, 200")
slope_lookback = st.sidebar.slider("Slope lookback (trading days)", min_value=2, max_value=20, value=5)

st.sidebar.markdown("---")
# 成交量开关，默认关闭
show_volume = st.sidebar.checkbox("Show volume on price chart", value=False)
# 【终极修复】：对数坐标开关，按照要求默认改为 False (未勾选)
log_scale = st.sidebar.checkbox("Log scale on price (useful for 10-20Y)", value=False)

# 解析均线周期
try:
    ma_periods = [int(x.strip()) for x in ma_input.split(",")]
except:
    st.sidebar.error("请输入正确的均线周期，用逗号分隔")
    ma_periods = [20, 50, 200]

# 映射时间范围
range_dict = {"1Y": "1y", "3Y": "3y", "5Y": "5y", "10Y": "10y"}

# 3. 数据下载与处理 (使用 auto_adjust=False 获取未复权原始收盘价)
@st.cache_data(ttl=3600)  
def load_data(symbol, period):
    data = yf.download(symbol, period=period, auto_adjust=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    # 获取 Close 和 Volume
    return data[['Close', 'Volume']].dropna()

try:
    df = load_data(ticker, range_dict[date_range])
except Exception as e:
    st.error(f"获取数据失败，请检查代码或网络: {e}")
    st.stop()

if df.empty:
    st.warning("未找到该股票数据")
    st.stop()

# --- UI：动态标题与副标题 ---
st.title(f"📊 {ticker} — Moving Averages & Slope Dashboard")
start_date_str = df.index[0].strftime('%Y-%m-%d')
end_date_str = df.index[-1].strftime('%Y-%m-%d')
st.caption(f"Range: {start_date_str} → {end_date_str} ({len(df)} trading days)")

# 4. 量化核心计算
stats_list = []
latest_close = df['Close'].iloc[-1]
latest_date = df.index[-1].strftime('%Y-%m-%d')

for ma in ma_periods:
    df[f'{ma}DMA'] = df['Close'].rolling(window=ma).mean()
    # 极简百分比变动斜率计算法
    df[f'{ma}Slope'] = (df[f'{ma}DMA'].pct_change(periods=slope_lookback) * 100) / slope_lookback
    
    slope_series = df[f'{ma}Slope'].dropna()
    current_slope = df[f'{ma}Slope'].iloc[-1]
    
    if not slope_series.empty:
        pctile = (slope_series < current_slope).mean() * 100
        mean_val = slope_series.mean()
        std_val = slope_series.std()
        min_val = slope_series.min()
        max_val = slope_series.max()
        min_date = slope_series.idxmin().strftime('%Y-%m-%d')
        neg_days_pct = (slope_series < 0).mean() * 100
    else:
        pctile = mean_val = std_val = min_val = max_val = neg_days_pct = 0
        min_date = "N/A"
        
    stats_list.append({
        "MA": f"{ma}DMA",
        "Current": current_slope,
        "Percentile": pctile,
        "Mean": mean_val,
        "Std": std_val,
        "Min": min_val,
        "Min date": min_date,
        "Max": max_val,
        "% days negative": f"{neg_days_pct:.1f}%",
        "MA_Value": df[f'{ma}DMA'].iloc[-1]
    })

# 5. 顶层看板渲染
cols = st.columns(len(ma_periods) + 1)
with cols[0]:
    st.metric(label=f"Close ({ticker})", value=f"${latest_close:.2f}", delta=f"as of {latest_date}", delta_color="inverse")

for idx, stat in enumerate(stats_list):
    ma_val = stat['MA_Value']
    p_diff = ((latest_close - ma_val) / ma_val) * 100
    with cols[idx + 1]:
        st.metric(
            label=stat['MA'], 
            value=f"${ma_val:.2f}", 
            delta=f"{p_diff:+.2f}% vs close",
            delta_color="normal" if p_diff > 0 else "inverse"
        )

slope_cols = st.columns(len(ma_periods) + 1)
slope_cols[0].write("**Slope (%/day):**")
for idx, stat in enumerate(stats_list):
    with slope_cols[idx + 1]:
        st.metric(label=f"{stat['MA']} slope (%/day)", value=f"{stat['Current']:+.3f}")
        st.caption(f"↑ {stat['Percentile']:.0f}th pctile of window")

st.markdown("---")

# 配色映射字典
color_map = {
    f"{ma_periods[0] if len(ma_periods)>0 else 20}DMA": "#1f77b4", # 蓝色
    f"{ma_periods[1] if len(ma_periods)>1 else 50}DMA": "#ff7f0e", # 橙色
    f"{ma_periods[2] if len(ma_periods)>2 else 200}DMA": "#d62728"  # 红色
}

# 6. 图表绘制模块
st.subheader("Price & Moving Averages")
fig_price = gr.Figure()

# 如果勾选了显示成交量，添加浅色柱状图到辅Y轴 (y2)
if show_volume:
    fig_price.add_trace(gr.Bar(
        x=df.index, y=df['Volume'], name='Volume', 
        marker_color='rgba(169, 169, 169, 0.4)', yaxis='y2'
    ))

# 绘制 K 线和均线
fig_price.add_trace(gr.Scatter(x=df.index, y=df['Close'], name=f'{ticker} Close', line=dict(color='black', width=1.5)))
for ma in ma_periods:
    ma_name = f'{ma}DMA'
    line_color = color_map.get(ma_name, "gray") 
    fig_price.add_trace(gr.Scatter(x=df.index, y=df[ma_name], name=ma_name, line=dict(color=line_color, width=1.2)))

# 主图排版配置
layout_update = dict(
    yaxis=dict(
        type="log" if log_scale else "linear",
        tickmode="array",
        tickvals=list(range(100, 2000, 100)) # 强制按100刻度显示
    ),
    xaxis=dict(
        dtick="M6",               # 每6个月标记一次
        tickformat="%b %Y",       # 底部X轴显示月份和年份
        hoverformat="%Y-%m-%d"    # 悬停提示框精确到天
    ),
    height=600, # 主图高度 600px 保证舒展
    margin=dict(l=20, r=20, t=10, b=20),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None)
)

# 动态调整Y轴区域，给底部成交量腾出 15% 的空间
if show_volume:
    layout_update['yaxis']['domain'] = [0.2, 1] 
    layout_update['yaxis2'] = dict(domain=[0, 0.15], showticklabels=False, showgrid=False) 
else:
    layout_update['yaxis']['domain'] = [0, 1]

fig_price.update_layout(**layout_update)
st.plotly_chart(fig_price, use_container_width=True)


st.subheader(f"SMA Slopes (% per day, {slope_lookback}-day lookback)")
fig_slope = gr.Figure()

for ma in ma_periods:
    ma_name = f'{ma}DMA'
    line_color = color_map.get(ma_name, "gray")
    fig_slope.add_trace(gr.Scatter(x=df.index, y=df[f'{ma}Slope'], name=f'{ma_name} Slope', line=dict(color=line_color, width=1.2)))
    
# 绘制 0 轴虚线
fig_slope.add_shape(type="line", x0=df.index[0], y0=0, x1=df.index[-1], y1=0, line=dict(color="gray", dash="dash"))

# 附图排版配置
fig_slope.update_layout(
    yaxis=dict(title="Slope (% per day)", dtick=0.2), # 强制 0.2 刻度
    xaxis=dict(
        dtick="M6",
        tickformat="%b %Y",
        hoverformat="%Y-%m-%d"
    ),
    height=500, # 附图高度 500px 
    margin=dict(l=20, r=20, t=10, b=20),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None)
)
st.plotly_chart(fig_slope, use_container_width=True)

st.markdown("---")

# 7. 统计表格渲染 (收进折叠面板)
with st.expander("Slope statistics for selected window"):
    stats_df = pd.DataFrame(stats_list).drop(columns=['MA_Value', 'Percentile'])
    stats_df = stats_df.set_index("MA")
    st.dataframe(stats_df.style.format({
        "Current": "{:+.3f}", "Mean": "{:.3f}", "Std": "{:.3f}", "Min": "{:.3f}", "Max": "{:.3f}"
    }), use_container_width=True)

with st.expander("Raw data (last 30 rows)"):
    display_cols = ['Close', 'Volume']
    for ma in ma_periods:
        display_cols.extend([f'{ma}DMA', f'{ma}Slope'])
    # 显示最近 30 天的原始数据
    raw_df = df[display_cols].tail(30).sort_index(ascending=False)
    st.dataframe(raw_df, use_container_width=True)
