import os
import json
import math
from web3 import Web3
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Read configuration from .env
RPC_URL = os.environ.get("RPC_URL")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
YOUR_ADDRESS = os.environ.get("YOUR_ADDRESS")
SWAP_EXECUTOR_ADDRESS = os.environ.get("SWAP_EXECUTOR_ADDRESS")

# Connect to the network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Connection to RPC failed.")
    exit()

YOUR_ADDRESS = w3.to_checksum_address(YOUR_ADDRESS)
SWAP_EXECUTOR_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ADDRESS)

# Load the SwapExecutor contract ABI from file (ensure SwapExecutorABI.json is in your folder)
with open('SwapExecutorABI.json', 'r') as abi_file:
    swap_executor_abi = json.load(abi_file)

# Instantiate the SwapExecutor contract
swap_executor = w3.eth.contract(address=SWAP_EXECUTOR_ADDRESS, abi=swap_executor_abi)

def get_gas_price():
    """
    Gets the current gas price from the network and applies a multiplier for better success rate.
    Returns the gas price in Wei.
    """
    base_gas_price = w3.eth.gas_price
    return int(base_gas_price * 1.1)  # Add 10% to the current gas price

# Minimal ERC20 ABI for allowance and approve functions
erc20_abi = [
    {
      "constant": True,
      "inputs": [
        {"name": "owner", "type": "address"},
        {"name": "spender", "type": "address"}
      ],
      "name": "allowance",
      "outputs": [{"name": "", "type": "uint256"}],
      "type": "function"
    },
    {
      "constant": False,
      "inputs": [
        {"name": "spender", "type": "address"},
        {"name": "amount", "type": "uint256"}
      ],
      "name": "approve",
      "outputs": [{"name": "", "type": "bool"}],
      "type": "function"
    }
]

def check_and_approve(token_address, spender, required_amount):
    """
    Checks the allowance for the given token from YOUR_ADDRESS to the spender (SwapExecutor).
    If the allowance is insufficient, it builds, signs, and sends an approve transaction.
    """
    token_address = w3.to_checksum_address(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    current_allowance = token_contract.functions.allowance(YOUR_ADDRESS, spender).call()
    print(f"Current allowance for token {token_address}: {current_allowance}")
    if current_allowance < required_amount:
        print(f"Allowance is less than required ({required_amount}). Sending approval transaction...")
        tx = token_contract.functions.approve(spender, required_amount).build_transaction({
            'from': YOUR_ADDRESS,
            'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
            'gas': 100000,  # Adjust if needed
            'gasPrice': get_gas_price()
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print("Approval tx sent. Tx hash:", w3.to_hex(tx_hash))
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("Approval receipt:", receipt)
    else:
        print("Sufficient allowance already exists.")

def get_pool_sqrt_price(pool_address):
    """
    Queries the target pool's slot0() to retrieve the current sqrtPriceX96.
    Returns the sqrtPriceX96 as an integer.
    """
    pool_address = w3.to_checksum_address(pool_address)
    pool_contract = w3.eth.contract(address=pool_address, abi=[
        {
            "inputs": [],
            "name": "slot0",
            "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
                {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
                {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ])
    slot0 = pool_contract.functions.slot0().call()
    sqrtPriceX96 = slot0[0]
    print(f"Current sqrtPriceX96 in pool {pool_address}: {sqrtPriceX96}")
    return sqrtPriceX96

def calculate_sqrt_price_limit_buy(current_sqrt_price):
    """
    For a buy swap (zeroForOne = true) where token0 is wS,
    set a price limit that is 5% lower than the current price.
    Returns an integer sqrtPriceLimitX96.
    """
    factor = math.sqrt(0.95)  # Approximately 0.97468
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sqrtPriceLimitX96 for buy swap (5% lower): {new_limit}")
    return new_limit

def calculate_sqrt_price_limit_sell(current_sqrt_price):
    """
    For a sell swap (zeroForOne = false) where token1 is EGGS,
    set a price limit that is 5% higher than the current price.
    Returns an integer sqrtPriceLimitX96.
    """
    factor = math.sqrt(1.05)  # Approximately 1.02470
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sqrtPriceLimitX96 for sell swap (5% higher): {new_limit}")
    return new_limit

def execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the SwapExecutor contract.
    Before executing, it auto-approves the spending token if necessary.
    
    pool_address: The target pool contract address.
    zeroForOne: If true, swaps token0 for token1 (for buy action, spending wS to get EGGS);
                if false, swaps token1 for token0 (for sell action).
    amountSpecified: Amount to swap (in the smallest unit of the input token).
    sqrtPriceLimitX96: Slippage limit in Q96 format. If set to 0, it will be computed automatically.
    """
    pool_address = w3.to_checksum_address(pool_address)
    # Create a minimal pool instance to query token0 and token1.
    pool_contract = w3.eth.contract(address=pool_address, abi=[
        {
            "constant": True,
            "inputs": [],
            "name": "token0",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        },
        {
            "constant": True,
            "inputs": [],
            "name": "token1",
            "outputs": [{"name": "", "type": "address"}],
            "type": "function"
        }
    ])
    
    if zeroForOne:
        # For a buy swap, we're spending token0 (wS) to buy token1 (EGGS).
        spend_token = pool_contract.functions.token0().call()
    else:
        # For a sell swap, we're spending token1 (EGGS) to get token0 (wS).
        spend_token = pool_contract.functions.token1().call()
    
    print(f"Spending token for swap: {spend_token}")
    
    # Auto-approve the spending token if needed.
    check_and_approve(spend_token, SWAP_EXECUTOR_ADDRESS, amountSpecified)
    
    # If sqrtPriceLimitX96 is zero, calculate it dynamically.
    if sqrtPriceLimitX96 == 0:
        current_sqrt_price = get_pool_sqrt_price(pool_address)
        if zeroForOne:
            # For buy swap, set limit 5% lower than current.
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_buy(current_sqrt_price)
        else:
            # For sell swap, set limit 5% higher than current.
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_sell(current_sqrt_price)
    
    tx = swap_executor.functions.executeSwap(
        pool_address,
        zeroForOne,
        amountSpecified,
        sqrtPriceLimitX96
    ).build_transaction({
        'from': YOUR_ADDRESS,
        'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
        'gas': 2000000,
        'gasPrice': get_gas_price()
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print("Swap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Swap receipt:", receipt)

def main():
        pool_address = input("Enter the target pool address: ").strip()
        direction = input("Enter direction ('buy' or 'sell'): ").strip().lower()

        if direction == "buy":
            zeroForOne = True 
        elif direction == "sell":
            zeroForOne = False
        else:
            print("Invalid direction.")
            return
        amount_str = input("Enter the swap amount (in tokens) for the input token: ").strip()
        decimals = int(input("Enter the input token decimals (e.g., 18): ").strip())
        amountSpecified = int(float(amount_str) * (10 ** decimals))
        sqrt_limit_input = input("Enter sqrtPriceLimitX96 (as a number) or 'auto' to calculate dynamically: ").strip()
        if sqrt_limit_input.lower() == "auto":
            sqrtPriceLimitX96 = 0  # signal to compute dynamically
        else:
            sqrtPriceLimitX96 = int(sqrt_limit_input)
        execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96)

if __name__ == "__main__":
    main()
