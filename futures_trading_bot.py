"""
Futures Trading Bot
===================

This module provides a simple example of a futures trading bot using
Interactive Brokers' API via the ib_insync library.  It illustrates how
to connect to IB, subscribe to market data, compute a simple moving
average crossover strategy, and place simulated orders.  The bot is
designed for educational purposes; it is *not* production ready and
should only be used in a paper trading environment.  You should
carefully review and test any code before using it with real money.

Usage
-----

1. Install the required dependencies:

   ``pip install ib_insync pandas``

2. Ensure you have IB Gateway or Trader Workstation running locally in
   paper trading mode.  The default port is typically 7497 for paper
   accounts.  Set the appropriate host, port and client ID in
   :data:`BOT_CONFIG` below.

3. Run the bot:

   ``python futures_trading_bot.py``

Configuration
-------------

All configurable parameters are gathered in the :data:`BOT_CONFIG`
dictionary.  Adjust these values to suit your needs.  The contract is
specified as a dictionary containing the symbol, exchange and last
trade date or contract month.  For example, the S&P 500 E‑mini futures
contract traded on the CME Globex exchange for March 2026 could be
defined as::

    {
        "symbol": "ES",
        "exchange": "GLOBEX",
        "lastTradeDateOrContractMonth": "202603"
    }

The strategy uses two simple moving averages (short and long) computed
on bar data.  When the short moving average crosses above the long
average, the bot will send a BUY order; when it crosses below, a
SELL order is sent.  Position sizing is fixed but configurable.

Disclaimer
----------

This code is provided for informational and educational purposes only.
It does not constitute investment advice.  Trading futures involves
substantial risk of loss and is not suitable for all investors.  The
author and distributor of this code do not guarantee its accuracy or
fitness for any particular purpose and are not responsible for any
losses incurred through its use.  Use at your own risk.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd
from ib_insync import IB, Future, util, Order


@dataclass
class BotConfig:
    """Configuration parameters for the futures trading bot."""

    # IB connection settings
    host: str = "127.0.0.1"
    port: int = 7497  # default port for paper trading (real accounts use 7496)
    client_id: int = 1  # unique client ID per connection

    # Contract details
    symbol: str = "ES"
    exchange: str = "GLOBEX"
    last_trade_date_or_contract_month: str = "202603"  # Example: March 2026 contract

    # Strategy parameters
    bar_size: str = "5 mins"
    history_duration: str = "2 D"  # how far back to fetch historical data
    short_window: int = 5  # number of bars for the short moving average
    long_window: int = 20  # number of bars for the long moving average
    order_size: int = 1  # number of contracts per trade

    # Risk management
    max_position: int = 1  # maximum absolute position size (long or short)

    # Logging
    verbose: bool = True

    # Trading session control
    start_time: Optional[str] = None  # e.g. "09:30" or None to start immediately
    end_time: Optional[str] = None  # e.g. "16:00" or None to run indefinitely


class FuturesTradingBot:
    """A simple event‑driven futures trading bot using ib_insync."""

    def __init__(self, config: BotConfig):
        self.config = config
        self.ib = IB()
        self.contract = Future(
            symbol=config.symbol,
            exchange=config.exchange,
            lastTradeDateOrContractMonth=config.last_trade_date_or_contract_month,
        )
        self.data: pd.DataFrame = pd.DataFrame()
        self.position = 0
        self.loop = asyncio.get_event_loop()
        self.ready_event = asyncio.Event()

    async def connect(self) -> None:
        """Establish a connection to the IB Gateway/Trader Workstation."""
        if self.config.verbose:
            print(f"Connecting to IB at {self.config.host}:{self.config.port} (clientId={self.config.client_id})")
        await self.ib.connectAsync(self.config.host, self.config.port, clientId=self.config.client_id)
        if not self.ib.isConnected():
            raise ConnectionError("Failed to connect to IB. Ensure Gateway/TWS is running and accessible.")
        if self.config.verbose:
            print("Connected successfully.")

    async def disconnect(self) -> None:
        """Disconnect from IB."""
        if self.ib.isConnected():
            if self.config.verbose:
                print("Disconnecting from IB...")
            await self.ib.disconnectAsync()
            if self.config.verbose:
                print("Disconnected.")

    async def fetch_historical_data(self) -> None:
        """Fetch initial historical bar data to seed the strategy."""
        end_time = ''  # an empty string means current time according to IB
        bars = await self.ib.reqHistoricalDataAsync(
            self.contract,
            endDateTime=end_time,
            durationStr=self.config.history_duration,
            barSizeSetting=self.config.bar_size,
            whatToShow='TRADES',
            useRTH=True,
            formatDate=1
        )
        if not bars:
            raise ValueError("No historical data returned; check contract details or market status.")
        df = util.df(bars)
        df.set_index('date', inplace=True)
        self.data = df
        if self.config.verbose:
            print(f"Fetched {len(df)} historical bars.")

    def compute_indicators(self) -> None:
        """Compute moving averages and signals on the stored bar data."""
        if self.data.empty:
            return
        df = self.data.copy()
        df['sma_short'] = df['close'].rolling(window=self.config.short_window).mean()
        df['sma_long'] = df['close'].rolling(window=self.config.long_window).mean()
        df['signal'] = 0
        # Generate signals: 1 for buy, -1 for sell when MA crossover occurs
        df['signal'][self.config.long_window:] = (
            (df['sma_short'][self.config.long_window:] > df['sma_long'][self.config.long_window:]).astype(int) * 2 - 1
        )
        self.data = df

    def latest_signal(self) -> int:
        """Return the latest trading signal (1 for long, -1 for short, 0 for flat)."""
        if 'signal' not in self.data.columns or self.data.empty:
            return 0
        return int(self.data['signal'].iloc[-1])

    async def on_bar_update(self, bars) -> None:
        """Callback for when a new bar is received."""
        bar_df = util.df([bars]).set_index('date')
        self.data = pd.concat([self.data, bar_df])
        # Keep only the necessary number of bars for indicator calculation
        max_lookback = max(self.config.short_window, self.config.long_window)
        if len(self.data) > max_lookback * 3:  # keep some buffer
            self.data = self.data.iloc[-max_lookback * 3:]
        self.compute_indicators()
        await self.execute_trade()

    async def execute_trade(self) -> None:
        """Check signals and execute trades accordingly."""
        signal = self.latest_signal()
        if self.config.verbose:
            ts = self.data.index[-1].strftime("%Y-%m-%d %H:%M:%S")
            last_price = self.data['close'].iloc[-1]
            print(f"[{ts}] Last price: {last_price:.2f}, Signal: {signal}, Position: {self.position}")
        # Determine desired position based on signal
        desired_position = signal * self.config.order_size
        # Clip desired position to the maximum allowed by risk management
        desired_position = max(-self.config.max_position, min(self.config.max_position, desired_position))
        delta = desired_position - self.position
        if delta == 0:
            return  # no change required
        # Determine order action
        action = 'BUY' if delta > 0 else 'SELL'
        quantity = abs(delta)
        order = Order(action=action, totalQuantity=quantity, orderType='MKT')
        if self.config.verbose:
            print(f"Placing order: {action} {quantity} contracts")
        trade = self.ib.placeOrder(self.contract, order)
        # Wait until the order is filled or cancelled
        while not trade.isDone():
            await asyncio.sleep(0.1)
        # Update internal position state
        if action == 'BUY':
            self.position += quantity
        else:
            self.position -= quantity
        if self.config.verbose:
            print(f"New position: {self.position}")

    async def run(self) -> None:
        """Main loop for running the trading bot."""
        await self.connect()
        try:
            await self.fetch_historical_data()
            self.compute_indicators()
            # Subscribe to real‑time bars
            self.ib.pendingTickersEvent += lambda tickers: None  # keep event loop awake
            bar_subscription = self.ib.reqRealTimeBars(
                self.contract,
                barSize=5,  # 5 second bars for more timely signal evaluation
                whatToShow='TRADES',
                useRTH=True,
                realTimeBarsOptions=[]
            )
            bar_subscription.updateEvent += lambda bars, hasNew: self.loop.create_task(self.on_bar_update(bars))
            if self.config.verbose:
                print("Subscribed to real‑time bars.")
            # Run until end_time (if specified)
            if self.config.end_time:
                end_dt = dt.datetime.combine(dt.date.today(), dt.datetime.strptime(self.config.end_time, "%H:%M").time())
                while dt.datetime.now() < end_dt:
                    await asyncio.sleep(1)
            else:
                # run indefinitely; in real usage you might implement graceful shutdown here
                while True:
                    await asyncio.sleep(1)
        finally:
            await self.disconnect()


def main() -> None:
    """Entry point for the script."""
    config = BotConfig()
    bot = FuturesTradingBot(config)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        print("Interrupted by user. Shutting down.")


if __name__ == "__main__":
    main()