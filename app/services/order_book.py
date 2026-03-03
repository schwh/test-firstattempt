# -------------------------------------------------------------------
# order_book.py — The limit order book.
#
# HOW IT WORKS:
#   Users can place "limit orders" — offers to buy or sell at a
#   specific price. These sit on the order book until:
#     a) Another user's order matches (crossed orders), or
#     b) A market order fills them, or
#     c) The user cancels them.
#
# MATCHING RULES:
#   - Buy orders (bids) match with sell orders (asks) when
#     the bid price >= ask price.
#   - Orders are matched price-first, then time-first (FIFO).
#     (Oldest order at the best price gets filled first.)
#
# ESCROW:
#   When you place a limit buy, your cash is "locked up" (escrowed)
#   so you can't spend it twice. Same for limit sells — your shares
#   are locked. If you cancel, you get them back.
# -------------------------------------------------------------------


def get_order_book(conn, player_id: int) -> dict:
    """
    Get the current order book for a player.

    Returns bids (buy orders) sorted high-to-low, and
    asks (sell orders) sorted low-to-high. This shows the
    "spread" — the gap between highest bid and lowest ask.
    """
    cursor = conn.cursor()

    # Bids: people wanting to BUY (sorted highest price first)
    cursor.execute("""
        SELECT o.id, o.user_id, u.username, o.price, o.quantity,
               o.filled_quantity, (o.quantity - o.filled_quantity) as remaining
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.player_id = ? AND o.side = 'buy'
              AND o.status IN ('open', 'partial')
        ORDER BY o.price DESC, o.created_at ASC
    """, (player_id,))
    bids = [dict(row) for row in cursor.fetchall()]

    # Asks: people wanting to SELL (sorted lowest price first)
    cursor.execute("""
        SELECT o.id, o.user_id, u.username, o.price, o.quantity,
               o.filled_quantity, (o.quantity - o.filled_quantity) as remaining
        FROM orders o
        JOIN users u ON o.user_id = u.id
        WHERE o.player_id = ? AND o.side = 'sell'
              AND o.status IN ('open', 'partial')
        ORDER BY o.price ASC, o.created_at ASC
    """, (player_id,))
    asks = [dict(row) for row in cursor.fetchall()]

    return {"bids": bids, "asks": asks}


def get_best_bid(conn, player_id: int):
    """Highest open buy order — the most someone is willing to pay."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders
        WHERE player_id = ? AND side = 'buy'
              AND status IN ('open', 'partial')
        ORDER BY price DESC, created_at ASC
        LIMIT 1
    """, (player_id,))
    return cursor.fetchone()


def get_best_ask(conn, player_id: int):
    """Lowest open sell order — the cheapest shares available."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM orders
        WHERE player_id = ? AND side = 'sell'
              AND status IN ('open', 'partial')
        ORDER BY price ASC, created_at ASC
        LIMIT 1
    """, (player_id,))
    return cursor.fetchone()


def match_buy_against_asks(conn, player_id: int, quantity: int, max_price: float = None):
    """
    Try to fill a buy by matching against existing sell orders.

    Args:
        player_id: which player's shares to buy
        quantity: how many shares the buyer wants
        max_price: if set, only match asks at or below this price

    Returns a list of "fills" — each is a dict describing a partial match:
        [{"order_id": 5, "seller_id": 3, "price": 48.0, "quantity": 10}, ...]

    The remaining unfilled quantity is: quantity - sum(fill["quantity"])
    """
    cursor = conn.cursor()

    # Get sell orders, cheapest first
    if max_price is not None:
        cursor.execute("""
            SELECT * FROM orders
            WHERE player_id = ? AND side = 'sell'
                  AND status IN ('open', 'partial')
                  AND price <= ?
            ORDER BY price ASC, created_at ASC
        """, (player_id, max_price))
    else:
        cursor.execute("""
            SELECT * FROM orders
            WHERE player_id = ? AND side = 'sell'
                  AND status IN ('open', 'partial')
            ORDER BY price ASC, created_at ASC
        """, (player_id,))

    asks = cursor.fetchall()
    fills = []
    remaining = quantity

    for ask in asks:
        if remaining <= 0:
            break

        available = ask["quantity"] - ask["filled_quantity"]
        fill_qty = min(remaining, available)

        fills.append({
            "order_id": ask["id"],
            "seller_id": ask["user_id"],
            "price": ask["price"],
            "quantity": fill_qty,
        })

        # Update the sell order's filled quantity
        new_filled = ask["filled_quantity"] + fill_qty
        new_status = "filled" if new_filled >= ask["quantity"] else "partial"
        cursor.execute("""
            UPDATE orders SET filled_quantity = ?, status = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (new_filled, new_status, ask["id"]))

        # Return escrowed shares for the filled portion to... well, they go
        # to the buyer. The seller already escrowed them when placing the order.

        remaining -= fill_qty

    return fills


def match_sell_against_bids(conn, player_id: int, quantity: int, min_price: float = None):
    """
    Try to fill a sell by matching against existing buy orders.

    Args:
        player_id: which player's shares to sell
        quantity: how many shares the seller has
        min_price: if set, only match bids at or above this price

    Returns a list of fills (same structure as match_buy_against_asks).
    """
    cursor = conn.cursor()

    # Get buy orders, highest price first
    if min_price is not None:
        cursor.execute("""
            SELECT * FROM orders
            WHERE player_id = ? AND side = 'buy'
                  AND status IN ('open', 'partial')
                  AND price >= ?
            ORDER BY price DESC, created_at ASC
        """, (player_id, min_price))
    else:
        cursor.execute("""
            SELECT * FROM orders
            WHERE player_id = ? AND side = 'buy'
                  AND status IN ('open', 'partial')
            ORDER BY price DESC, created_at ASC
        """, (player_id,))

    bids = cursor.fetchall()
    fills = []
    remaining = quantity

    for bid in bids:
        if remaining <= 0:
            break

        available = bid["quantity"] - bid["filled_quantity"]
        fill_qty = min(remaining, available)

        fills.append({
            "order_id": bid["id"],
            "buyer_id": bid["user_id"],
            "price": bid["price"],
            "quantity": fill_qty,
        })

        # Update the buy order's filled quantity
        new_filled = bid["filled_quantity"] + fill_qty
        new_status = "filled" if new_filled >= bid["quantity"] else "partial"
        cursor.execute("""
            UPDATE orders SET filled_quantity = ?, status = ?, updated_at = datetime('now')
            WHERE id = ?
        """, (new_filled, new_status, bid["id"]))

        remaining -= fill_qty

    return fills


def place_limit_order(conn, user_id: int, player_id: int, side: str,
                      price: float, quantity: int) -> dict:
    """
    Place a new limit order on the book.

    For buy orders: escrows (locks) the user's cash.
    For sell orders: escrows the user's shares.

    Returns the created order as a dict.
    """
    cursor = conn.cursor()

    if side == "buy":
        # Check user has enough balance to escrow
        escrow_amount = price * quantity
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if not user:
            raise ValueError(f"User {user_id} not found.")
        if user["balance"] < escrow_amount:
            raise ValueError(
                f"Insufficient balance. Need ${escrow_amount:.2f}, "
                f"have ${user['balance']:.2f}."
            )
        # Deduct the escrowed amount
        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE id = ?",
            (escrow_amount, user_id)
        )

    elif side == "sell":
        # Check user has enough shares to escrow
        cursor.execute(
            "SELECT shares FROM holdings WHERE user_id = ? AND player_id = ?",
            (user_id, player_id)
        )
        holding = cursor.fetchone()
        if not holding or holding["shares"] < quantity:
            available = holding["shares"] if holding else 0
            raise ValueError(
                f"Insufficient shares. Need {quantity}, have {available}."
            )
        # Deduct escrowed shares
        cursor.execute(
            "UPDATE holdings SET shares = shares - ? WHERE user_id = ? AND player_id = ?",
            (quantity, user_id, player_id)
        )
    else:
        raise ValueError("Side must be 'buy' or 'sell'.")

    # Insert the order
    cursor.execute("""
        INSERT INTO orders (user_id, player_id, side, price, quantity)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, player_id, side, price, quantity))

    order_id = cursor.lastrowid
    return {
        "id": order_id,
        "user_id": user_id,
        "player_id": player_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "filled_quantity": 0,
        "status": "open",
    }


def cancel_order(conn, user_id: int, order_id: int) -> dict:
    """
    Cancel an open or partially filled order.

    Returns the escrowed funds/shares for the unfilled portion.
    """
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()

    if not order:
        raise ValueError(f"Order {order_id} not found.")
    if order["user_id"] != user_id:
        raise ValueError("You can only cancel your own orders.")
    if order["status"] in ("filled", "cancelled"):
        raise ValueError(f"Order is already {order['status']}.")

    unfilled = order["quantity"] - order["filled_quantity"]

    if order["side"] == "buy":
        # Return escrowed cash for the unfilled portion
        refund = order["price"] * unfilled
        cursor.execute(
            "UPDATE users SET balance = balance + ? WHERE id = ?",
            (refund, user_id)
        )
    else:
        # Return escrowed shares
        cursor.execute("""
            UPDATE holdings SET shares = shares + ?
            WHERE user_id = ? AND player_id = ?
        """, (unfilled, user_id, order["player_id"]))

    # Mark order as cancelled
    cursor.execute("""
        UPDATE orders SET status = 'cancelled', updated_at = datetime('now')
        WHERE id = ?
    """, (order_id,))

    return {
        "id": order_id,
        "status": "cancelled",
        "unfilled_returned": unfilled,
    }
