import streamlit as st
import yfinance as yf
import pandas as pd
import re
import numpy as np
import edgar as edgar
from edgar import Company, set_identity

st.set_page_config(page_title="Equity Research Terminal", layout="wide")

# Required by SEC to identify the user
set_identity("collin.mccoll@gmail.com")

# ==========================================
# 0. Edgar Data Cleaner
# ==========================================
def clean_edgar_statement(statement):
    """Strips XBRL metadata and formats edgartools statements for financial modeling."""
    if not statement:
        return pd.DataFrame()
        
    df = statement.to_dataframe()
    if df.empty:
        return df
        
    # 1. Use human-readable SEC labels for the row index
    if 'label' in df.columns:
        df = df.set_index('label')
    elif 'concept' in df.columns:
        df = df.set_index('concept')
        
    # -> THE FIX: Drop duplicate index labels so df.at[] returns a scalar, not a Series
    df = df[~df.index.duplicated(keep='first')]
        
    # 2. Identify and keep ONLY columns that contain dates
    date_cols = [col for col in df.columns if isinstance(col, str) and re.search(r'\d{4}-\d{2}-\d{2}', col)]
    
    if not date_cols:
        return pd.DataFrame()
        
    clean_df = df[date_cols]
    
    # 3. Ensure all extracted data is strictly numeric so the styler's math works
    clean_df = clean_df.apply(pd.to_numeric, errors='coerce')
    
    return clean_df

# ==========================================
# 1. Ingestion Layer with Caching
# ==========================================
@st.cache_data(ttl=3600)
def get_comprehensive_ticker_data(symbol):
    ticker = yf.Ticker(symbol)
    info = ticker.info
    
    try:
        company = Company(symbol)
        
        # Extracting the latest 10-K filing
        filing = company.get_filings(form="10-K").latest()
        statement_obj = filing.obj()
        
        # Apply the cleaner function before passing data downstream
        financials = clean_edgar_statement(statement_obj.income_statement)
        balance_sheet = clean_edgar_statement(statement_obj.balance_sheet)
        cashflow = clean_edgar_statement(statement_obj.cash_flow_statement)
        
    except Exception:
        financials = balance_sheet = cashflow = pd.DataFrame()
        
    return info, financials, balance_sheet, cashflow

@st.cache_data(ttl=3600)
def get_indexed_performance(ticker_symbol, benchmark_symbol, period="1y"):
    try:
        data = yf.download([ticker_symbol, benchmark_symbol], period=period)['Close']
        data = data.ffill().dropna()
        
        if data.empty:
            return pd.DataFrame()
            
        indexed_data = (data / data.iloc[0] - 1) * 100
        return indexed_data
    except Exception as e:
        return pd.DataFrame()


# ==========================================
# 2. DataFrame Styling Helper Function
# ==========================================
def style_financial_statements(df):
    if df is None or df.empty:
        return df
        
    df = df.dropna(axis=1, how='all')
    if df.empty:
        return df
    
    cols = sorted(df.columns, reverse=True)
    numeric_df = df[cols].apply(pd.to_numeric, errors='coerce')
    numeric_df_filled = numeric_df.fillna(0)
    
    display_df = df[cols].copy().astype(object)
    
    def to_accounting(val):
        if pd.isna(val) or val == 0:
            return "" 
        if val < 0:
            return f"({abs(val):,.0f})" 
        return f"{val:,.0f}"
    
    for i, col in enumerate(cols):
        if i < len(cols) - 1:
            prev_col = cols[i+1]
            for idx in numeric_df.index:
                curr_val = numeric_df.at[idx, col]
                prev_val = numeric_df.at[idx, prev_col]
                
                if pd.isna(curr_val) or curr_val == 0:
                    display_df.at[idx, col] = ""
                    continue
                    
                delta = curr_val - prev_val
                
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
                    arrow = "" 
                    
                display_df.at[idx, col] = f"{to_accounting(curr_val)}{arrow}".strip()
        else: 
            for idx in numeric_df.index:
                curr_val = numeric_df.at[idx, col]
                if pd.isna(curr_val) or curr_val == 0:
                    display_df.at[idx, col] = ""
                else:
                    display_df.at[idx, col] = to_accounting(curr_val)
                    
    str_cols = [c.strftime('%Y-%m-%d') if hasattr(c, 'strftime') else str(c) for c in cols]
    display_df.columns = str_cols
    numeric_df_filled.columns = str_cols
    
    gmap_df = pd.DataFrame(index=numeric_df_filled.index, columns=numeric_df_filled.columns, dtype=float)
    
    for r in gmap_df.index:
        is_header_row = str(r).strip().endswith(':')
        row_data = numeric_df_filled.loc[r]
        
        if is_header_row:
            gmap_df.loc[r] = np.nan
        else:
            mn, mx = row_data.min(), row_data.max()
            for c in gmap_df.columns:
                display_val = str(display_df.at[r, c]).strip()
                if display_val == "":
                    gmap_df.at[r, c] = np.nan
                else:
                    gmap_df.at[r, c] = 0.5 if mx == mn else (row_data[c] - mn) / (mx - mn)

    # ---------------------------------------------------------
    # THE FIX: Isolate the index and force the text alignment
    # ---------------------------------------------------------
    display_df = display_df.reset_index()
    label_col = display_df.columns[0] 
    gmap_df = gmap_df.reset_index(drop=True)
    
    # 1. Function strictly for the label column
    def style_labels(val):
        if str(val).strip().endswith(':'):
            return 'font-weight: 800 !important; text-align: right !important;'
        return 'text-align: left !important;'

    # 2. Function strictly for the data columns
    def apply_data_styles(data):
        styles = pd.DataFrame('', index=data.index, columns=data.columns)
        for r in data.index:
            row_label = str(data.at[r, label_col]).strip()
            is_header_row = row_label.endswith(':')
            
            for c in data.columns:
                if c == label_col:
                    continue # Handled by style_labels
                    
                val = str(data.at[r, c]).strip()
                if is_header_row or val == "":
                    styles.at[r, c] = 'background-color: transparent !important; background-image: none !important;'
                else:
                    css = ""
                    if "↑" in val:
                        css += 'color: #00E676 !important;' 
                    elif "↓" in val:
                        css += 'color: #FF5252 !important;' 
                    styles.at[r, c] = css
        return styles
        
    styled_df = (
        display_df.style
        .set_properties(**{
            'font-family': '"Inter", "Segoe UI", system-ui, sans-serif',
            'font-size': '14px',
            'letter-spacing': '0.2px'       
        })
        # Hit the label column with the targeted bold/right-align
        .map(style_labels, subset=[label_col]) 
        # Hit the rest of the dataframe with colors/blanks
        .apply(apply_data_styles, axis=None)
        .background_gradient(axis=None, subset=str_cols, cmap='YlOrRd_r', gmap=gmap_df)
        .hide(axis="index") 
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
        
        with st.expander("View Full Business Operation Summary"):
            st.write(summary)

        # ==========================================
        # 5. Top-Level Executive Metrics Grid
        # ==========================================
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("Market Capitalization", f"${info.get('marketCap', 0):,}")
        m_col2.metric("Enterprise Value (EV)", f"${info.get('enterpriseValue', 0):,}")
        m_col3.metric("Trailing P/E Ratio", f"{info.get('trailingPE', 'N/A')}")
        
        raw_yield = info.get('dividendYield')
        if raw_yield is not None and raw_yield != 0:
            is_pre_multiplied = False
            if raw_yield > 0.2: 
                is_pre_multiplied = True
            display_yield = raw_yield if is_pre_multiplied else (raw_yield * 100)
            yield_str = f"{display_yield:.2f}%"
        else:
            yield_str = "0.00%"
            
        m_col4.metric("Dividend Yield", yield_str)
        
        # ==========================================
        # 5.5 Indexed Performance Comparison
        # ==========================================
        st.subheader("Relative Performance vs Benchmark")
        b_col1, b_col2, b_col3 = st.columns([1, 1, 2])
        with b_col1:
            benchmark_symbol = st.text_input("Benchmark Ticker", value="SPY").upper()
        with b_col2:
            timeframe = st.selectbox("Timeframe", options=["1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd"], index=3)
            
        if benchmark_symbol:
            with st.spinner(f"Compiling comparative price action against {benchmark_symbol}..."):
                perf_df = get_indexed_performance(ticker_symbol, benchmark_symbol, timeframe)
                if not perf_df.empty:
                    st.line_chart(perf_df, y_label="Cumulative Return (%)", use_container_width=True)
                else:
                    st.warning(f"Could not align historical data for {ticker_symbol} and {benchmark_symbol}.")

        # ==========================================
        # 6. Core Analytical Notebook Layout 
        # ==========================================
        st.subheader("Relative Valuation Multiples")
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

        st.subheader("Accounting Statements")
        st.write("Select and view all available quarterly statements below (Sourced via SEC EDGAR):")
        
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
