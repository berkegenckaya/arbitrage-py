import os
import time
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from flask_cors import CORS
import openai
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
SWAP_EXECUTOR_ADDRESS =os.environ.get("SWAP_EXECUTOR_ADDRESS")

# Connect to the network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    print("Connection to RPC failed.")
    exit()

YOUR_ADDRESS = w3.to_checksum_address(YOUR_ADDRESS)
SWAP_EXECUTOR_ADDRESS = w3.to_checksum_address(SWAP_EXECUTOR_ADDRESS)

# Load the SwapExecutor contract ABI from file
with open('SwapExecutorABI.json', 'r') as abi_file:
    swap_executor_abi = json.load(abi_file)

swap_executor = w3.eth.contract(address=SWAP_EXECUTOR_ADDRESS, abi=swap_executor_abi)

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


# Placeholder fonksiyonlar (OpenAI Thread API benzeri işlevler)
def get_gas_price():
    """ Fetches the current gas price and adds a 10% buffer. """
    base_gas_price = w3.eth.gas_price
    return int(base_gas_price * 1.1)

def check_and_approve(token_address, spender, required_amount):
    """ Checks and approves ERC20 token allowance. """
    token_address = w3.to_checksum_address(token_address)
    token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    current_allowance = token_contract.functions.allowance(YOUR_ADDRESS, spender).call()
    
    if current_allowance < required_amount:
        tx = token_contract.functions.approve(spender, required_amount).build_transaction({
            'from': YOUR_ADDRESS,
            'nonce': w3.eth.get_transaction_count(YOUR_ADDRESS),
            'gas': 100000,
            'gasPrice': get_gas_price()
        })
        signed_tx = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        return {"status": "approved", "tx_hash": w3.to_hex(tx_hash)}
    
    return {"status": "already_approved"}

def execute_swap(pool_address, zeroForOne, amountSpecified, sqrtPriceLimitX96):
    """ Executes a token swap. """
    pool_address = w3.to_checksum_address(pool_address)
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
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return {"status": "swap_executed", "tx_hash": w3.to_hex(tx_hash)}


def create_thread():
    print("Creating a new thread...")
    # Gerçek API çağrısı; örneğin:
    thread = openai.beta.threads.create()
    return thread

def add_message(thread_id, message):
    print(f"Adding a new message to thread: {thread_id}")
    # Mesajı eklerken tüm parametreleri keyword argümanları şeklinde veriyoruz.
    response = openai.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message
    )
    return response

def run_assistant(thread_id):
    print(f"Running assistant for thread: {thread_id}")
    response = openai.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
    )
    print(response)
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

def submit_tool_outputs(thread_id, run_id, tool_call_id, output_dict):
    print(f"Submitting tool outputs: thread={thread_id}, run={run_id}, tool_call_id={tool_call_id}")
    print("Output sent:", output_dict)
    response = openai.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=[{
            "tool_call_id": tool_call_id,
            "output": json.dumps(output_dict)
        }]
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
    url = f"https://api.dexscreener.com/token-pairs/v1/{chain_id}//{token_address}"
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
@app.route('/approve', methods=['POST'])
def approve_endpoint():
    data = request.get_json()
    token_address = data.get("token_address")
    amount = int(data.get("amount"))
    response = check_and_approve(token_address, SWAP_EXECUTOR_ADDRESS, amount)
    return jsonify(response)

@app.route('/swap', methods=['POST'])
def swap_endpoint():
    data = request.get_json()
    pool_address = data.get("pool_address")
    zeroForOne = data.get("zeroForOne")
    amountSpecified = data.get("amountSpecified")
    sqrtPriceLimitX96 = data.get("sqrtPriceLimitX96")

    response = execute_swap(pool_address, True, amountSpecified, 1461446703485210103287273052203988822378723970340)
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
        return jsonify({"error": "Hem 'message' hem de 'threadId' gereklidir."}), 400

    add_message(threadId, message)
    run = run_assistant(threadId)
    runId = run.id

    # Polling: Asistanın durumunu 5 saniyelik aralıklarla kontrol et
    while True:
        status, run_object = checking_status(threadId, runId)
        if status == "completed":
            messages_list = list_messages(threadId)
            # Gerçek OpenAI cevabı genellikle "assistant" rolündeki mesajda yer alır.
            assistant_message = next((msg for msg in messages_list if msg.role == "assistant"), None)
            if assistant_message:
                    return jsonify({"assistant_response": str(assistant_message.content[0].text.value)})

            else:
                return jsonify({"assistant_response": "Assistant yanıtı bulunamadı."})
        elif status == "requires_action":
            print("🔄 Assistant requires an action...")
            tool_calls = run_object.required_action.submit_tool_outputs.tool_calls
            if tool_calls:
                tool_call = tool_calls[0]
                function_name = tool_call.function.name;
                
                if function_name == "get_pair_info":
                    print("📩 Assistant requested yield pair analysis...")
                    parsed_args = json.loads(tool_call.function.arguments or "{}")
                    print("Parsed Args:", parsed_args)
                    chainId_arg = parsed_args.get("chainId")
                    tokenAddress_arg = parsed_args.get("tokenAddress")
                    pair_info = get_pair_info(chainId_arg, tokenAddress_arg)
                    submit_tool_outputs(threadId, runId, tool_call.id, {"pairInfo": pair_info})
                    print("✅ Yield pair info sent to OpenAI!")
                elif function_name == "execute_swap":
                    print("📩 Assistant requested swap execution...")
                    parsed_args = json.loads(tool_call.function.arguments or "{}")
                    print("Parsed Args:", parsed_args)
                    response = execute_swap(
                        parsed_args.get("pool_address"),
                        False,
                        parsed_args.get("amountSpecified"),
                        1461446703485210103287273052203988822378723970340
                    )
                    submit_tool_outputs(threadId, runId, tool_call.id, response)
                elif function_name == "approve_tokens":
                    parsed_args = json.loads(tool_call.function.arguments or "{}")
                    response = check_and_approve(
                        parsed_args.get("token_address"),
                        SWAP_EXECUTOR_ADDRESS,
                        parsed_args.get("amount")
                    )
                    submit_tool_outputs(threadId, runId, tool_call.id, response)

                
        time.sleep(5)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3001))
    app.run(host="0.0.0.0", port=port)