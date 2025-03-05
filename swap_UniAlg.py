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
    """Gets the current gas price and applies a 10% buffer; returns gas price in Wei."""
    base_gas_price = w3.eth.gas_price
    return int(base_gas_price * 1.1)

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
    """Checks allowance and, if insufficient, sends an approval transaction."""
    token_address = w3.to_checksum_address(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    current_allowance = token_contract.functions.allowance(YOUR_ADDRESS, spender).call()
    print(f"Current allowance for token {token_address}: {current_allowance}")
    if current_allowance < required_amount:
        print(f"Allowance is less than required ({required_amount}). Sending approval tx...")
        tx = token_contract.functions.approve(spender, required_amount).build_transaction({
            'from': YOUR_ADDRESS,
            'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
            'gas': 100000,
            'gasPrice': get_gas_price()
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        print("Approval tx sent. Tx hash:", w3.to_hex(tx_hash))
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        print("Approval receipt:", receipt)
    else:
        print("Sufficient allowance already exists.")

def get_pool_sqrt_price_uni(pool_address):
    """
    Queries a UniswapV3-style pool's slot0() to retrieve the current sqrtPriceX96.
    Returns an integer.
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
    sqrt_price = slot0[0]
    print(f"Uniswap pool sqrtPriceX96: {sqrt_price}")
    return sqrt_price

def get_pool_sqrt_price_alg(pool_address):
    """
    Queries an Algebra pool's globalState() to retrieve the current price.
    Assumes that globalState() returns a struct with the first element being the current sqrtPrice.
    Returns an integer.
    """
    pool_address = w3.to_checksum_address(pool_address)
    algebra_abi = [
        {
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "price", "type": "uint160"},
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
    ]
    pool_contract = w3.eth.contract(address=pool_address, abi=algebra_abi)
    gs = pool_contract.functions.globalState().call()
    current_price = gs[0]
    print(f"Algebra pool current price: {current_price}")
    return current_price

def calculate_sqrt_price_limit_buy(current_sqrt_price):
    """For a buy swap, calculate a sqrtPrice limit 5% lower than current."""
    factor = math.sqrt(0.95)  # ~0.97468
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated buy sqrtPriceLimitX96 (5% lower): {new_limit}")
    return new_limit

def calculate_sqrt_price_limit_sell(current_sqrt_price):
    """For a sell swap, calculate a sqrtPrice limit 5% higher than current."""
    factor = math.sqrt(1.05)  # ~1.02470
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sell sqrtPriceLimitX96 (5% higher): {new_limit}")
    return new_limit

def execute_swap(pool_address, pool_type, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the SwapExecutor contract.
    pool_address: Target pool address.
    pool_type: 'uni' for UniswapV3 style or 'alg' for Algebra style.
    zeroForOne: True for buy (spend token0 to get token1) or False for sell.
    amountSpecified: Amount (in smallest units) to swap.
    sqrtPriceLimitX96: If 0, computed dynamically with a 5% adjustment.
    """
    pool_address = w3.to_checksum_address(pool_address)
    # Create a minimal pool instance for token0 and token1 queries.
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
        # For buy: spend token0 (wS) to obtain token1 (EGGS)
        spend_token = pool_contract.functions.token0().call()
    else:
        # For sell: spend token1 (EGGS) to obtain token0 (wS)
        spend_token = pool_contract.functions.token1().call()
    print(f"Spending token for swap: {spend_token}")
    check_and_approve(spend_token, SWAP_EXECUTOR_ADDRESS, amountSpecified)
    
    # If sqrtPriceLimitX96 is 0, compute it dynamically based on pool type.
    if sqrtPriceLimitX96 == 0:
        if pool_type == 'uni':
            current_sqrt_price = get_pool_sqrt_price_uni(pool_address)
        elif pool_type == 'alg':
            current_sqrt_price = get_pool_sqrt_price_alg(pool_address)
        else:
            print("Invalid pool type provided.")
            return
        if zeroForOne:
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_buy(current_sqrt_price)
        else:
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
    pool_type = input("Enter pool type ('uni' for UniswapV3, 'alg' for Algebra): ").strip().lower()
    direction = input("Enter direction ('buy' for buying EGGS using wS, 'sell' for selling EGGS for wS): ").strip().lower()

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
    execute_swap(pool_address, pool_type, zeroForOne, amountSpecified, sqrtPriceLimitX96)

if __name__ == "__main__":
    main()
s