# -------------------------------------------------------------------
# routers/users.py — API endpoints for user management.
#
# Endpoints:
#   POST /users          — Create a new user (gets $10,000 starting cash)
#   GET  /users/{user_id} — Get user profile and balance
# -------------------------------------------------------------------

from app.db.database import get_connection
from app.config import STARTING_BALANCE


def register_routes(app):
    """Register user-related routes on the app."""

    @app.post("/users")
    def create_user(request):
        """
        Create a new user.

        Body: {"username": "mike_trout_fan"}
        Returns: the new user with their starting balance.
        """
        username = request["body"].get("username", "").strip()
        if not username:
            raise ValueError("Username is required.")
        if len(username) < 3:
            raise ValueError("Username must be at least 3 characters.")
        if len(username) > 30:
            raise ValueError("Username must be 30 characters or less.")

        conn = get_connection()
        cursor = conn.cursor()

        # Check if username already taken
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            conn.close()
            raise ValueError(f"Username '{username}' is already taken.")

        cursor.execute(
            "INSERT INTO users (username, balance) VALUES (?, ?)",
            (username, STARTING_BALANCE)
        )
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "id": user_id,
            "username": username,
            "balance": STARTING_BALANCE,
            "message": f"Welcome! You start with ${STARTING_BALANCE:,.2f} in fantasy cash.",
        }

    @app.get("/users/{user_id}")
    def get_user(request):
        """Get a user's profile and current balance."""
        user_id = int(request["path_params"]["user_id"])
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            raise ValueError(f"User {user_id} not found.")

        conn.close()
        return {
            "id": user["id"],
            "username": user["username"],
            "balance": round(user["balance"], 2),
            "created_at": user["created_at"],
        }
