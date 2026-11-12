"""Burst-momentum cbBTC bot for the make.fun BTC race (agent-fun/bars-replay/v1).

Strategy, in one paragraph: the bot sits in cash almost all of the time and
only buys when Bitcoin shows a genuine 60-minute momentum burst (the latest
close at least 0.75% above the close 60 bars ago), because a full round trip
costs about 26 bps in fees, slippage and price impact while a typical
one-minute bar moves only about 5 bps -- so only a real burst is worth
chasing. It buys with all of its cash, banks half the position once it is
up 0.6% over cost, and lets the rest ride behind a 0.8% trailing stop, a
1.0% stop-loss and a 360-bar maximum hold. If it has still never traded by
bar 1200 it takes one small (30% of equity) fallback trade on a weaker
+0.4% burst, so the entry still meets the race's minimum-trade guardrail
in a quiet window. It never holds into the end on purpose: the replay
flattens anything left at the last close.

Everything is a pure function of the bars received so far: no clock, no
environment, no files, no network, no randomness. The same bars always give
the same orders, so the two graded executions agree byte for byte.

Wire protocol: the vendored kit shim (vendor/makefun_bars.py, a byte-identical
copy of the kit's sdk/makefun_bars.py) owns stdin/stdout; this file only
decides orders in on_batch().
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (chosen on the dev window, see NOTES.md) ---
LOOKBACK_BARS = 60        # momentum window, in bars (minutes)
BURST_PCT = 0.0075        # entry: close >= 0.75% above the close LOOKBACK bars ago
FALLBACK_PCT = 0.0040     # weaker burst that arms the late-window fallback entry
FALLBACK_BAR = 1200       # fallback only once this many closes have been seen
FALLBACK_SIZE = 0.30      # fallback buys 30% of equity
TAKE_PROFIT_PCT = 0.006   # once per position: sell half when value/cost is +0.6%
TAKE_PROFIT_FRAC = 0.5    # fraction of the position the take-profit sells
TRAIL_PCT = 0.008         # sell all when value falls 0.8% below its peak since entry
STOP_LOSS_PCT = 0.010     # sell all when value/cost falls to -1.0%
MAX_HOLD_BARS = 360       # sell all this many bars after the entry decision
MAX_SLIPPAGE_BPS = 100    # 1% past the latest close; fills here cost ~10 bps total

# --- per-run state (all derived from the bars + fills, nothing else) ---
closes = []               # closes seen so far, as ints (raw price units)
filled_buys = 0           # buys the harness reported as filled
entry_bar = -1            # index into closes of the entry decision, -1 when flat
peak_close = 0            # highest close since entry (raw price units)
took_profit = False       # whether this position already took its partial profit


def _position_value(state):
    """(qty, value, cost) of the CBBTC position, from the harness account."""
    held = state.positions.get(SYMBOL)
    if held is None or held.qty <= 0:
        return 0, 0, 0
    return held.qty, state.value(SYMBOL, held.qty), held.cost


def on_batch(state, batch):
    global filled_buys, entry_bar, peak_close, took_profit

    for fill in batch.get("fills", []):
        if fill.get("status") == "filled" and fill.get("side") == "buy":
            filled_buys += 1

    for bar in batch.get("bars", []):
        if bar.get("symbol") == SYMBOL:
            closes.append(int(bar["c"]))

    if state.warming_up:
        return []

    qty, value, cost = _position_value(state)
    n = len(closes)

    if qty > 0:
        # --- manage an open position ---
        if entry_bar < 0:
            # Position arrived without our entry record (should not happen);
            # adopt it so the exits below still protect it.
            entry_bar = n - 1
            peak_close = closes[-1]
            took_profit = True
        peak_close = max(peak_close, closes[-1])
        peak_value = state.value(SYMBOL, qty, peak_close)

        # 1. Take half the profit once, at +0.6% over cost.
        if not took_profit and cost > 0 and value * 1000 >= cost * 1006:
            took_profit = True
            half = qty // 2
            if half > 0 and state.value(SYMBOL, half) >= 1_000_000:
                return [{"side": "sell", "symbol": SYMBOL, "qty": half,
                         "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 2. Trailing stop: 0.8% below the peak value since entry.
        if peak_value > 0 and value * 1000 < peak_value * 992:
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 3. Stop-loss: 1.0% under cost.
        if cost > 0 and value * 1000 <= cost * 990:
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        # 4. Maximum hold: 360 bars after the entry decision.
        if n - 1 - entry_bar >= MAX_HOLD_BARS:
            return [{"side": "sell", "symbol": SYMBOL, "qty": qty,
                     "max_slippage_bps": MAX_SLIPPAGE_BPS}]
        return []

    # --- flat: look for an entry ---
    entry_bar = -1
    if n <= LOOKBACK_BARS:
        return []
    now = closes[-1]
    then = closes[-LOOKBACK_BARS - 1]
    burst = (now - then) * 10000 >= then * 75  # now/then - 1 >= 0.75%, integers only
    fallback = (filled_buys == 0 and n >= FALLBACK_BAR
                and (now - then) * 10000 >= then * 40)  # >= 0.40%
    if not (burst or fallback):
        return []

    frac = FALLBACK_SIZE if (fallback and not burst) else 1.0
    spend = state.weight_room(SYMBOL)
    if frac < 1.0:
        spend = spend * 30 // 100
    spend = min(spend, state.cash)
    if spend < int(state.hello["fees"]["min_notional_quote_units"]):
        return []
    entry_bar = n - 1
    peak_close = now
    took_profit = False
    return [{"side": "buy", "symbol": SYMBOL, "notional_quote_units": spend,
             "max_slippage_bps": MAX_SLIPPAGE_BPS}]


makefun_bars.run(on_batch)
