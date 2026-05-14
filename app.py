from flask import Flask, jsonify, request, render_template
from flask import g
from flask_cors import CORS
import yfinance as yf
import requests
import pandas as pd
import json
import os
import sqlite3
from datetime import datetime, timedelta
import urllib.parse
import xml.etree.ElementTree as ET

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Simple in-memory user storage for demo (replace with database in production)
users_db = {}

def _db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')


def _get_db():
    db = getattr(g, '_db', None)
    if db is None:
        db = sqlite3.connect(_db_path())
        db.row_factory = sqlite3.Row
        g._db = db
    return db


def _init_db():
    db = sqlite3.connect(_db_path())
    try:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                email TEXT PRIMARY KEY,
                fullname TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
            """
        )
        db.commit()
    finally:
        db.close()


_init_db()


@app.teardown_appcontext
def _close_db(exception):
    db = getattr(g, '_db', None)
    if db is not None:
        db.close()


def _fetch_from_yahoo_chart_api(symbol: str, interval: str, range_str: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        'interval': interval,
        'range': range_str,
        'includePrePost': 'false',
        'events': 'div,splits',
    }
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Accept': 'application/json,text/plain,*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    chart = (payload or {}).get('chart') or {}
    if chart.get('error'):
        raise RuntimeError(str(chart.get('error')))
    result = (chart.get('result') or [])
    if not result:
        return None
    result0 = result[0] or {}

    timestamps = result0.get('timestamp') or []
    indicators = (result0.get('indicators') or {})
    quotes = (indicators.get('quote') or [])
    if not timestamps or not quotes:
        return None
    quote0 = quotes[0] or {}

    idx = pd.to_datetime(timestamps, unit='s', utc=True).tz_convert(None)
    df = pd.DataFrame({
        'Open': quote0.get('open'),
        'High': quote0.get('high'),
        'Low': quote0.get('low'),
        'Close': quote0.get('close'),
        'Volume': quote0.get('volume'),
    }, index=idx)
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'], how='any')
    return df


def _compute_supertrend(df: pd.DataFrame, period: int, multiplier: float):
    high = df['High']
    low = df['Low']
    close = df['Close']

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = tr.ewm(alpha=1 / period, adjust=False).mean()

    hl2 = (high + low) / 2
    basic_ub = hl2 + multiplier * atr
    basic_lb = hl2 - multiplier * atr

    final_ub = basic_ub.copy()
    final_lb = basic_lb.copy()

    for i in range(1, len(df)):
        if pd.isna(final_ub.iat[i - 1]):
            continue
        if basic_ub.iat[i] < final_ub.iat[i - 1] or close.iat[i - 1] > final_ub.iat[i - 1]:
            final_ub.iat[i] = basic_ub.iat[i]
        else:
            final_ub.iat[i] = final_ub.iat[i - 1]

        if basic_lb.iat[i] > final_lb.iat[i - 1] or close.iat[i - 1] < final_lb.iat[i - 1]:
            final_lb.iat[i] = basic_lb.iat[i]
        else:
            final_lb.iat[i] = final_lb.iat[i - 1]

    in_uptrend = pd.Series(False, index=df.index)
    for i in range(1, len(df)):
        if close.iat[i] > final_ub.iat[i - 1]:
            in_uptrend.iat[i] = True
        elif close.iat[i] < final_lb.iat[i - 1]:
            in_uptrend.iat[i] = False
        else:
            in_uptrend.iat[i] = in_uptrend.iat[i - 1]
            if in_uptrend.iat[i] and final_lb.iat[i] < final_lb.iat[i - 1]:
                final_lb.iat[i] = final_lb.iat[i - 1]
            if (not in_uptrend.iat[i]) and final_ub.iat[i] > final_ub.iat[i - 1]:
                final_ub.iat[i] = final_ub.iat[i - 1]

    supertrend = pd.Series(index=df.index, dtype='float64')
    supertrend[in_uptrend] = final_lb[in_uptrend]
    supertrend[~in_uptrend] = final_ub[~in_uptrend]
    return supertrend, in_uptrend

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/test-auth', methods=['GET'])
def test_auth():
    db = _get_db()
    row = db.execute('SELECT COUNT(*) AS c FROM users').fetchone()
    return jsonify({'status': 'auth endpoints ready', 'users_count': int(row['c'] if row else 0)}), 200

@app.route('/api/auth/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        print('[DEBUG] Register request received', flush=True)
        print(f'[DEBUG] Content-Type: {request.content_type}', flush=True)
        print(f'[DEBUG] Raw data: {request.data}', flush=True)
        
        data = request.get_json(force=True, silent=True)
        print(f'[DEBUG] Parsed JSON: {data}', flush=True)
        
        if data is None:
            print('[ERROR] No JSON data received', flush=True)
            return jsonify({'error': 'No JSON data received'}), 400
        
        fullname = (data.get('fullname') or '').strip()
        email = (data.get('email') or '').strip()
        password = (data.get('password') or '').strip()
        
        print(f'[DEBUG] fullname: "{fullname}", email: "{email}", password_len: {len(password)}', flush=True)
        
        if not email or not password or not fullname:
            print('[ERROR] Missing required fields', flush=True)
            return jsonify({'error': 'Missing required fields'}), 400

        db = _get_db()
        existing = db.execute('SELECT email FROM users WHERE email = ?', (email,)).fetchone()
        if existing is not None:
            print(f'[ERROR] Email {email} already registered', flush=True)
            return jsonify({'error': 'Email already registered'}), 409

        db.execute(
            'INSERT INTO users (email, fullname, password_hash, registered_at) VALUES (?, ?, ?, ?)',
            (email, fullname, generate_password_hash(password), datetime.now().isoformat()),
        )
        db.commit()
        
        print(f'[INFO] User {email} registered successfully', flush=True)
        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'user': {
                'email': email,
                'fullname': fullname
            }
        }), 201
    except Exception as e:
        print(f'[ERROR] Registration error: {e}', flush=True)
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        email = (data.get('email') or '').strip()
        password = (data.get('password') or '').strip()
        
        if not email or not password:
            return jsonify({'error': 'Missing email or password'}), 400

        db = _get_db()
        user = db.execute('SELECT email, fullname, password_hash FROM users WHERE email = ?', (email,)).fetchone()
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': {
                'email': email,
                'fullname': user['fullname']
            }
        }), 200
    except Exception as e:
        print(f'[ERROR] Login error: {e}')
        return jsonify({'error': 'Login failed'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    return jsonify({
        'success': True,
        'message': 'Logged out successfully'
    }), 200

@app.route('/api/candles', methods=['GET'])
@app.route('/api/candles/', methods=['GET'])
def get_candles():
    print('HIT /api/candles', flush=True)
    symbol = request.args.get('symbol', default='AAPL', type=str)
    interval = request.args.get('interval', default='1d', type=str)
    strategy = request.args.get('strategy', default='ema', type=str)
    print(f"[INFO] /api/candles called with symbol={symbol}, interval={interval}")
    try:
        symbol = (symbol or '').strip()
        if not symbol:
            print("[ERROR] Missing symbol")
            return jsonify({'error': 'Missing required query parameter: symbol'}), 400
        strategy = (strategy or '').strip().lower()
        if strategy not in ['ema', 'supertrend']:
            return jsonify({'error': 'Invalid strategy. Valid strategies: ema, supertrend'}), 400
        valid_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '1wk', '1mo']
        if interval not in valid_intervals:
            valids = ', '.join(valid_intervals)
            print(f"[ERROR] Invalid interval: {interval}. Valid intervals: {valids}")
            return jsonify({'error': f'Invalid interval. Valid intervals: {valids}'}), 400
        intraday_intervals = ['1m', '2m', '5m', '15m', '30m', '60m', '90m']
        if interval in intraday_intervals:
            period = '60d'
        else:
            period = 'max'
        # Yahoo's chart endpoint can silently aggregate when range=max and interval=1d.
        # Use a range that preserves daily granularity.
        chart_api_range = period
        if period == 'max':
            if interval == '1d':
                chart_api_range = '5y'
            elif interval == '1wk':
                chart_api_range = '20y'
            elif interval == '1mo':
                chart_api_range = 'max'
        print(f"[DEBUG] Downloading data for {symbol} with period={period} and interval={interval}")
        data = None
        try:
            data = yf.download(tickers=symbol, period=period, interval=interval)
        except Exception as yf_exc:
            print(f"[WARN] yfinance download failed for {symbol} at interval {interval}: {yf_exc}")
        print(f"[DEBUG] Data shape: {getattr(data, 'shape', None)}")
        if data is None or data.empty:
            print(f"[WARN] Trying yfinance Ticker().history fallback for symbol={symbol}, interval={interval}.")
            try:
                data = yf.Ticker(symbol).history(period=period, interval=interval)
                print(f"[DEBUG] Fallback history() shape: {getattr(data, 'shape', None)}")
            except Exception as yf_exc:
                print(f"[WARN] yfinance history() failed for {symbol} at interval {interval}: {yf_exc}")

        if data is None or data.empty:
            print(f"[WARN] Trying Yahoo chart API fallback for symbol={symbol}, interval={interval}, range={chart_api_range}.")
            try:
                data = _fetch_from_yahoo_chart_api(symbol=symbol, interval=interval, range_str=chart_api_range)
                print(f"[DEBUG] Yahoo chart API shape: {getattr(data, 'shape', None)}")
            except Exception as api_exc:
                print(f"[ERROR] Yahoo chart API failed for {symbol} at interval {interval}: {api_exc}")

        if data is None or data.empty:
            print(f"[ERROR] No data found for symbol={symbol}, interval={interval}")
            return jsonify({'error': f'No data found for symbol "{symbol}" or interval "{interval}".\n\n- Make sure the symbol is valid (e.g., TCS.NS, RELIANCE.NS, AAPL).\n- For intraday intervals, Yahoo only provides up to 60 days of data and not all symbols are supported.'}), 404
        if hasattr(data.columns, 'levels') and len(data.columns.levels) == 2:
            ticker_level = symbol.upper()
            try:
                data = data.xs(ticker_level, axis=1, level=1)
            except Exception as e:
                print(f"[ERROR] Could not select columns for ticker {ticker_level}: {e}")
                return jsonify({'error': f'Data for symbol "{symbol}" is missing or malformed.'}), 500
        required_cols = {'Open', 'High', 'Low', 'Close', 'Volume'}
        if not required_cols.issubset(set(data.columns)):
            print(f"[ERROR] Missing columns in data: {set(data.columns)}")
            return jsonify({'error': f'Data for symbol "{symbol}" is missing required columns. Try a different symbol or interval.'}), 500
        df = data.copy()
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close'], how='any')

        signals = []
        supertrend_series = None

        if strategy == 'ema':
            ema1 = int(request.args.get('ema_short', 20))
            ema2 = int(request.args.get('ema_long', 50))
            smaller_length = min(ema1, ema2)
            bigger_length = max(ema1, ema2)
            df['EMA_smaller'] = df['Close'].ewm(span=smaller_length, adjust=False).mean()
            df['EMA_bigger'] = df['Close'].ewm(span=bigger_length, adjust=False).mean()
            df['Signal'] = 0
            df.loc[(df['EMA_smaller'] > df['EMA_bigger']) & (df['EMA_smaller'].shift() <= df['EMA_bigger'].shift()), 'Signal'] = 1
            df.loc[(df['EMA_smaller'] < df['EMA_bigger']) & (df['EMA_smaller'].shift() >= df['EMA_bigger'].shift()), 'Signal'] = -1
        else:
            st_period = int(request.args.get('st_period', 7))
            st_multiplier = float(request.args.get('st_multiplier', 3))
            supertrend, in_uptrend = _compute_supertrend(df=df, period=st_period, multiplier=st_multiplier)
            df['Supertrend'] = supertrend
            df['InUptrend'] = in_uptrend
            df['Signal'] = 0
            df.loc[(df['InUptrend'] == True) & (df['InUptrend'].shift(1) == False), 'Signal'] = 1
            df.loc[(df['InUptrend'] == False) & (df['InUptrend'].shift(1) == True), 'Signal'] = -1
            supertrend_series = [
                {
                    'time': int(i.timestamp()),
                    'value': (None if pd.isna(v) else float(v)),
                    'trend': ('up' if bool(df.at[i, 'InUptrend']) else 'down'),
                }
                for i, v in df['Supertrend'].items()
            ]
        candles = []
        for idx, row in df.iterrows():
            try:
                t = int(idx.timestamp())
                candles.append({
                    'time': t,
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': float(row['Volume'])
                })
                if row['Signal'] == 1:
                    signals.append({'time': t, 'signal': 'buy', 'price': float(row['Close'])})
                elif row['Signal'] == -1:
                    signals.append({'time': t, 'signal': 'sell', 'price': float(row['Close'])})
            except Exception as row_err:
                print(f"[ERROR] Malformed row at {idx}: {row_err}")
        if not candles:
            print(f"[ERROR] No valid candle data found for symbol={symbol} and interval={interval}")
            return jsonify({'error': f'No valid candle data found for symbol "{symbol}" and interval "{interval}".'}), 404
        payload = {'candles': candles, 'signals': signals, 'strategy': strategy}
        if supertrend_series is not None:
            payload['supertrend'] = supertrend_series
        return jsonify(payload)
    except Exception as e:
        import traceback
        print('Exception in /api/candles:', e)
        traceback.print_exc()
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/test')
def test_api():
    return jsonify({'result': 'API test route works!'})

@app.route('/api/search_symbol')
def search_symbol():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'quotes': []})
    try:
        url = f'https://query2.finance.yahoo.com/v1/finance/search?q={query}&quotesCount=50&newsCount=0'
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=5, headers=headers)
        data = resp.json()
        # Yahoo returns quotes directly in the response
        quotes = data.get('quotes', [])
        return jsonify({'quotes': quotes})
    except Exception as e:
        print(f'[ERROR] Symbol search failed: {e}')
        return jsonify({'quotes': [], 'error': 'Failed to fetch suggestions'}), 500


@app.route('/api/sentiment_news')
def sentiment_news():
    query = (request.args.get('q') or 'Reliance Industries').strip()
    if not query:
        return jsonify({'error': 'Missing required query parameter: q'}), 400

    try:
        url = (
            'https://news.google.com/rss/search?'
            + urllib.parse.urlencode(
                {
                    'q': query,
                    'hl': 'en-IN',
                    'gl': 'IN',
                    'ceid': 'IN:en',
                }
            )
        )
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, timeout=10, headers=headers)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items: list[dict] = []
        headlines: list[str] = []
        for node in root.iter():
            tag = (node.tag or '').lower()
            if tag.endswith('item'):
                title = None
                link = None
                for child in list(node):
                    ctag = (child.tag or '').lower()
                    if ctag.endswith('title'):
                        title = (child.text or '').strip()
                    elif ctag.endswith('link'):
                        link = (child.text or '').strip()
                if title:
                    headlines.append(title)
                    items.append({'title': title, 'url': link})

        analyzer = SentimentIntensityAnalyzer()
        sentiment = {'positive': 0, 'neutral': 0, 'negative': 0}
        for line in headlines:
            score = analyzer.polarity_scores(line)
            compound = float(score.get('compound', 0.0))
            if compound >= 0.05:
                sentiment['positive'] += 1
            elif compound <= -0.05:
                sentiment['negative'] += 1
            else:
                sentiment['neutral'] += 1

        return jsonify(
            {
                'query': query,
                'total': len(headlines),
                'sentiment': sentiment,
                'headlines': headlines,
                'items': items,
            }
        )
    except ET.ParseError as e:
        print(f'[ERROR] RSS parse failed: {e}', flush=True)
        return jsonify({'error': 'Failed to parse RSS feed'}), 502
    except Exception as e:
        print(f'[ERROR] Sentiment news failed: {e}', flush=True)
        return jsonify({'error': 'Failed to fetch sentiment news'}), 502

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Not found', 'hint': 'This is a Flask 404, so Flask is running.'}), 404

@app.route('/api/test_yfinance')
def test_yfinance():
    """Test endpoint to debug yfinance on deployment platform."""
    try:
        print('[TEST] Testing yfinance for AAPL, 1d')
        data = None
        try:
            data = yf.download('AAPL', period='1mo', interval='1d')
            print(f'[TEST] yfinance returned shape: {getattr(data, "shape", None)}')
        except Exception as yf_exc:
            print(f'[TEST] yfinance download exception: {yf_exc}')
        if data is None or data.empty:
            try:
                data = _fetch_from_yahoo_chart_api(symbol='AAPL', interval='1d', range_str='1mo')
                print(f'[TEST] Yahoo chart API returned shape: {getattr(data, "shape", None)}')
            except Exception as api_exc:
                print(f'[TEST] Yahoo chart API exception: {api_exc}')
        if data is None:
            return jsonify({'shape': None, 'head': {}, 'error': 'No data returned'}), 502
        return jsonify({'shape': str(getattr(data, 'shape', None)), 'head': data.head(5).to_dict()}), 200
    except Exception as e:
        import traceback
        print('[TEST] yfinance exception:', e)
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

import os
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(debug=True, port=port, use_reloader=False)
