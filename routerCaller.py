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
WS_ADDRESS = os.environ.get("WS_ADDRESS")  # Wrapped S token address

# Connect to the network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Connection to RPC failed.")
    exit()

YOUR_ADDRESS = w3.to_checksum_address(YOUR_ADDRESS)
SWAP_EXECUTOR_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ADDRESS)
WS_ADDRESS = w3.to_checksum_address(WS_ADDRESS)

# Load the SwapExecutor contract ABI from file (ensure SwapExecutorABI.json is in your folder)
with open('SwapExecutorABI.json', 'r') as abi_file:
    swap_executor_abi = json.load(abi_file)

# Instantiate the SwapExecutor contract
swap_executor = w3.eth.contract(address=SWAP_EXECUTOR_ADDRESS, abi=swap_executor_abi)

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
    """
    Checks the allowance for the given token from YOUR_ADDRESS to the spender.
    If insufficient, it sends an approval transaction.
    """
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
    sqrt_price = slot0[0]
    print(f"Current sqrtPriceX96 in pool {pool_address}: {sqrt_price}")
    return sqrt_price

def calculate_sqrt_price_limit_buy(current_sqrt_price):
    """
    For a buy swap (zeroForOne = true) where token0 is wS,
    calculates a price limit that is 5% lower than the current price.
    Returns an integer.
    """
    factor = math.sqrt(0.95)  # ~0.97468
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sqrtPriceLimitX96 for buy swap (5% lower): {new_limit}")
    return new_limit

def calculate_sqrt_price_limit_sell(current_sqrt_price):
    """
    For a sell swap (zeroForOne = false) where token1 is EGGS,
    calculates a price limit that is 5% higher than the current price.
    Returns an integer.
    """
    factor = math.sqrt(1.05)  # ~1.02470
    new_limit = int(current_sqrt_price * factor)
    print(f"Calculated sqrtPriceLimitX96 for sell swap (5% higher): {new_limit}")
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

def execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the SwapExecutor contract.
    For a buy swap (zeroForOne=True), it checks the wS balance and wraps native S if needed.
    For a sell swap, after the swap it automatically unwraps the resulting wS back to S.
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
        # For a sell swap, we're spending token1 (EGGS) to obtain token0 (wS).
        spend_token = pool_contract.functions.token1().call()
    
    print(f"Spending token for swap: {spend_token}")
    
    # For a buy swap, check wS balance; if insufficient, wrap native S.
    if zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        current_ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        print(f"Current wS balance: {current_ws_balance}")
        if current_ws_balance < amountSpecified:
            deficit = amountSpecified - current_ws_balance
            print(f"Insufficient wS balance. Wrapping {deficit} wei of native S into wS...")
            wrap_native(deficit)
    
    # Auto-approve the spending token if needed.
    check_and_approve(spend_token, SWAP_EXECUTOR_ADDRESS, amountSpecified)
    
    # If sqrtPriceLimitX96 is zero, calculate it dynamically.
    if sqrtPriceLimitX96 == 0:
        current_sqrt_price = get_pool_sqrt_price(pool_address)
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
    
    # For a sell swap, automatically unwrap any resulting wS to native S.
    if not zeroForOne:
        ws_contract = w3.eth.contract(address=WS_ADDRESS, abi=erc20_abi)
        ws_balance = ws_contract.functions.balanceOf(YOUR_ADDRESS).call()
        if ws_balance > 0:
            print(f"Post-swap: unwrapping {ws_balance} wei of wS to native S...")
            unwrap_native(ws_balance)

def main():
    print("Select an action:")
    print("1. Approve token for SwapExecutor")
    print("2. Execute swap via SwapExecutor")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        token_address = input("Enter the token address to approve: ").strip()
        amount_str = input("Enter the amount to approve (in tokens, e.g., 100): ").strip()
        decimals = int(input("Enter token decimals (e.g., 18): ").strip())
        required_amount = int(float(amount_str) * (10 ** decimals))
        print(f"Approving {required_amount} (raw units) for token {token_address} to SwapExecutor...")
        check_and_approve(token_address, SWAP_EXECUTOR_ADDRESS, required_amount)
    elif choice == "2":
        pool_address = input("Enter the target pool address: ").strip()
        direction = input("Enter direction ('buy' for buying EGGS using wS, 'sell' for selling EGGS for wS): ").strip().lower()

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
            sqrtPriceLimitX96 = 0  # signal to compute dynamically
        else:
            sqrtPriceLimitX96 = int(sqrt_limit_input)
        execute_swap(pool_address, zero_for_one, amountSpecified, sqrtPriceLimitX96)
    else:
        print("Invalid action selected.")

if __name__ == "__main__":
    main()
