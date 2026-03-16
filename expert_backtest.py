import json
import pandas as pd
import numpy as np

def run_expert_backtest():
    print("日経225（^N225）過去5年分のデータで【相場式・完全再現チャレンジ版】を実行中...")
    try:
        with open("aiba-backtest/n225.json", "r") as f:
            data = json.load(f)
            
        result = data['chart']['result'][0]
        timestamps = result['timestamp']
        quote = result['indicators']['quote'][0]
        
        df = pd.DataFrame({
            'Open': quote['open'],
            'High': quote['high'],
            'Low': quote['low'],
            'Close': quote['close'],
        }, index=pd.to_datetime(timestamps, unit='s'))
        
        df = df.dropna()
        if len(df) == 0: return

        # 移動平均線（5, 20, 60, 100）
        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['60MA'] = df['Close'].rolling(window=60).mean()
        df['100MA'] = df['Close'].rolling(window=100).mean()
        df['5MA_prev'] = df['5MA'].shift(1)

        # ローソク足の形状
        df['Body'] = abs(df['Close'] - df['Open'])
        df['Range'] = df['High'] - df['Low']
        df['Is_Yang'] = df['Close'] > df['Open']
        df['Is_Yin'] = df['Close'] < df['Open']
        # コマ（実体が全体の30%未満の小さな足）
        df['Is_Koma'] = df['Body'] < (df['Range'] * 0.3)

        # 直近の高値・安値（過去20日間の最高値・最安値）
        df['Local_High'] = df['High'].rolling(20).max().shift(1)
        df['Local_Low'] = df['Low'].rolling(20).min().shift(1)

        # 節目（1000円単位、500円単位）からの距離（近ければ警戒）
        df['Dist_to_1000'] = df['Close'] % 1000
        df['Dist_to_1000'] = np.minimum(df['Dist_to_1000'], 1000 - df['Dist_to_1000'])
        df['Near_Milestone'] = df['Dist_to_1000'] <= 100  # 1000円の節目から±100円以内

        # 連続日数
        s_up = df['Close'] > df['Close'].shift(1)
        s_down = df['Close'] < df['Close'].shift(1)
        df['Up_Days'] = s_up.groupby((~s_up).cumsum()).cumsum()
        df['Down_Days'] = s_down.groupby((~s_down).cumsum()).cumsum()

        df = df.dropna()

        # 建玉管理
        initial_capital = 10_000_000
        capital = initial_capital
        long_qty = 0
        short_qty = 0
        avg_long_price = 0.0
        avg_short_price = 0.0
        trade_history = []

        def close_position(side, qty, price, reason=""):
            nonlocal long_qty, avg_long_price, short_qty, avg_short_price, capital
            if side == 'Long' and long_qty > 0:
                q = min(qty, long_qty)
                pnl = (price - avg_long_price) * q * 100
                capital += pnl
                long_qty -= q
                if long_qty == 0: avg_long_price = 0.0
                trade_history.append({'type': 'Close Long', 'pnl': pnl, 'reason': reason})
            elif side == 'Short' and short_qty > 0:
                q = min(qty, short_qty)
                pnl = (avg_short_price - price) * q * 100
                capital += pnl
                short_qty -= q
                if short_qty == 0: avg_short_price = 0.0
                trade_history.append({'type': 'Close Short', 'pnl': pnl, 'reason': reason})

        def open_position(side, qty, price):
            nonlocal long_qty, avg_long_price, short_qty, avg_short_price
            if side == 'Long':
                total = long_qty * avg_long_price + qty * price
                long_qty += qty
                avg_long_price = total / long_qty
            else:
                total = short_qty * avg_short_price + qty * price
                short_qty += qty
                avg_short_price = total / short_qty

        # ループ開始
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            price = curr['Close']

            # パンパカパン（完全な上昇/下落トレンド）
            panpakapan_up = (curr['5MA'] > curr['20MA'] > curr['60MA'] > curr['100MA'])
            panpakapan_down = (curr['5MA'] < curr['20MA'] < curr['60MA'] < curr['100MA'])

            # 基本シグナル
            shimohanshin = curr['Is_Yang'] and (curr['Close'] > curr['5MA']) and (curr['5MA'] > prev['5MA'])
            johanshin = curr['Is_Yin'] and (curr['Close'] < curr['5MA']) and (curr['5MA'] < prev['5MA'])

            # --- 手仕舞い・利益確定（警戒シグナル） ---
            warning_long = False
            warning_short = False

            # 警戒1：コマが出現（トレンド疲労）
            if curr['Is_Koma'] and curr['Up_Days'] >= 3: warning_long = True
            if curr['Is_Koma'] and curr['Down_Days'] >= 3: warning_short = True
            
            # 警戒2：節目（1000円単位）に到達
            if curr['Near_Milestone']:
                warning_long = True
                warning_short = True
                
            # 警戒3：前の高値・安値に並ぶ（ダブルトップ・ボトム警戒）
            if abs(curr['High'] - curr['Local_High']) / curr['High'] < 0.005: warning_long = True
            if abs(curr['Low'] - curr['Local_Low']) / curr['Low'] < 0.005: warning_short = True
            
            # 警戒4：7の法則
            if curr['Up_Days'] >= 7: warning_long = True
            if curr['Down_Days'] >= 7: warning_short = True

            # 警戒シグナルが出たら「半分手仕舞い」または「全決済」
            if long_qty > 0 and warning_long:
                if long_qty >= 2: close_position('Long', long_qty // 2, price, 'Warning: Half Close')
                else: close_position('Long', long_qty, price, 'Warning: Full Close')
                
            if short_qty > 0 and warning_short:
                if short_qty >= 2: close_position('Short', short_qty // 2, price, 'Warning: Half Close')
                else: close_position('Short', short_qty, price, 'Warning: Full Close')

            # --- トレンド崩壊での全決済とヘッジ ---
            if long_qty > 0:
                if curr['Close'] < curr['20MA']: # 20日線割れで全逃げ
                    close_position('Long', long_qty, price, 'Trend Broken (20MA)')
                elif curr['Close'] < curr['5MA'] and curr['Is_Yin']: # 5日線割れでヘッジ（2-2等）
                    diff = long_qty - short_qty
                    if diff > 0: open_position('Short', diff, price)

            if short_qty > 0:
                if curr['Close'] > curr['20MA']:
                    close_position('Short', short_qty, price, 'Trend Broken (20MA)')
                elif curr['Close'] > curr['5MA'] and curr['Is_Yang']:
                    diff = short_qty - long_qty
                    if diff > 0: open_position('Long', diff, price)

            # --- 新規エントリー＆追加（建玉操作） ---
            if long_qty == 0 and short_qty == 0:
                # ノーポジから
                if panpakapan_up and shimohanshin:
                    open_position('Long', 2, price)
                elif panpakapan_down and johanshin:
                    open_position('Short', 2, price)
            
            elif long_qty > 0 and short_qty > 0:
                # ヘッジ中（例: 2-2）
                if curr['Close'] > curr['5MA'] and curr['Is_Yang'] and curr['20MA'] > curr['60MA']:
                    close_position('Short', short_qty, price, 'Hedge Removed (Up)') # ヘッジ外し
                    open_position('Long', 1, price) # 追加
                elif curr['Close'] < curr['5MA'] and curr['Is_Yin'] and curr['20MA'] < curr['60MA']:
                    close_position('Long', long_qty, price, 'Hedge Removed (Down)')
                    open_position('Short', 1, price)

        # 最終日は全決済
        final = df.iloc[-1]['Close']
        if long_qty > 0: close_position('Long', long_qty, final, 'End')
        if short_qty > 0: close_position('Short', short_qty, final, 'End')

        total_pnl = sum([t['pnl'] for t in trade_history])
        win_trades = [t for t in trade_history if t['pnl'] > 0]
        
        print("\n=== 相場式トレード（完全再現チャレンジ版）バックテスト結果 ===")
        print(f"対象: 日経225 (^N225) / 過去5年間 / 取引単位: 日経225ミニ換算(100倍)")
        print(f"初期資金: 10,000,000 円")
        print(f"最終資金: {capital:,.0f} 円 (純利益: {total_pnl:,.0f} 円)")
        print(f"総決済回数: {len(trade_history)} 回")
        if len(trade_history) > 0:
            print(f"勝率: {len(win_trades) / len(trade_history) * 100:.2f}%")
            gross_profit = sum([t['pnl'] for t in trade_history if t['pnl'] > 0])
            gross_loss = abs(sum([t['pnl'] for t in trade_history if t['pnl'] < 0]))
            pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            print(f"プロフィットファクター: {pf:.2f}")
        print("==============================================")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    run_expert_backtest()
