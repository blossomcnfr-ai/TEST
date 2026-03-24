import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

# 页面配置
st.set_page_config(page_title="收租婆量化大师 V9.8.1", layout="wide", page_icon="🏦")

# ---------- 1. 基础数据抓取函数 (带容错) ----------
@st.cache_data(ttl=600)
def get_stock_data(ticker_symbol):
    try:
        t = yf.Ticker(ticker_symbol)
        return t.info
    except: return None

@st.cache_data(ttl=600)
def get_vix_price():
    try:
        vix = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
        return vix
    except: return 20.0

# ---------- 2. 估值核心算法 (严格保留 V9.7) ----------
def compute_dcf(fcf, growth, discount, shares):
    if fcf <= 0 or shares <= 0: return 0
    fcf_3y = fcf * (1 + growth) ** 3
    terminal_growth = min(growth, 0.03)
    spread = max(discount - terminal_growth, 0.02)
    terminal_value = fcf_3y / spread
    return (fcf_3y + terminal_value) / ((1 + discount) ** 3) / shares

def compute_div(div, growth, discount, price):
    if div <= 0: return 0
    spread = max(discount - growth, 0.02)
    return min(div / spread, price * 1.5)

# ---------- 3. 主界面布局 ----------
st.title("🏦 收租婆量化大师 V9.8.1")
ticker = st.text_input("输入股票代码", "KO").upper()

if ticker:
    with st.spinner('正在从纳斯达克搬运数据...'):
        info = get_stock_data(ticker)
    
    if info and "currentPrice" in info:
        # 1. 提取基础数据
        price = info.get("currentPrice", 1.0)
        eps = info.get("trailingEps", 0.0)
        fcf = info.get("freeCashflow", 0.0)
        shares = info.get("sharesOutstanding", 1)
        div_rate = info.get("dividendRate", 0.0)
        pe_ttm = info.get("trailingPE", 20.0)
        
        # 2. 顶部面板
        st.subheader(f"{ticker} - {info.get('longName', '')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("股价", f"${price:.2f}")
        c2.metric("PE (TTM)", f"{pe_ttm:.1f}")
        c3.metric("市值", f"{info.get('marketCap', 0)/1e9:.2f}B")
        c4.metric("股息率", f"{info.get('dividendYield', 0)*100:.2f}%")
        st.divider()

        # 3. 权重与增长控制
        col_a, col_b = st.columns(2)
        with col_a:
            st.write("📈 **增长与折现**")
            g_raw = max(info.get("earningsGrowth", 0.05), info.get("revenueGrowth", 0.05))
            growth_ui = st.slider("核心增长率 (%)", 0.0, 30.0, float(g_raw*100))
            discount_ui = st.slider("折现率 (%)", 5.0, 15.0, 7.5) / 100
        with col_b:
            st.write("⚖️ **权重调校**")
            w_pe = st.slider("PE 权重", 0.0, 1.0, 0.8)
            w_dcf = st.slider("DCF 权重", 0.0, 1.0, 0.2)
            w_div = max(0.0, 1.0 - w_pe - w_dcf)

        # 4. 计算逻辑
        growth_final = growth_ui / 100
        v_pe = eps * pe_ttm
        v_dcf = compute_dcf(fcf, growth_final, discount_ui, shares)
        v_div = compute_div(div_rate, growth_final, discount_ui, price)
        
        # 综合估值与区间 (回归 V9.7)
        net_cash = (info.get("totalCash", 0) - info.get("totalDebt", 0)) / shares
        base_val = (v_pe * w_pe) + (v_dcf * w_dcf) + (v_div * w_div)
        intrinsic = (base_val * 0.7 + price * 0.3) + (net_cash * 0.5)
        
        low_b, high_b = intrinsic * 0.85, intrinsic * 1.15

        # 5. 结果展示
        res_l, res_r = st.columns(2)
        with res_l:
            st.markdown(f"### 终极内在价值: **${intrinsic:.2f}**")
            margin = (intrinsic/price - 1)*100
            st.write(f"安全边际: {'🟩' if margin>0 else '🟥'} {margin:.2f}%")
            st.write(f"估值区间: `${low_b:.2f} — ${high_b:.2f}`")
        
        with res_r:
            vix = get_vix_price()
            st.write(f"VIX 恐慌指数: {vix:.2f}")
            if margin > 10: st.success("🎯 建议考虑 Sell Put 进场")
            else: st.warning("☁️ 溢价中，建议 Strike 设在区间下限")

        # ---------- 4. 新增：SPY 期权模块 (点击后才加载，防止卡死) ----------
        st.divider()
        with st.expander("🚀 点击查看 SPY 实战期权链 (需联网)"):
            try:
                spy_obj = yf.Ticker("SPY")
                target_date = spy_obj.options[1]
                puts = spy_obj.option_chain(target_date).puts
                # 过滤并计算
                puts = puts[(puts['strike'] >= price * 0.85) & (puts['strike'] <= price * 1.01)]
                days = (datetime.strptime(target_date, '%Y-%m-%d') - datetime.now()).days or 1
                puts['年化收益%'] = (puts['bid'] / puts['strike']) * (365 / days) * 100
                
                show_df = puts[['strike', 'bid', 'ask', '年化收益%']].copy()
                show_df['1手接货现金'] = show_df['strike'] * 100
                st.write(f"📅 到期日: {target_date} ({days}天后)")
                st.table(show_df.sort_values('strike', ascending=False).head(10))
            except:
                st.write("目前无法获取期权数据，请稍后再试。")

    else:
        st.error("数据抓取失败，请检查 Ticker 是否正确。")
