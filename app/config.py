# -------------------------------------------------------------------
# config.py — Central settings for the entire app.
#
# Everything tunable lives here so you only have one place to change.
# -------------------------------------------------------------------

import os

# -- Database -------------------------------------------------------
# SQLite stores everything in a single file. Easy to reset: just
# delete this file and restart the server.
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "diamond_hands.db")

# -- User Defaults --------------------------------------------------
# Every new user starts with this much fantasy cash.
STARTING_BALANCE = 10_000.00  # $10,000 fantasy dollars

# -- AMM Settings ---------------------------------------------------
# Fee charged on every AMM trade (0.003 = 0.3%).
# The fee stays in the pool, slowly deepening liquidity.
AMM_FEE = 0.003

# Default number of "shares" in each AMM pool at creation.
# More tokens = less price impact per trade (deeper liquidity).
AMM_DEFAULT_TOKEN_RESERVE = 1000

# Safety limit: you can't buy more than this fraction of the pool
# in a single trade (prevents division-by-zero edge cases).
AMM_MAX_BUY_FRACTION = 0.90  # 90% of pool

# -- Server ---------------------------------------------------------
HOST = "0.0.0.0"
PORT = 8000
