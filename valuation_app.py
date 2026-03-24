import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="收租婆量化大师 V9.8", layout="wide", page_icon="🏦")

# ---------- 1. 基础数据抓取 ----------
@st.cache_data(ttl=600)
def get_info(ticker):
    return yf.Ticker(ticker).info

@st.cache_data(ttl=600)
def get_vix():
    try:
        return yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
    except: return 20.0

# ---------- 2. 核心算法 (保留V9.7) ----------
def compute_dcf(fcf, growth, discount, shares):
    if fcf <= 0 or shares <= 0: return 0
    fcf_3y = fcf * (1 + growth) ** 3
    terminal_growth = min(growth, 0.03)
    spread = max(discount - terminal_growth, 0.02)
    terminal_value = fcf_3y / spread
    return (fcf_3y + terminal_value) / ((1 + discount) ** 3) / shares

def compute_div(div, growth, discount, price):
    spread = max(discount - growth, 0.02)
    return min(div / spread if div > 0 else 0, price * 1.5)

def classify_stock(div_yield, growth, buyback):
    total_yield = div_yield + buyback
    if total_yield > 0.05 and growth < 0.08: return "income"
    elif growth > 0.12: return "growth"
    else: return "blend"

# ---------- 3. 主界面 (保留所有已有功能) ----------
st.title("🏦 收租婆量化大师 V9.8")
ticker = st.text_input("输入股票代码", "SPY").upper()

if ticker:
    try:
        info = get_info(ticker)
        price = info.get("currentPrice") or 1.0
        eps = info.get("trailingEps") or 0.0
        fcf = info.get("freeCashflow") or 0.0
        shares = info.get("sharesOutstanding") or 1
        market_cap = info.get("marketCap") or 0
        div_yield = info.get("dividendYield") or 0.0
        div_rate = info.get("dividendRate") or 0.0
        pe = info.get("trailingPE") or (price / eps if eps > 0 else 0)
        net_cash_per_share = (info.get("totalCash", 0) - info.get("totalDebt", 0)) / shares

        # 顶部展示
        st.subheader(f"{ticker} - {info.get('longName', '')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("股价", f"${price:.2f}")
        c2.metric("PE", f"{pe:.1f}")
        c3.metric("市值", f"{market_cap/1e9:.1f}B")
        c4.metric("股息率", f"{div_yield*100:.2f}%")

        # 核心参数
        st.divider()
        g1, g2 = info.get("earningsGrowth") or 0, info.get("revenueGrowth") or 0
        base_growth = max(g1, g2 * 0.7, 0.04)
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            growth_input = st.slider("核心增长率 (%)", 0.0, 30.0, float(base_growth*100))
            discount = st.slider("折现率 (%)", 5.0, 15.0, 8.5) / 100
        with col_p2:
            stock_type = classify_stock(div_yield, growth_input/100, 0.02)
            st.info(f"系统识别类型：{stock_type.upper()}")
            w_pe = st.slider("PE权重", 0.0, 1.0, 0.5)
            w_dcf = st.slider("DCF权重", 0.0, 1.0, 0.4)

        # 估值计算
        growth = (growth_input / 100) + 0.02
        val_pe, val_dcf = eps * pe, compute_dcf(fcf, growth, discount, shares)
        val_div = compute_div(div_rate, growth, discount, price)
        raw_val = (val_pe * w_pe) + (val_dcf * w_dcf) + (val_div * (1 - w_pe - w_dcf))
        intrinsic = (raw_val * 0.65 + price * 0.35) + (net_cash_per_share * 0.5)
        margin = (intrinsic / price - 1) * 100

        # 结果输出
        r1, r2 = st.columns(2)
        r1.metric("终极内在价值", f"${intrinsic:.2f}", f"{margin:.2f}%")
        with r2:
            st.write(f"VIX 指数: {get_vix():.2f}")
            if margin > 10: st.success("🎯 建议 Sell Put 进场")
            else: st.warning("☁️ 建议观望或深度价外 Sell Put")

        # ---------- 4. 新增：SPY 期权链年化收益模块 ----------
        st.divider()
        st.subheader("📊 SPY 实战期权链 (Sell Put 收益率排名)")
        
        @st.cache_data(ttl=3600)
        def get_spy_options():
            spy = yf.Ticker("SPY")
            expirations = spy.options
            # 选最近一个周五到期的（通常选距离现在 7-45 天的比较稳）
            target_date = expirations[1] # 取第二个到期日，通常更有参考意义
            opt = spy.option_chain(target_date)
            return opt.puts, target_date

        try:
            puts, exp_date = get_spy_options()
            # 计算距离到期天数
            d1 = datetime.strptime(exp_date, '%Y-%m-%d')
            d2 = datetime.now()
            days_to_expiry = (d1 - d2).days
            if days_to_expiry <= 0: days_to_expiry = 1

            # 过滤行权价：只看股价附近的 Put (90% - 100% 价格区间)
            puts = puts[(puts['strike'] >= price * 0.85) & (puts['strike'] <= price * 1.01)]
            
            # 计算年化收益率逻辑
            # 公式: (权利金 / 行权价) * (365 / 天数)
            puts['Bid_Price'] = puts['bid']
            puts['Annual_Yield %'] = (puts['bid'] / puts['strike']) * (365 / days_to_expiry) * 100
            puts['接货需准备现金'] = puts['strike'] * 100
            
            # 美化显示
            display_df = puts[['strike', 'lastPrice', 'bid', 'ask', 'Annual_Yield %', '接货需准备现金']].copy()
            display_df.columns = ['行权价(Strike)', '最新成交价', '买一价(Bid)', '卖一价(Ask)', '年化收益率%', '1手接货金额($)']
            
            st.write(f"📅 目标到期日: **{exp_date}** (距离 {days_to_expiry} 天)")
            st.dataframe(display_df.sort_values('年化收益率%', ascending=False), use_container_width=True)
            
            st.caption("💡 提示：年化收益率越高，风险越大（行权价离现价越近）。建议选‘年化 10%-15%’且行权价低于你算出的‘内在价值’的档位。")

        except Exception as opt_e:
            st.error(f"期权链抓取失败 (可能是周末或API限制): {opt_e}")

        # 保留拆解面板
        with st.expander("📊 深度财务拆解"):
            st.write(f"每股净现金: ${net_cash_per_share:.2f}")
            st.write(f"DCF估值: ${val_dcf:.2f}")

    except Exception as e:
        st.error(f"主程序错误: {e}")
