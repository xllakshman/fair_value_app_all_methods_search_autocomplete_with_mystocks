
import streamlit as st
import pandas as pd
import requests
import yfinance as yf
import io  # Ensure at top of script
import requests
import altair as alt
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from ta.trend import MACD
import streamlit as st
import pandas as pd
import yfinance as yf

# ============================================================
# STREAMLIT CONFIG
# ============================================================
st.set_page_config(
    page_title="Bulk Fair Value Engine (100+ Stocks)",
    layout="wide"
)

st.title("📊 Bulk Fair Value Analysis (Yahoo Safe Mode)")
st.caption("Optimized for 100–500 tickers | No stock.info | Cached | Failure-proof")

# ============================================================
# ---------------------- DATA LAYER ---------------------------
# ============================================================

@st.cache_data(ttl=3600)
def bulk_price_history(tickers, years=5):
    """
    Fetch price history for all tickers in ONE call
    """
    try:
        data = yf.download(
            tickers=tickers,
            period=f"{years}y",
            group_by="ticker",
            auto_adjust=True,
            threads=True
        )
        return data
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def bulk_fast_info(tickers):
    """
    Lightweight metadata fetch (safe replacement for stock.info)
    """
    result = {}
    for t in tickers:
        try:
            result[t] = yf.Ticker(t).fast_info
        except Exception:
            result[t] = {}
    return result


@st.cache_data(ttl=7200)
def get_financials_safe(symbol):
    """
    Lazy fetch – call ONLY if needed
    """
    try:
        t = yf.Ticker(symbol)
        return {
            "income": t.financials,
            "cashflow": t.cashflow
        }
    except Exception:
        return {}

# ============================================================
# ------------------- SAFE HELPERS ----------------------------
# ============================================================

def safe_get(d, key):
    try:
        return d.get(key)
    except Exception:
        return None


def latest_column(df):
    if df is None or df.empty:
        return None
    return df.iloc[:, 0]


# ============================================================
# ------------------ VALUATION ENGINE -------------------------
# ============================================================

def compute_bulk_valuations(tickers, fast_info):
    """
    Vectorized fair value computation (no network calls)
    """
    rows = []

    for t in tickers:
        fi = fast_info.get(t, {})

        price = safe_get(fi, "last_price")
        market_cap = safe_get(fi, "market_cap")
        currency = safe_get(fi, "currency")

        # Simple deterministic valuation logic
        pe_fair = price * 1.25 if price else None
        ev_fair = market_cap * 1.20 if market_cap else None

        combined = None
        values = [v for v in [pe_fair, ev_fair] if v]
        if values:
            combined = sum(values) / len(values)

        rows.append({
            "Ticker": t,
            "Price": round(price, 2) if price else None,
            "MarketCap_Bn": round(market_cap / 1e9, 2) if market_cap else None,
            "PE_FairValue": round(pe_fair, 2) if pe_fair else None,
            "EV_FairValue_Bn": round(ev_fair / 1e9, 2) if ev_fair else None,
            "Combined_FairValue": round(combined, 2) if combined else None,
            "Currency": currency
        })

    return pd.DataFrame(rows)


# ============================================================
# ----------------------- UI ---------------------------------
# ============================================================

st.subheader("📥 Input Tickers")

tickers_input = st.text_area(
    "Enter tickers (comma separated)",
    value="AAPL,MSFT,GOOGL,NVDA,AMZN,META,TSLA"
)

tickers = sorted(
    list({t.strip().upper() for t in tickers_input.split(",") if t.strip()})
)

st.write(f"✅ {len(tickers)} tickers loaded")

if len(tickers) > 0:

    with st.spinner("🚀 Fetching market data (batched & cached)..."):
        prices = bulk_price_history(tickers)
        fast_info = bulk_fast_info(tickers)

    df = compute_bulk_valuations(tickers, fast_info)

    st.subheader("📊 Bulk Fair Value Table")
    st.dataframe(df, use_container_width=True)

    # ----------------- OPTIONAL CHART -----------------

    st.subheader("📈 Price Chart (Selected Stock)")
    selected = st.selectbox("Choose ticker", tickers)

    if not prices.empty and selected in prices.columns.get_level_values(0):
        try:
            close_prices = prices[selected]["Close"]
            st.line_chart(close_prices)
        except Exception:
            st.warning("Chart data unavailable")

else:
    st.info("Enter at least one ticker to begin.")
