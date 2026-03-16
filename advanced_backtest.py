import json
import pandas as pd
import numpy as np

def run_advanced_backtest():
    print("日経225（^N225）過去5年分のデータをローカルJSONから読み込み中...")
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
        if len(df) == 0:
            print("データの取得に失敗しました。")
            return

        # 移動平均線の計算（相場式：5日、20日、60日）
        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['60MA'] = df['Close'].rolling(window=60).mean()
        df['5MA_prev'] = df['5MA'].shift(1)
        df['20MA_prev'] = df['20MA'].shift(1)

        # 陽線・陰線の判定
        df['Is_Yang'] = df['Close'] > df['Open']
        df['Is_Yin'] = df['Close'] < df['Open']

        # 連続上昇・下落日数（7の法則など用）
        # 終値が前日比で上昇なら1、下落なら0。これを連続している間カウント。
        s_up = df['Close'] > df['Close'].shift(1)
        s_down = df['Close'] < df['Close'].shift(1)
        df['Up_Days'] = s_up.groupby((~s_up).cumsum()).cumsum()
        df['Down_Days'] = s_down.groupby((~s_down).cumsum()).cumsum()

        df = df.dropna()

        # ポジション管理
        initial_capital = 10_000_000  # 初期資金1000万円
        capital = initial_capital
        
        long_qty = 0
        short_qty = 0
        avg_long_price = 0.0
        avg_short_price = 0.0
        
        trade_history = [] # 決済ごとの履歴

        def close_longs(qty, current_price):
            nonlocal long_qty, avg_long_price, capital
            if long_qty == 0 or qty <= 0: return
            qty_to_close = min(qty, long_qty)
            # 1枚あたり1000倍として計算（ミニなら100倍、ラージなら1000倍。ここでは簡略化して100倍=ミニ日経で計算）
            multiplier = 100
            pnl = (current_price - avg_long_price) * qty_to_close * multiplier
            capital += pnl
            long_qty -= qty_to_close
            if long_qty == 0: avg_long_price = 0.0
            trade_history.append({'type': 'Close Long', 'pnl': pnl})

        def close_shorts(qty, current_price):
            nonlocal short_qty, avg_short_price, capital
            if short_qty == 0 or qty <= 0: return
            qty_to_close = min(qty, short_qty)
            multiplier = 100
            pnl = (avg_short_price - current_price) * qty_to_close * multiplier
            capital += pnl
            short_qty -= qty_to_close
            if short_qty == 0: avg_short_price = 0.0
            trade_history.append({'type': 'Close Short', 'pnl': pnl})
            
        def open_longs(qty, current_price):
            nonlocal long_qty, avg_long_price
            if qty <= 0: return
            total_cost = long_qty * avg_long_price + qty * current_price
            long_qty += qty
            avg_long_price = total_cost / long_qty

        def open_shorts(qty, current_price):
            nonlocal short_qty, avg_short_price
            if qty <= 0: return
            total_cost = short_qty * avg_short_price + qty * current_price
            short_qty += qty
            avg_short_price = total_cost / short_qty

        # トレードループ
        for i in range(1, len(df)):
            curr = df.iloc[i]
            prev = df.iloc[i-1]
            price = curr['Close']

            # --- 環境認識（パンパカパン・逆パンパカパン） ---
            # 20日線が上向きかつ20日線＞60日線で上昇トレンド
            is_uptrend = (curr['20MA'] > curr['60MA']) and (curr['20MA'] > curr['20MA_prev'])
            is_downtrend = (curr['20MA'] < curr['60MA']) and (curr['20MA'] < curr['20MA_prev'])

            # --- シグナル ---
            shimohanshin = curr['Is_Yang'] and (curr['Close'] > curr['5MA']) and (curr['5MA'] > prev['5MA'])
            johanshin = curr['Is_Yin'] and (curr['Close'] < curr['5MA']) and (curr['5MA'] < prev['5MA'])

            # 1. 利益確定（7の法則）
            # 連続して7日上昇したら一旦手仕舞い
            if long_qty > 0 and curr['Up_Days'] >= 7:
                close_longs(long_qty, price)
                close_shorts(short_qty, price)
                continue
            # 連続して7日下落したら一旦手仕舞い
            if short_qty > 0 and curr['Down_Days'] >= 7:
                close_longs(long_qty, price)
                close_shorts(short_qty, price)
                continue

            # 2. ノーポジション（0-0）からのエントリー
            if long_qty == 0 and short_qty == 0:
                if is_uptrend and shimohanshin:
                    open_longs(2, price) # 2-0でエントリー
                elif is_downtrend and johanshin:
                    open_shorts(2, price) # 0-2でエントリー
                continue

            # 3. 建玉の操作（ヘッジと追加）
            if long_qty > 0 and short_qty == 0:
                # [2-0] の状態（買いのみ）
                if curr['Close'] < curr['20MA']:
                    # トレンド崩壊 -> 全決済
                    close_longs(long_qty, price)
                    if johanshin: open_shorts(2, price) # ドテン
                elif curr['Close'] < curr['5MA']:
                    # 5日線割れ（陰線） -> スクエアヘッジ [2-2]
                    if curr['Is_Yin']: open_shorts(long_qty, price)

            elif short_qty > 0 and long_qty == 0:
                # [0-2] の状態（売りのみ）
                if curr['Close'] > curr['20MA']:
                    # トレンド崩壊 -> 全決済
                    close_shorts(short_qty, price)
                    if shimohanshin: open_longs(2, price) # ドテン
                elif curr['Close'] > curr['5MA']:
                    # 5日線越え（陽線） -> スクエアヘッジ [2-2]
                    if curr['Is_Yang']: open_longs(short_qty, price)

            elif long_qty > 0 and short_qty > 0:
                # [2-2] の状態（両建てヘッジ中）
                if curr['Close'] > curr['5MA'] and curr['Is_Yang']:
                    # 再び5日線上に浮上 -> 空売りヘッジを外し、買い玉追加 [3-0]
                    close_shorts(short_qty, price)
                    open_longs(1, price)
                elif curr['Close'] < curr['5MA'] and curr['Is_Yin']:
                    # 5日線下に沈む -> 買いヘッジを外し、売り玉追加 [0-3]
                    close_longs(long_qty, price)
                    open_shorts(1, price)

        # 最終日は全決済
        final_price = df.iloc[-1]['Close']
        if long_qty > 0: close_longs(long_qty, final_price)
        if short_qty > 0: close_shorts(short_qty, final_price)

        # 結果集計
        total_pnl = sum([t['pnl'] for t in trade_history])
        win_trades = [t for t in trade_history if t['pnl'] > 0]
        
        print("\n=== 相場式トレード（建玉操作・環境認識 追加版）バックテスト結果 ===")
        print(f"対象銘柄: 日経225 (^N225) / 期間: 過去5年間 / 取引単位: 日経225ミニ換算(1枚100倍)")
        print(f"初期資金: 10,000,000 円")
        print(f"最終資金: {capital:,.0f} 円 (純利益: {total_pnl:,.0f} 円)")
        print(f"総決済回数: {len(trade_history)} 回")
        if len(trade_history) > 0:
            print(f"勝率: {len(win_trades) / len(trade_history) * 100:.2f}%")
            # プロフィットファクターの計算
            gross_profit = sum([t['pnl'] for t in trade_history if t['pnl'] > 0])
            gross_loss = abs(sum([t['pnl'] for t in trade_history if t['pnl'] < 0]))
            pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
            print(f"プロフィットファクター: {pf:.2f}")
        print("==============================================")
        print("※追加した裁量ロジック:")
        print("1. 環境認識: 20日線＞60日線（かつ20日線上向き）の時のみ新規買い、逆は空売りのみ")
        print("2. ヘッジ(建玉操作): 5日線を割った(越えた)際に即損切りせず、同数の逆ポジションを入れる(2-2のスクエア)")
        print("3. 建玉追加: ヘッジ後に元のトレンド方向に戻ったら、ヘッジを外し追加玉を入れる(3-0/0-3)")
        print("4. 利確(7の法則): 7日連続で上昇または下落した場合は手仕舞い")

    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    run_advanced_backtest()
