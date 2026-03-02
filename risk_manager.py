"""
risk_manager.py
Enforces daily drawdown limits and loss cooldown.

Per the video strategy:
- NO cap on trades per session — take every good setup
- Daily drawdown halt is kept (protects account from catastrophic loss)
- Loss cooldown is kept (prevents immediate re-entry into same-direction losses)
"""

import threading
from datetime import datetime, date

from config import MAX_DAILY_DRAWDOWN_PCT, LOSS_COOLDOWN_CANDLES
from logger import logger


class RiskManager:
    """
    Tracks intra-day risk state.
    Thread-safe via a reentrant lock.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._starting_balance: float = 0.0
        self._candles_since_loss: int = LOSS_COOLDOWN_CANDLES  # start ready to trade
        self._trading_halted: bool = False
        self._reset_date: date = date.today()

    def set_starting_balance(self, balance: float) -> None:
        """Call once when the trading day begins or when connecting."""
        with self._lock:
            self._starting_balance = balance
            self._reset_if_new_day()

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if today != self._reset_date:
            self._candles_since_loss = LOSS_COOLDOWN_CANDLES
            self._trading_halted = False
            self._reset_date = today
            logger.info("Risk state reset for new trading day.")

    def record_trade_opened(self) -> None:
        """Call when a trade is opened (for logging/state tracking)."""
        with self._lock:
            self._reset_if_new_day()

    def record_loss(self) -> None:
        """Call when a trade closes as a loss."""
        with self._lock:
            self._candles_since_loss = 0
            logger.info(f"Loss recorded. Cooldown: waiting {LOSS_COOLDOWN_CANDLES} candles before next entry.")

    def record_win(self) -> None:
        """Call when a trade closes as a win."""
        with self._lock:
            self._candles_since_loss = LOSS_COOLDOWN_CANDLES  # no cooldown after win

    def tick_candle(self) -> None:
        """Call on each new M1 candle close."""
        with self._lock:
            self._reset_if_new_day()
            if self._candles_since_loss < LOSS_COOLDOWN_CANDLES:
                self._candles_since_loss += 1

    def check_drawdown(self, current_equity: float) -> bool:
        """
        Returns True if within drawdown limits.
        Returns False (and halts trading) if daily drawdown limit exceeded.
        """
        with self._lock:
            self._reset_if_new_day()
            if self._starting_balance <= 0:
                return True
            drawdown = (self._starting_balance - current_equity) / self._starting_balance
            if drawdown >= MAX_DAILY_DRAWDOWN_PCT:
                if not self._trading_halted:
                    logger.warning(
                        f"Daily drawdown limit reached: {drawdown*100:.1f}% >= "
                        f"{MAX_DAILY_DRAWDOWN_PCT*100:.1f}%. Trading halted."
                    )
                    self._trading_halted = True
                return False
            return True

    def can_trade(self, current_equity: float) -> tuple[bool, str]:
        """
        Master gate. Returns (True, "") if all conditions pass,
        or (False, reason) if blocked.

        NOTE: No MAX_TRADES_PER_SESSION check — video strategy says
        take trades whenever a valid setup appears, no artificial cap.
        """
        with self._lock:
            self._reset_if_new_day()

            if self._trading_halted:
                return False, "Daily drawdown limit exceeded. Trading halted."

            if not self.check_drawdown(current_equity):
                return False, "Daily drawdown limit exceeded."

            if self._candles_since_loss < LOSS_COOLDOWN_CANDLES:
                remaining = LOSS_COOLDOWN_CANDLES - self._candles_since_loss
                return False, f"Loss cooldown active. {remaining} candle(s) remaining."

            return True, ""

    def force_halt(self) -> None:
        with self._lock:
            self._trading_halted = True
            logger.warning("Trading force-halted by operator.")

    def resume(self) -> None:
        with self._lock:
            self._trading_halted = False
            logger.info("Trading resumed by operator.")

    @property
    def is_halted(self) -> bool:
        with self._lock:
            return self._trading_halted