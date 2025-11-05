#!/usr/bin/env python3
"""
Interactive transaction sender for manual testing
Usage: python3 send_transaction.py [--rpc-url URL] [--amount ETH] [--to ADDRESS]
"""

import sys
import argparse
from web3 import Web3
from eth_account import Account

# Default configuration
DEFAULT_RPC_URL = "http://127.0.0.1:51203"
DEFAULT_PRIVATE_KEY = "0xbcdf20249abf0ed6d944c0288fad489e33f66b3960d9e6229c1cd214ed3bbe31"

def send_transaction(rpc_url, private_key, to_address, amount_eth):
    """Send a transaction"""
    # Connect to network
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    
    if not w3.is_connected():
        print(f"❌ Failed to connect to {rpc_url}")
        return False
    
    print(f"✅ Connected to network (Chain ID: {w3.eth.chain_id})")
    print(f"   Current block: {w3.eth.block_number}")
    
    # Setup sender account
    sender = w3.eth.account.from_key(private_key)
    sender_balance = w3.eth.get_balance(sender.address)
    
    print(f"\n📋 Sender: {sender.address}")
    print(f"   Balance: {Web3.from_wei(sender_balance, 'ether')} ETH")
    
    # If no recipient specified, create a new account
    if to_address:
        receiver_address = Web3.to_checksum_address(to_address)
        receiver_balance_before = w3.eth.get_balance(receiver_address)
        print(f"\n📋 Receiver: {receiver_address}")
        print(f"   Balance before: {Web3.from_wei(receiver_balance_before, 'ether')} ETH")
    else:
        receiver = Account.create()
        receiver_address = receiver.address
        print(f"\n📋 Receiver: {receiver_address} (new account)")
        print(f"   Balance before: 0 ETH")
    
    # Convert amount to Wei
    amount_wei = Web3.to_wei(amount_eth, 'ether')
    
    # Build transaction
    print(f"\n💸 Sending {amount_eth} ETH...")
    
    tx = {
        'from': sender.address,
        'to': receiver_address,
        'value': amount_wei,
        'gas': 21000,
        'gasPrice': w3.eth.gas_price,
        'nonce': w3.eth.get_transaction_count(sender.address),
        'chainId': w3.eth.chain_id
    }
    
    print(f"   Gas price: {Web3.from_wei(tx['gasPrice'], 'gwei')} gwei")
    print(f"   Nonce: {tx['nonce']}")
    
    # Sign and send
    signed_tx = w3.eth.account.sign_transaction(tx, sender.key)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    
    print(f"   Transaction hash: {tx_hash.hex()}")
    
    # Wait for receipt
    print(f"\n⏳ Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    
    if receipt['status'] == 1:
        print(f"✅ Transaction confirmed in block {receipt['blockNumber']}")
        print(f"   Gas used: {receipt['gasUsed']}")
        
        receiver_balance_after = w3.eth.get_balance(receiver_address)
        print(f"\n📊 Receiver balance after: {Web3.from_wei(receiver_balance_after, 'ether')} ETH")
        
        return True
    else:
        print(f"❌ Transaction failed")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Send ETH transaction on Kurtosis network',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Send 1 ETH to a new random account
  python3 send_transaction.py
  
  # Send 5 ETH to a specific address
  python3 send_transaction.py --amount 5 --to 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb
  
  # Use a different RPC endpoint
  python3 send_transaction.py --rpc-url http://127.0.0.1:9545 --amount 2
        """
    )
    
    parser.add_argument(
        '--rpc-url',
        default=DEFAULT_RPC_URL,
        help=f'RPC endpoint (default: {DEFAULT_RPC_URL})'
    )
    
    parser.add_argument(
        '--private-key',
        default=DEFAULT_PRIVATE_KEY,
        help='Sender private key (default: genesis account)'
    )
    
    parser.add_argument(
        '--to',
        help='Recipient address (default: create new account)'
    )
    
    parser.add_argument(
        '--amount',
        type=float,
        default=1.0,
        help='Amount of ETH to send (default: 1.0)'
    )
    
    parser.add_argument(
        '--multiple',
        type=int,
        default=1,
        help='Send multiple transactions (default: 1)'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("💰 Transaction Sender")
    print("=" * 60)
    print()
    
    success_count = 0
    for i in range(args.multiple):
        if args.multiple > 1:
            print(f"\n{'='*60}")
            print(f"Transaction {i+1}/{args.multiple}")
            print(f"{'='*60}")
        
        success = send_transaction(
            args.rpc_url,
            args.private_key,
            args.to,
            args.amount
        )
        
        if success:
            success_count += 1
    
    print()
    print("=" * 60)
    if success_count == args.multiple:
        print(f"✅ All {args.multiple} transaction(s) successful")
        return 0
    else:
        print(f"⚠️  {success_count}/{args.multiple} transactions successful")
        return 1

if __name__ == "__main__":
    sys.exit(main())

