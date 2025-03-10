import requests

def fetch_token_pools(chain_id, token_address):
    """
    Fetch all pools for a given token address on a specified chain using the DexScreener API.
    Endpoint: /token-pairs/v1/{chainId}//{tokenAddress}
    Example URL for Sonic: https://api.dexscreener.com/token-pairs/v1/sonic//{tokenAddress}
    """
    url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}//{token_address}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        pools = response.json()  # Expected to be a JSON array of pool objects
        return pools
    except Exception as e:
        print("Error fetching token pools:", e)
        return []

def report_arbitrage_from_pools(pools, token_address, min_liquidity=10000):
    """
    For a list of pool objects, compute the USD price for the given token,
    but only consider pools where the token appears as the base token and
    the DEX is one of: shadow-exchange, swapx, wagmi, silverswap, spookyswap, or sushiswap.
    Pools with liquidity below min_liquidity are filtered out.
    Then, sort the pools by price (high to low) and report the highest and lowest prices,
    along with the computed percentage difference. Display the DEX, constructed pair name, and pair address.
    """
    token_address_lower = token_address.lower()
    valid_prices = []
    token_name = None

    # Allowed DEXes (all lower-case)
    allowed_dexes = {"shadow-exchange", "swapx", "wagmi", "silverswap", "spookyswap", "sushiswap"}

    for pool in pools:
        try:
            liquidity_usd = float(pool.get("liquidity", {}).get("usd", 0))
            if liquidity_usd < min_liquidity:
                continue  # Skip pools with insufficient liquidity

            # Only consider pools where the token is the base token.
            base = pool.get("baseToken", {})
            base_addr = base.get("address", "").lower()
            if token_address_lower != base_addr:
                continue

            # Filter by allowed dexes:
            dex_id = pool.get("dexId", "").lower()
            if dex_id not in allowed_dexes:
                continue

            try:
                priceUsd = float(pool.get("priceUsd", "0"))
            except Exception:
                continue

            # Get token name once from the base token data.
            if token_name is None:
                token_name = base.get("name", "Unknown Token")

            # Construct a pair name from base and quote token symbols.
            quote = pool.get("quoteToken", {})
            base_symbol = base.get("symbol", "N/A")
            quote_symbol = quote.get("symbol", "N/A")
            pair_name = f"{base_symbol}/{quote_symbol}"

            valid_prices.append({
                "dexId": pool.get("dexId", "unknown"),
                "priceUsd": priceUsd,
                "pairAddress": pool.get("pairAddress", "unknown"),
                "liquidityUsd": liquidity_usd,
                "pairName": pair_name
            })
        except Exception:
            continue

    if len(valid_prices) > 1:
        # Sort the pools by priceUsd in descending order.
        sorted_prices = sorted(valid_prices, key=lambda x: x["priceUsd"], reverse=True)
        highest = sorted_prices[0]
        lowest = sorted_prices[-1]

        if lowest["priceUsd"] > 0:
            diff_percent = ((highest["priceUsd"] - lowest["priceUsd"]) / lowest["priceUsd"]) * 100
            token_label = token_name if token_name else "Token"
            print("\nArbitrage details for {} (Address: {}) – considering pools with liquidity >= ${}:".format(token_label, token_address, min_liquidity))
            print("-" * 80)
            for entry in sorted_prices:
                print(f"DEX: {entry['dexId']} | Pair: {entry['pairName']} | Pair Address: {entry['pairAddress']} | Price: {entry['priceUsd']:.6f} USD | Liquidity: ${entry['liquidityUsd']:.2f}")
            print("-" * 80)
            print("Highest Price:")
            print(f"   {highest['priceUsd']:.6f} USD on DEX: {highest['dexId']} | Pair: {highest['pairName']} | Pair Address: {highest['pairAddress']}")
            print("Lowest Price:")
            print(f"   {lowest['priceUsd']:.6f} USD on DEX: {lowest['dexId']} | Pair: {lowest['pairName']} | Pair Address: {lowest['pairAddress']}")
            print(f"Price Difference: {diff_percent:.2f}%\n")
        else:
            print("Lowest price is zero, cannot calculate arbitrage.")
    else:
        print("Not enough pool data to compute arbitrage details.")

def main():
    chain_id = "sonic"  # For Sonic chain
    token_address = input("Enter the token address to check pools: ").strip()
    
    print(f"\nFetching pools for token {token_address} on {chain_id}...")
    pools = fetch_token_pools(chain_id, token_address)
    
    if pools:
        print(f"Found {len(pools)} pools for token {token_address}.")
        report_arbitrage_from_pools(pools, token_address, min_liquidity=10000)
    else:
        print("No pool data found.")

if __name__ == "__main__":
    main()
