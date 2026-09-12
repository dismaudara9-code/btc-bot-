
# BTCUSDT 5-Minute AI Entry Bot

This is a simple live-signal app for Bybit BTCUSDT perpetual futures.

## What it does
- Reads live 5-minute BTCUSDT candles from Bybit public API
- Uses EMA 9/21, RSI 14, MACD, ATR and volume
- Outputs LONG / SHORT / WAIT
- Gives entry, stop loss, TP1, TP2 and confidence score
- Includes paper-risk position sizing
- Does NOT place real trades

## Run on PC
1. Install Python 3.10+
2. Open a terminal in this folder
3. Run:
   pip install -r requirements.txt
4. Then:
   streamlit run app.py

## Run free in browser
You can upload these files to a GitHub repo and deploy with Streamlit Community Cloud.

## Important
This is not a guaranteed-profit system. Backtest and paper trade it first.
