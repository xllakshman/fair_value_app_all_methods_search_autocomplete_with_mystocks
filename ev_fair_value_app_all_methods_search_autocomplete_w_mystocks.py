import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import altair as alt
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="Global Equities Fair Value Recommendation", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

ALPHA_API_KEY = st.secrets["ALPHA_VANTAGE_API_KEY"]

# =====================================================
# FORMAT HELPERS
# =====================================================
def format_currency(val, currency="USD"):
    symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}
    s = symbols.get(currency, currency)
    return f"{s}{val:,.2f}" if val is not None else "-"

def safe_format_currency(df, col, currency):
    if col in df.columns:
        df[col] = df[col].apply(lambda x: format_currency(x, currency))

# =====================================================
# FUNDAMENTALS – ALPHA VANTAGE (CACHED)
# =====================================================
@st.cache_data(ttl=86400)
def get_fundamentals(ticker):
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "OVERVIEW",
        "symbol": ticker,
        "apikey": ALPHA_API_KEY
    }
    r = requests.get(url, params=params, timeout=10).json()

    def f(x):
        return float(x) if x not in [None, "None", ""] else None

    return {
        "eps": f(r.get("EPS")),
        "bvps": f(r.get("BookValue")),
        "ebitda": f(r.get("EBITDA")),
        "shares": f(r.get("SharesOutstanding")),
        "currency": r.get("Currency", "USD"),
        "name": r.get("Name", ""),
        "industry": r.get("Industry", "")
    }

# =====================================================
# VALUATION LOGIC (UNCHANGED)
# =====================================================
def dcf_valuation(eps, growth_rate=0.08, discount_rate=0.10):
    if eps is None or eps <= 0:
        return None
    cf = eps * (1 + growth_rate)
    return round(cf / (discount_rate - growth_rate), 2)

def graham_valuation(eps, bvps):
    if not eps or not bvps or eps <= 0 or bvps <= 0:
        return None
    return round((22.5 * eps * bvps) ** 0.5, 2)

def pe_valuation(eps, pe_ratio=15):
    if eps is None or eps <= 0:
        return None
    return round(eps * pe_ratio, 2)

def ev_valuation(ticker):
    stock = yf.Ticker(ticker)
    hist = stock.history(period="3y")

    fi = stock.fast_info
    current_price = fi.get("last_price")

    fund = get_fundamentals(ticker)
    ebitda = fund["ebitda"]
    shares = fund["shares"]

    if not current_price or not ebitda or not shares:
        return None

    ev_multiple = 10  # same assumption as before
    projected_ebitda = ebitda * 1.10
    fair_price = (projected_ebitda * ev_multiple) / shares

    high_3y = hist["High"].max() if not hist.empty else None
    low_3y = hist["Low"].min() if not hist.empty else None

    underval_pct = ((fair_price - current_price) / current_price) * 100

    band = (
        "Deep Discount" if underval_pct > 30 else
        "High Value" if underval_pct > 20 else
        "Undervalued" if underval_pct > 10 else
        "Fair/Premium"
    )

    return {
        "Symbol": ticker,
        "Market Value (EV)": round(fair_price, 2),
        "Current Price": round(current_price, 2),
        "Undervalued (%)": round(underval_pct, 2),
        "Valuation Band": band,
        "Industry": fund["industry"],
        "3Y High": round(high_3y, 2) if high_3y else None,
        "3Y Low": round(low_3y, 2) if low_3y else None,
        "Entry Price": round(low_3y * 1.05, 2) if low_3y else None,
        "Exit Price": round(high_3y * 0.95, 2) if high_3y else None,
        "Signal": "Buy" if fair_price > current_price else "Hold/Sell"
    }

# =====================================================
# UI
# =====================================================
ticker = st.text_input("🔍 Enter Stock Ticker (e.g. AAPL, AMZN, MSFT)").upper().strip()

if ticker:
    result = ev_valuation(ticker)
    fund = get_fundamentals(ticker)

    if result is None:
        st.warning("⚠️ Fair Value unavailable due to missing fundamentals.")
        st.stop()

    eps = fund["eps"]
    bvps = fund["bvps"]

    dcf_val = dcf_valuation(eps)
    graham_val = graham_valuation(eps, bvps)
    pe_val = pe_valuation(eps)

    tab1, tab2, tab3 = st.tabs(
        ["📋 Fair Value", "📂 Valuation by method", "📈 Technical Indicators"]
    )

    with tab1:
        df = pd.DataFrame([result])
        for col in ["Market Value (EV)", "Current Price", "3Y High", "3Y Low", "Entry Price", "Exit Price"]:
            safe_format_currency(df, col, fund["currency"])
        st.dataframe(df)

    with tab2:
        st.dataframe(pd.DataFrame([{
            "EV Value": format_currency(result["Market Value (EV)"], fund["currency"]),
            "DCF Value": format_currency(dcf_val, fund["currency"]),
            "Graham Value": format_currency(graham_val, fund["currency"]),
            "PE Value": format_currency(pe_val, fund["currency"])
        }]))

    with tab3:
        hist = yf.Ticker(ticker).history(period="5y")
        hist.reset_index(inplace=True)

        hist["SMA_50"] = SMAIndicator(hist["Close"], 50).sma_indicator()
        hist["SMA_200"] = SMAIndicator(hist["Close"], 200).sma_indicator()
        hist["RSI"] = RSIIndicator(hist["Close"], 14).rsi()
        macd = MACD(hist["Close"])
        hist["MACD"] = macd.macd()
        hist["Signal"] = macd.macd_signal()

        base = alt.Chart(hist).encode(x="Date:T")

        st.altair_chart(
            base.mark_line().encode(y="Close") +
            base.mark_line(strokeDash=[4, 4]).encode(y="SMA_50") +
            base.mark_line(strokeDash=[2, 2]).encode(y="SMA_200"),
            use_container_width=True
        )

        st.altair_chart(
            base.mark_line().encode(y="MACD") +
            base.mark_line().encode(y="Signal"),
            use_container_width=True
        )

        st.altair_chart(
            alt.Chart(hist).mark_line().encode(x="Date:T", y="RSI"),
            use_container_width=True
        )
