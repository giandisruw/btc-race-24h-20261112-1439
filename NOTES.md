# NOTES — strategy, parameters, and measured results

## Strategy

Long-only burst-momentum bot on 1-minute cbBTC/USDC bars. The dev window is
a slow grind: +1.3% over the first ~4 hours, then a choppy −3.5% decline
over the remaining ~20 hours, with 1-minute return stdev ≈ 5 bps and a
round-trip cost of ≈ 26 bps. Frequent trading loses (the house EMA-cross
baseline: −9.59% on dev with 68 trades). So the bot trades rarely, only on
a strong 60-minute burst, banks half the profit early, and otherwise sits
in cash through the decline.

## Parameters (all in `main.py`)

| Parameter | Value | Why |
|---|---|---|
| Momentum lookback | 60 bars | 60-min return is the burst signal; 30/45/90-min lookbacks scored worse |
| Burst threshold | +0.75% | 0.70–0.80% plateau at +0.42–0.43%; 0.60% loses (−0.40%, extra losing trade); 0.90% only +0.12% |
| Position size | 100% of equity | Size sweep: 50% → +0.16%, 75% → +0.21%, 100% → +0.25% (pre-TP baseline) |
| Take profit | sell 50% at +0.6% over cost | TP grid: +0.5/+0.6/+0.7% all ≈ +0.43–0.44% (plateau, not knife-edge); no-TP baseline +0.25% |
| Trailing stop | 0.8% below peak value | 0.8% and 1.2% identical on dev; 0.3% gives +0.23% with lower drawdown |
| Stop-loss | −1.0% vs cost | Never triggered on dev (0.8–2.0% all identical); safety net only |
| Max hold | 360 bars | 240 → +0.41%, 360 → +0.43%, 480 → −0.24% (trail-only exit is worse) |
| Max slippage | 100 bps | Fills cost ~10 bps; cap only guards freak opens |
| Fallback entry | bar ≥1200, no filled buy yet, 60-min ≥ +0.4%, 30% size | Guardrail insurance for a quiet race window; never fires on dev |

Deliberately NOT used: dip-buying / mean reversion (tested: −0.20% alone,
−1.20% when combined with the burst — buying dips in the downtrend loses),
EMA-cross entries (whipsaw), Donchian breakouts (−2.02% best), RSI
mean reversion (−1.87% best), time-based flatten (the replay auto-flattens;
verified identical with and without it).

## Measured results

### A. Official `grade-local` (house baselines, for calibration)

Command (from the unpacked kit dir):
`node cli/makefun.mjs grade-local --kit . --bot <dir> --driver process --json`

| Bot | Net PnL | Return | Trades | Fees | Max DD |
|---|---|---|---|---|---|
| buy-and-hold (kit baseline) | −25.97 USDC | −2.597% | 1 | 0.79 USDC | 3.94% |
| ema-cross (kit baseline) | −95.88 USDC | −9.588% | 68 | 26.07 USDC | 10.00% |

My float backtester reproduced these within ~0.01–0.26 pp
(buy-hold −2.596%, EMA-cross −9.85%), which validated the backtester.

### B. Exact-integer protocol driver (the real `main.py`, end to end)

The official `grade-local --driver process` cannot grade a Python bot
("the process sandbox runs node22 only (python3.13 runs only inside
Docker)") and this VM has no Docker, so I verified `main.py` with a driver
(`~/workspace/makefun-btc-race-research/driver.py`) that spawns the real
`main.py` as a subprocess, feeds it hello + one batch per dev bar, and
applies the harness's own integer fill model copied from
`harness-src/sim/bars/engine.ts` (BarsPool constant-product impact,
4 bps fee, 2 bps slippage, decision checks, flatten at last close vs
c_depth). Two full runs, reply bytes compared:

- Run 1: net PnL **+4.2031 USDC (+0.420%)**, 3 trades, fees 0.8018 USDC,
  maxDD 0.33%, max position 0.0135 BTC, max decision 53.7 ms/bar,
  0 rejected orders.
- Run 2: net PnL **+4.2031 USDC (+0.420%)**, 3 trades — identical.
- Determinism: reply bytes identical across both runs (True).
- Fills: BUY 0.01348429 BTC @ 74,130.70752 (decided bar 90, filled bar 91,
  notional 1,000 USDC, fee 0.40 USDC); SELL 50% @ 74,620.39098 (decided
  bar 159, filled bar 160); SELL rest @ 74,383.37160 (decided bar 450,
  filled bar 451 — max-hold exit). Flat from bar 451 of 1,439; nothing
  left for the end-of-window flatten.
- Backtest (float model) of the same parameters: +0.42%, 3 trades — the
  two independent models agree.

### C. Edge tests (`edge_test.py`, synthetic series through the real bot)

- Warmup (`warmup_bars=60`): 0 orders during warmup, clean exit rc=0.
- Synthetic quiet window with a late +0.54% 60-min burst: fallback fires
  once at 30% size (300,000,000 quote units) at bar 1292; repeated buys
  in that test only because the test harness never reports a fill (the
  real harness reports the fill, `filled_buys` becomes 1, and it stops).
- Flat window, no burst at all: 0 orders — documents the guardrail
  boundary (a window with no burst at all would fail the min-1-trade
  guardrail; the fallback exists to cover realistic quiet windows).

### D. What was NOT reached

Target was +2% net on dev if achievable without overfitting. Best honest
result is **+0.42%**. The dev window's only clean move is the early rally
(≈ +1.3% peak-to-trough); the theoretical best single round trip is
≈ +1.0% net, and the burst rule captures +0.42% of it while refusing
every later re-entry in the decline. The dev leaderboard top (+21.13%,
per the brief) was not chased: it cannot come from this window's price
action with a robust rule and is almost certainly overfit to the frozen
window. This bot passes the dev gate (+0.42% > $0) with 3 trades and
0.33% max drawdown, and its behaviour — one selective entry, disciplined
exits, flat through downtrends — is the part designed to generalise to
the unseen race window.

## Discrepancies found (kit vs brief)

1. Entrypoint: the brief said `bot.py`; the kit requires `main.py` at the
   repo root (`python3 -P -s /bot/main.py`). Followed the kit.
2. The brief said the baseline long-only bot scores −1.03% net on dev;
   official `grade-local` on the kit's own buy-and-hold baseline gives
   −2.597% (my driver/backtester agree). The −1.03% figure looks stale.
3. Starter repo `https://github.com/make-fun/btc-race-starter` returns
   404 (and GitHub is unreachable from this VM); the kit's baselines were
   used as reference instead. No baseline code was copied.
4. `grade-local --driver process` cannot run Python bots (Node-only);
   no Docker on this VM — hence the exact-model driver in (B) above.
