
def ohlc_resample(x, rule):
    return x.resample(rule, label="right", closed="right").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open","high","low","close"])

def confirmed_pivot_high(s, n):
    candidate = s["high"].eq(s["high"].rolling(2*n+1, center=True).max())
    # Pivot is usable only after n bars have completed.
    return s["high"].where(candidate).shift(n)

def confirmed_pivot_low(s, n):
    candidate = s["low"].eq(s["low"].rolling(2*n+1, center=True).min())
    return s["low"].where(candidate).shift(n)

m5 = ohlc_resample(df, "5min")
m15 = ohlc_resample(df, "15min")

m15["ema_fast"] = m15["close"].ewm(span=CFG["bias_fast_len"], adjust=False).mean()
m15["ema_slow"] = m15["close"].ewm(span=CFG["bias_slow_len"], adjust=False).mean()
m15["ph"] = confirmed_pivot_high(m15, CFG["bias_swing_len"])
m15["pl"] = confirmed_pivot_low(m15, CFG["bias_swing_len"])

m5["ph"] = confirmed_pivot_high(m5, CFG["liq_pivot_len"])
m5["pl"] = confirmed_pivot_low(m5, CFG["liq_pivot_len"])

# Map completed HTF information onto each 1M bar.
work = df.copy()
for c in ["close","ema_fast","ema_slow","ph","pl"]:
    work["m15_" + c] = m15[c].reindex(work.index, method="ffill")

work["m5_ph"] = m5["ph"].reindex(work.index, method="ffill")
work["m5_pl"] = m5["pl"].reindex(work.index, method="ffill")

# Previous completed New York trading day high/low.
daily = df.resample("1D", label="right", closed="right").agg({"high":"max","low":"min"})
prev_daily = daily.shift(1)
work["prior_day_high"] = prev_daily["high"].reindex(work.index, method="ffill")
work["prior_day_low"] = prev_daily["low"].reindex(work.index, method="ffill")

# Wilder-style ATR approximation.
tr1 = work["high"] - work["low"]
tr2 = (work["high"] - work["close"].shift()).abs()
tr3 = (work["low"] - work["close"].shift()).abs()
work["tr"] = pd.concat([tr1,tr2,tr3], axis=1).max(axis=1)
work["atr"] = work["tr"].ewm(alpha=1/CFG["atr_length"], adjust=False).mean()

work["recent_swing_high"] = work["high"].shift(1).rolling(CFG["mss_lookback"]).max()
work["recent_swing_low"] = work["low"].shift(1).rolling(CFG["mss_lookback"]).min()

print("Prepared:", len(work), "1M bars")
