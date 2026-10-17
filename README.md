# AlpacaSniping: moving-average crossover bot

Buys when the 20-day moving average crosses above the 50-day one, sells when it crosses below,
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
pytest                    # unit tests for the crossover logic
```

## How it decides
- Downloads `LOOKBACK_DAYS` of daily closes from yfinance and computes simple moving averages.
- A crossover is real only if the fast MA was on one side of the slow MA yesterday and on the other side today.
- Buy: skipped if you already hold the stock or an order is already open (so running twice a day doesn't double-buy).
- Sell: sells up to `TRADE_SIZE` shares you hold; it never sells short.
- Refuses to run unless `APCA_API_BASE_URL` is the paper URL.
- Crypto: orders use `gtc` (Alpaca crypto doesn't accept `day`), and since yfinance crypto bars are UTC days,
  the current UTC day's bar is always dropped. Crypto trades 24/7, so it can run on any day.

Run it once per day. It is scheduled every weekday at 9:30 ET (market open); at that time it uses the
last completed daily bars (today's unfinished bar is dropped), and a market order fills right away.

## Logs
Every run appends timestamped lines (data fetched, MA values, signal, order id/status, errors) to
`logs/bot_YYYY-MM-DD.log` and prints them to the console. The last line of each run starts with `RESULT:`.
Choose another folder with `--log-dir` or `BOT_LOG_DIR`. The scheduled run writes to
`/mnt/project-files/AlpacaSniping/logs/` in the project's shared folder.
