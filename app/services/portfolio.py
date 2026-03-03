# -------------------------------------------------------------------
# portfolio.py — Portfolio tracking and P&L calculation.
#
# P&L = Profit & Loss. It tells you how much money you've made
# (or lost) on your investments.
#
# UNREALIZED P&L: what you'd make if you sold right now.
#   = (current_price - avg_cost_basis) * shares
#
# Example: You bought 10 shares of Ohtani at $50 each.
#   avg_cost_basis = $50
#   If current price is $60: unrealized P&L = ($60 - $50) * 10 = +$100
#   If current price is $45: unrealized P&L = ($45 - $50) * 10 = -$50
# -------------------------------------------------------------------

from app.services.amm import get_pool_info


def get_portfolio(conn, user_id: int) -> dict:
    """
    Get a user's full portfolio: cash balance, holdings, and P&L.
    """
    cursor = conn.cursor()

    # Get user info
    cursor.execute("SELECT id, username, balance FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise ValueError(f"User {user_id} not found.")

    # Get all holdings with player info
    cursor.execute("""
        SELECT h.player_id, h.shares, h.avg_cost_basis,
               p.name, p.team, p.position
        FROM holdings h
        JOIN players p ON h.player_id = p.id
        WHERE h.user_id = ? AND h.shares > 0
        ORDER BY h.shares * h.avg_cost_basis DESC
    """, (user_id,))

    holdings = []
    total_holdings_value = 0
    total_unrealized_pnl = 0

    for row in cursor.fetchall():
        pool = get_pool_info(conn, row["player_id"])
        current_price = pool["spot_price"] if pool else 0

        market_value = current_price * row["shares"]
        cost_basis_total = row["avg_cost_basis"] * row["shares"]
        unrealized_pnl = market_value - cost_basis_total
        pnl_percent = ((current_price - row["avg_cost_basis"]) / row["avg_cost_basis"] * 100
                       if row["avg_cost_basis"] > 0 else 0)

        holdings.append({
            "player_id": row["player_id"],
            "player_name": row["name"],
            "team": row["team"],
            "position": row["position"],
            "shares": row["shares"],
            "avg_cost_basis": round(row["avg_cost_basis"], 2),
            "current_price": current_price,
            "market_value": round(market_value, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
        })

        total_holdings_value += market_value
        total_unrealized_pnl += unrealized_pnl

    return {
        "user_id": user["id"],
        "username": user["username"],
        "cash_balance": round(user["balance"], 2),
        "holdings_value": round(total_holdings_value, 2),
        "total_portfolio_value": round(user["balance"] + total_holdings_value, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "holdings": holdings,
    }


def get_trade_history(conn, user_id: int, limit: int = 50) -> list:
    """Get a user's recent trades."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT t.id, t.player_id, p.name as player_name,
               t.price, t.quantity, t.trade_type, t.created_at,
               CASE
                   WHEN t.buyer_id = ? THEN 'buy'
                   ELSE 'sell'
               END as side,
               t.price * t.quantity as total
        FROM trades t
        JOIN players p ON t.player_id = p.id
        WHERE t.buyer_id = ? OR t.seller_id = ?
        ORDER BY t.created_at DESC
        LIMIT ?
    """, (user_id, user_id, user_id, limit))

    return [dict(row) for row in cursor.fetchall()]
