# AlpacaSniping: moving-average crossover bot

Buys when the 20-day moving average crosses above the 50-day one, sells when it crosses below,
on an Alpaca **paper** account. Settings live in `config.py`.

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env   # then put your paper keys in .env
```

## Run
```bash
python bot.py --dry-run   # show the signal, place nothing
python bot.py             # place the order if a crossover happened
pytest                    # unit tests for the crossover logic
```

## How it decides
- Downloads `LOOKBACK_DAYS` of daily closes from yfinance and computes simple moving averages.
- A crossover is real only if the fast MA was on one side of the slow MA yesterday and on the other side today.
- Buy: skipped if you already hold the stock or an order is already open (so running twice a day doesn't double-buy).
- Sell: sells up to `TRADE_SIZE` shares you hold; it never sells short.
- Refuses to run unless `APCA_API_BASE_URL` is the paper URL.

Run it once per day, e.g. with cron after the close; a market order placed then fills at the next open.
