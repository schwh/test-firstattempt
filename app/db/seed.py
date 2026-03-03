# -------------------------------------------------------------------
# seed.py — Populates the database with sample MLB players.
#
# Each player gets an AMM pool. The initial price is set by the
# ratio: price = currency_reserve / token_reserve.
#
# Players are organized into tiers based on star power:
#   Tier 1 (Superstars): $50-80/share
#   Tier 2 (All-Stars):  $30-50/share
#   Tier 3 (Starters):   $15-30/share
#   Tier 4 (Prospects):  $5-15/share
#
# Stats are approximate and for demonstration purposes.
# In a real app, you'd pull these from a stats API.
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.config import AMM_DEFAULT_TOKEN_RESERVE

# Each tuple: (name, team, position, batting_avg, HR, RBI, ERA, wins, K, initial_price)
# For batters: ERA, wins, strikeouts are None
# For pitchers: batting_avg, HR, RBI are None

PLAYERS = [
    # ============ TIER 1: SUPERSTARS ($50-80) ============
    ("Shohei Ohtani",     "LAD", "DH",    0.304, 54, 130, None, None, None,   75.00),
    ("Aaron Judge",       "NYY", "RF",    0.322, 58, 144, None, None, None,   70.00),
    ("Mookie Betts",      "LAD", "SS",    0.289, 29, 82,  None, None, None,   60.00),
    ("Ronald Acuna Jr.",  "ATL", "RF",    0.281, 24, 69,  None, None, None,   55.00),
    ("Trea Turner",       "PHI", "SS",    0.295, 21, 76,  None, None, None,   50.00),

    # ============ TIER 2: ALL-STARS ($30-50) ============
    ("Freddie Freeman",   "LAD", "1B",    0.282, 22, 98,  None, None, None,   45.00),
    ("Julio Rodriguez",   "SEA", "CF",    0.275, 28, 85,  None, None, None,   42.00),
    ("Corey Seager",      "TEX", "SS",    0.285, 33, 100, None, None, None,   40.00),
    ("Bobby Witt Jr.",    "KC",  "SS",    0.290, 30, 95,  None, None, None,   38.00),
    ("Corbin Burnes",     "ARI", "SP",    None,  None, None, 2.92, 15, 220,   35.00),
    ("Gerrit Cole",       "NYY", "SP",    None,  None, None, 3.41, 13, 205,   33.00),

    # ============ TIER 3: SOLID STARTERS ($15-30) ============
    ("Pete Alonso",       "NYM", "1B",    0.240, 35, 88,  None, None, None,   28.00),
    ("Adley Rutschman",   "BAL", "C",     0.260, 20, 78,  None, None, None,   25.00),
    ("CJ Abrams",         "WSH", "SS",    0.270, 18, 65,  None, None, None,   22.00),
    ("Marcus Semien",     "TEX", "2B",    0.265, 25, 82,  None, None, None,   20.00),
    ("Gunnar Henderson",  "BAL", "SS",    0.282, 28, 85,  None, None, None,   27.00),
    ("Zack Wheeler",      "PHI", "SP",    None,  None, None, 3.07, 12, 195,   23.00),
    ("Logan Webb",        "SF",  "SP",    None,  None, None, 3.25, 14, 175,   18.00),

    # ============ TIER 4: PROSPECTS/VALUE ($5-15) ============
    ("Jackson Merrill",   "SD",  "CF",    0.265, 15, 55,  None, None, None,   12.00),
    ("Paul Skenes",       "PIT", "SP",    None,  None, None, 1.96, 11, 170,   15.00),
    ("Jackson Chourio",   "MIL", "RF",    0.255, 18, 62,  None, None, None,   10.00),
    ("Evan Carter",       "TEX", "LF",    0.248, 12, 45,  None, None, None,   8.00),
    ("Wyatt Langford",    "TEX", "RF",    0.252, 14, 50,  None, None, None,   7.00),
]


def seed_database():
    """
    Insert all players and their AMM pools into the database.

    This is safe to run multiple times — it skips if data already exists.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # Check if we already have players (don't double-seed)
    cursor.execute("SELECT COUNT(*) FROM players")
    count = cursor.fetchone()[0]
    if count > 0:
        print(f"Database already has {count} players. Skipping seed.")
        conn.close()
        return

    print("Seeding database with MLB players...")

    for player_data in PLAYERS:
        (name, team, position, batting_avg, hr, rbi,
         era, wins, strikeouts, initial_price) = player_data

        # Insert the player
        cursor.execute("""
            INSERT INTO players (name, team, position, batting_avg, home_runs, rbi, era, wins, strikeouts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (name, team, position, batting_avg, hr, rbi, era, wins, strikeouts))

        player_id = cursor.lastrowid

        # Create the AMM pool for this player.
        # token_reserve = 1000 shares in the pool
        # currency_reserve = 1000 * initial_price
        # So: price = currency_reserve / token_reserve = initial_price
        token_reserve = AMM_DEFAULT_TOKEN_RESERVE
        currency_reserve = token_reserve * initial_price

        cursor.execute("""
            INSERT INTO amm_pools (player_id, token_reserve, currency_reserve)
            VALUES (?, ?, ?)
        """, (player_id, token_reserve, currency_reserve))

        # Record the initial price in history
        cursor.execute("""
            INSERT INTO price_history (player_id, price, source)
            VALUES (?, ?, 'snapshot')
        """, (player_id, initial_price))

        print(f"  Added {name} ({team}) — ${initial_price:.2f}/share")

    conn.commit()
    conn.close()
    print(f"Seeded {len(PLAYERS)} players successfully!")
