import json
import os
import time
from dotenv import load_dotenv
from web3 import Web3
from eth_account import Account
from flashbots import flashbot, Flashbots

# Load environment variables
load_dotenv()

# Initialize Web3 with Alchemy RPC
ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
if not ALCHEMY_API_KEY:
    raise ValueError("ALCHEMY_API_KEY is missing in environment variables")

w3 = Web3(Web3.HTTPProvider(f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"))

# Check RPC connection
if not w3.is_connected():
    raise ConnectionError("Failed to connect to Ethereum RPC")

print("RPC Connected:", w3.is_connected())
print("Current Block Number:", w3.eth.block_number)
print("Chain ID:", w3.eth.chain_id)

# Load private keys
SPONSOR_PRIVATE_KEY = os.getenv("SPONSOR_PRIVATE_KEY")
HACKED_PRIVATE_KEY = os.getenv("HACKED_PRIVATE_KEY")

if not SPONSOR_PRIVATE_KEY or not HACKED_PRIVATE_KEY:
    raise ValueError("Private key missing in environment variables")

# Create account objects
sponsor_account = Account.from_key(SPONSOR_PRIVATE_KEY.strip())
hacked_account = Account.from_key(HACKED_PRIVATE_KEY.strip())

print("Sponsor Wallet Address:", sponsor_account.address)
print("Hacked Wallet Address:", hacked_account.address)

# Initialize Flashbots middleware
flashbot(w3, sponsor_account, "https://relay.flashbots.net")

# WETH Token Contract
TOKEN_ADDRESS = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
TOKEN_ABI = json.loads('[{"constant":true,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"guy","type":"address"},{"name":"wad","type":"uint256"}],"name":"approve","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"src","type":"address"},{"name":"dst","type":"address"},{"name":"wad","type":"uint256"}],"name":"transferFrom","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":false,"inputs":[{"name":"wad","type":"uint256"}],"name":"withdraw","outputs":[],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":true,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[{"name":"","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":true,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":false,"stateMutability":"view","type":"function"},{"constant":false,"inputs":[{"name":"dst","type":"address"},{"name":"wad","type":"uint256"}],"name":"transfer","outputs":[{"name":"","type":"bool"}],"payable":false,"stateMutability":"nonpayable","type":"function"},{"constant":false,"inputs":[{"name":"guy","type":"address"},{"name":"wad","type":"uint256"}],"name":"deposit","outputs":[],"payable":true,"stateMutability":"payable","type":"function"},{"constant":true,"inputs":[],"name":"allowance","outputs":[{"name":"","type":"uint256"}],"payable":false,"stateMutability":"view","type":"function"},{"payable":true,"stateMutability":"payable","type":"fallback"},{"anonymous":false,"inputs":[{"indexed":true,"name":"src","type":"address"},{"indexed":true,"name":"guy","type":"address"},{"indexed":false,"name":"wad","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"src","type":"address"},{"indexed":true,"name":"dst","type":"address"},{"indexed":false,"name":"wad","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"dst","type":"address"},{"indexed":false,"name":"wad","type":"uint256"}],"name":"Deposit","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"name":"src","type":"address"},{"indexed":false,"name":"wad","type":"uint256"}],"name":"Withdrawal","type":"event"}]')

token_contract = w3.eth.contract(address=TOKEN_ADDRESS, abi=TOKEN_ABI)
print("Token Contract Address:", token_contract.address)

# Check WETH balance of hacked wallet
wallet_to_check = Web3.to_checksum_address(hacked_account.address)
balance = token_contract.functions.balanceOf(wallet_to_check).call()

if balance == 0:
    print(f"No WETH found in the wallet {wallet_to_check}")
    exit()

print(f"WETH balance in wallet {wallet_to_check}: {Web3.from_wei(balance, 'ether')} WETH")

SAFE_WALLET = "0xxxxxxxxxxxxxxxx"

# Get nonce for sponsor and hacked accounts
nonce_sponsor = w3.eth.get_transaction_count(sponsor_account.address)
nonce_hacked = w3.eth.get_transaction_count(hacked_account.address)

# Estimate EIP-1559 gas fees
fee_history = w3.eth.fee_history(5, "latest", [10, 90])
maxPriorityFeePerGas = int(fee_history['reward'][-1][0])
baseFee = w3.eth.get_block('latest')['baseFeePerGas']
maxFeePerGas = baseFee + maxPriorityFeePerGas + Web3.to_wei(2, 'gwei')

# Check ETH balance of hacked wallet
hacked_eth_balance = w3.eth.get_balance(hacked_account.address)

# Bundle transactions
bundle = []

# Transaction 1: Sponsor sends ETH to hacked wallet (if needed)
if hacked_eth_balance < maxFeePerGas * 100000:
    tx_sponsor = {
        'to': hacked_account.address,
        'value': Web3.to_wei(0.001, 'ether'),  # Send enough ETH for gas fees
        'gas': 21000,
        'maxPriorityFeePerGas': maxPriorityFeePerGas,
        'maxFeePerGas': maxFeePerGas,
        'nonce': nonce_sponsor,
        'chainId': 1,
        'type': 2
    }
    signed_tx_sponsor = sponsor_account.sign_transaction(tx_sponsor)
    bundle.append(signed_tx_sponsor.rawTransaction)
    nonce_sponsor += 1

# Transaction 2: Hacked wallet transfers WETH to safe wallet
tx_hacked = token_contract.functions.transfer(SAFE_WALLET, balance).build_transaction({
    'gas': 100000,
    'maxPriorityFeePerGas': maxPriorityFeePerGas,
    'maxFeePerGas': maxFeePerGas,
    'nonce': nonce_hacked,
    'chainId': 1,
    'type': 2
})

# Sign the WETH transfer transaction with the hacked account
signed_tx_hacked = hacked_account.sign_transaction(tx_hacked)

# Append signed transaction to the bundle
bundle.append(signed_tx_hacked.rawTransaction)

# Retry mechanism
MAX_RETRIES = 5
retry_count = 0

while retry_count < MAX_RETRIES:
    try:
        # Add extra blocks to avoid block delays
        target_block = w3.eth.block_number + 10

        # Send bundle via Flashbots
        flashbots_response = w3.flashbots.send_raw_bundle(bundle, target_block)
        print(f"Bundle sent. Target block: {target_block}")

        # Wait until the target block is mined
        while w3.eth.block_number < target_block:
            time.sleep(1)

        print("Transaction included in the block.")
        break  # Exit loop if successful
    except Exception as e:
        retry_count += 1
        print(f"Error sending bundle to Flashbots: {str(e)}. Retrying... ({retry_count}/{MAX_RETRIES})")
        time.sleep(2)  # Short delay before retrying

if retry_count == MAX_RETRIES:
    print("Failed to send transaction after maximum retries.")

# flashbotsponsor
