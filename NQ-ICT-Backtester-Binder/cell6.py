
def run_backtest(data, cfg):
    tick = cfg["tick_size"]
    slip = cfg["slippage_ticks"] * tick
    trades = []

    long_armed = False
    short_armed = False
    long_sweep_bar = None
    short_sweep_bar = None
    long_sweep_low = np.nan
    short_sweep_high = np.nan

    long_fvg = None   # (bar_number, top, bottom)
    short_fvg = None

    position = None
    trades_today = 0
    losses_today = 0
    current_date = None

    # For 15M structure, keep the last two confirmed pivot values.
    bias_highs = []
    bias_lows = []

    last_buy_side = np.nan
    last_sell_side = np.nan

    rows = list(data.iterrows())

    for i, (ts, r) in enumerate(rows):
        if ts.date() != current_date:
            current_date = ts.date()
            trades_today = 0
            losses_today = 0

        if pd.notna(r["m5_ph"]):
            last_buy_side = float(r["m5_ph"])
        if pd.notna(r["m5_pl"]):
            last_sell_side = float(r["m5_pl"])

        # Update confirmed 15M pivots without using future information.
        # The ffill series can repeat a pivot across 1M bars, so update only
        # when the value changes.
        if pd.notna(r["m15_ph"]):
            if not bias_highs or r["m15_ph"] != bias_highs[-1]:
                bias_highs.append(float(r["m15_ph"]))
                bias_highs = bias_highs[-2:]
        if pd.notna(r["m15_pl"]):
            if not bias_lows or r["m15_pl"] != bias_lows[-1]:
                bias_lows.append(float(r["m15_pl"]))
                bias_lows = bias_lows[-2:]

        structure_bull = (
            len(bias_highs) == 2 and len(bias_lows) == 2
            and bias_highs[-1] > bias_highs[-2]
            and bias_lows[-1] > bias_lows[-2]
        )
        structure_bear = (
            len(bias_highs) == 2 and len(bias_lows) == 2
            and bias_highs[-1] < bias_highs[-2]
            and bias_lows[-1] < bias_lows[-2]
        )

        bull_bias = (
            pd.notna(r["m15_close"])
            and r["m15_close"] > r["m15_ema_fast"] > r["m15_ema_slow"]
            and structure_bull
        )
        bear_bias = (
            pd.notna(r["m15_close"])
            and r["m15_close"] < r["m15_ema_fast"] < r["m15_ema_slow"]
            and structure_bear
        )

        minutes = ts.hour * 60 + ts.minute
        start_m = int(cfg["session_start"][:2]) * 60 + int(cfg["session_start"][3:])
        end_m = int(cfg["session_end"][:2]) * 60 + int(cfg["session_end"][3:])
        in_session = start_m <= minutes <= end_m

        # ---------------- EXISTING POSITION ----------------
        if position is not None:
            side = position["side"]

            if side == "long":
                if cfg["move_to_be"] and not position["be"]:
                    if r["high"] >= position["entry"] + position["risk"] * cfg["be_trigger_r"]:
                        position["be"] = True

                stop = position["entry"] if position["be"] else position["stop"]
                hit_stop = r["low"] <= stop
                hit_target = r["high"] >= position["target"]

                if hit_stop or hit_target:
                    # Conservative same-bar assumption: stop first.
                    if hit_stop:
                        exit_price = stop - slip
                        result = "LOSS"
                    else:
                        exit_price = position["target"] - slip
                        result = "WIN"

                    gross = (exit_price - position["entry"]) * cfg["point_value"] * position["qty"]
                    commission = cfg["commission_per_contract_side"] * position["qty"] * 2
                    net = gross - commission

                    trades.append({
                        **position,
                        "exit_time": ts,
                        "exit": exit_price,
                        "gross_pnl": gross,
                        "commission": commission,
                        "net_pnl": net,
                        "r": (exit_price - position["entry"]) / position["risk"],
                        "result": "LOSS" if net < 0 else result,
                    })
                    if net < 0:
                        losses_today += 1
                    position = None
                    continue

            else:
                if cfg["move_to_be"] and not position["be"]:
                    if r["low"] <= position["entry"] - position["risk"] * cfg["be_trigger_r"]:
                        position["be"] = True

                stop = position["entry"] if position["be"] else position["stop"]
                hit_stop = r["high"] >= stop
                hit_target = r["low"] <= position["target"]

                if hit_stop or hit_target:
                    if hit_stop:
                        exit_price = stop + slip
                        result = "LOSS"
                    else:
                        exit_price = position["target"] + slip
                        result = "WIN"

                    gross = (position["entry"] - exit_price) * cfg["point_value"] * position["qty"]
                    commission = cfg["commission_per_contract_side"] * position["qty"] * 2
                    net = gross - commission

                    trades.append({
                        **position,
                        "exit_time": ts,
                        "exit": exit_price,
                        "gross_pnl": gross,
                        "commission": commission,
                        "net_pnl": net,
                        "r": (position["entry"] - exit_price) / position["risk"],
                        "result": "LOSS" if net < 0 else result,
                    })
                    if net < 0:
                        losses_today += 1
                    position = None
                    continue

        # ---------------- FILTERS ----------------
        if (
            position is not None
            or not in_session
            or trades_today >= cfg["max_trades_day"]
            or losses_today >= cfg["max_losses_day"]
        ):
            continue

        # ---------------- LIQUIDITY SWEEPS ----------------
        sweep_sell_side = (
            cfg["allow_longs"] and bull_bias
            and pd.notna(last_sell_side)
            and r["low"] < last_sell_side - cfg["sweep_buffer_ticks"] * tick
            and r["close"] > last_sell_side
        )
        sweep_buy_side = (
            cfg["allow_shorts"] and bear_bias
            and pd.notna(last_buy_side)
            and r["high"] > last_buy_side + cfg["sweep_buffer_ticks"] * tick
            and r["close"] < last_buy_side
        )
        sweep_prior_low = (
            cfg["allow_longs"] and bull_bias
            and pd.notna(r["prior_day_low"])
            and r["low"] < r["prior_day_low"] - cfg["sweep_buffer_ticks"] * tick
            and r["close"] > r["prior_day_low"]
        )
        sweep_prior_high = (
            cfg["allow_shorts"] and bear_bias
            and pd.notna(r["prior_day_high"])
            and r["high"] > r["prior_day_high"] + cfg["sweep_buffer_ticks"] * tick
            and r["close"] < r["prior_day_high"]
        )

        if sweep_sell_side or sweep_prior_low:
            long_armed = True
            long_sweep_bar = i
            long_sweep_low = float(r["low"])
            long_fvg = None

        if sweep_buy_side or sweep_prior_high:
            short_armed = True
            short_sweep_bar = i
            short_sweep_high = float(r["high"])
            short_fvg = None

        # ---------------- EXPIRE SWEEPS ----------------
        if long_armed and i - long_sweep_bar > cfg["setup_expiry"]:
            long_armed = False
            long_sweep_bar = None
            long_sweep_low = np.nan

        if short_armed and i - short_sweep_bar > cfg["setup_expiry"]:
            short_armed = False
            short_sweep_bar = None
            short_sweep_high = np.nan

        # ---------------- MSS / DISPLACEMENT ----------------
        bull_mss = (
            long_armed
            and pd.notna(r["recent_swing_high"])
            and r["close"] > r["recent_swing_high"]
            and r["close"] > r["open"]
        )
        bear_mss = (
            short_armed
            and pd.notna(r["recent_swing_low"])
            and r["close"] < r["recent_swing_low"]
            and r["close"] < r["open"]
        )

        body = abs(r["close"] - r["open"])
        bull_disp = bull_mss and body >= r["atr"] * cfg["displacement_atr"]
        bear_disp = bear_mss and body >= r["atr"] * cfg["displacement_atr"]

        # ---------------- FVG ----------------
        if i >= 2 and bull_disp and r["low"] > rows[i-2][1]["high"]:
            long_fvg = (i, float(r["low"]), float(rows[i-2][1]["high"]))
            long_armed = False

        if i >= 2 and bear_disp and r["high"] < rows[i-2][1]["low"]:
            short_fvg = (i, float(rows[i-2][1]["low"]), float(r["high"]))
            short_armed = False

        if long_fvg and i - long_fvg[0] > cfg["fvg_expiry"]:
            long_fvg = None
        if short_fvg and i - short_fvg[0] > cfg["fvg_expiry"]:
            short_fvg = None

        # ---------------- FVG RETRACEMENT ----------------
        candidates = []

        if long_fvg:
            _, top, bottom = long_fvg
            if cfg["fvg_entry_mode"] == "Touch":
                entry = top
            elif cfg["fvg_entry_mode"] == "50%":
                entry = (top + bottom) / 2
            else:
                entry = bottom

            reached = r["low"] <= entry and r["close"] >= bottom
            if reached:
                stop = long_sweep_low - cfg["stop_buffer_ticks"] * tick
                risk = entry - stop

                liquidity = np.nan
                if pd.notna(last_buy_side) and last_buy_side > entry:
                    liquidity = last_buy_side
                elif pd.notna(r["prior_day_high"]) and r["prior_day_high"] > entry:
                    liquidity = r["prior_day_high"]

                fixed_target = entry + risk * cfg["fixed_rr"]
                if cfg["target_mode"] == "Fixed R" or pd.isna(liquidity):
                    target = fixed_target
                elif cfg["target_mode"] == "Liquidity":
                    target = liquidity
                else:
                    target = liquidity if liquidity >= entry + risk * cfg["minimum_rr"] else fixed_target

                rr = (target - entry) / risk if risk > 0 else np.nan
                if risk > 0 and rr >= cfg["minimum_rr"]:
                    candidates.append(("long", entry, stop, target, risk, rr))

        if short_fvg:
            _, top, bottom = short_fvg
            if cfg["fvg_entry_mode"] == "Touch":
                entry = bottom
            elif cfg["fvg_entry_mode"] == "50%":
                entry = (top + bottom) / 2
            else:
                entry = top

            reached = r["high"] >= entry and r["close"] <= top
            if reached:
                stop = short_sweep_high + cfg["stop_buffer_ticks"] * tick
                risk = stop - entry

                liquidity = np.nan
                if pd.notna(last_sell_side) and last_sell_side < entry:
                    liquidity = last_sell_side
                elif pd.notna(r["prior_day_low"]) and r["prior_day_low"] < entry:
                    liquidity = r["prior_day_low"]

                fixed_target = entry - risk * cfg["fixed_rr"]
                if cfg["target_mode"] == "Fixed R" or pd.isna(liquidity):
                    target = fixed_target
                elif cfg["target_mode"] == "Liquidity":
                    target = liquidity
                else:
                    target = liquidity if liquidity <= entry - risk * cfg["minimum_rr"] else fixed_target

                rr = (entry - target) / risk if risk > 0 else np.nan
                if risk > 0 and rr >= cfg["minimum_rr"]:
                    candidates.append(("short", entry, stop, target, risk, rr))

        # ---------------- ENTER ----------------
        if candidates:
            side, entry, stop, target, risk, rr = candidates[0]
            qty = cfg["contracts"]

            position = {
                "side": side,
                "entry_time": ts,
                "entry": entry + (slip if side == "long" else -slip),
                "stop": stop,
                "target": target,
                "risk": risk,
                "rr_planned": rr,
                "qty": qty,
                "be": False,
            }
            trades_today += 1

            if side == "long":
                long_fvg = None
            else:
                short_fvg = None

    # Close an open trade at the last close so it appears in results.
    if position is not None:
        ts = data.index[-1]
        last = data.iloc[-1]["close"]
        if position["side"] == "long":
            gross = (last - position["entry"]) * cfg["point_value"] * position["qty"]
            r_mult = (last - position["entry"]) / position["risk"]
        else:
            gross = (position["entry"] - last) * cfg["point_value"] * position["qty"]
            r_mult = (position["entry"] - last) / position["risk"]
        commission = cfg["commission_per_contract_side"] * position["qty"] * 2
        net = gross - commission
        trades.append({
            **position, "exit_time": ts, "exit": last,
            "gross_pnl": gross, "commission": commission,
            "net_pnl": net, "r": r_mult,
            "result": "WIN" if net > 0 else "LOSS"
        })

    return pd.DataFrame(trades)

trades = run_backtest(work, CFG)
print("Completed trades:", len(trades))
if len(trades):
    display(trades.head(20))
