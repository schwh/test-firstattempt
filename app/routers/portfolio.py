# -------------------------------------------------------------------
# routers/portfolio.py — API endpoints for portfolio and trade history.
#
# Endpoints:
#   GET /users/{user_id}/portfolio — Full portfolio with P&L
#   GET /users/{user_id}/trades    — Trade history
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.services import portfolio as portfolio_service


def register_routes(app):
    """Register portfolio-related routes on the app."""

    @app.get("/users/{user_id}/portfolio")
    def get_portfolio(request):
        """
        Get a user's full portfolio.

        Returns cash balance, all holdings with current values,
        and unrealized P&L for each position.
        """
        user_id = int(request["path_params"]["user_id"])
        conn = get_connection()
        try:
            result = portfolio_service.get_portfolio(conn, user_id)
            return result
        finally:
            conn.close()

    @app.get("/users/{user_id}/trades")
    def get_trades(request):
        """Get a user's trade history."""
        user_id = int(request["path_params"]["user_id"])
        limit = int(request["query_params"].get("limit", 50))
        conn = get_connection()
        try:
            trades = portfolio_service.get_trade_history(conn, user_id, limit)
            return {"trades": trades, "count": len(trades)}
        finally:
            conn.close()
