import json
import pandas as pd
import numpy as np

def run_backtest():
    print("日経225（^N225）過去5年分のデータをローカルJSONから読み込み中...")
    try:
        with open("n225.json", "r") as f:
            data = json.load(f)
            
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        
        df = pd.DataFrame({
            'Open': quote['open'],
            'High': quote['high'],
            'Low': quote['low'],
            'Close': quote['close'],
            'Volume': quote['volume']
        }, index=pd.to_datetime(timestamps, unit='s'))
        
        df = df.dropna()
        if len(df) == 0:
            print("データの取得に失敗しました。")
            return

        # 移動平均線の計算（相場式：5日、20日、60日）
        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['60MA'] = df['Close'].rolling(window=60).mean()
        df['5MA_prev'] = df['5MA'].shift(1)

        # 陽線・陰線の判定
        df['Is_Yang'] = df['Close'] > df['Open']
        df['Is_Yin'] = df['Close'] < df['Open']

        # 相場式シグナル（簡易版）
        df['Buy_Signal'] = df['Is_Yang'] & (df['Close'] > df['5MA']) & (df['5MA'] > df['5MA_prev'])
        df['Sell_Signal'] = df['Is_Yin'] & (df['Close'] < df['5MA']) & (df['5MA'] < df['5MA_prev'])

        position = 0 # 1: 買い, -1: 空売り, 0: ノーポジ
        entry_price = 0
        trades = []

        for i in range(1, len(df)):
            current = df.iloc[i]
            
            # 手仕舞い判定
            if position == 1:
                if current['Close'] < current['5MA'] or current['Sell_Signal']:
                    pnl_pct = (current['Close'] - entry_price) / entry_price
                    trades.append(('Long', entry_price, current['Close'], pnl_pct))
                    position = 0
            elif position == -1:
                if current['Close'] > current['5MA'] or current['Buy_Signal']:
                    pnl_pct = (entry_price - current['Close']) / entry_price
                    trades.append(('Short', entry_price, current['Close'], pnl_pct))
                    position = 0

            # エントリー判定
            if position == 0:
                if current['Buy_Signal']:
                    position = 1
                    entry_price = current['Close']
                elif current['Sell_Signal']:
                    position = -1
                    entry_price = current['Close']

        # 結果集計
        if len(trades) > 0:
            win_trades = [t for t in trades if t[3] > 0]
            win_rate = len(win_trades) / len(trades) * 100
            compounded_return = np.prod([1 + t[3] for t in trades]) - 1
            
            long_trades = [t for t in trades if t[0] == 'Long']
            short_trades = [t for t in trades if t[0] == 'Short']

            print("\n=== 相場式トレード（簡易版）バックテスト結果 ===")
            print(f"対象銘柄: 日経225 (^N225) / 期間: 過去5年間")
            print(f"総トレード数: {len(trades)} 回 (買い: {len(long_trades)} 回, 空売り: {len(short_trades)} 回)")
            print(f"勝率: {win_rate:.2f}%")
            print(f"累積リターン（単利合計）: {sum([t[3] for t in trades]) * 100:.2f}%")
            print(f"累積リターン（複利）: {compounded_return * 100:.2f}%")
            print("==============================================")
            print("※シグナルロジック（簡易版）:")
            print("- 買い(下半身): 陽線 ＆ 終値が5日線上 ＆ 5日線が上向き")
            print("- 売り(逆下半身): 陰線 ＆ 終値が5日線下 ＆ 5日線が下向き")
            print("- 決済: 終値が5日線を逆側に割る、または逆シグナル点灯")
        else:
            print("条件に合致するトレードが発生しませんでした。")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    run_backtest()
