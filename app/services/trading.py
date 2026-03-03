# -------------------------------------------------------------------
# trading.py — The hybrid trading engine.
#
# This is the ORCHESTRATOR. When someone wants to trade, this module:
#   1. Checks the order book for matching limit orders
#   2. Fills what it can from the order book
#   3. Sends the rest to the AMM for instant execution
#
# WHY HYBRID?
#   - Order book alone: nobody can trade if the book is empty.
#   - AMM alone: no way to set your own price.
#   - Hybrid: best of both worlds. The AMM guarantees you can
#     always trade, while the order book lets you get better prices
#     when other users are willing to deal.
#
# ALL TRADES ARE ATOMIC:
#   Every trade happens inside a single database transaction.
#   If any step fails, everything rolls back (nothing changes).
#   This prevents bugs like "money left your account but shares
#   never arrived."
# -------------------------------------------------------------------

from app.services import amm as amm_service
from app.services import order_book


def execute_market_buy(conn, user_id: int, player_id: int, quantity: int) -> dict:
    """
    Buy shares at the best available price.

    Order of execution:
      1. Check order book for sell orders cheaper than the AMM price
      2. Fill from those first (cheaper for the buyer)
      3. Any remaining shares: buy from the AMM

    Returns a summary of everything that happened.
    """
    cursor = conn.cursor()

    # --- Validate the user exists and the player exists ---
    cursor.execute("SELECT id, balance FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise ValueError(f"User {user_id} not found.")

    cursor.execute("SELECT id, name FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    if not player:
        raise ValueError(f"Player {player_id} not found.")

    # --- Get the AMM spot price for reference ---
    pool_info = amm_service.get_pool_info(conn, player_id)
    amm_spot_price = pool_info["spot_price"]

    # --- Step 1: Try to fill from the order book ---
    # Only match sell orders priced at or below the AMM price
    # (otherwise the AMM is cheaper, so we skip the book)
    book_fills = order_book.match_buy_against_asks(
        conn, player_id, quantity, max_price=amm_spot_price
    )

    filled_from_book = sum(f["quantity"] for f in book_fills)
    book_cost = sum(f["price"] * f["quantity"] for f in book_fills)
    remaining = quantity - filled_from_book

    # Process book fills: transfer shares from sellers to buyer
    for fill in book_fills:
        _settle_book_trade(
            conn,
            buyer_id=user_id,
            seller_id=fill["seller_id"],
            player_id=player_id,
            price=fill["price"],
            quantity=fill["quantity"],
            trade_type="limit",
        )

    # --- Step 2: Fill remaining from AMM ---
    amm_cost = 0
    amm_result = None
    if remaining > 0:
        amm_result = amm_service.execute_amm_buy(conn, player_id, remaining)
        amm_cost = amm_result["total_cost"]

        # Deduct cash from buyer
        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (amm_cost, user_id)
        )

        # Verify balance didn't go negative
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        if cursor.fetchone()["balance"] < 0:
            raise ValueError(
                f"Insufficient balance. Trade would cost ${book_cost + amm_cost:.2f} "
                f"but you only have ${user['balance']:.2f}."
            )

        # Give shares to buyer
        _add_shares(conn, user_id, player_id, remaining, amm_result["avg_price"])

        # Record AMM trade
        cursor.execute("""
            INSERT INTO trades (buyer_id, seller_id, player_id, price, quantity, trade_type)
            VALUES (?, NULL, ?, ?, ?, 'amm')
        """, (user_id, player_id, amm_result["avg_price"], remaining))

    total_cost = book_cost + amm_cost
    total_shares = quantity

    # Record the new price in history
    new_pool = amm_service.get_pool_info(conn, player_id)
    cursor.execute("""
        INSERT INTO price_history (player_id, price, source)
        VALUES (?, ?, 'trade')
    """, (player_id, new_pool["spot_price"]))

    conn.commit()

    return {
        "action": "buy",
        "player": player["name"],
        "player_id": player_id,
        "total_shares": total_shares,
        "total_cost": round(total_cost, 2),
        "avg_price": round(total_cost / total_shares, 2) if total_shares > 0 else 0,
        "filled_from_book": filled_from_book,
        "filled_from_amm": remaining,
        "book_fills": book_fills,
        "amm_details": amm_result,
        "new_price": new_pool["spot_price"],
    }


def execute_market_sell(conn, user_id: int, player_id: int, quantity: int) -> dict:
    """
    Sell shares at the best available price.

    Mirror of execute_market_buy:
      1. Check order book for buy orders above the AMM price
      2. Fill from those first (better price for the seller)
      3. Any remaining: sell to the AMM
    """
    cursor = conn.cursor()

    # --- Validate ---
    cursor.execute("SELECT id, balance FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    if not user:
        raise ValueError(f"User {user_id} not found.")

    cursor.execute("SELECT id, name FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    if not player:
        raise ValueError(f"Player {player_id} not found.")

    # Check the user actually has enough shares
    cursor.execute(
        "SELECT shares FROM holdings WHERE user_id = ? AND player_id = ?",
        (user_id, player_id)
    )
    holding = cursor.fetchone()
    if not holding or holding["shares"] < quantity:
        available = holding["shares"] if holding else 0
        raise ValueError(
            f"Insufficient shares. You have {available}, trying to sell {quantity}."
        )

    # --- Get AMM spot price ---
    pool_info = amm_service.get_pool_info(conn, player_id)
    amm_spot_price = pool_info["spot_price"]

    # --- Step 1: Fill from order book (bids above AMM price) ---
    book_fills = order_book.match_sell_against_bids(
        conn, player_id, quantity, min_price=amm_spot_price
    )

    filled_from_book = sum(f["quantity"] for f in book_fills)
    book_revenue = sum(f["price"] * f["quantity"] for f in book_fills)
    remaining = quantity - filled_from_book

    # Process book fills
    for fill in book_fills:
        _settle_book_trade_for_sell(
            conn,
            seller_id=user_id,
            buyer_id=fill["buyer_id"],
            player_id=player_id,
            price=fill["price"],
            quantity=fill["quantity"],
            trade_type="limit",
        )

    # --- Step 2: Sell remaining to AMM ---
    amm_revenue = 0
    amm_result = None
    if remaining > 0:
        amm_result = amm_service.execute_amm_sell(conn, player_id, remaining)
        amm_revenue = amm_result["total_revenue"]

        # Give cash to seller
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (amm_revenue, user_id)
        )

        # Remove shares from seller
        _remove_shares(conn, user_id, player_id, remaining)

        # Record AMM trade (NULL buyer = AMM was the buyer)
        cursor.execute("""
            INSERT INTO trades (buyer_id, seller_id, player_id, price, quantity, trade_type)
            VALUES (NULL, ?, ?, ?, ?, 'amm')
        """, (user_id, player_id, amm_result["avg_price"], remaining))

    total_revenue = book_revenue + amm_revenue
    total_shares = quantity

    # Record the new price
    new_pool = amm_service.get_pool_info(conn, player_id)
    cursor.execute("""
        INSERT INTO price_history (player_id, price, source)
        VALUES (?, ?, 'trade')
    """, (player_id, new_pool["spot_price"]))

    conn.commit()

    return {
        "action": "sell",
        "player": player["name"],
        "player_id": player_id,
        "total_shares": total_shares,
        "total_revenue": round(total_revenue, 2),
        "avg_price": round(total_revenue / total_shares, 2) if total_shares > 0 else 0,
        "filled_from_book": filled_from_book,
        "filled_from_amm": remaining,
        "book_fills": book_fills,
        "amm_details": amm_result,
        "new_price": new_pool["spot_price"],
    }


def place_limit_order(conn, user_id: int, player_id: int, side: str,
                      price: float, quantity: int) -> dict:
    """
    Place a limit order. May fill immediately if it crosses existing orders.
    """
    cursor = conn.cursor()

    # Validate player exists
    cursor.execute("SELECT id, name FROM players WHERE id = ?", (player_id,))
    player = cursor.fetchone()
    if not player:
        raise ValueError(f"Player {player_id} not found.")

    # Place the order (this handles escrow)
    order = order_book.place_limit_order(conn, user_id, player_id, side, price, quantity)

    # Try to match immediately against existing orders
    if side == "buy":
        # A buy at $55 might match a sell at $50
        fills = order_book.match_buy_against_asks(conn, player_id, quantity, max_price=price)
        for fill in fills:
            _settle_book_trade(
                conn, buyer_id=user_id, seller_id=fill["seller_id"],
                player_id=player_id, price=fill["price"],
                quantity=fill["quantity"], trade_type="limit",
            )
            # The buyer escrowed at `price` but may fill at lower `fill["price"]`
            # Refund the difference
            savings = (price - fill["price"]) * fill["quantity"]
            if savings > 0:
                cursor.execute(
                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                    (savings, user_id)
                )
    else:
        fills = order_book.match_sell_against_bids(conn, player_id, quantity, min_price=price)
        for fill in fills:
            _settle_book_trade_for_sell(
                conn, seller_id=user_id, buyer_id=fill["buyer_id"],
                player_id=player_id, price=fill["price"],
                quantity=fill["quantity"], trade_type="limit",
            )
            # The seller gets the bid price which may be higher than their ask
            bonus = (fill["price"] - price) * fill["quantity"]
            if bonus > 0:
                cursor.execute(
                    "UPDATE users SET balance = balance + ? WHERE id = ?",
                    (bonus, user_id)
                )

    filled_qty = sum(f["quantity"] for f in fills)

    # Update our order status
    if filled_qty >= quantity:
        cursor.execute(
            "UPDATE orders SET filled_quantity = ?, status = 'filled', updated_at = datetime('now') WHERE id = ?",
            (filled_qty, order["id"])
        )
        order["status"] = "filled"
    elif filled_qty > 0:
        cursor.execute(
            "UPDATE orders SET filled_quantity = ?, status = 'partial', updated_at = datetime('now') WHERE id = ?",
            (filled_qty, order["id"])
        )
        order["status"] = "partial"

    order["filled_quantity"] = filled_qty
    order["fills"] = fills
    order["player_name"] = player["name"]

    conn.commit()
    return order


def cancel_order(conn, user_id: int, order_id: int) -> dict:
    """Cancel an open limit order and return escrowed funds/shares."""
    result = order_book.cancel_order(conn, user_id, order_id)
    conn.commit()
    return result


# -------------------------------------------------------------------
# Helper functions (internal — not part of the public API)
# -------------------------------------------------------------------

def _add_shares(conn, user_id: int, player_id: int, quantity: int, price_per_share: float):
    """
    Add shares to a user's holdings, updating average cost basis.

    avg_cost_basis tracks the average price you paid across all buys.
    This is used to calculate profit/loss later.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT shares, avg_cost_basis FROM holdings WHERE user_id = ? AND player_id = ?",
        (user_id, player_id)
    )
    holding = cursor.fetchone()

    if holding:
        old_shares = holding["shares"]
        old_cost = holding["avg_cost_basis"]
        new_shares = old_shares + quantity
        # Weighted average: (old_total + new_total) / new_shares
        new_avg = ((old_shares * old_cost) + (quantity * price_per_share)) / new_shares
        cursor.execute("""
            UPDATE holdings SET shares = ?, avg_cost_basis = ?
            WHERE user_id = ? AND player_id = ?
        """, (new_shares, new_avg, user_id, player_id))
    else:
        cursor.execute("""
            INSERT INTO holdings (user_id, player_id, shares, avg_cost_basis)
            VALUES (?, ?, ?, ?)
        """, (user_id, player_id, quantity, price_per_share))


def _remove_shares(conn, user_id: int, player_id: int, quantity: int):
    """Remove shares from a user's holdings."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE holdings SET shares = shares - ?
        WHERE user_id = ? AND player_id = ?
    """, (quantity, user_id, player_id))


def _settle_book_trade(conn, buyer_id: int, seller_id: int, player_id: int,
                       price: float, quantity: int, trade_type: str):
    """
    Settle a trade that was matched on the order book.

    The seller already escrowed their shares when placing the order,
    so we just need to:
      1. Give shares to buyer
      2. Give cash to seller
      3. Take cash from buyer (already escrowed for limit buys)
      4. Record the trade
    """
    cursor = conn.cursor()
    total = price * quantity

    # Give cash to seller
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ?",
        (total, seller_id)
    )

    # Buyer: for market buys, deduct cash now. For limit buys, already escrowed.
    if trade_type == "market":
        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (total, buyer_id)
        )

    # Give shares to buyer
    _add_shares(conn, buyer_id, player_id, quantity, price)

    # Record trade
    cursor.execute("""
        INSERT INTO trades (buyer_id, seller_id, player_id, price, quantity, trade_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (buyer_id, seller_id, player_id, price, quantity, trade_type))


def _settle_book_trade_for_sell(conn, seller_id: int, buyer_id: int, player_id: int,
                                price: float, quantity: int, trade_type: str):
    """
    Settle a trade where someone is selling into existing buy orders.

    The buyer already escrowed cash. The seller has the shares.
    """
    cursor = conn.cursor()
    total = price * quantity

    # Give cash to seller
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE id = ?",
        (total, seller_id)
    )

    # Remove shares from seller (for market sells)
    if trade_type == "market":
        _remove_shares(conn, seller_id, player_id, quantity)

    # Give shares to buyer
    _add_shares(conn, buyer_id, player_id, quantity, price)

    # Record trade
    cursor.execute("""
        INSERT INTO trades (buyer_id, seller_id, player_id, price, quantity, trade_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (buyer_id, seller_id, player_id, price, quantity, trade_type))
