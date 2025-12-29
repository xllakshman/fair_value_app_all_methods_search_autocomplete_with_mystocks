import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import io
import altair as alt
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
from yfinance.exceptions import YFRateLimitError

# =====================================================
# STREAMLIT CONFIG
# =====================================================
st.set_page_config(page_title="Stock Fair Value Analyzer", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

GITHUB_CSV_URL = "https://raw.githubusercontent.com/xllakshman/f...l_methods_search_autocomplete_with_mystocks/main/stock_list.csv"

# =====================================================
# ✅ SAFE YAHOO INFO FIX (ONLY ADDITION)
# =====================================================
@st.cache_data(ttl=3600)
def safe_stock_info(ticker: str):
    """
    Drop-in replacement for stock.info
    Prevents Yahoo rate-limit crashes
    """
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
# EXISTING FUNCTIONS (UNCHANGED)
# =====================================================
def get_pe_fair_value(eps, pe_ratio=20):
    try:
        return round(eps * pe_ratio, 2)
    except:
        return None


def get_fair_value(ticker, growth_rate=0.10):
    try:
        stock = yf.Ticker(ticker)

        # ✅ FIXED LINE (ONLY CHANGE)
        info = safe_stock_info(ticker)

        ev = info.get("enterpriseValue")
        ebitda = info.get("ebitda")
        shares = info.get("sharesOutstanding")
        current_price = info.get("currentPrice")

        if not (ev and ebitda and shares):
            return None

        ev_to_ebitda = ev / ebitda
        fair_price = (ev / shares)

        return round(fair_price, 2)
    except Exception:
        return None


# =====================================================
# UI / DATA LOADING (UNCHANGED)
# =====================================================
@st.cache_data
def load_stock_list():
    response = requests.get(GITHUB_CSV_URL)
    return pd.read_csv(io.StringIO(response.text))


df_stocks = load_stock_list()
tickers = df_stocks["Ticker"].unique().tolist()

selected_ticker = st.selectbox("Select Stock", tickers)

if selected_ticker:
    stock = yf.Ticker(selected_ticker)

    hist = stock.history(period="5y")

    if not hist.empty:
        st.subheader("📊 Price Chart")

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
