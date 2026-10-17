# AlpacaSniping: moving-average crossover bot

Buys when the 20-day moving average crosses above the 50-day one (only while the price is above its
200-day average), sells when it crosses below or when a position is 10% under its entry price,
on an Alpaca **paper** account. Settings live in `config.py`.

What it trades is chosen with `--market` or `BOT_MARKET`:
- `stocks` (default): every symbol in `universe_stocks.txt`, the liquid US stocks and ETFs on Alpaca
  (average daily traded value of at least `MIN_DOLLAR_VOLUME`, $20M), 1 share each. Data is downloaded in
  batches, every symbol gets one log line, and at most `MAX_BUYS_PER_RUN` (5) new buys are placed per run,
  most traded first. Sells are not capped. Rebuild the list with `python build_universe.py`.
- `crypto`: every non-stablecoin USD pair on Alpaca listed in `config.CRYPTO_UNIVERSE` (30 coins; BONK, SHIB
  and PEPE are left out because Yahoo rounds their prices). Each buy is worth `CRYPTO_ORDER_USD` ($100), at
  most `MAX_CRYPTO_BUYS_PER_RUN` (3) per run. Crypto bars close at 00:00 UTC every day, so run it daily
  shortly after that (weekends included), separately from the weekday stock run.
- `aapl` (1 share) and `btc` (BTC/USD, 0.001 BTC), defined in `config.MARKETS`.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then put your paper keys in .env
```

## Run
```bash
python bot.py --dry-run   # show the signal, place nothing
python bot.py             # place the order if a crossover happened
python bot.py --market btc --dry-run   # same strategy on BTC/USD
python bot.py --market crypto --dry-run  # all coins
python bot.py --market aapl            # only AAPL
python build_universe.py               # refresh the stock list (places no orders)
python backtest.py                     # 10-year backtest of the strategy variants (places no orders)
pytest                    # unit tests
```

## How it decides
- Downloads `LOOKBACK_DAYS` of daily closes from yfinance and computes simple moving averages.
- A crossover is real only if the fast MA was on one side of the slow MA yesterday and on the other side today.
- Trend filter: a buy crossover counts only if the close is above its `TREND_MA_PERIOD` (200) day average.

## Risk limits (live universe runs)
- Stop-loss: any position of the asset class being run that is `STOP_LOSS_PCT` (10%) below its average entry
  price is sold in full, whether or not its moving averages crossed. It is checked once per run, at the run's price.
- Per position: a buy is skipped if it would bring that position above `MAX_POSITION_PCT` (5%) of account equity.
- Total: a buy is skipped if all positions together would go above `MAX_INVESTED_PCT` (50%) of equity.
- Then the per-run buy caps (`MAX_BUYS_PER_RUN`, `MAX_CRYPTO_BUYS_PER_RUN`) apply, most traded first.
- Buy: skipped if you already hold the stock or an order is already open (so running twice a day doesn't double-buy).
- Sell: sells up to `TRADE_SIZE` shares you hold; it never sells short.
- Refuses to run unless `APCA_API_BASE_URL` is the paper URL.
- Crypto: orders use `gtc` (Alpaca crypto doesn't accept `day`), and since yfinance crypto bars are UTC days,
  the current UTC day's bar is always dropped. Crypto trades 24/7, so it can run on any day.

Run it once per day. It is scheduled every weekday at 15:50 ET, ten minutes before the close: from
`STOCK_BAR_CUTOFF` (15:30 ET) on, today's bar counts as the day's close, so the bot trades on the crossover day
itself instead of the next morning, and a market order still fills before 16:00. Before 15:30 today's bar is dropped.

## Backtest
`python backtest.py` downloads 10 years of daily yfinance data for AAPL, SPY and 100 symbols spread over the
universe, and trades each symbol on its own with equal capital. Result on 2026-10-17 (68 symbols with data
since 2015, 0.05% slippage per side):

| Variant | CAGR | Max drawdown | Sharpe | Win rate | Time invested |
|---|---|---|---|---|---|
| 20/50, order at next open (old 9:30 run) | 6.7% | -23.6% | 0.66 | 43.8% | 59% |
| 20/50, order at the close (15:50 run) | 7.2% | -23.7% | 0.70 | 43.7% | 59% |
| + 200-day trend filter | 5.9% | -13.1% | 0.76 | 43.4% | 41% |
| + trend filter + 10% stop-loss (live settings) | 5.6% | -12.1% | 0.77 | 42.4% | 39% |
| + trend filter + 8% stop-loss | 5.1% | -11.1% | 0.74 | 41.2% | 38% |
| Buy and hold, same symbols | 17.6% | -39.0% | 0.85 | | 100% |

The crossover earns far less than holding, mostly because it is out of the market about half the time;
the trend filter halves the drawdown. The sample is today's liquid stocks, so delisted companies are
missing (survivorship bias) and real results would likely be worse.

## Dashboard
`python export_dashboard.py --out dashboard_data --log-dir logs` exports the paper account (account, positions,
last 200 orders, daily equity for a year) and every logged run result as JSON files. The scheduled run uploads
them to the project's results dashboard after each run. Places no orders.

## Logs
Every run appends timestamped lines (data fetched, MA values, signal, order id/status, errors) to
`logs/bot_YYYY-MM-DD.log` and prints them to the console. The last line of each run starts with `RESULT:`.
Choose another folder with `--log-dir` or `BOT_LOG_DIR`. The scheduled run writes to
`/mnt/project-files/AlpacaSniping/logs/` in the project's shared folder.
