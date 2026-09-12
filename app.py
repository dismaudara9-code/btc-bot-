
import time
import requests
import pandas as pd
import numpy as np
import streamlit as st

BYBIT_KLINES = "https://api.bybit.com/v5/market/kline"

st.set_page_config(page_title="BTCUSDT 5m AI Entry Bot", layout="wide")

st.title("BTCUSDT 5-Minute AI Entry Bot")
st.caption("Signal / paper-trading mode. Uses live Bybit public market data. No real orders are placed.")

def fetch_klines(symbol="BTCUSDT", interval="5", limit=300):
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    r = requests.get(BYBIT_KLINES, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    rows = data["result"]["list"]
    rows = list(reversed(rows))
    df = pd.DataFrame(rows, columns=[
        "startTime","open","high","low","close","volume","turnover"
    ])
    for c in ["open","high","low","close","volume","turnover"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["startTime"] = pd.to_datetime(pd.to_numeric(df["startTime"]), unit="ms", utc=True)
    return df

def ema(s, span):
    return s.ewm(span=span, adjust=False).mean()

def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()

def enrich(df):
    df = df.copy()
    df["ema9"] = ema(df["close"], 9)
    df["ema21"] = ema(df["close"], 21)
    df["rsi14"] = rsi(df["close"], 14)
    df["macd"] = ema(df["close"], 12) - ema(df["close"], 26)
    df["macd_signal"] = ema(df["macd"], 9)
    df["atr14"] = atr(df, 14)
    df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df

def make_signal(df):
    x = df.iloc[-1]
    p = df.iloc[-2]
    score_long = 0
    score_short = 0
    reasons = []

    if x["ema9"] > x["ema21"]:
        score_long += 2
        reasons.append("EMA 9 is above EMA 21")
    else:
        score_short += 2
        reasons.append("EMA 9 is below EMA 21")

    if x["macd"] > x["macd_signal"]:
        score_long += 2
        reasons.append("MACD is bullish")
    else:
        score_short += 2
        reasons.append("MACD is bearish")

    if 52 <= x["rsi14"] <= 68:
        score_long += 2
        reasons.append("RSI supports bullish momentum")
    elif 32 <= x["rsi14"] <= 48:
        score_short += 2
        reasons.append("RSI supports bearish momentum")
    elif x["rsi14"] > 72:
        score_short += 1
        reasons.append("RSI is overbought")
    elif x["rsi14"] < 28:
        score_long += 1
        reasons.append("RSI is oversold")

    if x["close"] > p["high"]:
        score_long += 1
        reasons.append("Current close broke above previous high")
    elif x["close"] < p["low"]:
        score_short += 1
        reasons.append("Current close broke below previous low")

    if pd.notna(x["vol_ma20"]) and x["volume"] > x["vol_ma20"]:
        if score_long > score_short:
            score_long += 1
        elif score_short > score_long:
            score_short += 1
        reasons.append("Volume is above 20-candle average")

    if score_long >= 6 and score_long >= score_short + 2:
        side = "LONG"
        confidence = min(95, 55 + score_long * 5)
    elif score_short >= 6 and score_short >= score_long + 2:
        side = "SHORT"
        confidence = min(95, 55 + score_short * 5)
    else:
        side = "WAIT"
        confidence = max(score_long, score_short) * 10

    entry = float(x["close"])
    atrv = float(x["atr14"]) if pd.notna(x["atr14"]) else entry * 0.003

    if side == "LONG":
        sl = entry - 1.2 * atrv
        tp1 = entry + 1.5 * atrv
        tp2 = entry + 2.5 * atrv
    elif side == "SHORT":
        sl = entry + 1.2 * atrv
        tp1 = entry - 1.5 * atrv
        tp2 = entry - 2.5 * atrv
    else:
        sl = tp1 = tp2 = None

    return {
        "side": side,
        "confidence": int(confidence),
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "rsi": float(x["rsi14"]),
        "ema9": float(x["ema9"]),
        "ema21": float(x["ema21"]),
        "macd": float(x["macd"]),
        "macd_signal": float(x["macd_signal"]),
        "atr": atrv,
        "reasons": reasons
    }

with st.sidebar:
    st.header("Settings")
    refresh = st.selectbox("Refresh every", ["Manual", "15 sec", "30 sec", "60 sec"], index=1)
    min_conf = st.slider("Minimum confidence to highlight", 50, 95, 70)
    account = st.number_input("Paper account size (USDT)", min_value=10.0, value=100.0, step=10.0)
    risk_pct = st.slider("Risk per trade (%)", 0.25, 2.0, 1.0, 0.25)

placeholder = st.empty()

def render():
    try:
        df = enrich(fetch_klines())
        sig = make_signal(df)

        with placeholder.container():
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("BTCUSDT", f"${sig['entry']:,.2f}")
            c2.metric("Signal", sig["side"])
            c3.metric("Confidence", f"{sig['confidence']}%")
            c4.metric("RSI 14", f"{sig['rsi']:.1f}")

            if sig["side"] != "WAIT" and sig["confidence"] >= min_conf:
                risk_usdt = account * (risk_pct / 100)
                stop_dist = abs(sig["entry"] - sig["sl"])
                qty = risk_usdt / stop_dist if stop_dist > 0 else 0
                notional = qty * sig["entry"]

                st.subheader(f"{sig['side']} setup")
                a,b,c,d = st.columns(4)
                a.metric("Entry", f"{sig['entry']:,.2f}")
                b.metric("Stop loss", f"{sig['sl']:,.2f}")
                c.metric("Take profit 1", f"{sig['tp1']:,.2f}")
                d.metric("Take profit 2", f"{sig['tp2']:,.2f}")

                st.write(f"Paper risk: **{risk_usdt:.2f} USDT**")
                st.write(f"Approx BTC size by stop distance: **{qty:.6f} BTC**")
                st.write(f"Approx notional: **{notional:.2f} USDT**")
            else:
                st.info("No high-confidence trade right now. WAIT.")

            st.subheader("Why")
            for r in sig["reasons"]:
                st.write("• " + r)

            st.subheader("Recent candles")
            view = df[["startTime","open","high","low","close","volume","ema9","ema21","rsi14"]].tail(30).copy()
            st.dataframe(view, use_container_width=True)

            st.warning(
                "This tool is for analysis and paper trading. Futures are high risk. "
                "Do not treat the signal as guaranteed profit."
            )
    except Exception as e:
        with placeholder.container():
            st.error(f"Could not load Bybit data: {e}")

render()

if refresh != "Manual":
    seconds = int(refresh.split()[0])
    time.sleep(seconds)
    st.rerun()
