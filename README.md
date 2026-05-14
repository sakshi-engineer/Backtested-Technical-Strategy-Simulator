Backtest Pro (Candlestick Backtesting Web App)

A full-stack web application to 📊 backtest technical trading strategies on historical market data with interactive candlestick charts, strategy overlays, trade generation, and a simple learning + sentiment module.

✨ Features

🔹 Backtesting
• Fetch historical OHLCV candles (Yahoo Finance)
• Strategies:
• EMA Crossover (short/long EMA)
• Supertrend (ATR period + multiplier)
• BUY/SELL signal markers on the chart
• Trades table built from signals
• Summary stats: total trades, win rate, compounded net return

🔹 Symbol Search
• Company-name search suggestions using Yahoo Finance search
• Auto-fills the ticker symbol from suggestions

🔹 Sentiment (News Headlines)
• Fetches Google News RSS headlines for a query
• VADER-based sentiment counts (positive/neutral/negative)
• Clickable headline links (when available)

🔹 Authentication (Local)
• Register / login flow
• SQLite-backed persistent user storage (users.db)

⚙️ Tech Stack

🔹 Backend
• Python, Flask
• yfinance, requests, pandas
• vaderSentiment for headline sentiment
• SQLite (sqlite3) for auth data

🔹 Frontend
• React + TypeScript
• Vite
• Tailwind CSS
• lightweight-charts for candlestick charting
• axios for API calls
• react-router-dom for routing

📁 Project Structure

candlestick-chart-app/
├── app.py
├── requirements.txt
├── users.db
├── templates/
├── static/
└── frontend/
├── package.json
├── vite.config.ts
└── src/
├── pages/
├── components/
└── lib/

🚀 Getting Started (Local Setup)

🔹 Backend setup (Flask)

From the project root:

python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py

Backend runs on:
http://127.0.0.1:8000

🔹 Frontend setup (React/Vite)

In a new terminal:

cd frontend
npm install
npm run dev

Frontend runs on:
http://localhost:5173

Note: frontend/vite.config.ts proxies /api/* to the backend on port 8000

🧭 Usage

1. Open the frontend at http://localhost:5173
2. Register a user account
3. Log in and navigate to Backtesting
4. Type a company name, pick a suggestion, and run a backtest
5. Switch strategies (EMA / Supertrend) and adjust parameters
6. Visit Sentiment to view news sentiment + headline links

🔗 API Endpoints (Backend)

• GET /api/test
• GET /api/test-auth
• POST /api/auth/register
• POST /api/auth/login
• POST /api/auth/logout
• GET /api/search_symbol?q=<query>
• GET /api/candles?symbol=<SYMBOL>&interval=<INTERVAL>&strategy=ema&ema_short=<N>&ema_long=<N>
• GET /api/candles?symbol=<SYMBOL>&interval=<INTERVAL>&strategy=supertrend&st_period=<N>&st_multiplier=<M>
• GET /api/sentiment_news?q=<query>

⚠️ Common Issues

🔹 npm error ENOENT ... package.json
You ran npm commands in the project root. Run them inside frontend/:

cd frontend
npm run dev

🔹 No data found from /api/candles
• Verify the symbol is valid (e.g., AAPL, TCS.NS, RELIANCE.NS)
• Try a different interval (e.g., 1d)
• Intraday intervals may only provide up to ~60 days of data

📌 Disclaimer

This project is for educational and research purposes only. It does not provide financial advice.
