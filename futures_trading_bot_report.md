# Futures Trading Bot – Design & Usage

This report outlines the design rationale behind the provided Python-based futures trading bot and offers guidance on how to deploy it responsibly.  The goal is to supply a clear, well-documented example that demonstrates the mechanics of building a basic automated trading system without taking on live execution risk.  **Use this code in a simulated or paper-trading environment only.**

## Why Interactive Brokers & ib_insync?

Interactive Brokers (IB) is a widely adopted brokerage that offers robust support for futures trading and a well‑documented API.  When connecting to IB’s Trader Workstation (TWS) or IB Gateway, the API listens on specific ports:  the default port for paper (simulated) TWS sessions is **7497**, while the live trading port is **7496**; for IB Gateway, the ports are **4002** and **4001** respectively【410194285314290†L106-L113】.  The trading bot connects to `127.0.0.1:7497` by default, so it will talk to a locally running paper‑trading TWS or gateway.

The bot uses the **ib_insync** library, which wraps IB’s `ibapi` into an asynchronous Python interface.  This simplifies the connection, event handling, and order management aspects of the API.

## Core Components

The bot is implemented in `futures_trading_bot.py` and organised around a few key components:

| Component | Description |
| --- | --- |
| `BotConfig` | A dataclass that stores configuration parameters: IB connection details (`host`, `port`, `client_id`), contract specifications (`symbol`, `exchange`, `last_trade_date_or_contract_month`), strategy parameters (bar size, look‑back duration, short/long moving average windows), order size, risk limits, and logging controls.  This makes it easy to customise the bot without editing the core logic. |
| `FuturesTradingBot` | Encapsulates the trading logic.  On startup it connects to IB, fetches historical bar data, computes moving averages, and subscribes to real‑time bars.  Each time a new bar arrives the bot updates its data frame, recalculates indicators, and decides whether to place an order based on a simple moving average crossover strategy. |
| `compute_indicators()` | Calculates short and long simple moving averages on the close prices and derives a signal (`+1` for long, `−1` for short) once enough data is available. |
| `execute_trade()` | Determines the difference between the current position and the desired position implied by the most recent signal.  It places market orders (via `ib.placeOrder`) to correct any mismatch, subject to the maximum position limit.  All order placement occurs in a paper‑trading environment by default. |
| `run()` | Orchestrates the overall workflow: connecting to IB, obtaining historical data, subscribing to real‑time bars, running the strategy loop until a specified end time or indefinitely, and then disconnecting gracefully. |

## Strategy & Risk Controls

The example strategy uses a **moving average crossover**: when the short moving average rises above the long moving average, the bot goes long; when it drops below, it goes short.  It trades a fixed number of contracts defined by `order_size`.  A `max_position` parameter prevents the bot from exceeding a pre‑set exposure, ensuring that it does not pyramid positions uncontrollably.  All order submissions are market orders for simplicity.  Although this is a simplistic approach, it illustrates how to tie data analysis to order execution.

The code includes verbose logging to print the time, last price, current signal, and position on each bar update.  This is intended to aid debugging and monitoring, rather than to serve as a full‑fledged audit trail.

## Limitations & Safety Considerations

1. **Educational use only:** The strategy is rudimentary and does not account for commissions, slippage, or more sophisticated risk management.  It is not suitable for live trading without significant enhancements and testing.
2. **Paper trading by default:** Because of the default port (`7497` for paper TWS)【410194285314290†L106-L113】, the bot connects to a simulated IB session.  Transitioning to a live account would require changing the port and ensuring regulatory compliance; this is discouraged in this example.
3. **No guarantee of profit:** There is no assurance that the moving average strategy will be profitable.  Users should treat this as a learning tool.
4. **Requires running TWS/Gateway:** You must have IB’s TWS or Gateway running locally with API access enabled.  Without this, the bot cannot connect and will throw a connection error.

## Getting Started

1. Install dependencies listed in `requirements.txt` (`ib_insync` and `pandas`).
2. Launch IB Trader Workstation or Gateway in paper mode and ensure the API is enabled on port 7497.
3. Adjust `BotConfig` in `futures_trading_bot.py` to match the contract you want to trade (e.g., ES futures), the date/contract month, and your preferred moving average windows.  Make sure the contract month is current or in the future; expired contracts will not stream data.
4. Run the script with `python futures_trading_bot.py`.  The bot will connect, fetch historical data, compute indicators, and start processing real‑time bars.
5. Monitor the console output.  Orders will be placed only in the simulated environment by default.

## Final Thoughts

This bot demonstrates a minimal end‑to‑end pipeline for algorithmic futures trading using the Interactive Brokers API.  By exposing configuration via a dataclass and using the asynchronous `ib_insync` wrapper, it remains flexible and relatively easy to extend.  Nevertheless, serious trading requires more robust error handling, risk management, and thorough backtesting.  The example code should serve as a scaffold for further experimentation rather than a plug‑and‑play trading solution.