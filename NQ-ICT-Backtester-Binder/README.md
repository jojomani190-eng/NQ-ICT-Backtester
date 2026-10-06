# NQ ICT 1-Minute Backtester

This is a Python backtest implementation of the uploaded Pine strategy:
15M bias -> 5M liquidity -> 1M sweep -> MSS -> displacement -> FVG -> retracement entry.

## Files
- `NQ_ICT_Backtest.ipynb` — main backtest notebook
- `requirements.txt` — Binder dependencies
- `README.md` — setup instructions

## Data
Use a CSV containing 1-minute NQ futures OHLC data. A TradingView export is recommended.
Columns can be named Time/Date/Datetime plus Open, High, Low, Close, and optional Volume.

## Binder
1. Create a **public** GitHub repository.
2. Upload all three files.
3. Go to https://mybinder.org/
4. Repository: `YOUR_USERNAME/NQ-ICT-Backtester`
5. Git ref: `main`
6. File to open: `NQ_ICT_Backtest.ipynb`
7. Click Launch.

## Backtest assumptions
- NQ point value: $20/point.
- Tick size: 0.25.
- Commission: $2.50 per contract per side.
- Slippage: 1 tick.
- Default session: 09:30–12:00 America/New_York.
- If both stop and target are touched inside the same 1-minute candle, the stop is assumed to hit first.
- Higher-timeframe information is only used after its bar has completed.
