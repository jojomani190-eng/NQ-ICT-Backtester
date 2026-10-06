
# Normalize common CSV column names.
lower = {c.lower().strip(): c for c in raw.columns}

def find_col(names, required=True):
    for name in names:
        if name in lower:
            return lower[name]
    if required:
        raise ValueError(f"Missing one of {names}. Found: {list(raw.columns)}")
    return None

time_col = find_col(["time", "datetime", "date", "timestamp"])
open_col = find_col(["open"])
high_col = find_col(["high"])
low_col = find_col(["low"])
close_col = find_col(["close"])
vol_col = find_col(["volume", "vol"], required=False)

df = pd.DataFrame({
    "time": pd.to_datetime(raw[time_col], errors="coerce"),
    "open": pd.to_numeric(raw[open_col], errors="coerce"),
    "high": pd.to_numeric(raw[high_col], errors="coerce"),
    "low": pd.to_numeric(raw[low_col], errors="coerce"),
    "close": pd.to_numeric(raw[close_col], errors="coerce"),
})

df["volume"] = pd.to_numeric(raw[vol_col], errors="coerce") if vol_col else np.nan
df = df.dropna(subset=["time","open","high","low","close"]).sort_values("time").drop_duplicates("time")

if df["time"].dt.tz is None:
    df["time"] = df["time"].dt.tz_localize("America/New_York")
else:
    df["time"] = df["time"].dt.tz_convert("America/New_York")

df = df.set_index("time")
print(f"{len(df):,} one-minute bars")
print("From:", df.index.min())
print("To:  ", df.index.max())
