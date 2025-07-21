
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

st.set_page_config(page_title="Stock Fair Value Analyzer", layout="wide")
st.title("📈 Global Equities Fair Value Recommendation")

GITHUB_CSV_URL = "https://raw.githubusercontent.com/xllakshman/fair_value_app_all_methods_search_autocomplete_with_mystocks/main/stock_list.csv"

def format_currency(val, currency_code="USD"):
    symbols = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£", "JPY": "¥"}
    symbol = symbols.get(currency_code, currency_code)
    try:
        return f"{symbol}{val:,.2f}" if val is not None else "-"
    except:
        return "-"

# To handle errors due to lack of data in yfinance
def safe_format_currency(df, col, currency):
    if df is not None and col in df.columns:
        df[col] = df[col].apply(lambda x: format_currency(x, currency) if pd.notna(x) else None)

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

def get_fair_value(ticker, growth_rate=0.10):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        ev = info.get("enterpriseValue")
        ebitda = info.get("ebitda")
        shares = info.get("sharesOutstanding")
        current_price = info.get("currentPrice")
  
        if not (ev and ebitda and shares):
            return None, None
        ev_ebitda_ratio = ev / ebitda
        projected_ebitda = ebitda * (1 + growth_rate)
        projected_ev = projected_ebitda * ev_ebitda_ratio
        fair_price = projected_ev / shares
        return fair_price, current_price
    except:
        return None, None

def ev_valuation(ticker):
    try:
        ticker = ticker.upper()
        fair_price, current_price = get_fair_value(ticker)
        if fair_price is None or current_price is None:
            return None
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="3y")
        company_name = info.get("shortName", "N/A")
        market_cap = info.get("marketCap", 0)
        industry = info.get("industry", "N/A")
        cap_type = (
            "Mega" if market_cap >= 200_000_000_000 else
            "Large" if market_cap >= 10_000_000_000 else
            "Mid" if market_cap >= 2_000_000_000 else "Small"
        )
        market = "India" if ticker.endswith(".NS") else "USA"
        underval_pct = ((fair_price - current_price) / current_price) * 100
        if fair_price < 0 or underval_pct < 5:
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
        entry_price = round(low_3y * 1.05, 2) if low_3y else "N/A"
        exit_price = round(high_3y * 0.95, 2) if high_3y else "N/A"
        currency = info.get("currency", "USD")
        return {
            "Symbol": ticker,
            "Name": company_name,
            "Market Value (EV)": round(fair_price, 2),
            "Current Price": round(current_price, 2),
            "Undervalued (%)": round(underval_pct, 2),
            "Valuation Band": band,
            "Market": market,
            "Cap Size": cap_type,
            "Industry": industry,
            "3Y High": round(high_3y, 2) if high_3y else "N/A",
            "3Y Low": round(low_3y, 2) if low_3y else "N/A",
            "Entry Price": entry_price,
            "Exit Price": exit_price,
            "Signal": "Buy" if fair_price > current_price else "Hold/Sell"
        }
    except:
        return None


@st.cache_data(show_spinner=False)
def search_yahoo_finance(query):
    """Search Yahoo Finance for ticker/company name matches."""
    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=10&newsCount=0"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/114.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, headers=headers, timeout=5)

        if response.status_code != 200:
            st.warning(f"❗ Lookup failed: HTTP {response.status_code}")
            return []

        if not response.text.strip():
            st.warning("❗ Lookup failed: Empty response from server")
            return []

        data = response.json()
        matches = []
        for item in data.get("quotes", []):
            symbol = item.get("symbol")
            name = item.get("shortname") or item.get("longname") or ""
            exch = item.get("exchange", "")
            if symbol and name:
                display = f"{symbol} - {name} ({exch})"
                matches.append(display)

        return matches

    except requests.exceptions.RequestException as req_err:
        st.warning(f"❗ Network error: {req_err}")
        return []

    except ValueError as json_err:
        st.warning(f"❗ JSON decode error: {json_err}")
        return []

    except Exception as e:
        st.warning(f"❗ Unexpected error during lookup: {e}")
        return []


# --- UI Input to Serach a ticker ---
query_input = st.text_input("🔍 Type company name or stock ticker:")

ticker_symbol = None
if query_input and len(query_input) >= 2:
    matches = search_yahoo_finance(query_input)
    if matches:
        selected_display = st.selectbox("Select a match from drop down:", matches)
        if selected_display:
            ticker_symbol = selected_display.split(" - ")[0]
    else:
        st.info("No matching tickers or companies found.")

if ticker_symbol:
    result = ev_valuation(ticker_symbol)
    stock = yf.Ticker(ticker_symbol)
    info = stock.info

    eps = info.get("trailingEps", 0)
    bvps = info.get("bookValue", 0)
    pe_ratio = info.get("trailingPE", 15)
    current_price = info.get("currentPrice")

    if result is not None and result.get("Market Value (EV)", None) is not None:
        ev_val = result["Market Value (EV)"] 
    else:
        st.warning(f"⚠️ We have limited data availability to provide fair value estimates for {ticker_symbol}.")
        ev_val = 0
    #ev_val = result.get("Market Value (EV)", None)
    dcf_val = dcf_valuation(eps)
    graham_val = graham_valuation(eps, bvps)
    pe_val = pe_valuation(eps, pe_ratio)

    tab1, tab2, tab3, tab4 = st.tabs(["📋 Fair Value", "📂 Valuation by method", "📈 Technical Indicators","MyStocks_Wathclist"])

    with tab1:
        df = pd.DataFrame([result])
        currency = info.get("currency", "USD")

       # Apply to all price-related columns to handle lack of data in yfinance
        for col in ["Market Value (EV)", "Current Price", "3Y High", "3Y Low", "Entry Price", "Exit Price"]:
            safe_format_currency(df, col, currency)
        
        st.dataframe(df)
        
        st.markdown("## Stock Fair Value Comparison")
        st.markdown("##### 🔍 Slide the bar for each method to find the most suitable Fair Value of the Stock")
        weight_ev = st.slider("Actual Market Value", 0, 100, 30)
        weight_dcf = st.slider("Cashflow Value (DCF)", 0, 100, 30)
        weight_graham = st.slider("Safe Value (Graham)", 0, 100, 20)
        weight_pe = st.slider("Profit Value (PE)", 0, 100, 20)

        total_weight = weight_ev + weight_dcf + weight_graham + weight_pe
        if total_weight == 100 and all(v is not None for v in [ev_val, dcf_val, graham_val, pe_val]):
            combined_val = round(
                (ev_val * weight_ev +
                 dcf_val * weight_dcf +
                 graham_val * weight_graham +
                 pe_val * weight_pe) / 100, 2
            )
            st.markdown("#### 💰 Stock Fair Valuation Comparison")
            st.table({
                "Method": [
                    "Current Price",
                    "Actual Market Value (EV)", 
                    "Cashflow Value (DCF)", 
                    "Safe Value (Graham)", 
                    "Profit Value (PE)", 
                    "Fair Value (Combined)",
                    "Expected Return %"
                    ],
                "Fair Value": [
                    format_currency(current_price, currency),
                    format_currency(ev_val, currency),
                    format_currency(dcf_val, currency),
                    format_currency(graham_val, currency),
                    format_currency(pe_val, currency),
                    format_currency(combined_val, currency),
                    round(((combined_val - current_price) / current_price) * 100,2)
                ]
            })


    with tab2:
        full_df = pd.DataFrame([{
            "Ticker": ticker_symbol,
            "EPS": format_currency(eps, currency),
            "BVPS": format_currency(bvps, currency),
            "PE Ratio": format_currency(pe_ratio, currency),
            "Market Value (EV)": format_currency(ev_val, currency),
            "Cashflow Value (DCF)": format_currency(dcf_val, currency),
            "Safe Value (Graham)": format_currency(graham_val, currency),
            "Profit Value (PE)": format_currency(pe_val, currency)
        }])
        st.dataframe(full_df)

    with tab3:

        hist = stock.history(period="5y")
        if hist.empty:
            hist = stock.history(period="3y")
        hist.reset_index(inplace=True)

        hist["SMA_50"] = SMAIndicator(close=hist["Close"], window=50).sma_indicator()
        hist["SMA_200"] = SMAIndicator(close=hist["Close"], window=200).sma_indicator()
        hist["RSI"] = RSIIndicator(close=hist["Close"], window=14).rsi()
        macd = MACD(close=hist["Close"])
        hist["MACD"] = macd.macd()
        hist["Signal"] = macd.macd_signal()

        base = alt.Chart(hist).encode(x="Date:T")
        st.altair_chart(base.mark_line(color="blue").encode(y="Close") +
                        base.mark_line(strokeDash=[4, 4], color="orange").encode(y="SMA_50") +
                        base.mark_line(strokeDash=[2, 2], color="green").encode(y="SMA_200"),
                        use_container_width=True)

        st.altair_chart(base.mark_line(color="purple").encode(y="MACD") +
                        base.mark_line(color="red").encode(y="Signal"),
                        use_container_width=True)

        st.altair_chart(alt.Chart(hist).mark_line(color="darkgreen").encode(x="Date:T", y="RSI"),
                        use_container_width=True)

    with tab4:

        st.subheader("📋 Key Stocks Watchlist")

        uploaded_file = st.file_uploader("Upload CSV with Stock Tickers", type=["csv"])

        # Fallback to default CSV from GitHub
        if uploaded_file is not None:
            watchlist_df = pd.read_csv(uploaded_file)
            st.info("✅ Custom CSV uploaded.")
        else:
            try:
                response = requests.get(GITHUB_CSV_URL)
                response.raise_for_status()
                watchlist_df = pd.read_csv(io.StringIO(response.text))
                st.info("📦 Assessing more than 200 tickers  fair value, estimted wait time is approximately 180 seconds...")
            except Exception as e:
                st.error("❌ Could not load default watchlist from GitHub.")
                st.stop()

        if "Symbol" not in watchlist_df.columns:
            st.error("❌ CSV must contain a 'Symbol' column.")
        else:
            tickers = watchlist_df["Symbol"].dropna().unique().tolist()
            results = []

            st.markdown("### 🔧 Set Weights for Fair Value Recommendation for stocks")
            col1, col2, col3, col4 = st.columns(4)
            weight_ev = col1.slider("EV %", 0, 100, 40)
            weight_dcf = col2.slider("DCF %", 0, 100, 30)
            weight_graham = col3.slider("Graham %", 0, 100, 10)
            weight_pe = col4.slider("PE %", 0, 100, 20)

            total_weight = weight_ev + weight_dcf + weight_graham + weight_pe
            if total_weight != 100:
                st.warning("⚠️ Total weight must equal 100. Adjust sliders.")
            else:
                weight_ev /= 100
                weight_dcf /= 100
                weight_graham /= 100
                weight_pe /= 100

                for ticker in tickers:
                    try:
                        result = ev_valuation(ticker)
                        stock = yf.Ticker(ticker)
                        info = stock.info
                        country = info.get("country", "Unknown")
                        name = info.get("shortName", "")
                        current_price = info.get("currentPrice")
                        eps = info.get("trailingEps", 0)
                        bvps = info.get("bookValue", 0)
                        pe_ratio = info.get("trailingPE", 15)

                        # Skip if current price not available or country not valid
                        if current_price is None or country not in ["India", "United States"]:
                            continue

                        ev_val = result["Market Value (EV)"] if result and result.get("Market Value (EV)") else None
                        dcf_val = dcf_valuation(eps)
                        graham_val = graham_valuation(eps, bvps)
                        pe_val = pe_valuation(eps, pe_ratio)

                        # Only compute combined value if all parts are available
                        if all(val is not None for val in [ev_val, dcf_val, graham_val, pe_val]):
                            combined_fair_value = round(
                                ev_val * weight_ev +
                                dcf_val * weight_dcf +
                                graham_val * weight_graham +
                                pe_val * weight_pe, 2
                            )
                            return_pct = round(((combined_fair_value - current_price) / current_price) * 100, 2)
                        else:
                            combined_fair_value = None
                            return_pct = None

                        results.append({
                            "Ticker": ticker,
                            "Company Name": name,
                            "Country": country,
                            "Current Price": current_price,
                            "Market Value (EV)": ev_val,
                            "Cashflow Value (DCF)": dcf_val,
                            "Safe Value (Graham)": graham_val,
                            "Profit Value (PE)": pe_val,
                            "Net Fair Value": combined_fair_value,
                            "Expected Return %": return_pct
                        })
                    except Exception as e:
                        st.warning(f"⚠️ Could not fetch data for {ticker}: {e}")

                if results:
                    results_df = pd.DataFrame(results)

                    # --- Filtering & Sorting ---
                    company_filter = st.text_input("🔍 Filter by Company Name")
                    if company_filter:
                        company_filter = company_filter.upper()
                        results_df = results_df[results_df["Company Name"].str.contains(company_filter, case=False)]

                    sort_by = st.selectbox("📊 Sort By", ["Expected Return %", "Net Fair Value"])
                    results_df = results_df.sort_values(by=sort_by, ascending=False, na_position="last")

                    # Format currency for display
                    currency = "USD"
                    for col in ["Current Price", "Market Value (EV)", "Cashflow Value (DCF)", "Safe Value (Graham)", "Profit Value (PE)", "Net Fair Value"]:
                        results_df[col] = results_df[col].apply(lambda x: format_currency(x, currency) if pd.notna(x) else "-")

                    st.dataframe(results_df, use_container_width=True)
                else:
                    st.warning("⚠️ No valid data found for the uploaded/watchlist tickers.")
