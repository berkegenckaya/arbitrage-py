import os
import json
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

def execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Executes a swap via the SwapExecutor contract.
    pool_address: The target pool contract address.
    zeroForOne: If true, swaps token0 for token1 (sell base); if false, swaps token1 for token0 (buy base).
    amountSpecified: Amount to swap (in the smallest unit of the input token).
    sqrtPriceLimitX96: Slippage limit in Q96 format (if 'max', use TickMath.MAX_SQRT_RATIO - 1).
    """
    pool_address = w3.to_checksum_address(pool_address)
    tx = swap_executor.functions.executeSwap(
        pool_address,
        zeroForOne,
        amountSpecified,
        sqrtPriceLimitX96
    ).build_transaction({
        'from': YOUR_ADDRESS,
        'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
        'gas': 2000000,  # Adjust according to your needs
        'gasPrice': get_gas_price()
    })
    signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    print("Swap tx sent. Tx hash:", w3.to_hex(tx_hash))
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    print("Swap receipt:", receipt)

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
        direction = input("Enter direction ('buy' for buying token0 with token1, 'sell' for selling token0 for token1): ").strip().lower()
        if direction == "buy":
            zeroForOne = False
        elif direction == "sell":
            zeroForOne = True
        else:
            print("Invalid direction.")
            return
        amount_str = input("Enter the swap amount (in tokens) for the input token: ").strip()
        decimals = int(input("Enter the input token decimals (e.g., 18): ").strip())
        amountSpecified = int(float(amount_str) * (10 ** decimals))
        sqrt_limit_input = input("Enter sqrtPriceLimitX96 (as a number) or 'max' for no effective limit: ").strip()
        if sqrt_limit_input.lower() == "max":
            sqrtPriceLimitX96 = 1461446703485210103287273052203988822378723970340  # TickMath.MAX_SQRT_RATIO - 1
        else:
            sqrtPriceLimitX96 = int(sqrt_limit_input)
        execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96)
    else:
        print("Invalid action selected.")

if __name__ == "__main__":
    main()
