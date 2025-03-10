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
WS_ADDRESS = os.environ.get("WS_ADDRESS")  # Wrapped S token address
SWAP_EXECUTOR_UNI_ADDRESS = os.environ.get("SWAP_EXECUTOR_UNI_ADDRESS")
SWAP_EXECUTOR_ALG_ADDRESS = os.environ.get("SWAP_EXECUTOR_ALG_ADDRESS")

# Connect to the network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Connection to RPC failed.")
    exit()

YOUR_ADDRESS = w3.to_checksum_address(YOUR_ADDRESS)
WS_ADDRESS = w3.to_checksum_address(WS_ADDRESS)
SWAP_EXECUTOR_UNI_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_UNI_ADDRESS)
SWAP_EXECUTOR_ALG_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ALG_ADDRESS)

def get_gas_price():
    """Gets the current gas price and adds a 10% buffer; returns gas price in Wei."""
    base_gas_price = w3.eth.gas_price
    return int(base_gas_price * 1.1)

# Minimal ERC20 ABI for allowance, approve, and balanceOf functions
erc20_abi = [
    {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uints256"}],
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
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

# Minimal ABI for the wS contract (wrapped S)
ws_abi = [
    {
        "inputs": [],
        "name": "deposit",
        "outputs": [],
        "stateMutability": "payable",
        "type": "function"
    },
    {
        "inputs": [{"internalType": "uint256", "name": "wad", "type": "uint256"}],
        "name": "withdraw",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    }
]

def check_and_approve(token_address, spender, required_amount):
    """Checks token allowance and sends an approval tx if needed."""
    token_address = w3.to_checksum_address(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    current_allowance = token_contract.functions.allowance(YOUR_ADDRESS, spender).call()
    print(f"Current allowance for token {token_address}: {current_allowance}")
    if current_allowance < required_amount:
        print(f"Allowance ({current_allowance}) is less than required ({required_amount}). Sending approval tx...")
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
    """Queries a UniswapV3-style pool's slot0() and returns sqrtPriceX96 as an integer."""
    pool_address = w3.to_checksum_address(pool_address)
    uni_abi = [
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
    ]
    try:
        pool_contract = w3.eth.contract(address=pool_address, abi=uni_abi)
        slot0 = pool_contract.functions.slot0().call()
        sqrt_price = slot0[0]
        print(f"Detected Uniswap pool. sqrtPriceX96: {sqrt_price}")
        return sqrt_price
    except Exception as e:
        raise Exception("Not a Uniswap-style pool.")

def get_pool_sqrt_price_alg(pool_address):
    """
    Queries an Algebra pool's globalState() and returns the current price (assumed to be sqrtPriceX96).
    Adjust the ABI if your Algebra pool uses a different getter.
    """
    pool_address = w3.to_checksum_address(pool_address)
    alg_abi = [
        {
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "price", "type": "uint160"},
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "fee", "type": "uint16"},
                {"internalType": "uint16", "name": "index", "type": "uint16"},
                {"internalType": "uint16", "name": "parameter", "type": "uint16"},
                {"internalType": "bool", "name": "unlocked", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        }
    ]
    try:
        pool_contract = w3.eth.contract(address=pool_address, abi=alg_abi)
        gs = pool_contract.functions.globalState().call()
        current_price = gs[0]
        print(f"Detected Algebra pool. Current price: {current_price}")
        return current_price
    except Exception as e:
        raise Exception("Not an Algebra-style pool.")

def autodetect_pool_type(pool_address):
    """
    Attempts to autodetect the pool type by first trying a Uniswap-style call,
    then an Algebra-style call.
    Returns "uni" if Uniswap-style, "alg" if Algebra-style, or None if neither.
    """
    try:
        get_pool_sqrt_price_uni(pool_address)
        return "uni"
    except Exception:
        try:
            get_pool_sqrt_price_alg(pool_address)
            return "alg"
        except Exception:
            return None

def calculate_sqrt_price_limit_buy(current_sqrt_price):
    """Calculates a buy swap price limit 5% lower than current sqrtPriceX96."""
    factor = math.sqrt(0.95)
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated buy sqrtPriceLimitX96 (5% lower): {new_limit}")
    return new_limit

def calculate_sqrt_price_limit_sell(current_sqrt_price):
    """Calculates a sell swap price limit 5% higher than current sqrtPriceX96."""
    factor = math.sqrt(1.05)
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sell sqrtPriceLimitX96 (5% higher): {new_limit}")
    return new_limit

def wrap_native(amount):
    """
    Wraps native S into wS by calling the wS contract's deposit() function.
    'amount' is in wei.
    """
    ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=ws_abi)
    tx = ws_contract.functions.deposit().build_transaction({
        'from': YOUR_ADDRESS,
        'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
        'gas': 100000,
        'gasPrice': get_gas_price(),
        'value': amount
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print("Wrap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Wrap receipt:", receipt)

def unwrap_native(amount):
    """
    Unwraps wS into native S by calling the wS contract's withdraw() function.
    'amount' is in raw units.
    """
    ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=ws_abi)
    tx = ws_contract.functions.withdraw(amount).build_transaction({
        'from': YOUR_ADDRESS,
        'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
        'gas': 100000,
        'gasPrice': get_gas_price()
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print("Unwrap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Unwrap receipt:", receipt)

##############################
# Executor Call Branches
##############################

def execute_swap_uni(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the UniswapV3-style executor contract.
    Checks wS balance for buy swaps and wraps native S if needed.
    """
    pool_address = w3.to_checksum_address(pool_address)
    # Query the pool for token addresses.
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
        spend_token = pool_contract.functions.token0().call()
    else:
        spend_token = pool_contract.functions.token1().call()
    print(f"Uniswap branch – spending token: {spend_token}")
    check_and_approve(spend_token, SWAP_EXECUTOR_UNI_ADDRESS, amountSpecified)
    if zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        current_ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        print(f"Current wS balance: {current_ws_balance}")
        if current_ws_balance < amountSpecified:
            deficit = amountSpecified - current_ws_balance
            print(f"Insufficient wS balance. Wrapping {deficit} wei native S into wS...")
            wrap_native(deficit)
    if sqrtPriceLimitX96 == 0:
        current_sqrt_price = get_pool_sqrt_price_uni(pool_address)
        if zeroForOne:
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_buy(current_sqrt_price)
        else:
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_sell(current_sqrt_price)
    with open('SwapExecutorUniABI.json', 'r') as abi_file:
        uni_abi = json.load(abi_file)
    uni_executor = w3.eth.contract(address=SWAP_EXECUTOR_UNI_ADDRESS, abi=uni_abi)
    tx = uni_executor.functions.executeSwap(
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
    print("Uni swap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Uni swap receipt:", receipt)
    if not zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        if ws_balance > 0:
            print(f"Post-sell (Uni): unwrapping {ws_balance} wei of wS to native S...")
            unwrap_native(ws_balance)

def execute_swap_alg(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the Algebra executor contract.
    The user provides the target Algebra pool address, direction, swap amount, and slippage limit.
    Supports both buy (zeroForOne=True) and sell (zeroForOne=False) swaps.
    """
    pool_address = w3.to_checksum_address(pool_address)
    # Query the pool for token addresses.
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
        spend_token = pool_contract.functions.token0().call()
    else:
        spend_token = pool_contract.functions.token1().call()
    print(f"Algebra branch – spending token: {spend_token}")
    check_and_approve(spend_token, SWAP_EXECUTOR_ALG_ADDRESS, amountSpecified)
    if zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        current_ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        print(f"Current wS balance: {current_ws_balance}")
        if current_ws_balance < amountSpecified:
            deficit = amountSpecified - current_ws_balance
            print(f"Insufficient wS balance. Wrapping {deficit} wei native S into wS...")
            wrap_native(deficit)
    if sqrtPriceLimitX96 == 0:
        current_sqrt_price = get_pool_sqrt_price_alg(pool_address)
        if zeroForOne:
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_buy(current_sqrt_price)
        else:
            sqrtPriceLimitX96 = calculate_sqrt_price_limit_sell(current_sqrt_price)
    with open('SwapExecutorAlgABI.json', 'r') as abi_file:
        alg_abi = json.load(abi_file)
    alg_executor = w3.eth.contract(address=SWAP_EXECUTOR_ALG_ADDRESS, abi=alg_abi)
    tx = alg_executor.functions.executeSwap(
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
    print("Alg swap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Alg swap receipt:", receipt)
    if not zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        if ws_balance > 0:
            print(f"Post-sell (Alg): unwrapping {ws_balance} wei of wS to native S...")
            unwrap_native(ws_balance)

def main():
    pool_address = input("Enter the target pool address: ").strip()
    # Autodetect pool type using minimal calls.
    pool_type = None
    try:
        pool_type = "uni"  # try uni first
        _ = get_pool_sqrt_price_uni(pool_address)
    except Exception:
        try:
            pool_type = "alg"
            _ = get_pool_sqrt_price_alg(pool_address)
        except Exception:
            print("Could not autodetect pool type for this address.")
            return

    print(f"Autodetected pool type: {pool_type}")
    direction = input("Enter direction ('buy' for buying using wS, 'sell' for selling for wS): ").strip().lower()
    if direction == "buy":
        zero_for_one = True
    elif direction == "sell":
        zero_for_one = False
    else:
        print("Invalid direction.")
        return
    amount_str = input("Enter the swap amount (in tokens) for the input token: ").strip()
    decimals = int(input("Enter the input token decimals (e.g., 18): ").strip())
    amountSpecified = int(float(amount_str) * (10 ** decimals))
    sqrt_limit_input = input("Enter sqrtPriceLimitX96 (as a number) or 'auto' to calculate dynamically: ").strip()
    if sqrt_limit_input.lower() == "auto":
        sqrtPriceLimitX96 = 0
    else:
        sqrtPriceLimitX96 = int(sqrt_limit_input)
    
    if pool_type == "uni":
        execute_swap_uni(pool_address, zero_for_one, amountSpecified, sqrtPriceLimitX96)
    elif pool_type == "alg":
        execute_swap_alg(pool_address, zero_for_one, amountSpecified, sqrtPriceLimitX96)

if __name__ == "__main__":
    main()
