# -------------------------------------------------------------------
# main.py — The entry point for Diamond Hands MLB.
#
# This file:
#   1. Creates the database tables (if they don't exist)
#   2. Seeds sample MLB player data (if empty)
#   3. Registers all API routes
#   4. Starts the HTTP server
#
# Run with: python -m app.main
# -------------------------------------------------------------------

from app.server import Router, create_server
from app.db.database import create_tables
from app.db.seed import seed_database
from app.config import HOST, PORT

# Import route registrars
from app.routers import players, users, trading, portfolio, market


def build_app() -> Router:
    """Create the app and register all routes."""
    app = Router()

    # Register a welcome endpoint
    @app.get("/")
    def index(request):
        return {
            "name": "Diamond Hands MLB",
            "description": "Virtual stock market for MLB players",
            "version": "0.1.0",
            "endpoints": {
                "GET /players": "List all players",
                "GET /players/{id}": "Get player details + price",
                "GET /players/{id}/orderbook": "View order book",
                "POST /users": "Create a new user",
                "GET /users/{id}": "Get user profile",
                "GET /users/{id}/portfolio": "Get portfolio with P&L",
                "GET /users/{id}/trades": "Get trade history",
                "POST /trade/market": "Execute market buy/sell",
                "POST /trade/limit": "Place a limit order",
                "GET /trade/orders/{user_id}": "Get open orders",
                "DELETE /trade/orders/{id}?user_id=X": "Cancel order",
                "GET /trade/quote/{player_id}?side=buy&quantity=10": "Get price quote",
                "GET /market/overview": "All players ranked by price",
                "GET /market/movers": "Top gainers and losers",
            },
        }

    # Register all route modules
    players.register_routes(app)
    users.register_routes(app)
    trading.register_routes(app)
    portfolio.register_routes(app)
    market.register_routes(app)

    return app


def main():
    """Initialize database, seed data, and start the server."""
    print("=" * 55)
    print("  Diamond Hands MLB — Virtual Player Stock Market")
    print("=" * 55)
    print()

    # Step 1: Create tables
    print("[1/3] Setting up database...")
    create_tables()

    # Step 2: Seed player data
    print("[2/3] Checking seed data...")
    seed_database()

    # Step 3: Start the server
    print(f"[3/3] Starting server on http://{HOST}:{PORT}")
    print()
    print("API is ready! Try these:")
    print(f"  curl http://localhost:{PORT}/players")
    print(f"  curl http://localhost:{PORT}/market/overview")
    print(f"  curl -X POST http://localhost:{PORT}/users -d '{{\"username\":\"test\"}}'")
    print()
    print("Press Ctrl+C to stop.")
    print("-" * 55)

    app = build_app()
    server = create_server(app, HOST, PORT)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
