import os
import json
from dotenv import load_dotenv
from web3 import Web3
from web3.exceptions import ContractLogicError, BadFunctionCallOutput

# Load environment variables
load_dotenv()

# Get RPC URL from .env file
RPC_URL = os.getenv("RPC_URL")
if not RPC_URL:
    print("Error: RPC_URL not found in .env file")
    exit(1)

# Pool address to check
POOL_ADDRESS = "0x6fEae13B486A225fB2247CCFda40bF8F1Dd9d4B1"

# Connect to the blockchain
web3 = Web3(Web3.HTTPProvider(RPC_URL))
if not web3.is_connected():
    print(f"Error: Could not connect to the blockchain using {RPC_URL}")
    exit(1)

print(f"Connected to blockchain at {RPC_URL}")
print(f"Checking pool contract at {POOL_ADDRESS}")

# Check if the address is valid
if not web3.is_address(POOL_ADDRESS):
    print(f"Error: {POOL_ADDRESS} is not a valid address")
    exit(1)

# Check if the address is a contract
code = web3.eth.get_code(Web3.to_checksum_address(POOL_ADDRESS))
if code == b'':
    print(f"Error: No contract found at address {POOL_ADDRESS}")
    exit(1)

print(f"Contract found at {POOL_ADDRESS}")

# ABIs for the methods we want to check
UNI_V3_SLOT0_ABI = [{
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
}]

ALGEBRA_GLOBAL_STATE_ABI = [{
    "inputs": [],
    "name": "globalState",
    "outputs": [
        {"internalType": "uint160", "name": "price", "type": "uint160"},
        {"internalType": "int24", "name": "tick", "type": "int24"},
        {"internalType": "uint16", "name": "fee", "type": "uint16"},
        {"internalType": "uint16", "name": "timepointIndex", "type": "uint16"},
        {"internalType": "uint8", "name": "communityFeeToken0", "type": "uint8"},
        {"internalType": "uint8", "name": "communityFeeToken1", "type": "uint8"},
        {"internalType": "bool", "name": "unlocked", "type": "bool"}
    ],
    "stateMutability": "view",
    "type": "function"
}]

# Get token information
TOKEN_ABI = [{
    "inputs": [],
    "name": "token0",
    "outputs": [{"internalType": "address", "name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
}, {
    "inputs": [],
    "name": "token1",
    "outputs": [{"internalType": "address", "name": "", "type": "address"}],
    "stateMutability": "view",
    "type": "function"
}]

ERC20_ABI = [{
    "constant": True,
    "inputs": [],
    "name": "symbol",
    "outputs": [{"name": "", "type": "string"}],
    "payable": False,
    "stateMutability": "view",
    "type": "function"
}]

def get_token_symbol(address):
    try:
        token_contract = web3.eth.contract(address=address, abi=ERC20_ABI)
        symbol = token_contract.functions.symbol().call()
        return symbol
    except Exception as e:
        return f"Unknown ({str(e)[:50]}...)"

# Try to get tokens
pool_contract = web3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=TOKEN_ABI)
try:
    token0_address = pool_contract.functions.token0().call()
    token1_address = pool_contract.functions.token1().call()
    token0_symbol = get_token_symbol(token0_address)
    token1_symbol = get_token_symbol(token1_address)
    print(f"\nPool tokens:")
    print(f"Token0: {token0_address} ({token0_symbol})")
    print(f"Token1: {token1_address} ({token1_symbol})")
except Exception as e:
    print(f"Error getting token information: {str(e)}")

print("\nTrying UniswapV3 interface...")
# Try to call slot0 method (UniswapV3)
uni_pool = web3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=UNI_V3_SLOT0_ABI)
try:
    slot0_result = uni_pool.functions.slot0().call()
    print("✅ UniswapV3 slot0() call succeeded!")
    print(f"sqrtPriceX96: {slot0_result[0]}")
    print(f"tick: {slot0_result[1]}")
    print(f"unlocked: {slot0_result[6]}")
    uniswap_v3_compatible = True
except ContractLogicError as e:
    print(f"❌ UniswapV3 slot0() call failed with contract logic error: {str(e)}")
    uniswap_v3_compatible = False
except BadFunctionCallOutput as e:
    print(f"❌ UniswapV3 slot0() call failed with bad output error: {str(e)}")
    uniswap_v3_compatible = False
except Exception as e:
    print(f"❌ UniswapV3 slot0() call failed with error: {str(e)}")
    uniswap_v3_compatible = False

print("\nTrying Algebra interface...")
# Try to call globalState method (Algebra)
algebra_pool = web3.eth.contract(address=Web3.to_checksum_address(POOL_ADDRESS), abi=ALGEBRA_GLOBAL_STATE_ABI)
try:
    global_state = algebra_pool.functions.globalState().call()
    print("✅ Algebra globalState() call succeeded!")
    print(f"price: {global_state[0]}")
    print(f"tick: {global_state[1]}")
    print(f"fee: {global_state[2]}")
    print(f"unlocked: {global_state[6]}")
    algebra_compatible = True
except ContractLogicError as e:
    print(f"❌ Algebra globalState() call failed with contract logic error: {str(e)}")
    algebra_compatible = False
except BadFunctionCallOutput as e:
    print(f"❌ Algebra globalState() call failed with bad output error: {str(e)}")
    algebra_compatible = False
except Exception as e:
    print(f"❌ Algebra globalState() call failed with error: {str(e)}")
    algebra_compatible = False

print("\nConclusion:")
if uniswap_v3_compatible and not algebra_compatible:
    print("This appears to be a Uniswap V3 pool (slot0() works, globalState() fails)")
elif algebra_compatible and not uniswap_v3_compatible:
    print("This appears to be an Algebra pool (globalState() works, slot0() fails)")
elif uniswap_v3_compatible and algebra_compatible:
    print("This contract implements both Uniswap V3 and Algebra interfaces (both calls work)")
else:
    print("This contract doesn't appear to match either Uniswap V3 or Algebra interface (both calls fail)")
    print("It might be a different type of pool or use a different interface.")

