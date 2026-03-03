# -------------------------------------------------------------------
# routers/market.py — Market overview and leaderboard endpoints.
#
# Endpoints:
#   GET /market/overview  — All players ranked by price
#   GET /market/movers    — Biggest price changes
#   GET /players/{player_id}/orderbook — View the order book
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.services.amm import get_pool_info
from app.services.order_book import get_order_book


def register_routes(app):
    """Register market-related routes on the app."""

    @app.get("/market/overview")
    def market_overview(request):
        """
        Market overview — all players with current prices.

        Like a stock ticker: see every player's current price at a glance.
        Sorted by price descending (most valuable first).
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, team, position FROM players ORDER BY name")
        players = []

        for row in cursor.fetchall():
            pool = get_pool_info(conn, row["id"])
            price = pool["spot_price"] if pool else 0

            # Get price change from first recorded price
            cursor.execute("""
                SELECT price FROM price_history
                WHERE player_id = ?
                ORDER BY recorded_at ASC LIMIT 1
            """, (row["id"],))
            first = cursor.fetchone()
            initial_price = first["price"] if first else price

            change = price - initial_price
            change_pct = (change / initial_price * 100) if initial_price > 0 else 0

            players.append({
                "id": row["id"],
                "name": row["name"],
                "team": row["team"],
                "position": row["position"],
                "price": price,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            })

        # Sort by price, highest first
        players.sort(key=lambda p: p["price"], reverse=True)

        conn.close()
        return {"players": players, "count": len(players)}

    @app.get("/market/movers")
    def market_movers(request):
        """
        Top gainers and losers — players with the biggest price swings.
        """
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT id, name, team, position FROM players")
        players = []

        for row in cursor.fetchall():
            pool = get_pool_info(conn, row["id"])
            price = pool["spot_price"] if pool else 0

            cursor.execute("""
                SELECT price FROM price_history
                WHERE player_id = ?
                ORDER BY recorded_at ASC LIMIT 1
            """, (row["id"],))
            first = cursor.fetchone()
            initial_price = first["price"] if first else price

            change = price - initial_price
            change_pct = (change / initial_price * 100) if initial_price > 0 else 0

            players.append({
                "id": row["id"],
                "name": row["name"],
                "team": row["team"],
                "price": price,
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            })

        # Top 5 gainers and top 5 losers
        players.sort(key=lambda p: p["change_pct"], reverse=True)
        gainers = [p for p in players if p["change_pct"] > 0][:5]
        losers = [p for p in reversed(players) if p["change_pct"] < 0][:5]

        conn.close()
        return {"gainers": gainers, "losers": losers}

    @app.get("/players/{player_id}/orderbook")
    def player_orderbook(request):
        """View the limit order book for a player."""
        player_id = int(request["path_params"]["player_id"])
        conn = get_connection()

        pool = get_pool_info(conn, player_id)
        if not pool:
            conn.close()
            raise ValueError(f"Player {player_id} not found.")

        book = get_order_book(conn, player_id)

        conn.close()
        return {
            "player_id": player_id,
            "amm_price": pool["spot_price"],
            "bids": book["bids"],
            "asks": book["asks"],
            "spread": _calculate_spread(book, pool["spot_price"]),
        }


def _calculate_spread(book, amm_price):
    """Calculate the bid-ask spread."""
    best_bid = book["bids"][0]["price"] if book["bids"] else None
    best_ask = book["asks"][0]["price"] if book["asks"] else None

    # If no book orders, spread is based on AMM
    if not best_bid and not best_ask:
        return {"best_bid": amm_price, "best_ask": amm_price, "spread": 0}

    effective_bid = best_bid or amm_price
    effective_ask = best_ask or amm_price

    return {
        "best_bid": effective_bid,
        "best_ask": effective_ask,
        "spread": round(effective_ask - effective_bid, 2),
    }
