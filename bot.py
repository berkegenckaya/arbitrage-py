import os
import time
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
import openai
import math
from web3 import Web3

load_dotenv()

app = Flask(__name__)
CORS(app) 

# OpenAI ayarları
openai.api_key = "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"
assistant_id = "asst_IbPuyTELoe3dEZxhFzs05VbM"

RPC_URL = os.environ.get("RPC_URL")
PRIVATE_KEY = os.environ.get("PRIVATE_KEY")
YOUR_ADDRESS = os.environ.get("YOUR_ADDRESS")
""" SWAP_EXECUTOR_ADDRESS =os.environ.get("SWAP_EXECUTOR_ADDRESS") """
WS_ADDRESS = os.environ.get("WS_ADDRESS")  # Wrapped S token address
SWAP_EXECUTOR_UNI_ADDRESS = os.environ.get("SWAP_EXECUTOR_UNI_ADDRESS")
SWAP_EXECUTOR_ALG_ADDRESS = os.environ.get("SWAP_EXECUTOR_ALG_ADDRESS")




# Connect to the network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Connection to RPC failed.")
    exit()


YOUR_ADDRESS = w3.to_checksum_address(YOUR_ADDRESS)
""" SWAP_EXECUTOR_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ADDRESS) """
WS_ADDRESS = w3.to_checksum_address("0x039e2fB66102314Ce7b64Ce5Ce3E5183bc94aD38")
SWAP_EXECUTOR_UNI_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_UNI_ADDRESS)
SWAP_EXECUTOR_ALG_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ALG_ADDRESS)

# Load the SwapExecutor contract ABI from file
with open('SwapExecutorUniABI.json', 'r') as abi_file:
    swap_executor_abi = json.load(abi_file)

""" swap_executor = w3.eth.contract(address=SWAP_EXECUTOR_ADDRESS, abi=swap_executor_abi)
 """
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


# Placeholder fonksiyonlar (OpenAI Thread API benzeri işlevler)
def get_gas_price():
    """ Fetches the current gas price and adds a 10% buffer. """
    base_gas_price = w3.eth.gas_price
    return int(base_gas_price * 1.1)

def check_and_approve(token_address, spender, required_amount):
    """Checks token allowance and sends an approval transaction if needed."""
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
        return {"status": "approved"}
    
    return {"status": "already_approved"}

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
    return {"status": "swapped", "tx_hash": w3.to_hex(tx_hash)}

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

    return {"status": "swapped", "tx_hash": w3.to_hex(tx_hash)}


def execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """
    Automatically detects if the pool is Uniswap or Algebra, then calls the appropriate function.
    """
    pool_type = autodetect_pool_type(pool_address)
    if pool_type == "uni":
        print("Detected Uniswap pool. Routing to execute_swap_uni...")
        return execute_swap_uni(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96)
    elif pool_type == "alg":
        print("Detected Algebra pool. Routing to execute_swap_alg...")
        return execute_swap_alg(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96)
    else:
        raise Exception("Could not detect pool type. Not a Uniswap or Algebra pool.")
    

def create_thread():
    print("Creating a new thread...")
    # Gerçek API çağrısı; örneğin:
    thread = openai.beta.threads.create()
    return thread

def get_active_run(thread_id):
    """Return the active run ID if there is one, else None."""
    runs = openai.beta.threads.runs.list(thread_id=thread_id)
    for run in runs.data:
        if run.status in ["queued", "in_progress"]:
            return run.id
    return None

def wait_for_run_to_complete(thread_id, run_id, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        run = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        if run.status in ["completed", "failed", "cancelled"]:
            print(f"Run {run_id} has completed or been cancelled.")
            return True
        print(f"Run {run_id} is still active. Waiting 5 seconds...")
        time.sleep(5)
    return False

def cancel_run(thread_id, run_id):
    """Cancel the active run for the given thread."""
    try:
        print(f"Cancelling run {run_id} in thread {thread_id}...")
        response = openai.beta.threads.runs.cancel(
            thread_id=thread_id,
            run_id=run_id
        )
        print(f"Run {run_id} cancellation initiated.")
        return response
    except Exception as e:
        print(f"Error cancelling run {run_id}: {e}")
        return None
def cancel_run_with_retries(thread_id, run_id, retries=3, delay=3):
    for i in range(retries):
        try:
            print(f"Attempt {i+1} to cancel run {run_id}...")
            cancel_run(thread_id, run_id)
            if wait_for_run_to_complete(thread_id, run_id, timeout=5):
                return True
        except Exception as e:
            print(f"Cancel attempt {i+1} failed: {e}")
        time.sleep(delay)
    return False

def add_message_safe(thread_id, message, max_retries=5, retry_interval=3):
    retries = 0
    while retries < max_retries:
        try:
            print(f"Attempting to add new message to thread: {thread_id}")
            response = openai.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=message
            )
            print("Message added successfully.")
            return response
        except openai.BadRequestError as e:
            error_str = str(e)
            if "Can't add messages to" in error_str:
                print(f"Error detected: {error_str}")
                active_run = get_active_run(thread_id)
                if active_run:
                    print(f"Active run {active_run} detected. Attempting to cancel it...")
                    if not cancel_run_with_retries(thread_id, active_run):
                        print("Warning: Active run could not be cancelled in time. Proceeding anyway might cause errors.")
                else:
                    print("No active run detected despite error message.")
            else:
                raise e
        retries += 1
        print(f"Retrying to add message (attempt {retries}/{max_retries})...")
        time.sleep(retry_interval)
    raise Exception("Max retries exceeded. Could not add message to thread.")
def run_assistant_with_cancel(thread_id):
    """
    Cancels any active run and then starts a new run on the thread.
    """
    active_run = get_active_run(thread_id)
    if active_run:
        print(f"Active run {active_run} detected. Cancelling it...")
        cancel_run(thread_id, active_run)
        if not wait_for_run_to_complete(thread_id, active_run):
            raise Exception("Active run did not finish cancelling within the timeout period.")
    print(f"Starting new run for thread: {thread_id}")
    response = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    print("New run started:", response)
    return response

def add_message_safe(thread_id, message):
    """
    Adds a message to the thread safely. If a run is active, it cancels it first.
    """
    active_run = get_active_run(thread_id)
    if active_run:
        print(f"Active run {active_run} found. Cancelling before adding new message...")
        cancel_run(thread_id, active_run)
        time.sleep(5)  # Give time for cancellation to take effect.
    print(f"Adding a new message to thread: {thread_id}")
    response = openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
    return response

def retrieve_run(thread_id, run_id):
    print(f"Retrieving run status for thread {thread_id}, run {run_id}...")
    response = openai.beta.threads.runs.retrieve(
        thread_id=thread_id,
        run_id=run_id
    )
    return response

def list_messages(thread_id):
    print(f"Listing messages for thread: {thread_id}")
    # Gerçek API çağrısı; yanıtın yapısına göre mesajları döndürün.
    response = openai.beta.threads.messages.list(thread_id)
    messages = response.data
    return messages

def submit_tool_outputs(thread_id, run_id, tool_outputs):
    print(f"Submitting {len(tool_outputs)} tool outputs: thread={thread_id}, run={run_id}")
    for tool_output in tool_outputs:
        print(f"🔹 Tool Call ID: {tool_output['call_id']}")
        print(f"🔹 Output Sent: {tool_output['output']}")

    # Submit all tool outputs at once
    response = openai.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=[{
            "tool_call_id": tool_output["call_id"],
            "output": json.dumps(tool_output["output"])
        } for tool_output in tool_outputs]  # Convert list to correct format
    )

    return response


def checking_status(thread_id, run_id):
    run_object = retrieve_run(thread_id, run_id)
    status = run_object.status
    print("Current status:", status)
    return status, run_object

# DexScreener API Entegrasyonu
""" def analyze_yield_pair(api_response):
    pairs = []
    if isinstance(api_response, list):
        pairs = api_response
    elif "pairs" in api_response and isinstance(api_response["pairs"], list):
        pairs = api_response["pairs"]
    elif "pair" in api_response:
        pairs = [api_response["pair"]]
    else:
        return ["Beklenen formatta bir API cevabı alınamadı."]
    
    results = []
    for pair in pairs:
        baseToken = pair.get("baseToken", {})
        dexId = pair.get("dexId", "Bilinmiyor")
        quoteToken = pair.get("quoteToken", {})
        priceNative = pair.get("priceNative", "Bilinmiyor")
        priceUsd = pair.get("priceUsd", "Bilinmiyor")
        result = (f"Yield Çifti: {baseToken.get('symbol', 'Bilinmiyor')}/"
                  f"{quoteToken.get('symbol', 'Bilinmiyor')}\n"
                  f"Dex ID: {dexId}\n"
                  f"Native Fiyat: {priceNative}\n"
                  f"USD Fiyat: {priceUsd}\n\n")
        results.append(result)
    return results
 """
def fetch_token_pools(chain_id, token_address):
    """
    Fetch all pools for a given token address on a specified chain using the DexScreener API.
    Endpoint: /token-pairs/v1/{chainId}//{tokenAddress}
    Example URL for Sonic: https://api.dexscreener.com/token-pairs/v1/sonic//{tokenAddress}
    """
    url = f"https://api.dexscreener.com/token-pairs/v1/sonic//{token_address}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        pools = response.json()  # Expected to be a JSON array of pool objects
        return pools
    except Exception as e:
        print("Error fetching token pools:", e)
        return []
    
""" def compute_effective_price(pool, token_address_lower):
    
    Given a pool and the token address (lowercase), determine the effective USD price for that token.
    - If the token is the baseToken, use priceUsd.
    - If the token is the quoteToken, effective price is 1/priceUsd.
    Returns effective price (float) and a string indicating the token position ("base" or "quote").
   
    try:
        priceUsd = float(pool.get("priceUsd", "0"))
    except Exception:
        return None, None

    base = pool.get("baseToken", {})
    quote = pool.get("quoteToken", {})
    base_addr = base.get("address", "").lower()
    quote_addr = quote.get("address", "").lower()
    
    # If token appears as baseToken
    if token_address_lower == base_addr:
        return priceUsd, "base"
    # If token appears as quoteToken, invert priceUsd (if non-zero)
    elif token_address_lower == quote_addr:
        if priceUsd != 0:
            return 1 / priceUsd, "quote"
        else:
            return None, None
    else:
        # Token not found in this pool (shouldn't happen if filtering by token address)
        return None, None

 """
def report_arbitrage_from_pools(pools, token_address, min_liquidity=10000):
    """
    For a list of pool objects, compute the USD price for the given token,
    but only consider pools where the token appears as the base token.
    Pools with liquidity below min_liquidity are filtered out.
    Then, sort the pools by price (high to low) and report the highest and lowest prices,
    along with the computed percentage difference. Display the DEX, constructed pair name, and pair address.
    """
    token_address_lower = token_address.lower()
    valid_prices = []
    token_name = None

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
            lines = []
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
            lines.append(f"Arbitrage details for {token_label} (Address: {token_address}) – considering pools with liquidity >= ${min_liquidity}:\n")
            lines.append("-" * 80)
            for entry in sorted_prices:
                lines.append(f"DEX: {entry['dexId']} | Pair: {entry['pairName']} | Pair Address: {entry['pairAddress']} | Price: {entry['priceUsd']:.6f} USD | Liquidity: ${entry['liquidityUsd']:.2f}")
            lines.append("-" * 80)
            lines.append("Highest Price:")
            lines.append(f"   {highest['priceUsd']:.6f} USD on DEX: {highest['dexId']} | Pair: {highest['pairName']} | Pair Address: {highest['pairAddress']}")
            lines.append("Lowest Price:")
            lines.append(f"   {lowest['priceUsd']:.6f} USD on DEX: {lowest['dexId']} | Pair: {lowest['pairName']} | Pair Address: {lowest['pairAddress']}")
            lines.append(f"Price Difference: {diff_percent:.2f}%\n")
            return "\n".join(lines)
        else:
            print("Lowest price is zero, cannot calculate arbitrage.")
    else:
        print("Not enough pool data to compute arbitrage details.")
        
def get_pair_info(chain_id, token_address):
    """
    OpenAI asistanı tarafından çağrıldığında, verilen chain ve token adresine göre DexScreener API'sinden 
    havuz verilerini çekip arbitrage raporu oluşturur.
    """
    print(f"Fetching token pools for chain {chain_id} and token {token_address}...")
    pools = fetch_token_pools(chain_id, token_address)
    if pools:
        arbitrage_report = report_arbitrage_from_pools(pools, token_address, min_liquidity=10000)
        return arbitrage_report
    else:
        return "No pool data found."
""" @app.route('/approve', methods=['POST'])
def approve_endpoint():
    data = request.get_json()
    token_address = data.get("token_address")
    amount = int(data.get("amount"))
    response = check_and_approve(token_address, SWAP_EXECUTOR_ADDRESS, amount)
    return jsonify(response) """

@app.route('/swap', methods=['POST'])
def swap_endpoint():
    data = request.get_json()
    pool_address = "0x713FB5036dC70012588d77a5B066f1Dd05c712d7"
    zeroForOne = True
    amountSpecified = 1
    

    response = execute_swap("0x713FB5036dC70012588d77a5B066f1Dd05c712d7", True, 1, 79228162514264337593543950336)
    return jsonify(response)
# Flask Endpoint'leri
@app.route('/pairinfo', methods=['GET'])
def pairinfo():
    chainId = request.args.get('chainId')
    tokenAddress = request.args.get('tokenAddress')
    if not chainId or not tokenAddress:
        return jsonify({"error": "chainId ve tokenAddress sorgu parametreleri gereklidir."}), 400
    result = get_pair_info(chainId, tokenAddress)
    return jsonify({"result": result})

@app.route('/thread', methods=['GET'])
def thread_endpoint():
    thread = create_thread()
    return jsonify({"threadId": thread.id})

@app.route('/message', methods=['POST'])
def message_endpoint():
    data = request.get_json()
    message = data.get("message")
    threadId = data.get("threadId")

    if not message or not threadId:
        return jsonify({"error": "Both 'message' and 'threadId' are required."}), 400

    # Add message and initiate assistant run
    add_message_safe(threadId, message)
    run = run_assistant_with_cancel(threadId)
    runId = run.id

    # Polling: Check assistant status every 5 seconds
    while True:
        status, run_object = checking_status(threadId, runId)

        if status == "completed":
            messages_list = list_messages(threadId)
            assistant_message = next((msg for msg in messages_list if msg.role == "assistant"), None)

            return jsonify({"assistant_response": assistant_message.content[0].text.value if assistant_message else "No response from assistant."})

        elif status == "requires_action":
            print("🔄 Assistant requires an action...")

            tool_calls = run_object.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []

            for tool_call in tool_calls:
                function_name = tool_call.function.name
                parsed_args = json.loads(tool_call.function.arguments or "{}")
                print(f"📩 Assistant requested: {function_name}")
                print("Parsed Args:", parsed_args)

                if function_name == "get_pair_info":
                    response = get_pair_info(parsed_args.get("chainId"), parsed_args.get("tokenAddress"))
                    tool_outputs.append({"call_id": tool_call.id, "output": {"pairInfo": response}})
                    print("✅ Yield pair info sent to OpenAI!")

                elif function_name == "execute_swap":
                    response = execute_swap(
                        parsed_args.get("pool_address"),
                        parsed_args.get("zeroForOne"),
                        int(float(parsed_args.get("amountSpecified")* (10 ** 18))),
                        0,
                    )
                    tool_outputs.append({"call_id": tool_call.id, "output": response})
                    print("✅ Swap execution response sent to OpenAI!")

              

            # Submit all tool outputs at once to prevent missing responses
            if tool_outputs:
                submit_tool_outputs(threadId, runId, tool_outputs)

        time.sleep(5)  # Wait before polling again

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3001))
    app.run(host="0.0.0.0", port=port)


"""  elif function_name == "approve_tokens":
                    response = check_and_approve(
                        parsed_args.get("token_address"),
                        SWAP_EXECUTOR_ADDRESS,
                        parsed_args.get("amount")
                    )
                    tool_outputs.append({"call_id": tool_call.id, "output": response})
                    print("✅ Token approval response sent to OpenAI!") """