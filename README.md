# Equity Research Terminal

A lightweight, institutional-grade equity research dashboard built with Python and Streamlit. This tool ingests real-time market data and historical financials via `yfinance` and formats them into a clean, terminal-style interface for top-down and bottom-up company analysis.

## Features
* **Executive Summary Grid:** Real-time extraction of Market Cap, Enterprise Value, P/E ratios, and Dividend Yields.
* **Valuation & Efficiency Frameworks:** Clean data tables tracking margins, ROE, ROA, and liquidity metrics.
* **Accounting-Grade Financial Statements:** * Strict accounting formatting (e.g., `(1,500)` for negatives, `—` for absolute zeros).
  * Period-over-period percentage changes with text-based delta arrows (`↑`/`↓`).
  * Dynamic row-wise heatmaps to visually track metric performance over time.
  * Conditional CSS injection for rapid trend identification.

## Installation

1. Clone this repository:
   ```bash
   git clone [https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git](https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git)
   cd YOUR_REPO_NAME
