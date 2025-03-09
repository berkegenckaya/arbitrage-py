from web3 import Web3
import os
import json
import binascii
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Connect to the blockchain
rpc_url = os.getenv("RPC_URL")
if not rpc_url:
    print("Error: RPC_URL not found in .env file")
    exit(1)

w3 = Web3(Web3.HTTPProvider(rpc_url))
if not w3.is_connected():
    print(f"Error: Could not connect to {rpc_url}")
    exit(1)

print(f"Connected to network: {w3.eth.chain_id}")

# Pool address to check
POOL_ADDRESS = "0x6fEae13B486A225fB2247CCFda40bF8F1Dd9d4B1"

# Different ABI variations for globalState
abi_variations = [
    # Original ABI from swap_UniAlg.py - returns 7 values
    {
        "name": "Original Algebra ABI",
        "abi": [{
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "price", "type": "uint160"}, 
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "fee", "type": "uint16"},
                {"internalType": "uint16", "name": "timepointIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "communityFeeToken0", "type": "uint16"},
                {"internalType": "uint8", "name": "communityFeeToken1", "type": "uint8"}, 
                {"internalType": "bool", "name": "unlocked", "type": "bool"}
            ],
            "stateMutability": "view",
            "type": "function"
        }]
    },
    
    # Modified ABI variation 1 - try different types or order
    {
        "name": "Modified ABI 1 (sqrtPriceX96 only)",
        "abi": [{
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"}
            ],
            "stateMutability": "view",
            "type": "function"
        }]
    },
    
    # Modified ABI variation 2 - try fewer parameters
    {
        "name": "Modified ABI 2 (price and tick only)",
        "abi": [{
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "price", "type": "uint160"}, 
                {"internalType": "int24", "name": "tick", "type": "int24"}
            ],
            "stateMutability": "view",
            "type": "function"
        }]
    },
    
    # Modified ABI variation 3 - try with all uint256
    {
        "name": "Modified ABI 3 (all uint256)",
        "abi": [{
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint256", "name": "price", "type": "uint256"}, 
                {"internalType": "uint256", "name": "tick", "type": "uint256"},
                {"internalType": "uint256", "name": "fee", "type": "uint256"}
            ],
            "stateMutability": "view",
            "type": "function"
        }]
    },
    
    # Try 5 parameters variation
    {
        "name": "Modified ABI 4 (5 parameters)",
        "abi": [{
            "inputs": [],
            "name": "globalState",
            "outputs": [
                {"internalType": "uint160", "name": "price", "type": "uint160"}, 
                {"internalType": "int24", "name": "tick", "type": "int24"},
                {"internalType": "uint16", "name": "fee", "type": "uint16"},
                {"internalType": "uint16", "name": "timepointIndex", "type": "uint16"},
                {"internalType": "uint16", "name": "communityFee", "type": "uint16"}
            ],
            "stateMutability": "view",
            "type": "function"
        }]
    }
]

def get_raw_data(contract_address, method_signature):
    """Get raw bytes from a contract call without decoding"""
    method_signature_hash = w3.keccak(text=method_signature)[:4].hex()
    data = {'to': contract_address, 'data': method_signature_hash}
    result = w3.eth.call(data)
    return result

def main():
    pool_address = Web3.to_checksum_address(POOL_ADDRESS)
    print(f"Checking Algebra pool at {pool_address}\n")
    
    # First, get and display the raw return data
    raw_result = get_raw_data(pool_address, "globalState()")
    print(f"Raw data from globalState() call: {raw_result.hex()}")
    print(f"Raw data length: {len(raw_result)} bytes")
    print("=" * 80)
    
    # Try each ABI variation
    for variation in abi_variations:
        print(f"Testing {variation['name']}:")
        
        # Create contract instance with this ABI
        contract = w3.eth.contract(address=pool_address, abi=variation['abi'])
        
        try:
            # Try to call the function with this ABI
            result = contract.functions.globalState().call()
            print(f"Success! Result: {result}")
        except Exception as e:
            print(f"Error: {e}")
        
        print("-" * 80)
    
    # Manually inspect raw bytes
    print("\nManual analysis of the raw bytes:")
    raw_bytes = raw_result
    
    # Try to parse different chunks of the binary data
    if len(raw_bytes) >= 32:
        # First 32 bytes - potential first parameter (e.g., uint160 sqrtPriceX96)
        first_value = int.from_bytes(raw_bytes[:32], byteorder='big')
        print(f"First 32 bytes as uint256: {first_value}")
        print(f"As hex: 0x{first_value:x}")
    
    if len(raw_bytes) >= 64:
        # Second 32 bytes - potential second parameter
        second_value = int.from_bytes(raw_bytes[32:64], byteorder='big')
        print(f"Second 32 bytes as uint256: {second_value}")
        print(f"As hex: 0x{second_value:x}")
        # Try interpreting as int24
        if second_value > 2**23:  # If this might be a negative number in 24 bits
            adjusted = second_value - 2**24
        else:
            adjusted = second_value
        print(f"Second value as int24: {adjusted}")
    
    # Print the raw bytes in chunks of 32 bytes for easier analysis
    print("\nBytes in 32-byte chunks:")
    for i in range(0, len(raw_bytes), 32):
        chunk = raw_bytes[i:i+32]
        chunk_hex = chunk.hex()
        chunk_int = int.from_bytes(chunk, byteorder='big')
        print(f"Chunk {i//32 + 1}: 0x{chunk_hex} (int: {chunk_int})")

if __name__ == "__main__":
    main()

