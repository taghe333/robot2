import os
import time
import requests
from web3 import Web3
from web3.logs import STRICT, IGNORE, DISCARD
from dotenv import load_dotenv
from telegram.ext import Application
import asyncio
import json

# بارگذاری متغیرهای محیطی
load_dotenv()
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
TELEGRAM_BOT_TOKEN = "7800901726:AAFQE1AylajC6MA6W_GZHgwFI-HiMWhgW5E"
CHAT_ID = "@Wallethack1_bot"

# بررسی امنیت کلید خصوصی
if not PRIVATE_KEY:
    raise ValueError("کلید خصوصی در فایل .env پیدا نشد! ربات اجرا نمی‌شود.")

# تنظیمات شبکه Linea
LINEA_RPC_URL = "https://rpc.linea.build"
w3 = Web3(Web3.HTTPProvider(LINEA_RPC_URL))

# آدرس کیف پول و مقصد
WALLET_ADDRESS = "YOUR_HACKED_WALLET_ADDRESS"  # آدرس ولت هک‌شده
DESTINATION_ADDRESS = "YOUR_SAFE_WALLET_ADDRESS"  # آدرس ولت جدید و امن

# آدرس قرارداد توکن‌های شناخته‌شده
KNOWN_TOKENS = {
    "LXP": "0xd83af4fbD77f3AB65C3B1Dc4B38D7e67AEcf599A",  # آدرس LXP
    "USDC": "0xf56dc6695cF1f5c364eDEbC7Dc7077ac9B586068",  # آدرس USDC
    "LINEA": "0xYOUR_LINEA_TOKEN_ADDRESS"  # آدرس توکن $LINEA (بعد از اعلام رسمی جایگزین کن)
}

# ABI ساده برای توکن ERC-20
ERC20_ABI = json.loads('''
[
    {"constant":true,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"},
    {"constant":false,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[{"name":"success","type":"bool"}],"type":"function"},
    {"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}
]
''')

# دریافت قیمت ETH از CoinGecko
def get_eth_price():
    try:
        response = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd")
        return response.json()["ethereum"]["usd"]
    except:
        return 0

# بررسی موجودی ETH
def get_eth_balance(wallet_address):
    balance = w3.eth.get_balance(Web3.to_checksum_address(wallet_address))
    return balance / 10**18

# بررسی قابلیت انتقال توکن
def is_token_transferable(contract_address):
    if contract_address.lower() == KNOWN_TOKENS.get("LXP", "").lower():
        return False  # LXP فعلاً soulbound است
    return True

# انتقال ETH
def transfer_eth(amount, to_address, gas_multiplier=20):
    gas_price = w3.eth.gas_price * gas_multiplier
    if gas_price > 10**10:  # حداکثر ۱۰ Gwei
        gas_price = 10**10
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(WALLET_ADDRESS))

    txn = {
        'to': Web3.to_checksum_address(to_address),
        'value': int(amount * 10**18),
        'gas': 21000,
        'gasPrice': gas_price,
        'nonce': nonce,
        'chainId': 59144
    }

    signed_txn = w3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    return w3.to_hex(tx_hash)

# انتقال توکن ERC-20
def transfer_token(contract_address, amount, to_address, decimals=18, gas_multiplier=20):
    contract = w3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=ERC20_ABI)
    amount_wei = int(amount * 10**decimals)
    gas_price = w3.eth.gas_price * gas_multiplier
    if gas_price > 10**10:  # حداکثر ۱۰ Gwei
        gas_price = 10**10
    nonce = w3.eth.get_transaction_count(Web3.to_checksum_address(WALLET_ADDRESS))

    txn = contract.functions.transfer(
        Web3.to_checksum_address(to_address),
        amount_wei
    ).build_transaction({
        'from': Web3.to_checksum_address(WALLET_ADDRESS),
        'gas': 100000,
        'gasPrice': gas_price,
        'nonce': nonce,
        'chainId': 59144
    })

    signed_txn = w3.eth.account.sign_transaction(txn, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    return w3.to_hex(tx_hash)

# شناسایی توکن‌های جدید و مقدار واریزی
def get_new_tokens(wallet_address, last_block):
    new_tokens = {}
    current_block = w3.eth.block_number
    if last_block is None:
        last_block = current_block - 100

    for token_name, token_address in KNOWN_TOKENS.items():
        contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
        transfer_filter = contract.events.Transfer.create_filter(
            fromBlock=last_block,
            toBlock=current_block,
            argument_filters={'to': Web3.to_checksum_address(wallet_address)}
        )
        events = transfer_filter.get_all_entries()
        for event in events:
            if event['args']['to'].lower() == wallet_address.lower():
                token_address = event['address'].lower()
                amount = event['args']['value'] / 10**18  # فرض اولیه: 18 دسیمال
                if token_name == "USDC":
                    amount = event['args']['value'] / 10**6  # USDC 6 دسیمال
                if token_address not in new_tokens:
                    new_tokens[token_address] = {'address': token_address, 'amount': amount, 'name': token_name}
                elif token_address == KNOWN_TOKENS.get("LINEA", "").lower():
                    new_tokens["LINEA"] = {'address': token_address, 'amount': amount, 'name': "LINEA"}
                elif token_address == KNOWN_TOKENS.get("LXP", "").lower():
                    new_tokens["LXP"] = {'address': token_address, 'amount': amount, 'name': "LXP"}

    return new_tokens, current_block

# ارسال پیام به تلگرام
async def send_telegram_message(message):
    try:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        await app.bot.send_message(chat_id=CHAT_ID, text=message)
    except Exception as e:
        print(f"خطا در ارسال پیام به تلگرام: {str(e)}")

# چک کردن و انتقال خودکار
async def check_and_transfer():
    # ارسال پیام استارت ربات
    await send_telegram_message("ربات استارت شد! شروع رصد ولت هک‌شده...")
    print("ربات استارت شد!")

    last_block = None
    while True:
        try:
            # شناسایی توکن‌های جدید
            new_tokens, current_block = get_new_tokens(WALLET_ADDRESS, last_block)
            last_block = current_block

            # بررسی موجودی ETH
            eth_balance = get_eth_balance(WALLET_ADDRESS)
            eth_price = get_eth_price()
            eth_value_usd = eth_balance * eth_price

            if eth_balance > 0 and eth_value_usd > 5:  # حداقل ۵ دلار
                tx_hash = transfer_eth(eth_balance, DESTINATION_ADDRESS)
                message = f"انتقال ETH انجام شد! مقدار: {eth_balance:.4f} ETH (ارزش: ${eth_value_usd:.2f}) TXID: {tx_hash}"
                await send_telegram_message(message)
                print(message)

            # بررسی و انتقال توکن‌های جدید (شناخته‌شده و ناشناس)
            for token_key, token_info in new_tokens.items():
                token_address = token_info['address']
                amount = token_info['amount']
                token_name = token_info.get('name', token_address[:10])
                decimals = 6 if token_address.lower() == KNOWN_TOKENS.get("USDC", "").lower() else 18
                if amount > 0:
                    if not is_token_transferable(token_address):
                        message = f"توکن {token_name} (مقدار: {amount:.4f}) فعلاً غیرقابل انتقال است!"
                        await send_telegram_message(message)
                        print(message)
                        continue

                    tx_hash = transfer_token(token_address, amount, DESTINATION_ADDRESS, decimals)
                    message = f"انتقال {token_name} انجام شد! مقدار: {amount:.4f} TXID: {tx_hash}"
                    await send_telegram_message(message)
                    print(message)

        except Exception as e:
            error_message = f"خطا: {str(e)}"
            await send_telegram_message(error_message)
            print(error_message)
            if "429" in str(e) or "rate limit" in str(e).lower():
                print("خطای Rate Limit! ۵ ثانیه صبر می‌کنم...")
                time.sleep(5)
            elif "gas price" in str(e).lower():
                print("خطای گس فی! تلاش با گس فی کمتر...")
                time.sleep(2)
            else:
                time.sleep(2)  # بازه ۲ ثانیه

# اجرای ربات
def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(check_and_transfer())

if __name__ == "__main__":
    main()
