import os
import time
import json
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import openai

load_dotenv()

app = Flask(__name__)

# OpenAI ayarları
openai.api_key = "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"
assistant_id = "asst_IbPuyTELoe3dEZxhFzs05VbM"

# Placeholder fonksiyonlar (OpenAI Thread API benzeri işlevler)

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
def analyze_yield_pair(api_response):
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
    
def compute_effective_price(pool, token_address_lower):
    """
    Given a pool and the token address (lowercase), determine the effective USD price for that token.
    - If the token is the baseToken, use priceUsd.
    - If the token is the quoteToken, effective price is 1/priceUsd.
    Returns effective price (float) and a string indicating the token position ("base" or "quote").
    """
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


def report_arbitrage_from_pools(pools, token_address, min_liquidity=10000):
    token_address_lower = token_address.lower()
    effective_prices = []
    
    for pool in pools:
        try:
            liquidity_usd = float(pool.get("liquidity", {}).get("usd", 0))
            if liquidity_usd < min_liquidity:
                continue

            eff_price, position = compute_effective_price(pool, token_address_lower)
            if eff_price is None:
                continue
            effective_prices.append({
                "dexId": pool.get("dexId", "unknown"),
                "effectivePrice": eff_price,
                "pairAddress": pool.get("pairAddress", "unknown"),
                "liquidityUsd": liquidity_usd,
                "position": position
            })
        except Exception:
            continue

    if len(effective_prices) > 1:
        highest = max(effective_prices, key=lambda x: x["effectivePrice"])
        lowest = min(effective_prices, key=lambda x: x["effectivePrice"])
        if lowest["effectivePrice"] > 0:
            diff_percent = ((highest["effectivePrice"] - lowest["effectivePrice"]) / lowest["effectivePrice"]) * 100
            lines = []
            lines.append(f"Arbitrage details for token (pools with liquidity >= ${min_liquidity}):")
            for entry in effective_prices:
                lines.append(f"  DEX: {entry['dexId']} - Effective Price: {entry['effectivePrice']:.6f} USD "
                             f"(Position: {entry['position']}), Liquidity: ${entry['liquidityUsd']:.2f}")
            lines.append(f"Highest Effective Price: {highest['effectivePrice']:.6f} USD, "
                         f"Lowest Effective Price: {lowest['effectivePrice']:.6f} USD")
            lines.append(f"Price Difference: {diff_percent:.2f}%")
            return "\n".join(lines)
        else:
            return "Lowest effective price is zero, cannot calculate arbitrage."
    else:
        return "Not enough pool data to compute arbitrage details."

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
        time.sleep(5)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port)