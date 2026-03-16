import json
import pandas as pd
import numpy as np
import warnings
import os
import subprocess

warnings.filterwarnings('ignore')

def check_daily_signal():
    try:
        # curlでYahoo Finance APIから直近100日分データを取得
        subprocess.run(['curl', '-H', 'User-Agent: Mozilla/5.0', '-s', 'https://query2.finance.yahoo.com/v8/finance/chart/^N225?interval=1d&range=200d', '-o', 'aiba-backtest/latest_n225.json'])
        
        with open("aiba-backtest/latest_n225.json", "r") as f:
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
            print("データ取得失敗")
            return
            
        df['5MA'] = df['Close'].rolling(window=5).mean()
        df['20MA'] = df['Close'].rolling(window=20).mean()
        df['60MA'] = df['Close'].rolling(window=60).mean()
        df['100MA'] = df['Close'].rolling(window=100).mean()
        
        df['Body'] = abs(df['Close'] - df['Open'])
        df['Range'] = df['High'] - df['Low']
        df['Is_Yang'] = df['Close'] > df['Open']
        df['Is_Yin'] = df['Close'] < df['Open']
        
        # ゼロ除算回避のため0.001を足す
        df['Is_Koma'] = df['Body'] < ((df['Range'] + 0.001) * 0.3)
        
        df = df.dropna()
        
        curr = df.iloc[-1]
        prev = df.iloc[-2]
        date_str = df.index[-1].strftime('%Y-%m-%d')
        
        # パンパカパン
        panpakapan_up = (curr['5MA'] > curr['20MA'] > curr['60MA'] > curr['100MA'])
        panpakapan_down = (curr['5MA'] < curr['20MA'] < curr['60MA'] < curr['100MA'])
        
        # 下半身・逆下半身
        shimohanshin = curr['Is_Yang'] and (curr['Close'] > curr['5MA']) and (curr['5MA'] > prev['5MA'])
        johanshin = curr['Is_Yin'] and (curr['Close'] < curr['5MA']) and (curr['5MA'] < prev['5MA'])
        
        # 物別れ（押し目買いシグナル）: 5日線が20日線に接近後、上を向く
        monowakare_up = (df.iloc[-3]['5MA'] > prev['5MA']) and (curr['5MA'] > prev['5MA']) and (curr['5MA'] > curr['20MA'])

        signal_msg = f"[{date_str} 日経225 相場式シグナル]\n"
        has_signal = False
        
        if panpakapan_up and shimohanshin:
            signal_msg += "🟢 【買いシグナル】完全パンパカパン状態での「下半身」が発生しました！\n"
            has_signal = True
        if panpakapan_down and johanshin:
            signal_msg += "🔴 【売りシグナル】逆パンパカパン状態での「逆下半身」が発生しました！\n"
            has_signal = True
        if monowakare_up and curr['Is_Yang']:
            signal_msg += "⭐ 【物別れ（買い）】20日線の上で5日線が反発（物別れ）しました。勝率の高い押し目買いチャンスです！\n"
            has_signal = True
        if curr['Is_Koma']:
            signal_msg += "⚠️ 【警戒】コマ（迷い線）が出現。トレンド転換や一旦の手仕舞いを検討してください。\n"
            has_signal = True
            
        if not has_signal:
            signal_msg += "本日は明確なエントリーシグナル（下半身/逆下半身/物別れ）はありませんでした。"
            
        print(signal_msg)
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")

if __name__ == "__main__":
    check_daily_signal()
