#!/usr/bin/env python3
"""
Test script for Lighthouse patches in Kurtosis blockchain
Performs a simple ETH transfer and monitors block creation
"""

import time
import sys
from web3 import Web3
from eth_account import Account

# Configuration
RPC_URL = "http://127.0.0.1:55707"  # Update this with your actual Kurtosis EL RPC endpoint
TRANSFER_AMOUNT = Web3.to_wei(1, 'ether')  # Transfer 1 ETH

# For Kurtosis networks, validator accounts are derived from the mnemonic
# Private key found by find_funded_accounts.py
DEFAULT_PRIVATE_KEY = "0xbcdf20249abf0ed6d944c0288fad489e33f66b3960d9e6229c1cd214ed3bbe31"

def connect_to_network():
    """Connect to the Kurtosis network"""
    print(f"Connecting to network at {RPC_URL}...")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    if not w3.is_connected():
        print("❌ Failed to connect to network")
        print("Make sure Kurtosis is running and update RPC_URL in this script")
        sys.exit(1)
    
    print("✅ Connected to network")
    print(f"   Chain ID: {w3.eth.chain_id}")
    print(f"   Latest block: {w3.eth.block_number}")
    return w3

def setup_accounts(w3):
    """Setup sender and receiver accounts"""
    # Use account derived from mnemonic (has funds)
    sender = w3.eth.account.from_key(DEFAULT_PRIVATE_KEY)
    
    # Create a new receiver account
    receiver = Account.create()
    
    print("\n📋 Account Information:")
    print(f"   Sender: {sender.address}")
    print(f"   Receiver: {receiver.address}")
    
    sender_balance = w3.eth.get_balance(sender.address)
    print(f"   Sender balance: {Web3.from_wei(sender_balance, 'ether')} ETH")
    
    if sender_balance == 0:
        print("\n❌ ERROR: Sender account has no balance!")
        print("   Run ./find_funded_accounts.py to find a funded account")
        print("   Then update DEFAULT_PRIVATE_KEY in this script")
        sys.exit(1)
    
    return sender, receiver

def send_transfer(w3, sender, receiver_address, amount):
    """Send ETH transfer and return transaction hash"""
    print(f"\n💸 Sending {Web3.from_wei(amount, 'ether')} ETH to {receiver_address}...")
    
    # Get current block number before transaction
    block_before = w3.eth.block_number
    print(f"   Current block: {block_before}")
    
    # Build transaction
    tx = {
        'from': sender.address,
        'to': receiver_address,
        'value': amount,
        'gas': 21000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(sender.address),
        'chainId': w3.eth.chain_id
    }
    
    # Sign and send transaction
    signed_tx = w3.eth.account.sign_transaction(tx, sender.key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    print(f"   Transaction hash: {tx_hash.hex()}")
    return tx_hash, block_before

def monitor_transaction(w3, tx_hash, block_before):
    """Monitor transaction inclusion in a block"""
    print(f"\n⏳ Waiting for transaction to be mined...")
    
    timeout = 360  # seconds
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            print(f"Receipt: {receipt}")
            if receipt:
                print(f"✅ Transaction mined in block {receipt['blockNumber']}")
                print(f"   Gas used: {receipt['gasUsed']}")
                print(f"   Status: {'Success' if receipt['status'] == 1 else 'Failed'}")
                print(f"   New blocks created: {receipt['blockNumber'] - block_before}")
                return receipt
        except Exception:
            pass
        
        current_block = w3.eth.block_number
        if current_block > block_before:
            print(f"   Block {current_block} created...")
        
        time.sleep(2)
    
    print("❌ Transaction not mined within timeout")
    return None

def verify_transfer(w3, receiver_address, expected_amount):
    """Verify the receiver got the funds"""
    print(f"\n🔍 Verifying transfer...")
    balance = w3.eth.get_balance(receiver_address)
    print(f"   Receiver balance: {Web3.from_wei(balance, 'ether')} ETH")
    
    if balance >= expected_amount:
        print("✅ Transfer verified successfully!")
        return True
    else:
        print("❌ Transfer amount mismatch")
        return False

def main():
    """Main test flow"""
    print("=" * 60)
    print("🧪 Lighthouse Kurtosis Blockchain Test")
    print("=" * 60)
    
    # Connect to network
    w3 = connect_to_network()
    
    # Setup accounts
    sender, receiver = setup_accounts(w3)
    
    # Send transfer
    tx_hash, block_before = send_transfer(w3, sender, receiver.address, TRANSFER_AMOUNT)
    
    # Monitor transaction
    receipt = monitor_transaction(w3, tx_hash, block_before)
    
    if receipt and receipt['status'] == 1:
        # Verify transfer
        verify_transfer(w3, receiver.address, TRANSFER_AMOUNT)
        
        print("\n" + "=" * 60)
        print("✅ TEST PASSED: Block creation and validation successful!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ TEST FAILED")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
