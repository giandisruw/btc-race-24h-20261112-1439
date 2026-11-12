# Burst-Momentum cbBTC Bot — make.fun BTC Race 24h

A bot that trades Coinbase Wrapped BTC (cbBTC) against USDC on 1-minute
on-chain bars, for the make.fun competition `btc-race-24h-20261112-1439`.

## What it does

The bot sits in cash almost all of the time and only buys when Bitcoin shows
a genuine **60-minute momentum burst**: the latest close at least **0.75%**
above the close 60 bars ago. A full round trip costs ~26 bps in fees,
slippage and price impact while a typical one-minute bar moves only ~5 bps,
so only a real burst is worth chasing.

Once in, it manages the position with four exits:

1. **Take profit** — sells half the position once it is up 0.6% over cost.
2. **Trailing stop** — sells everything if the position falls 0.8% below its
   peak value since entry.
3. **Stop-loss** — sells everything if the position falls 1.0% under cost.
4. **Maximum hold** — sells everything 360 bars after entry.

If it has still never traded by bar 1200, it takes one small (30% of equity)
fallback trade on a weaker +0.4% burst, so the entry still meets the race's
minimum-trade guardrail in a quiet window. It never needs to flatten
manually at the end: the replay flattens anything left at the last close.

## Files

- `main.py` — the entrypoint (the kit requires `main.py` at the repo root).
  Pure standard library, deterministic: every decision is integer math on
  the bars received so far. No clock, no environment, no files, no network,
  no randomness.
- `vendor/makefun_bars.py` — byte-identical copy of the kit's Python SDK
  shim (`sdk/makefun_bars.py`); it owns the stdin/stdout wire protocol.
- `LICENSE` — MIT.
- `NOTES.md` — strategy parameters and every measured test result.

No `requirements.txt` is needed: the bot uses only the standard library, and
the grader performs no install step anyway.

## How it works (per bar)

1. Record the bar's close; count filled buys from the batch's fills.
2. While warming up, send no orders.
3. If holding: check take-profit, trailing stop, stop-loss, max hold — in
   that order — and sell when one triggers. Otherwise hold.
4. If flat: buy with all cash when the 60-minute return is ≥ +0.75%, or
   with 30% of equity when the late-window fallback is armed (no filled buy
   yet, ≥1200 closes seen, 60-minute return ≥ +0.4%).
5. Every order caps slippage at 100 bps (1%) past the latest close; fills
   here cost ~10 bps total, so the cap only guards against freak opens.

## Local test results (dev window)

Measured with an exact-integer protocol driver that runs the real `main.py`
as a subprocess over the 1,439 dev bars and applies the harness's own fill
model (see `NOTES.md` for why the official `grade-local` could not run a
Python bot on this machine):

- **Net PnL +4.20 USDC (+0.42%)** on $1,000 start — passes the dev gate
  (needs > $0).
- **3 trades** (1 buy, 2 sells), fees 0.80 USDC, max drawdown 0.33%.
- Max position 0.0135 BTC (cap is 1.0 BTC); position flat from bar 451 of
  1,439 — no reliance on the end-of-window flatten.
- Max decision time 54 ms per bar (limit is 20 s); replies byte-identical
  across two full runs (deterministic).

For comparison on the same window (official `grade-local`, process driver):
buy-and-hold −2.60%, EMA-cross baseline −9.59%.

## Note on the entrypoint name

The bounty brief named the entrypoint `bot.py`, but the kit (`RULES.txt`,
`competition.yaml`) requires `main.py` at the repository root — the grader
runs `python3 -P -s /bot/main.py`. This repo follows the kit.
