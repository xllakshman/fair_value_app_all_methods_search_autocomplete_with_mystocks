import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import io
import altair as alt
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator
from yfinance.exceptions import YFRateLimitError

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(page_title="Stock Fair Value Analyzer", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

GITHUB_CSV_URL = "https://raw.githubusercontent.com/xllakshman/f.../stock_list.csv"

# =====================================================
# SAFE YAHOO INFO FIX (UNCHANGED)
# =====================================================
@st.cache_data(ttl=3600)
def safe_stock_info(ticker: str):
    try:
        return yf.Ticker(ticker).info
    except YFRateLimitError:
        try:
            fi = yf.Ticker(ticker).fast_info
            return {
                "enterpriseValue": fi.get("market_cap"),
                "ebitda": None,
                "sharesOutstanding": None,
                "currentPrice": fi.get("last_price"),
                "marketCap": fi.get("market_cap"),
                "currency": fi.get("currency"),
            }
        except Exception:
            return {}
    except Exception:
        return {}

# =====================================================
# EXISTING LOGIC (UNCHANGED)
# =====================================================
def get_fair_value(ticker):
    try:
        info = safe_stock_info(ticker)
        ev = info.get("enterpriseValue")
        ebitda = info.get("ebitda")
        shares = info.get("sharesOutstanding")

        if not (ev and ebitda and shares):
            return None

        return round(ev / shares, 2)
    except Exception:
        return None

# =====================================================
# DATA LOADING (FIXED)
# =====================================================
@st.cache_data
def load_stock_list():
    response = requests.get(GITHUB_CSV_URL)
    return pd.read_csv(io.StringIO(response.text))

df_stocks = load_stock_list()

# ✅ FIX: Normalize + auto-detect ticker column
df_stocks.columns = df_stocks.columns.str.strip().str.lower()

possible_cols = ["ticker", "symbol", "stock", "code"]
ticker_col = next((c for c in possible_cols if c in df_stocks.columns), None)

if not ticker_col:
    st.error(f"No ticker column found. Available columns: {list(df_stocks.columns)}")
    st.stop()

tickers = df_stocks[ticker_col].dropna().unique().tolist()

# =====================================================
# UI (UNCHANGED)
# =====================================================
selected_ticker = st.selectbox("Select Stock", tickers)

if selected_ticker:
    stock = yf.Ticker(selected_ticker)
    hist = stock.history(period="5y")

    if not hist.empty:
        hist["SMA_50"] = SMAIndicator(hist["Close"], 50).sma_indicator()
        hist["RSI"] = RSIIndicator(hist["Close"]).rsi()

        macd = MACD(hist["Close"])
        hist["MACD"] = macd.macd()
        hist["MACD_SIGNAL"] = macd.macd_signal()

        chart = alt.Chart(hist.reset_index()).mark_line().encode(
            x="Date",
            y="Close"
        )
        st.altair_chart(chart, use_container_width=True)

    fair_value = get_fair_value(selected_ticker)
    st.subheader("💰 Fair Value Analysis")
    st.write(f"Estimated Fair Value: {fair_value if fair_value else 'NA'}")
