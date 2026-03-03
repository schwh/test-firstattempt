# -------------------------------------------------------------------
# routers/players.py — API endpoints for browsing MLB players.
#
# Endpoints:
#   GET /players              — List all players (with optional search)
#   GET /players/{player_id}  — Get one player's full details + price
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.services.amm import get_pool_info


def register_routes(app):
    """Register player-related routes on the app."""

    @app.get("/players")
    def list_players(request):
        """
        List all players, optionally filtered by name or team.

        Query params:
            ?search=ohtani  — filter by name (case-insensitive)
            ?team=LAD       — filter by team
            ?sort=price     — sort by current price (default: name)
        """
        conn = get_connection()
        cursor = conn.cursor()

        search = request["query_params"].get("search", "")
        team = request["query_params"].get("team", "")
        sort = request["query_params"].get("sort", "name")

        query = "SELECT * FROM players WHERE 1=1"
        params = []

        if search:
            query += " AND LOWER(name) LIKE ?"
            params.append(f"%{search.lower()}%")

        if team:
            query += " AND UPPER(team) = ?"
            params.append(team.upper())

        query += " ORDER BY name ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        players = []
        for row in rows:
            pool = get_pool_info(conn, row["id"])
            player = {
                "id": row["id"],
                "name": row["name"],
                "team": row["team"],
                "position": row["position"],
                "price": pool["spot_price"] if pool else 0,
                "stats": {},
            }
            # Add stats based on position (batter vs pitcher)
            if row["batting_avg"] is not None:
                player["stats"]["batting_avg"] = row["batting_avg"]
                player["stats"]["home_runs"] = row["home_runs"]
                player["stats"]["rbi"] = row["rbi"]
            if row["era"] is not None:
                player["stats"]["era"] = row["era"]
                player["stats"]["wins"] = row["wins"]
                player["stats"]["strikeouts"] = row["strikeouts"]

            players.append(player)

        # Sort by price if requested
        if sort == "price":
            players.sort(key=lambda p: p["price"], reverse=True)

        conn.close()
        return {"players": players, "count": len(players)}

    @app.get("/players/{player_id}")
    def get_player(request):
        """Get detailed info about a single player including price data."""
        player_id = int(request["path_params"]["player_id"])
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM players WHERE id = ?", (player_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            raise ValueError(f"Player {player_id} not found.")

        pool = get_pool_info(conn, player_id)

        # Get recent price history
        cursor.execute("""
            SELECT price, source, recorded_at
            FROM price_history
            WHERE player_id = ?
            ORDER BY recorded_at DESC
            LIMIT 50
        """, (player_id,))
        price_history = [dict(r) for r in cursor.fetchall()]

        # Get recent trades
        cursor.execute("""
            SELECT t.price, t.quantity, t.trade_type, t.created_at
            FROM trades t
            WHERE t.player_id = ?
            ORDER BY t.created_at DESC
            LIMIT 20
        """, (player_id,))
        recent_trades = [dict(r) for r in cursor.fetchall()]

        player = {
            "id": row["id"],
            "name": row["name"],
            "team": row["team"],
            "position": row["position"],
            "stats": {},
            "price": pool["spot_price"] if pool else 0,
            "pool": pool,
            "price_history": price_history,
            "recent_trades": recent_trades,
        }

        if row["batting_avg"] is not None:
            player["stats"]["batting_avg"] = row["batting_avg"]
            player["stats"]["home_runs"] = row["home_runs"]
            player["stats"]["rbi"] = row["rbi"]
        if row["era"] is not None:
            player["stats"]["era"] = row["era"]
            player["stats"]["wins"] = row["wins"]
            player["stats"]["strikeouts"] = row["strikeouts"]

        conn.close()
        return player
