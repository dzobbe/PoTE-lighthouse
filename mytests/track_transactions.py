#!/usr/bin/env python3
"""
Real-time blockchain transaction tracker
Alternative to Blockscout for monitoring transactions
"""

import sys
import time
from web3 import Web3
from datetime import datetime

RPC_URL = "http://127.0.0.1:55707"

def format_timestamp(ts):
    """Format unix timestamp"""
    return datetime.fromtimestamp(ts).strftime('%H:%M:%S')

def format_value(wei):
    """Format Wei to ETH"""
    eth = Web3.from_wei(wei, 'ether')
    if eth == 0:
        return "0 ETH"
    elif eth < 0.0001:
        return f"{float(eth):.8f} ETH"
    else:
        return f"{float(eth):.4f} ETH"

def track_blocks(w3, show_empty=False):
    """Track new blocks and transactions in real-time"""
    
    try:
        last_block = w3.eth.block_number
    except Exception as e:
        print(f"❌ Cannot connect to RPC: {e}")
        return 1
    
    print("=" * 80)
    print(f"🔍 Transaction Tracker - Starting from block {last_block}")
    print(f"   RPC: {RPC_URL}")
    print(f"   Chain ID: {w3.eth.chain_id}")
    print("=" * 80)
    print("\nPress Ctrl+C to stop\n")
    
    tx_count = 0
    block_count = 0
    
    try:
        while True:
            current_block = w3.eth.block_number
            
            if current_block > last_block:
                for block_num in range(last_block + 1, current_block + 1):
                    try:
                        block = w3.eth.get_block(block_num, full_transactions=True)
                        block_count += 1
                        
                        tx_in_block = len(block['transactions'])
                        
                        if tx_in_block > 0 or show_empty:
                            print(f"\n{'='*80}")
                            print(f"📦 Block #{block_num} ({format_timestamp(block['timestamp'])})")
                            print(f"{'='*80}")
                            print(f"   Hash: {block['hash'].hex()}")
                            print(f"   Miner: {block['miner']}")
                            print(f"   Gas Used: {block['gasUsed']:,} / {block['gasLimit']:,}")
                            print(f"   Transactions: {tx_in_block}")
                            
                            if tx_in_block > 0:
                                print(f"\n   Transactions:")
                                print(f"   {'-'*76}")
                                
                                for i, tx in enumerate(block['transactions'], 1):
                                    tx_count += 1
                                    
                                    print(f"\n   #{i} {tx['hash'].hex()}")
                                    print(f"      From:  {tx['from']}")
                                    print(f"      To:    {tx['to'] if tx['to'] else '(Contract Creation)'}")
                                    print(f"      Value: {format_value(tx['value'])}")
                                    print(f"      Gas:   {tx['gas']:,} @ {Web3.from_wei(tx['gasPrice'], 'gwei'):.2f} gwei")
                                    
                                    # Get receipt for status
                                    try:
                                        receipt = w3.eth.get_transaction_receipt(tx['hash'])
                                        status = "✅ Success" if receipt['status'] == 1 else "❌ Failed"
                                        print(f"      Status: {status}")
                                        
                                        if receipt.get('contractAddress'):
                                            print(f"      Contract: {receipt['contractAddress']}")
                                    except:
                                        pass
                        
                    except Exception as e:
                        print(f"❌ Error processing block {block_num}: {e}")
                
                last_block = current_block
                
                # Show summary periodically
                if block_count % 10 == 0 and block_count > 0:
                    print(f"\n{'='*80}")
                    print(f"📊 Summary: {block_count} blocks processed, {tx_count} transactions found")
                    print(f"{'='*80}\n")
            
            time.sleep(2)
            
    except KeyboardInterrupt:
        print(f"\n\n{'='*80}")
        print("📊 Final Summary")
        print(f"{'='*80}")
        print(f"   Blocks processed: {block_count}")
        print(f"   Transactions found: {tx_count}")
        print(f"   Final block: {last_block}")
        print(f"{'='*80}\n")
        return 0

def show_recent_history(w3, num_blocks=10):
    """Show recent block history"""
    
    current_block = w3.eth.block_number
    start_block = max(0, current_block - num_blocks + 1)
    
    print("=" * 80)
    print(f"📜 Recent History (Last {num_blocks} blocks)")
    print("=" * 80)
    print(f"   Current block: {current_block}")
    print(f"   Showing blocks {start_block} to {current_block}\n")
    
    total_txs = 0
    
    for block_num in range(start_block, current_block + 1):
        try:
            block = w3.eth.get_block(block_num, full_transactions=False)
            tx_count = len(block['transactions'])
            total_txs += tx_count
            
            if tx_count > 0:
                print(f"📦 Block #{block_num}: {tx_count} transactions")
                print(f"   {block['hash'].hex()}")
        except Exception as e:
            print(f"❌ Error reading block {block_num}: {e}")
    
    print(f"\n📊 Total transactions in last {num_blocks} blocks: {total_txs}")
    print("=" * 80 + "\n")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Track blockchain transactions in real-time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Track new transactions in real-time
  python3 track_transactions.py
  
  # Track including empty blocks
  python3 track_transactions.py --show-empty
  
  # Show history only
  python3 track_transactions.py --history --blocks 20
  
  # Use different RPC endpoint
  python3 track_transactions.py --rpc http://127.0.0.1:9545
        """
    )
    
    parser.add_argument(
        '--rpc',
        default=RPC_URL,
        help=f'RPC endpoint (default: {RPC_URL})'
    )
    
    parser.add_argument(
        '--show-empty',
        action='store_true',
        help='Show blocks even if they have no transactions'
    )
    
    parser.add_argument(
        '--history',
        action='store_true',
        help='Show recent history instead of live tracking'
    )
    
    parser.add_argument(
        '--blocks',
        type=int,
        default=10,
        help='Number of historical blocks to show (default: 10)'
    )
    
    args = parser.parse_args()
    
    # Connect
    print(f"Connecting to {args.rpc}...")
    w3 = Web3(Web3.HTTPProvider(args.rpc))
    
    if not w3.is_connected():
        print(f"❌ Failed to connect to {args.rpc}")
        return 1
    
    print("✅ Connected\n")
    
    # Run appropriate mode
    if args.history:
        show_recent_history(w3, args.blocks)
        return 0
    else:
        return track_blocks(w3, args.show_empty)

if __name__ == "__main__":
    sys.exit(main())

