import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="Equity Research Terminal", layout="wide")

# ==========================================
# 1. Ingestion Layer with Caching
# ==========================================
@st.cache_data(ttl=3600)
def get_comprehensive_ticker_data(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    # Safely extract financials to avoid crashing if unavailable
    try:
        financials = ticker.quarterly_financials
        balance_sheet = ticker.quarterly_balance_sheet
        cashflow = ticker.quarterly_cashflow
    except Exception:
        financials = balance_sheet = cashflow = pd.DataFrame()
        
    return info, financials, balance_sheet, cashflow

# ==========================================
# 2. DataFrame Styling Helper Function
# ==========================================
def style_financial_statements(df):
    """Formats statements with accounting standards (parentheses for negatives), text arrows (↑/↓), % change, and a row-wise heatmap."""
    if df is None or df.empty:
        return df
        
    # 1. Ensure columns are sorted newest to oldest (Standard yfinance output)
    cols = sorted(df.columns, reverse=True)
    
    # 2. Create a purely numeric copy for math/heatmaps (handling NaNs)
    numeric_df = df[cols].apply(pd.to_numeric, errors='coerce').fillna(0)
    
    # Cast display_df to 'object' so Pandas allows us to inject strings (arrows, %, N/A)
    display_df = df[cols].copy().astype(object)
    
    # --- NEW: Strict Accounting Formatter ---
    def to_accounting(val):
        if pd.isna(val):
            return "N/A"
        if val == 0:
            return "—" # Em-dash for exactly zero
        if val < 0:
            return f"({abs(val):,.0f})" # Parentheses for negatives
        return f"{val:,.0f}"
    
    # 3. Calculate Deltas, % Change, and Assign Text Arrows
    for i, col in enumerate(cols):
        if i < len(cols) - 1: # We have a previous period (to the right) to compare against
            prev_col = cols[i+1]
            for idx in numeric_df.index:
                curr_val = numeric_df.at[idx, col]
                prev_val = numeric_df.at[idx, prev_col]
                
                # Handle missing data points
                if pd.isna(df.at[idx, col]):
                    display_df.at[idx, col] = "N/A"
                    continue
                    
                delta = curr_val - prev_val
                
                # Calculate percentage change safely
                if prev_val != 0 and not pd.isna(prev_val):
                    pct_change = (delta / abs(prev_val)) * 100
                    pct_str = f" ({pct_change:+,.1f}%)" 
                else:
                    pct_str = "" 
                    
                if delta > 0:
                    arrow = f" ↑{pct_str}"
                elif delta < 0:
                    arrow = f" ↓{pct_str}"
                else:
                    arrow = " -"
                    
                # Apply accounting format to the base number, then append the arrow/pct
                display_df.at[idx, col] = f"{to_accounting(curr_val)}{arrow}"
        else: # Oldest period (No prior data to compare)
            for idx in numeric_df.index:
                curr_val = numeric_df.at[idx, col]
                display_df.at[idx, col] = to_accounting(curr_val)
                    
    # 4. Clean up column headers (Convert Pandas Timestamps to YYYY-MM-DD Strings)
    str_cols = [c.strftime('%Y-%m-%d') if hasattr(c, 'strftime') else str(c) for c in cols]
    display_df.columns = str_cols
    numeric_df.columns = str_cols
    
    # 5. Create a row-normalized gmap for the background gradient
    def normalize_row(row):
        mn, mx = row.min(), row.max()
        if mx == mn:
            return pd.Series(0.5, index=row.index)
        return (row - mn) / (mx - mn)

    gmap_df = numeric_df.apply(normalize_row, axis=1)
    
    # 6. Styler function for injecting CSS text colors based on the text arrow
    def apply_arrow_colors(data):
        styles = pd.DataFrame('', index=data.index, columns=data.columns)
        for c in data.columns:
            for r in data.index:
                val = str(data.at[r, c])
                if "↑" in val:
                    styles.at[r, c] = 'color: #00E676 !important;' # Bright Green
                elif "↓" in val:
                    styles.at[r, c] = 'color: #FF5252 !important;' # Bright Red
        return styles
        
    # 7. Apply full Pandas Styling Chain 
    styled_df = (
        display_df.style
        .set_properties(**{
            'font-family': 'Roboto',
            'background-color': '#0a0a0a', 
            'color': '#888888',            
            'border-color': '#333333',
            'text-align': 'right'          # <--- NEW: Forces strict right-alignment
        })
        .apply(apply_arrow_colors, axis=None)
        .background_gradient(axis=None, subset=str_cols, cmap='YlOrRd_r', gmap=gmap_df) 
    )
    
    return styled_df

# ==========================================
# 3. Sidebar Controls
# ==========================================
st.sidebar.header("Equity Research Config")
ticker_symbol = st.sidebar.text_input("Ticker Symbol", value="AAPL").upper()

if ticker_symbol:
    try:
        with st.spinner(f"Extracting all financial layers for {ticker_symbol}..."):
            info, financials, balance, cashflow = get_comprehensive_ticker_data(ticker_symbol)
            
        # ==========================================
        # 4. Header Section
        # ==========================================
        company_name = info.get('longName', ticker_symbol)
        sector = info.get('sector', 'N/A')
        industry = info.get('industry', 'N/A')
        summary = info.get('longBusinessSummary', 'No summary available.')
        
        st.title(f"{company_name} ({ticker_symbol})")
        st.caption(f"**Sector:** {sector} | **Industry:** {industry} | **Currency:** {info.get('currency', 'USD')}")
        
        # Business Summary Section
        with st.expander("View Full Business Operation Summary"):
            st.write(summary)

        # ==========================================
        # 5. Top-Level Executive Metrics Grid
        # ==========================================
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Market Capitalization", f"${info.get('marketCap', 0):,}")
        m_col2.metric("Enterprise Value (EV)", f"${info.get('enterpriseValue', 0):,}")
        m_col3.metric("Trailing P/E Ratio", f"{info.get('trailingPE', 'N/A')}")
        m_col4.metric("Dividend Yield", f"{info.get('dividendYield', 0) * 100:.2f}%" if info.get('dividendYield') else "0.00%")
        
        # ==========================================
        # 6. Core Analytical Notebook Layout 
        # ==========================================
        st.subheader("🔍 Relative Valuation Multiples")
        val_data = {
            "Multiple": ["Trailing P/E", "Forward P/E", "PEG Ratio (5yr expected)", "Price to Sales (TTM)", "Price to Book", "EV / Revenue", "EV / EBITDA"],
            "Value": [info.get('trailingPE'), info.get('forwardPE'), info.get('pegRatio'), info.get('priceToSalesTrailing12Months'), info.get('priceToBook'), info.get('enterpriseToRevenue'), info.get('enterpriseToEbitda')]
        }
        st.dataframe(pd.DataFrame(val_data), use_container_width=True, hide_index=True)

        st.subheader("Operating Efficiency & Capital Returns")
        p_col1, p_col2 = st.columns(2)
        with p_col1:
            prof_data = {
                "Margin Type": ["Gross Margin", "Operating Margin", "EBITDA Margin", "Net Profit Margin"],
                "Percentage": [f"{info.get('grossMargins', 0)*100:.2f}%", f"{info.get('operatingMargins', 0)*100:.2f}%", f"{info.get('ebitdaMargins', 0)*100:.2f}%", f"{info.get('profitMargins', 0)*100:.2f}%"]
            }
            st.dataframe(pd.DataFrame(prof_data), use_container_width=True, hide_index=True)
        with p_col2:
            eff_data = {
                "Metric": ["Return on Equity (ROE)", "Return on Assets (ROA)"],
                "Value": [f"{info.get('returnOnEquity', 0)*100:.2f}%", f"{info.get('returnOnAssets', 0)*100:.2f}%"]
            }
            st.dataframe(pd.DataFrame(eff_data), use_container_width=True, hide_index=True)

        st.subheader("Solvency, Liquidity & Market Risk")
        h_col1, h_col2 = st.columns(2)
        with h_col1:
            health_data = {
                "Balance Sheet Metric": ["Total Cash", "Total Debt", "Debt to Equity Ratio", "Current Ratio", "Quick Ratio"],
                "Value": [f"${info.get('totalCash', 0):,}", f"${info.get('totalDebt', 0):,}", f"{info.get('debtToEquity', 'N/A')}%", f"{info.get('currentRatio', 'N/A')}", f"{info.get('quickRatio', 'N/A')}"]
            }
            st.dataframe(pd.DataFrame(health_data), use_container_width=True, hide_index=True)
        with h_col2:
            risk_data = {
                "Market/Price Metric": ["Beta (5Y Monthly)", "52-Week High", "52-Week Low", "50-Day Moving Avg", "200-Day Moving Avg"],
                "Value": [info.get('beta'), info.get('fiftyTwoWeekHigh'), info.get('fiftyTwoWeekLow'), info.get('fiftyDayAverage'), info.get('twoHundredDayAverage')]
            }
            st.dataframe(pd.DataFrame(risk_data), use_container_width=True, hide_index=True)

        st.subheader("Quarterly Accounting Statements")
        st.write("Select and view all available quarterly statements below:")
        
        # Apply our new styling function before displaying
        if not financials.empty:
            st.markdown("**Income Statement**")
            st.dataframe(style_financial_statements(financials), use_container_width=True)
        else:
            st.info("Income Statement data unavailable.")

        if not balance.empty:
            st.markdown("**Balance Sheet**")
            st.dataframe(style_financial_statements(balance), use_container_width=True)
        else:
            st.info("Balance Sheet data unavailable.")

        if not cashflow.empty:
            st.markdown("**Cash Flow Statement**")
            st.dataframe(style_financial_statements(cashflow), use_container_width=True)
        else:
            st.info("Cash Flow data unavailable.")

    except Exception as e:
        st.error(f"Error compiling equity profile for '{ticker_symbol}'. Verification of ticker configuration or network required.")
        st.exception(e)