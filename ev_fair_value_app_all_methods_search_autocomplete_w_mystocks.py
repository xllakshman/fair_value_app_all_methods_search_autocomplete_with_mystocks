import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import altair as alt
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator
from yfinance.exceptions import YFRateLimitError

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="Stock Fair Value Analyzer", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

# =====================================================
# FORMAT HELPERS
# =====================================================
def format_currency(val, currency="USD"):
    symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}
    symbol = symbols.get(currency, currency)
    return f"{symbol}{val:,.2f}" if val is not None else "-"

def safe_format_currency(df, col, currency):
    if col in df.columns:
        df[col] = df[col].apply(lambda x: format_currency(x, currency) if pd.notna(x) else None)

# =====================================================
# YAHOO SAFE DATA ADAPTER (CACHE-SAFE)
# =====================================================
@st.cache_data(ttl=3600)
def get_yahoo_info(ticker):
    """
    Fetch ONLY serializable Yahoo data.
    No yf.Ticker object returned.
    """
    t = yf.Ticker(ticker)

    try:
        info = t.info
    except YFRateLimitError:
        info = {}
    except Exception:
        info = {}

    try:
        fi = t.fast_info or {}
    except Exception:
        fi = {}

    return {
        "enterpriseValue": info.get("enterpriseValue"),
        "ebitda": info.get("ebitda"),
        "sharesOutstanding": info.get("sharesOutstanding"),
        "currentPrice": info.get("currentPrice") or fi.get("last_price"),
        "marketCap": info.get("marketCap") or fi.get("market_cap"),
        "shortName": info.get("shortName", "N/A"),
        "industry": info.get("industry", "N/A"),
        "currency": info.get("currency", "USD"),
        "trailingEps": info.get("trailingEps"),
        "bookValue": info.get("bookValue"),
        "trailingPE": info.get("trailingPE", 15),
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

def get_fair_value(ticker, growth_rate=0.10):
    info = get_yahoo_info(ticker)

    ev = info["enterpriseValue"]
    ebitda = info["ebitda"]
    shares = info["sharesOutstanding"]
    current_price = info["currentPrice"]

    if not (ev and ebitda and shares and current_price):
        return None, None

    ev_ebitda_ratio = ev / ebitda
    projected_ebitda = ebitda * (1 + growth_rate)
    projected_ev = projected_ebitda * ev_ebitda_ratio
    fair_price = projected_ev / shares

    return round(fair_price, 2), current_price

def ev_valuation(ticker):
    fair_price, current_price = get_fair_value(ticker)
    if fair_price is None:
        return None

    info = get_yahoo_info(ticker)
    hist = yf.Ticker(ticker).history(period="3y")

    market_cap = info["marketCap"]
    cap_type = (
        "Mega" if market_cap and market_cap >= 200_000_000_000 else
        "Large" if market_cap and market_cap >= 10_000_000_000 else
        "Mid" if market_cap and market_cap >= 2_000_000_000 else "Small"
    )

    underval_pct = ((fair_price - current_price) / current_price) * 100

    band = (
        "Deep Discount" if underval_pct > 30 else
        "High Value" if underval_pct > 20 else
        "Undervalued" if underval_pct > 10 else
        "Fair/Premium"
    )

    high_3y = hist["High"].max() if not hist.empty else None
    low_3y = hist["Low"].min() if not hist.empty else None

    return {
        "Symbol": ticker,
        "Name": info["shortName"],
        "Market Value (EV)": fair_price,
        "Current Price": current_price,
        "Undervalued (%)": round(underval_pct, 2),
        "Valuation Band": band,
        "Cap Size": cap_type,
        "Industry": info["industry"],
        "3Y High": round(high_3y, 2) if high_3y else None,
        "3Y Low": round(low_3y, 2) if low_3y else None,
        "Entry Price": round(low_3y * 1.05, 2) if low_3y else None,
        "Exit Price": round(high_3y * 0.95, 2) if high_3y else None,
        "Signal": "Buy" if fair_price > current_price else "Hold/Sell"
    }

# =====================================================
# YAHOO SEARCH (CACHED)
# =====================================================
@st.cache_data(show_spinner=False)
def search_yahoo_finance(query):
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
    headers = {"User-Agent": "Mozilla/5.0"}
    r = requests.get(url, headers=headers, timeout=5)
    if r.status_code != 200:
        return []
    data = r.json()
    return [
        f"{q['symbol']} - {q.get('shortname','')}"
        for q in data.get("quotes", [])
        if q.get("symbol")
    ]

# =====================================================
# UI
# =====================================================
query = st.text_input("🔍 Type company name or stock ticker:")

ticker_symbol = None
if query and len(query) >= 2:
    matches = search_yahoo_finance(query)
    if matches:
        sel = st.selectbox("Select a match:", matches)
        ticker_symbol = sel.split(" - ")[0]

if ticker_symbol:
    result = ev_valuation(ticker_symbol)
    info = get_yahoo_info(ticker_symbol)

    if result is None:
        st.warning("⚠️ Yahoo has limited data for this stock.")
        st.stop()

    eps = info["trailingEps"]
    bvps = info["bookValue"]
    pe_ratio = info["trailingPE"]
    currency = info["currency"]

    ev_val = result["Market Value (EV)"]
    dcf_val = dcf_valuation(eps)
    graham_val = graham_valuation(eps, bvps)
    pe_val = pe_valuation(eps, pe_ratio)

    tab1, tab2, tab3 = st.tabs(["📋 Fair Value", "📂 Valuation by method", "📈 Technical Indicators"])

    with tab1:
        df = pd.DataFrame([result])
        for col in ["Market Value (EV)", "Current Price", "3Y High", "3Y Low", "Entry Price", "Exit Price"]:
            safe_format_currency(df, col, currency)
        st.dataframe(df)

    with tab2:
        st.dataframe(pd.DataFrame([{
            "EV Value": format_currency(ev_val, currency),
            "DCF Value": format_currency(dcf_val, currency),
            "Graham Value": format_currency(graham_val, currency),
            "PE Value": format_currency(pe_val, currency)
        }]))

    with tab3:
        hist = yf.Ticker(ticker_symbol).history(period="5y")
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
