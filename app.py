import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as gr
from scipy.stats import linregress

# 1. 页面配置
st.set_page_config(page_title="MA Slope Dashboard", layout="wide")
st.title("📊 Moving Averages & Slope Dashboard")

# 2. 左侧配置栏 (Sidebar)
st.sidebar.header("Configuration")
ticker = st.sidebar.text_input("Ticker", value="QQQ").upper()
date_range = st.sidebar.selectbox("Date range", ["1Y", "3Y", "5Y", "10Y"], index=1)
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
@st.cache_data(ttl=3600)  # 缓存数据 1 小时，避免重复请求
def load_data(symbol, period):
    data = yf.download(symbol, period=period)
    # yfinance返回的多级索引处理
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

# 4. 量化核心计算：均线与滚动斜率
def calculate_slope(series, window):
    """使用最小二乘法计算滚动窗口的线性回归斜率，并转换为每日百分比"""
    slopes = [np.nan] * len(series)
    x = np.arange(window)
    
    # 转换为 numpy 数组加速计算
    y_vals = series.values
    
    for i in range(window - 1, len(series)):
        y = y_vals[i - window + 1 : i + 1]
        if np.isnan(y).any():
            continue
        slope, _, _, _, _ = linregress(x, y)
        # 斜率归一化：(绝对斜率 / 当前价格) * 100 变成百分比
        slopes[i] = (slope / y_vals[i]) * 100
    return pd.Series(slopes, index=series.index)

# 计算各项指标
stats_list = []
latest_close = df['Close'].iloc[-1]
latest_date = df.index[-1].strftime('%Y-%m-%d')

# 动态计算用户输入的每一条均线
for ma in ma_periods:
    df[f'{ma}DMA'] = df['Close'].rolling(window=ma).mean()
    df[f'{ma}Slope'] = calculate_slope(df[f'{ma}DMA'], slope_lookback)
    
    # 计算统计特征
    slope_series = df[f'{ma}Slope'].dropna()
    current_slope = df[f'{ma}Slope'].iloc[-1]
    
    # 计算历史百分位
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

# 5. 顶层看板渲染 (KPI Metrics)
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

# 渲染斜率 KPI
slope_cols = st.columns(len(ma_periods) + 1)
slope_cols[0].write("**Slope (%/day):**")
for idx, stat in enumerate(stats_list):
    with slope_cols[idx + 1]:
        st.metric(label=f"{stat['MA']} Slope", value=f"{stat['Current']:+.3f}")
        st.caption(f"↑ {stat['Percentile']:.0f}th pctile")

st.markdown("---")

# 6. 图表绘制模块
# 主图：价格与均线
fig_price = gr.Figure()
fig_price.add_trace(gr.Scatter(x=df.index, y=df['Close'], name=f'{ticker} Close', line=dict(color='black', width=1.5)))
for ma in ma_periods:
    fig_price.add_trace(gr.Scatter(x=df.index, y=df[f'{ma}DMA'], name=f'{ma}DMA', line=dict(width=1.2)))
fig_price.update_layout(
    title="Price & Moving Averages",
    yaxis_type="log" if log_scale else "linear",
    height=400, margin=dict(l=20, r=20, t=40, b=20),
    hovermode="x unified"
)
st.plotly_chart(fig_price, use_container_width=True)

# 附图：斜率历史曲线
fig_slope = gr.Figure()
for ma in ma_periods:
    fig_slope.add_trace(gr.Scatter(x=df.index, y=df[f'{ma}Slope'], name=f'{ma}DMA Slope', line=dict(width=1.2)))
fig_slope.add_shape(type="line", x0=df.index[0], y0=0, x1=df.index[-1], y1=0, line=dict(color="gray", dash="dash"))
fig_slope.update_layout(
    title=f"SMA Slopes (% per day, {slope_lookback}-day lookback)",
    height=300, margin=dict(l=20, r=20, t=40, b=20),
    hovermode="x unified"
)
st.plotly_chart(fig_slope, use_container_width=True)

# 7. 统计表格渲染
st.markdown("### 📈 Slope statistics for selected window")
stats_df = pd.DataFrame(stats_list).drop(columns=['MA_Value', 'Percentile'])
stats_df = stats_df.set_index("MA")
# 格式化输出
st.dataframe(stats_df.style.format({
    "Current": "{:+.3f}", "Mean": "{:.3f}", "Std": "{:.3f}", "Min": "{:.3f}", "Max": "{:.3f}"
}), use_container_width=True)
