import streamlit as st
import pandas as pd
import yfinance as yf
import io
import altair as alt
from ta.trend import SMAIndicator, MACD
from ta.momentum import RSIIndicator

# =====================================================
# CONFIG
# =====================================================
st.set_page_config(page_title="Stock Fair Value Analyzer", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

# =====================================================
# HELPERS
# =====================================================
def format_currency(val, currency_code="USD"):
    symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}
    symbol = symbols.get(currency_code, currency_code)
    try:
        return f"{symbol}{val:,.2f}" if val is not None else "-"
    except:
        return "-"


def safe_format_currency(df, col, currency):
    if df is not None and col in df.columns:
        df[col] = df[col].apply(lambda x: format_currency(x, currency) if pd.notna(x) else None)


# =====================================================
# VALUATION METHODS (UNCHANGED LOGIC)
# =====================================================
def dcf_valuation(eps, growth_rate=0.08, discount_rate=0.10):
    try:
        if eps <= 0:
            return None
        cf = eps * (1 + growth_rate)
        return round(cf / (discount_rate - growth_rate), 2)
    except:
        return None


def graham_valuation(eps, bvps):
    try:
        if eps <= 0 or bvps <= 0:
            return None
        return round((22.5 * eps * bvps) ** 0.5, 2)
    except:
        return None


def pe_valuation(eps, pe_ratio=15):
    try:
        if eps <= 0:
            return None
        return round(eps * pe_ratio, 2)
    except:
        return None


# =====================================================
# FAIR VALUE (RATE-LIMIT SAFE)
# =====================================================
def get_fair_value(ticker, growth_rate=0.10):
    try:
        stock = yf.Ticker(ticker)
        fi = stock.fast_info

        market_cap = fi.get("market_cap")
        current_price = fi.get("last_price")
        shares = fi.get("shares")

        # EBITDA not reliably available without .info → graceful fallback
        if not (market_cap and shares):
            return None, None

        projected_market_cap = market_cap * (1 + growth_rate)
        fair_price = projected_market_cap / shares

        return round(fair_price, 2), current_price
    except:
        return None, None


def ev_valuation(ticker):
    try:
        ticker = ticker.upper()
        fair_price, current_price = get_fair_value(ticker)
        if fair_price is None or current_price is None:
            return None

        stock = yf.Ticker(ticker)
        hist = stock.history(period="3y")

        fi = stock.fast_info
        market_cap = fi.get("market_cap", 0)

        cap_type = (
            "Mega" if market_cap >= 200_000_000_000 else
            "Large" if market_cap >= 10_000_000_000 else
            "Mid" if market_cap >= 2_000_000_000 else "Small"
        )

        underval_pct = ((fair_price - current_price) / current_price) * 100

        if underval_pct < 5:
            band = "Over Valued"
        elif underval_pct > 30:
            band = "Deep Discount"
        elif underval_pct > 20:
            band = "High Value"
        elif underval_pct > 18:
            band = "Undervalued"
        else:
            band = "Fair/Premium"

        high_3y = hist["High"].max() if not hist.empty else None
        low_3y = hist["Low"].min() if not hist.empty else None

        return {
            "Symbol": ticker,
            "Market Value (EV)": fair_price,
            "Current Price": current_price,
            "Undervalued (%)": round(underval_pct, 2),
            "Valuation Band": band,
            "Cap Size": cap_type,
            "3Y High": high_3y,
            "3Y Low": low_3y,
            "Entry Price": round(low_3y * 1.05, 2) if low_3y else None,
            "Exit Price": round(high_3y * 0.95, 2) if high_3y else None,
            "Signal": "Buy" if fair_price > current_price else "Hold/Sell"
        }
    except:
        return None


# =====================================================
# UI INPUT (NO YAHOO SEARCH)
# =====================================================
ticker_symbol = st.text_input("🔍 Enter Stock Ticker (e.g. AAPL, MSFT, TCS.NS)").upper().strip()

if ticker_symbol:
    result = ev_valuation(ticker_symbol)
    stock = yf.Ticker(ticker_symbol)

    hist = stock.history(period="5y")
    if hist.empty:
        hist = stock.history(period="3y")

    eps = None
    bvps = None
    pe_ratio = 15
    current_price = result["Current Price"] if result else None

    ev_val = result["Market Value (EV)"] if result else None
    dcf_val = dcf_valuation(eps) if eps else None
    graham_val = graham_valuation(eps, bvps) if eps and bvps else None
    pe_val = pe_valuation(eps, pe_ratio) if eps else None

    tab1, tab2, tab3 = st.tabs(["📋 Fair Value", "📂 Valuation by method", "📈 Technical Indicators"])

    # ---------------- TAB 1 ----------------
    with tab1:
        df = pd.DataFrame([result])
        for col in ["Market Value (EV)", "Current Price", "3Y High", "3Y Low", "Entry Price", "Exit Price"]:
            safe_format_currency(df, col, "USD")
        st.dataframe(df)

    # ---------------- TAB 2 ----------------
    with tab2:
        st.dataframe(pd.DataFrame([{
            "Market Value (EV)": format_currency(ev_val),
            "Cashflow Value (DCF)": format_currency(dcf_val),
            "Safe Value (Graham)": format_currency(graham_val),
            "Profit Value (PE)": format_currency(pe_val)
        }]))

    # ---------------- TAB 3 (UNCHANGED) ----------------
    with tab3:
        hist.reset_index(inplace=True)

        hist["SMA_50"] = SMAIndicator(hist["Close"], 50).sma_indicator()
        hist["SMA_200"] = SMAIndicator(hist["Close"], 200).sma_indicator()
        hist["RSI"] = RSIIndicator(hist["Close"], 14).rsi()
        macd = MACD(hist["Close"])
        hist["MACD"] = macd.macd()
        hist["Signal"] = macd.macd_signal()

        base = alt.Chart(hist).encode(x="Date:T")

        st.altair_chart(
            base.mark_line(color="blue").encode(y="Close") +
            base.mark_line(strokeDash=[4, 4], color="orange").encode(y="SMA_50") +
            base.mark_line(strokeDash=[2, 2], color="green").encode(y="SMA_200"),
            use_container_width=True
        )

        st.altair_chart(
            base.mark_line(color="purple").encode(y="MACD") +
            base.mark_line(color="red").encode(y="Signal"),
            use_container_width=True
        )

        st.altair_chart(
            alt.Chart(hist).mark_line(color="darkgreen").encode(x="Date:T", y="RSI"),
            use_container_width=True
        )
