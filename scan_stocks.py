import json
import pandas as pd
import numpy as np
import urllib.request
import time
import warnings

warnings.filterwarnings('ignore')

tickers = {
    '7203.T': 'トヨタ自動車',
    '6758.T': 'ソニーG',
    '8306.T': '三菱UFJ',
    '9983.T': 'ファーストリテイリング',
    '6861.T': 'キーエンス',
    '8035.T': '東京エレクトロン',
    '7974.T': '任天堂',
    '8001.T': '伊藤忠商事',
    '4063.T': '信越化学',
    '9432.T': 'NTT',
    '6501.T': '日立製作所',
    '6981.T': '村田製作所',
    '4568.T': '第一三共',
    '6367.T': 'ダイキン工業',
    '6098.T': 'リクルートHD'
}

def fetch_data(ticker):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=10y"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        df = pd.DataFrame({
            'Open': quote['open'],
            'High': quote['high'],
            'Low': quote['low'],
            'Close': quote['close'],
        }, index=pd.to_datetime(timestamps, unit='s'))
        return df.dropna()
    except Exception as e:
        return None

def test_ticker(ticker, name):
    df = fetch_data(ticker)
    if df is None or len(df) < 500: return None

    # 移動平均線
    df['5MA'] = df['Close'].rolling(window=5).mean()
    df['20MA'] = df['Close'].rolling(window=20).mean()
    df['60MA'] = df['Close'].rolling(window=60).mean()
    df['100MA'] = df['Close'].rolling(window=100).mean()
    df['300MA'] = df['Close'].rolling(window=300).mean()
    
    df['5MA_prev'] = df['5MA'].shift(1)
    df['5MA_prev2'] = df['5MA'].shift(2)
    df['20MA_prev'] = df['20MA'].shift(1)

    df['Body'] = abs(df['Close'] - df['Open'])
    df['Range'] = df['High'] - df['Low']
    df['Is_Yang'] = df['Close'] > df['Open']
    df['Is_Yin'] = df['Close'] < df['Open']
    df['Is_Koma'] = df['Body'] < ((df['Range'] + 0.001) * 0.3)

    df['Local_High'] = df['High'].rolling(20).max().shift(1)
    df['Local_Low'] = df['Low'].rolling(20).min().shift(1)

    # 節目（株価水準に合わせて動的に変更。例: 1000円以上なら500円節目、1000円未満なら100円節目）
    avg_price = df['Close'].mean()
    milestone = 1000 if avg_price > 2000 else (500 if avg_price > 500 else 100)
    warning_margin = milestone * 0.1
    
    df['Dist_to_Milestone'] = df['Close'] % milestone
    df['Dist_to_Milestone'] = np.minimum(df['Dist_to_Milestone'], milestone - df['Dist_to_Milestone'])
    df['Near_Milestone'] = df['Dist_to_Milestone'] <= warning_margin

    s_up = df['Close'] > df['Close'].shift(1)
    s_down = df['Close'] < df['Close'].shift(1)
    df['Up_Days'] = s_up.groupby((~s_up).cumsum()).cumsum()
    df['Down_Days'] = s_down.groupby((~s_down).cumsum()).cumsum()

    df = df.dropna()

    df['Monowakare_Buy'] = (df['5MA_prev2'] > df['5MA_prev']) & (df['5MA'] > df['5MA_prev']) & (df['5MA'] > df['20MA']) & (df['20MA'] > df['20MA_prev']) & df['Is_Yang']
    df['Monowakare_Sell'] = (df['5MA_prev2'] < df['5MA_prev']) & (df['5MA'] < df['5MA_prev']) & (df['5MA'] < df['20MA']) & (df['20MA'] < df['20MA_prev']) & df['Is_Yin']
    
    df['Macro_Up'] = df['Close'] > df['300MA']
    df['Macro_Down'] = df['Close'] < df['300MA']

    capital = 10_000_000
    long_qty, short_qty = 0, 0
    avg_long, avg_short = 0.0, 0.0
    trade_history = []

    def close_pos(side, qty, price):
        nonlocal long_qty, avg_long, short_qty, avg_short, capital
        if side == 'Long' and long_qty > 0:
            q = min(qty, long_qty)
            pnl = (price - avg_long) * q * 100  # 1単元100株
            capital += pnl
            long_qty -= q
            if long_qty == 0: avg_long = 0.0
            trade_history.append({'pnl': pnl})
        elif side == 'Short' and short_qty > 0:
            q = min(qty, short_qty)
            pnl = (avg_short - price) * q * 100
            capital += pnl
            short_qty -= q
            if short_qty == 0: avg_short = 0.0
            trade_history.append({'pnl': pnl})

    def open_pos(side, qty, price):
        nonlocal long_qty, avg_long, short_qty, avg_short
        if side == 'Long':
            tot = long_qty * avg_long + qty * price
            long_qty += qty
            avg_long = tot / long_qty
        else:
            tot = short_qty * avg_short + qty * price
            short_qty += qty
            avg_short = tot / short_qty

    for i in range(1, len(df)):
        curr = df.iloc[i]
        prev = df.iloc[i-1]
        price = curr['Close']

        p_up = (curr['5MA'] > curr['20MA'] > curr['60MA'] > curr['100MA'])
        p_down = (curr['5MA'] < curr['20MA'] < curr['60MA'] < curr['100MA'])
        
        shimo = curr['Is_Yang'] and (curr['Close'] > curr['5MA']) and (curr['5MA'] > prev['5MA'])
        jyohan = curr['Is_Yin'] and (curr['Close'] < curr['5MA']) and (curr['5MA'] < prev['5MA'])

        warn_l, warn_s = False, False
        if curr['Is_Koma'] and curr['Up_Days'] >= 3: warn_l = True
        if curr['Is_Koma'] and curr['Down_Days'] >= 3: warn_s = True
        if curr['Near_Milestone']: warn_l = warn_s = True
        if abs(curr['High'] - curr['Local_High']) / curr['High'] < 0.005: warn_l = True
        if abs(curr['Low'] - curr['Local_Low']) / curr['Low'] < 0.005: warn_s = True
        if curr['Up_Days'] >= 7: warn_l = True
        if curr['Down_Days'] >= 7: warn_s = True

        if long_qty > 0 and warn_l:
            if long_qty >= 2: close_pos('Long', long_qty // 2, price)
            else: close_pos('Long', long_qty, price)
        if short_qty > 0 and warn_s:
            if short_qty >= 2: close_pos('Short', short_qty // 2, price)
            else: close_pos('Short', short_qty, price)

        if long_qty > 0:
            if curr['Close'] < curr['20MA']: close_pos('Long', long_qty, price)
            elif curr['Close'] < curr['5MA'] and curr['Is_Yin']: 
                diff = long_qty - short_qty
                if diff > 0: open_pos('Short', diff, price)

        if short_qty > 0:
            if curr['Close'] > curr['20MA']: close_pos('Short', short_qty, price)
            elif curr['Close'] > curr['5MA'] and curr['Is_Yang']:
                diff = short_qty - long_qty
                if diff > 0: open_pos('Long', diff, price)

        if long_qty == 0 and short_qty == 0:
            if ((p_up and shimo) or curr['Monowakare_Buy']) and curr['Macro_Up']: open_pos('Long', 2, price)
            elif ((p_down and jyohan) or curr['Monowakare_Sell']) and curr['Macro_Down']: open_pos('Short', 2, price)
            
        elif long_qty > 0 and short_qty > 0:
            if curr['Close'] > curr['5MA'] and curr['Is_Yang'] and curr['20MA'] > curr['60MA']:
                close_pos('Short', short_qty, price)
                open_pos('Long', 2 if curr['Monowakare_Buy'] else 1, price)
            elif curr['Close'] < curr['5MA'] and curr['Is_Yin'] and curr['20MA'] < curr['60MA']:
                close_pos('Long', long_qty, price)
                open_pos('Short', 2 if curr['Monowakare_Sell'] else 1, price)

    final = df.iloc[-1]['Close']
    if long_qty > 0: close_pos('Long', long_qty, final)
    if short_qty > 0: close_pos('Short', short_qty, final)

    total_pnl = sum([t['pnl'] for t in trade_history])
    win_trades = [t for t in trade_history if t['pnl'] > 0]
    
    if len(trade_history) > 0:
        win_rate = len(win_trades) / len(trade_history) * 100
        gross_profit = sum([t['pnl'] for t in trade_history if t['pnl'] > 0])
        gross_loss = abs(sum([t['pnl'] for t in trade_history if t['pnl'] < 0]))
        pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        return {'ticker': ticker, 'name': name, 'pnl': total_pnl, 'win_rate': win_rate, 'pf': pf, 'trades': len(trade_history)}
    return None

results = []
print("大型銘柄15社を対象に、過去10年間の相場式【究極版】バックテストを実行中...")
for t, n in tickers.items():
    res = test_ticker(t, n)
    if res: results.append(res)

results.sort(key=lambda x: x['pf'], reverse=True)

print("\n=== 相場式トレード 個別銘柄ランキング (PF順 / 過去10年) ===")
print(f"{'銘柄名':<15} | {'PF':<4} | {'勝率':<6} | {'純利益(円)':<10} | {'決済回数'}")
print("-" * 65)
for r in results:
    print(f"{r['name']:<15} | {r['pf']:.2f} | {r['win_rate']:>5.1f}% | {r['pnl']:>12,.0f} | {r['trades']:>4}")
