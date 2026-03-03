# -------------------------------------------------------------------
# amm.py — Automated Market Maker (the pricing engine).
#
# HOW IT WORKS (the simple version):
#   Imagine a pool with two things in it:
#     - Some player SHARES (called "token_reserve")
#     - Some CASH (called "currency_reserve")
#
#   The PRICE of one share = cash in pool / shares in pool.
#
#   When you BUY shares, you add cash and take shares out.
#   -> Fewer shares in pool = price goes UP (supply decreased).
#
#   When you SELL shares, you add shares and take cash out.
#   -> More shares in pool = price goes DOWN (supply increased).
#
# THE MATH (constant product formula, same as Uniswap):
#   The rule is: token_reserve * currency_reserve = k (a constant)
#
#   This "k" never changes (except from fees). So if someone buys
#   shares (removing tokens), the currency_reserve must increase
#   to keep k the same. That increase IS the price the buyer pays.
#
# EXAMPLE:
#   Pool starts: 1000 shares, $50,000 cash. k = 50,000,000.
#   Price = $50,000 / 1000 = $50/share.
#
#   User buys 10 shares:
#     New token_reserve = 1000 - 10 = 990
#     New currency_reserve = k / 990 = 50,505.05
#     Cost = 50,505.05 - 50,000 = $505.05
#     Average price per share = $505.05 / 10 = $50.51
#     (Slightly more than $50 because buying pushes price up!)
#
# WHY THIS WORKS FOR US:
#   - There's always a price (no need to wait for a buyer/seller)
#   - Popular players naturally get more expensive
#   - Large trades cause more "slippage" (price impact), which is
#     realistic — big buys move the market more
# -------------------------------------------------------------------

from app.config import AMM_FEE, AMM_MAX_BUY_FRACTION


def get_spot_price(token_reserve: float, currency_reserve: float) -> float:
    """
    Current price of ONE share.

    This is just the ratio of cash to shares in the pool.
    """
    if token_reserve <= 0:
        return 0.0
    return currency_reserve / token_reserve


def calculate_buy_cost(token_reserve: float, currency_reserve: float, shares: int) -> dict:
    """
    Calculate how much it costs to buy `shares` from the AMM.

    Returns a dict with:
        - total_cost: total fantasy dollars the buyer pays
        - avg_price: average price per share
        - new_token_reserve: pool state after the trade
        - new_currency_reserve: pool state after the trade
        - price_impact: how much this trade moves the price (%)
        - fee: the fee portion of the cost

    Raises ValueError if trying to buy too many shares.
    """
    if shares <= 0:
        raise ValueError("Must buy at least 1 share.")

    max_buyable = int(token_reserve * AMM_MAX_BUY_FRACTION)
    if shares > max_buyable:
        raise ValueError(
            f"Can't buy {shares} shares. Maximum is {max_buyable} "
            f"(90% of the {int(token_reserve)} shares in the pool)."
        )

    # The constant product: k = x * y
    k = token_reserve * currency_reserve

    # After buying, shares leave the pool
    new_token_reserve = token_reserve - shares

    # To maintain k, currency_reserve must increase
    new_currency_reserve = k / new_token_reserve

    # The cost is how much more cash is in the pool
    cost_before_fee = new_currency_reserve - currency_reserve

    # Fee is charged on top (buyer pays a little extra)
    fee = cost_before_fee * AMM_FEE
    total_cost = cost_before_fee + fee

    # Price impact: how much did the price change?
    old_price = get_spot_price(token_reserve, currency_reserve)
    # After fee, the pool gets slightly more currency (fee stays in pool)
    final_currency_reserve = new_currency_reserve + fee
    new_price = get_spot_price(new_token_reserve, final_currency_reserve)
    price_impact = ((new_price - old_price) / old_price) * 100

    return {
        "total_cost": round(total_cost, 2),
        "avg_price": round(total_cost / shares, 2),
        "new_token_reserve": new_token_reserve,
        "new_currency_reserve": final_currency_reserve,
        "price_impact": round(price_impact, 2),
        "fee": round(fee, 2),
    }


def calculate_sell_revenue(token_reserve: float, currency_reserve: float, shares: int) -> dict:
    """
    Calculate how much cash you get for selling `shares` to the AMM.

    Returns a dict with:
        - total_revenue: fantasy dollars the seller receives
        - avg_price: average price per share received
        - new_token_reserve: pool state after the trade
        - new_currency_reserve: pool state after the trade
        - price_impact: how much this trade moves the price (%)
        - fee: the fee deducted from revenue
    """
    if shares <= 0:
        raise ValueError("Must sell at least 1 share.")

    # The constant product: k = x * y
    k = token_reserve * currency_reserve

    # After selling, shares enter the pool
    new_token_reserve = token_reserve + shares

    # To maintain k, currency_reserve must decrease
    new_currency_reserve = k / new_token_reserve

    # The revenue is how much cash left the pool
    revenue_before_fee = currency_reserve - new_currency_reserve

    if revenue_before_fee <= 0:
        raise ValueError("Trade too large — not enough liquidity in the pool.")

    # Fee is deducted from what the seller receives
    fee = revenue_before_fee * AMM_FEE
    total_revenue = revenue_before_fee - fee

    # Price impact
    old_price = get_spot_price(token_reserve, currency_reserve)
    # Fee stays in pool, so pool keeps a bit more currency
    final_currency_reserve = new_currency_reserve + fee
    new_price = get_spot_price(new_token_reserve, final_currency_reserve)
    price_impact = ((new_price - old_price) / old_price) * 100

    return {
        "total_revenue": round(total_revenue, 2),
        "avg_price": round(total_revenue / shares, 2),
        "new_token_reserve": new_token_reserve,
        "new_currency_reserve": final_currency_reserve,
        "price_impact": round(price_impact, 2),
        "fee": round(fee, 2),
    }


def execute_amm_buy(conn, player_id: int, shares: int) -> dict:
    """
    Actually execute a buy against the AMM pool, updating the database.

    Returns the same dict as calculate_buy_cost, plus updates the pool.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token_reserve, currency_reserve FROM amm_pools WHERE player_id = ?",
        (player_id,)
    )
    pool = cursor.fetchone()
    if not pool:
        raise ValueError(f"No AMM pool found for player {player_id}")

    result = calculate_buy_cost(pool["token_reserve"], pool["currency_reserve"], shares)

    # Update the pool reserves
    cursor.execute("""
        UPDATE amm_pools
        SET token_reserve = ?, currency_reserve = ?, updated_at = datetime('now')
        WHERE player_id = ?
    """, (result["new_token_reserve"], result["new_currency_reserve"], player_id))

    return result


def execute_amm_sell(conn, player_id: int, shares: int) -> dict:
    """
    Actually execute a sell against the AMM pool, updating the database.

    Returns the same dict as calculate_sell_revenue, plus updates the pool.
    """
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token_reserve, currency_reserve FROM amm_pools WHERE player_id = ?",
        (player_id,)
    )
    pool = cursor.fetchone()
    if not pool:
        raise ValueError(f"No AMM pool found for player {player_id}")

    result = calculate_sell_revenue(pool["token_reserve"], pool["currency_reserve"], shares)

    # Update the pool reserves
    cursor.execute("""
        UPDATE amm_pools
        SET token_reserve = ?, currency_reserve = ?, updated_at = datetime('now')
        WHERE player_id = ?
    """, (result["new_token_reserve"], result["new_currency_reserve"], player_id))

    return result


def get_pool_info(conn, player_id: int) -> dict:
    """Get the current state of a player's AMM pool."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT token_reserve, currency_reserve FROM amm_pools WHERE player_id = ?",
        (player_id,)
    )
    pool = cursor.fetchone()
    if not pool:
        return None

    token_reserve = pool["token_reserve"]
    currency_reserve = pool["currency_reserve"]

    return {
        "player_id": player_id,
        "token_reserve": round(token_reserve, 2),
        "currency_reserve": round(currency_reserve, 2),
        "spot_price": round(get_spot_price(token_reserve, currency_reserve), 2),
        "k": round(token_reserve * currency_reserve, 2),
    }
