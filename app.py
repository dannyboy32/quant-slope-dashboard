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
log_scale = st.sidebar.checkbox("Log scale on price", value=True)

# 解析均线周期
try:
    ma_periods = [int(x.strip()) for x in ma_input.split(",")]
except:
    st.sidebar.error("请输入正确的均线周期，用逗号分隔")
    ma_periods = [20, 50, 200]

# 映射时间范围
range_dict = {"1Y": "1y", "3Y": "3y", "5Y": "5y", "10Y": "10y"}

# 3. 数据下载与处理 
@st.cache_data(ttl=3600)  
def load_data(symbol, period):
    data = yf.download(symbol, period=period, auto_adjust=False)
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data[['Close']].dropna()

try:
    df = load_data(ticker, range_dict[date_range])
except Exception as e:
    st.error(f"获取数据失败，请检查代码或网络: {e}")
    st.stop()

if df.empty:
    st.warning("未找到该股票数据")
    st.stop()

# --- 新版 UI：动态标题与副标题 ---
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

color_map = {
    f"{ma_periods[0] if len(ma_periods)>0 else 20}DMA": "#1f77b4", 
    f"{ma_periods[1] if len(ma_periods)>1 else 50}DMA": "#ff7f0e", 
    f"{ma_periods[2] if len(ma_periods)>2 else 200}DMA": "#d62728"  
}

# 6. 图表绘制模块
st.subheader("Price & Moving Averages")
fig_price = gr.Figure()
fig_price.add_trace(gr.Scatter(x=df.index, y=df['Close'], name=f'{ticker} Close', line=dict(color='black', width=1.5)))
for ma in ma_periods:
    ma_name = f'{ma}DMA'
    line_color = color_map.get(ma_name, "gray") 
    fig_price.add_trace(gr.Scatter(x=df.index, y=df[ma_name], name=ma_name, line=dict(color=line_color, width=1.2)))
    
fig_price.update_layout(
    # 【修复2】：强制Y轴只显示 100, 200, 300... 整百刻度
    yaxis=dict(
        type="log" if log_scale else "linear",
        tickmode="array",
        tickvals=list(range(100, 2000, 100))
    ),
    # 【修复1】：强制X轴每6个月显示一次，格式为 "Jul 2021"
    xaxis=dict(
        dtick="M6",
        tickformat="%b %Y"
    ),
    height=400, 
    margin=dict(l=20, r=20, t=10, b=20),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None)
)
st.plotly_chart(fig_price, use_container_width=True)


st.subheader(f"SMA Slopes (% per day, {slope_lookback}-day lookback)")
fig_slope = gr.Figure()
for ma in ma_periods:
    ma_name = f'{ma}DMA'
    line_color = color_map.get(ma_name, "gray")
    fig_slope.add_trace(gr.Scatter(x=df.index, y=df[f'{ma}Slope'], name=f'{ma_name} Slope', line=dict(color=line_color, width=1.2)))
    
fig_slope.add_shape(type="line", x0=df.index[0], y0=0, x1=df.index[-1], y1=0, line=dict(color="gray", dash="dash"))

fig_slope.update_layout(
    yaxis=dict(title="Slope (% per day)", dtick=0.2), 
    # 【修复1】：附图X轴同步格式化
    xaxis=dict(
        dtick="M6",
        tickformat="%b %Y"
    ),
    height=300, 
    margin=dict(l=20, r=20, t=10, b=20),
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None)
)
st.plotly_chart(fig_slope, use_container_width=True)

st.markdown("---")

# 7. 统计表格渲染
with st.expander("Slope statistics for selected window"):
    stats_df = pd.DataFrame(stats_list).drop(columns=['MA_Value', 'Percentile'])
    stats_df = stats_df.set_index("MA")
    st.dataframe(stats_df.style.format({
        "Current": "{:+.3f}", "Mean": "{:.3f}", "Std": "{:.3f}", "Min": "{:.3f}", "Max": "{:.3f}"
    }), use_container_width=True)

with st.expander("Raw data (last 30 rows)"):
    display_cols = ['Close']
    for ma in ma_periods:
        display_cols.extend([f'{ma}DMA', f'{ma}Slope'])
    raw_df = df[display_cols].tail(30).sort_index(ascending=False)
    st.dataframe(raw_df, use_container_width=True)
