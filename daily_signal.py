import json
import pandas as pd
import numpy as np
import warnings
import subprocess
import os

warnings.filterwarnings('ignore')

def check_daily_signal():
    targets = [
        {'ticker': '^N225', 'name': '日経225'},
        {'ticker': '8306.T', 'name': '三菱UFJ'},
        {'ticker': '8035.T', 'name': '東京エレクトロン'},
        {'ticker': '7974.T', 'name': '任天堂'}
    ]
    
    final_msg = ""
    has_any_signal = False
    
    for target in targets:
        ticker = target['ticker']
        name = target['name']
        
        try:
            # ファイル名に使えない文字を置換
            safe_ticker = ticker.replace('^', '')
            json_path = f"aiba-backtest/latest_{safe_ticker}.json"
            
            subprocess.run([
                'curl', '-H', 'User-Agent: Mozilla/5.0', '-s', 
                f'https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=200d', 
                '-o', json_path
            ])
            
            with open(json_path, "r") as f:
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
                continue
                
            df['5MA'] = df['Close'].rolling(window=5).mean()
            df['20MA'] = df['Close'].rolling(window=20).mean()
            df['60MA'] = df['Close'].rolling(window=60).mean()
            df['100MA'] = df['Close'].rolling(window=100).mean()
            
            df['Body'] = abs(df['Close'] - df['Open'])
            df['Range'] = df['High'] - df['Low']
            df['Is_Yang'] = df['Close'] > df['Open']
            df['Is_Yin'] = df['Close'] < df['Open']
            df['Is_Koma'] = df['Body'] < ((df['Range'] + 0.001) * 0.3)
            
            df = df.dropna()
            
            curr = df.iloc[-1]
            prev = df.iloc[-2]
            date_str = df.index[-1].strftime('%Y-%m-%d')
            
            panpakapan_up = (curr['5MA'] > curr['20MA'] > curr['60MA'] > curr['100MA'])
            panpakapan_down = (curr['5MA'] < curr['20MA'] < curr['60MA'] < curr['100MA'])
            
            shimohanshin = curr['Is_Yang'] and (curr['Close'] > curr['5MA']) and (curr['5MA'] > prev['5MA'])
            johanshin = curr['Is_Yin'] and (curr['Close'] < curr['5MA']) and (curr['5MA'] < prev['5MA'])
            
            monowakare_up = (df.iloc[-3]['5MA'] > prev['5MA']) and (curr['5MA'] > prev['5MA']) and (curr['5MA'] > curr['20MA'])

            signal_msg = f"■ {name} ({date_str})\n"
            local_signal = False
            
            if panpakapan_up and shimohanshin:
                signal_msg += " 🟢 【買いシグナル】完全パンパカパン状態での「下半身」が発生！\n"
                local_signal = True
            if panpakapan_down and johanshin:
                signal_msg += " 🔴 【売りシグナル】逆パンパカパン状態での「逆下半身」が発生！\n"
                local_signal = True
            if monowakare_up and curr['Is_Yang']:
                signal_msg += " ⭐ 【物別れ(買い)】押し目買いチャンス！\n"
                local_signal = True
            if curr['Is_Koma']:
                signal_msg += " ⚠️ 【警戒】コマ(迷い線)出現。手仕舞いを検討。\n"
                local_signal = True
                
            if local_signal:
                final_msg += signal_msg + "\n"
                has_any_signal = True
                
        except Exception as e:
            # エラー時はスキップして次の銘柄へ
            pass
            
    if has_any_signal:
        print("[相場式シグナル監視レポート]\n\n" + final_msg.strip())
    else:
        print("本日は明確なエントリーシグナル（下半身/逆下半身/物別れ）はありませんでした。")

if __name__ == "__main__":
    check_daily_signal()
