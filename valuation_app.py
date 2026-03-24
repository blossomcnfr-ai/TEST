import streamlit as st
import yfinance as yf

st.set_page_config(page_title="收租婆量化大师 V9.7", layout="wide", page_icon="🏦")

# ---------- 1. 缓存与数据抓取 ----------
@st.cache_data(ttl=600)
def get_info(ticker):
    return yf.Ticker(ticker).info

@st.cache_data(ttl=600)
def get_vix():
    try:
        return yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
    except:
        return 20.0

# ---------- 2. 核心估值算法 (DCF 终值保护) ----------
def compute_dcf(fcf, growth, discount, shares):
    if fcf <= 0 or shares <= 0:
        return 0

    # 前3年增长
    fcf_3y = fcf * (1 + growth) ** 3
    
    # 终值阶段：增长率强制锁定在 2%-3% (永续增长不能超过GDP)
    terminal_growth = min(growth, 0.03)
    spread = max(discount - terminal_growth, 0.02)

    terminal_value = fcf_3y / spread
    # 折现到现值
    total_present_val = (fcf_3y + terminal_value) / ((1 + discount) ** 3)
    
    return total_present_val / shares

def compute_div(div, growth, discount, price):
    spread = max(discount - growth, 0.02)
    val = div / spread if div > 0 else 0
    return min(val, price * 1.5) # 防止股息估值过分夸张

# ---------- 3. 股票分类逻辑 ----------
def classify_stock(div_yield, growth, buyback):
    total_yield = div_yield + buyback
    if total_yield > 0.05 and growth < 0.08:
        return "income"
    elif growth > 0.12:
        return "growth"
    else:
        return "blend"

# ---------- 4. 主程序 ----------
st.title("🏦 收租婆量化大师 V9.7")
st.caption("现金净额修正 | DCF安全锚 | 2026实战版")

ticker = st.text_input("输入股票代码", "HIMX").upper()

if ticker:
    try:
        info = get_info(ticker)

        # --- 基础数据 ---
        price = info.get("currentPrice") or 1.0
        eps = info.get("trailingEps") or 0.0
        fcf = info.get("freeCashflow") or 0.0
        shares = info.get("sharesOutstanding") or 1
        market_cap = info.get("marketCap") or 0
        div_yield = info.get("dividendYield") or 0.0
        div_rate = info.get("dividendRate") or 0.0
        pe = info.get("trailingPE") or (price / eps if eps > 0 else 0)
        avg_vol = info.get("averageVolume", 1000000)

        # --- 新增：净现金计算 (针对烟蒂股的关键) ---
        total_cash = info.get("totalCash", 0)
        total_debt = info.get("totalDebt", 0)
        net_cash_per_share = (total_cash - total_debt) / shares if shares > 0 else 0

        # --- 回购 ---
        buyback = min(fcf / market_cap, 0.05) if market_cap > 0 else 0

        # --- 顶部UI (保留V9.6所有信息) ---
        st.subheader(f"{ticker} - {info.get('longName', '')}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("股价", f"${price:.2f}")
        c2.metric("PE", f"{pe:.1f}")
        c3.metric("市值", f"{market_cap/1e9:.2f}B" if market_cap else "N/A")
        c4.metric("股息率", f"{div_yield*100:.2f}%")

        c5, c6, c7 = st.columns(3)
        c5.metric("回购收益率", f"{buyback*100:.2f}%")
        c6.metric("EPS", f"${eps:.2f}")
        c7.metric("每股净现金", f"${net_cash_per_share:.2f}", 
                  help="账面现金减去总债务后摊到每股的价值")

        # --- 增长率参数 ---
        st.divider()
        g1 = info.get("earningsGrowth") or 0
        g2 = info.get("revenueGrowth") or 0
        base_growth = max(g1, g2 * 0.7, 0.04)

        col_p1, col_p2 = st.columns(2)
        with col_p1:
            growth_input = st.slider("核心增长率 (%)", 0.0, 30.0, float(base_growth*100))
            discount = st.slider("折现率 (%)", 5.0, 15.0, 9.0) / 100
        
        with col_p2:
            st.write("📈 **估值权重调整**")
            stock_type = classify_stock(div_yield, growth_input/100, buyback)
            st.info(f"系统识别类型：{stock_type.upper()}")
            
            # 权重智能预设
            if stock_type == "growth":
                w_pe, w_dcf, w_div = 0.3, 0.7, 0.0
            elif stock_type == "income":
                w_pe, w_dcf, w_div = 0.4, 0.2, 0.4
            else:
                w_pe, w_dcf, w_div = 0.5, 0.5, 0.0
            
            w_pe = st.slider("PE权重", 0.0, 1.0, w_pe)
            w_dcf = st.slider("DCF权重", 0.0, 1.0, w_dcf)

        # --- 模型计算 ---
        growth = (growth_input / 100) + buyback
        val_pe = eps * pe
        val_dcf = compute_dcf(fcf, growth, discount, shares)
        val_div = compute_div(div_rate, growth, discount, price)

        # 原始估值
        raw_val = (val_pe * w_pe) + (val_dcf * w_dcf) + (val_div * (1 - w_pe - w_dcf))
        
        # 终极内在价值 = (模型预测 * 0.65 + 市场价格 * 0.35) + 净现金修正
        # 这里的逻辑是：即便业务归零，公司账面的净现金也应该保底
        intrinsic = (raw_val * 0.65 + price * 0.35) + (net_cash_per_share * 0.5)

        margin = (intrinsic / price - 1) * 100

        # --- 输出结果 ---
        st.divider()
        r1, r2 = st.columns(2)
        r1.metric("终极内在价值", f"${intrinsic:.2f}", f"{margin:.2f}% 安全边际")
        r1.write(f"估值区间: ${intrinsic*0.85:.2f} - ${intrinsic*1.15:.2f}")

        # --- Sell Put 模块改进 ---
        with r2:
            st.subheader("🎯 Sell Put 指南")
            vix = get_vix()
            st.write(f"市场恐慌度 (VIX): **{vix:.2f}**")
            
            # 流动性警示
            if avg_vol < 500000:
                st.warning("⚠️ 此股成交稀疏，期权价差大，请使用限价单‘钓鱼’。")
            
            strike = intrinsic * 0.85
            if margin > 15:
                st.success(f"强烈低估！建议 Strike: ${strike:.2f}")
            elif margin > -5:
                st.info(f"估值合理。建议 Strike: ${strike:.2f}")
            else:
                st.warning(f"目前溢价，建议 Strike: ${intrinsic*0.75:.2f}")

        # --- 拆解面板 ---
        with st.expander("📊 深度财务拆解"):
            st.write(f"- PE估值项: ${val_pe:.2f}")
            st.write(f"- DCF估值项(含保护): ${val_dcf:.2f}")
            st.write(f"- 每股净现金(Net Cash): ${net_cash_per_share:.2f}")
            st.write(f"- 综合模型原始值: ${raw_val:.2f}")
            st.caption("注：终极价值计入了 50% 的净现金保底，这是烟蒂股的最后防线。")

    except Exception as e:
        st.error(f"数据抓取失败: {e}")