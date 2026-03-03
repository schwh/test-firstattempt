# -------------------------------------------------------------------
# routers/trading.py — API endpoints for buying and selling.
#
# Endpoints:
#   POST /trade/market         — Execute a market buy or sell
#   POST /trade/limit          — Place a limit order
#   GET  /trade/orders/{user_id} — Get a user's open orders
#   DELETE /trade/orders/{order_id} — Cancel a limit order
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.services import trading as trading_service
from app.services.amm import get_pool_info


def register_routes(app):
    """Register trading-related routes on the app."""

    @app.post("/trade/market")
    def market_trade(request):
        """
        Execute a market order (buy or sell at best available price).

        Body: {
            "user_id": 1,
            "player_id": 1,
            "side": "buy",    // "buy" or "sell"
            "quantity": 10
        }
        """
        body = request["body"]
        user_id = body.get("user_id")
        player_id = body.get("player_id")
        side = body.get("side", "").lower()
        quantity = body.get("quantity")

        if not all([user_id, player_id, side, quantity]):
            raise ValueError("Required fields: user_id, player_id, side, quantity")
        if side not in ("buy", "sell"):
            raise ValueError("Side must be 'buy' or 'sell'.")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        conn = get_connection()
        try:
            if side == "buy":
                result = trading_service.execute_market_buy(
                    conn, int(user_id), int(player_id), int(quantity)
                )
            else:
                result = trading_service.execute_market_sell(
                    conn, int(user_id), int(player_id), int(quantity)
                )
            return result
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    @app.post("/trade/limit")
    def limit_order(request):
        """
        Place a limit order.

        Body: {
            "user_id": 1,
            "player_id": 1,
            "side": "buy",
            "price": 48.50,
            "quantity": 10
        }
        """
        body = request["body"]
        user_id = body.get("user_id")
        player_id = body.get("player_id")
        side = body.get("side", "").lower()
        price = body.get("price")
        quantity = body.get("quantity")

        if not all([user_id, player_id, side, price, quantity]):
            raise ValueError("Required fields: user_id, player_id, side, price, quantity")
        if side not in ("buy", "sell"):
            raise ValueError("Side must be 'buy' or 'sell'.")
        if not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")
        if price <= 0:
            raise ValueError("Price must be positive.")

        conn = get_connection()
        try:
            result = trading_service.place_limit_order(
                conn, int(user_id), int(player_id), side, float(price), int(quantity)
            )
            return result
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    @app.get("/trade/orders/{user_id}")
    def get_user_orders(request):
        """Get all open/partial orders for a user."""
        user_id = int(request["path_params"]["user_id"])
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT o.*, p.name as player_name
            FROM orders o
            JOIN players p ON o.player_id = p.id
            WHERE o.user_id = ? AND o.status IN ('open', 'partial')
            ORDER BY o.created_at DESC
        """, (user_id,))

        orders = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {"orders": orders, "count": len(orders)}

    @app.delete("/trade/orders/{order_id}")
    def cancel_order(request):
        """
        Cancel a limit order.

        Query params: ?user_id=1  (to verify ownership)
        """
        order_id = int(request["path_params"]["order_id"])
        user_id = request["query_params"].get("user_id")
        if not user_id:
            raise ValueError("user_id query parameter is required.")

        conn = get_connection()
        try:
            result = trading_service.cancel_order(conn, int(user_id), order_id)
            return result
        except Exception as e:
            conn.rollback()
            raise
        finally:
            conn.close()

    @app.get("/trade/quote/{player_id}")
    def get_quote(request):
        """
        Get a price quote for a potential trade (without executing it).

        Query params: ?side=buy&quantity=10
        """
        player_id = int(request["path_params"]["player_id"])
        side = request["query_params"].get("side", "buy")
        quantity = int(request["query_params"].get("quantity", 1))

        conn = get_connection()
        pool = get_pool_info(conn, player_id)
        if not pool:
            conn.close()
            raise ValueError(f"Player {player_id} not found.")

        from app.services.amm import calculate_buy_cost, calculate_sell_revenue

        if side == "buy":
            result = calculate_buy_cost(
                pool["token_reserve"], pool["currency_reserve"], quantity
            )
            conn.close()
            return {
                "side": "buy",
                "quantity": quantity,
                "estimated_cost": result["total_cost"],
                "avg_price": result["avg_price"],
                "price_impact": result["price_impact"],
                "fee": result["fee"],
                "spot_price": pool["spot_price"],
            }
        else:
            result = calculate_sell_revenue(
                pool["token_reserve"], pool["currency_reserve"], quantity
            )
            conn.close()
            return {
                "side": "sell",
                "quantity": quantity,
                "estimated_revenue": result["total_revenue"],
                "avg_price": result["avg_price"],
                "price_impact": result["price_impact"],
                "fee": result["fee"],
                "spot_price": pool["spot_price"],
            }
