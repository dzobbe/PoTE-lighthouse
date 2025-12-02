#!/usr/bin/env python3
"""
Generate complex blocks by sending many transactions to the network.
This script continuously sends transactions to fill blocks and increase block complexity.

Usage:
    python3 generate_complex_blocks.py [options]

Options:
    --rpc-url URL          Execution layer RPC URL (default: auto-detect from Kurtosis)
    --transactions N        Number of transactions to send (default: 100)
    --rate N               Transactions per second (default: 10)
    --amount ETH           Amount per transaction in ETH (default: 0.001)
    --duration SECONDS     Run for specified duration (overrides --transactions)
    --private-key KEY      Private key of funded account (default: genesis account)
    --gas-price GWEI       Gas price in Gwei (default: auto)
"""

import argparse
import time
import sys
import subprocess
import re
from web3 import Web3
from eth_account import Account
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Default configuration
DEFAULT_PRIVATE_KEY = "0xbcdf20249abf0ed6d944c0288fad489e33f66b3960d9e6229c1cd214ed3bbe31"
DEFAULT_TRANSACTIONS = 100
DEFAULT_RATE = 10  # transactions per second
DEFAULT_AMOUNT_ETH = 0.001

# Statistics
stats = {
    'sent': 0,
    'confirmed': 0,
    'failed': 0,
    'pending': 0,
    'total_gas_used': 0,
    'lock': threading.Lock()
}


def find_kurtosis_rpc_port():
    """Try to find the RPC port from Kurtosis output or docker ps"""
    # Method 1: Try kurtosis enclave inspect
    try:
        result = subprocess.run(
            ['kurtosis', 'enclave', 'inspect'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Look for geth RPC port (usually 8545)
            # Pattern: cl-1-lighthouse-geth rpc: 8545/tcp -> http://127.0.0.1:PORT
            pattern = r'cl-1-lighthouse-geth[^\n]*rpc[^\n]*->\s*http://127\.0\.0\.1:(\d+)'
            match = re.search(pattern, result.stdout)
            if match:
                return int(match.group(1))
            
            # Alternative pattern
            pattern = r'rpc:\s*8545/tcp\s*->\s*http://127\.0\.0\.1:(\d+)'
            match = re.search(pattern, result.stdout)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    
    # Method 2: Try docker ps (fallback)
    try:
        result = subprocess.run(
            ['docker', 'ps', '--format', '{{.Names}}\t{{.Ports}}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Look for execution layer containers (el-*-geth-lighthouse)
            # Pattern: 0.0.0.0:PORT->8545/tcp (RPC port mapping)
            lines = result.stdout.split('\n')
            first_match = None
            
            for line in lines:
                # Look for el-* containers with 8545 port mapping
                if 'el-' in line and 'geth-lighthouse' in line and '8545/tcp' in line:
                    # Extract port from pattern: 0.0.0.0:PORT->8545/tcp
                    pattern = r'0\.0\.0\.0:(\d+)->8545/tcp'
                    match = re.search(pattern, line)
                    if match:
                        port = int(match.group(1))
                        # Prefer el-1 if available
                        if 'el-1-' in line:
                            return port
                        # Store first match as fallback
                        if first_match is None:
                            first_match = port
            
            # Return first match if el-1 not found
            if first_match is not None:
                return first_match
    except Exception:
        pass
    
    return None


def connect_to_network(rpc_url):
    """Connect to the network"""
    print(f"🔌 Connecting to network at {rpc_url}...")
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={'timeout': 10}))
    
    if not w3.is_connected():
        print(f"❌ Failed to connect to {rpc_url}")
        return None
    
    print(f"✅ Connected (Chain ID: {w3.eth.chain_id})")
    print(f"   Current block: {w3.eth.block_number}")
    print(f"   Gas price: {Web3.from_wei(w3.eth.gas_price, 'gwei'):.2f} gwei")
    return w3


def setup_sender(w3, private_key):
    """Setup sender account"""
    sender = w3.eth.account.from_key(private_key)
    balance = w3.eth.get_balance(sender.address)
    
    print(f"\n📋 Sender Account:")
    print(f"   Address: {sender.address}")
    print(f"   Balance: {Web3.from_wei(balance, 'ether'):.2f} ETH")
    
    if balance == 0:
        print("❌ ERROR: Sender account has no balance!")
        return None
    
    return sender


def send_transaction(w3, sender, receiver_address, amount_wei, gas_price=None):
    """Send a single transaction"""
    try:
        nonce = w3.eth.get_transaction_count(sender.address, 'pending')
        
        tx = {
            'from': sender.address,
            'to': receiver_address,
            'value': amount_wei,
            'gas': 21000,
            'gasPrice': gas_price or w3.eth.gas_price,
            'nonce': nonce,
            'chainId': w3.eth.chain_id
        }
        
        signed_tx = w3.eth.account.sign_transaction(tx, sender.key)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        
        with stats['lock']:
            stats['sent'] += 1
            stats['pending'] += 1
        
        return tx_hash
    except Exception as e:
        with stats['lock']:
            stats['failed'] += 1
        print(f"⚠️  Failed to send transaction: {e}")
        return None


def check_transaction(w3, tx_hash):
    """Check if transaction is confirmed"""
    try:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt:
            with stats['lock']:
                stats['confirmed'] += 1
                stats['pending'] -= 1
                stats['total_gas_used'] += receipt['gasUsed']
            return receipt
    except Exception:
        pass
    return None


def monitor_transactions(w3, tx_hashes):
    """Monitor pending transactions"""
    print(f"\n⏳ Monitoring {len(tx_hashes)} transactions...")
    
    confirmed = set()
    start_time = time.time()
    timeout = 300  # 5 minutes
    
    while len(confirmed) < len(tx_hashes) and (time.time() - start_time) < timeout:
        for tx_hash in tx_hashes:
            if tx_hash and tx_hash not in confirmed:
                receipt = check_transaction(w3, tx_hash)
                if receipt:
                    confirmed.add(tx_hash)
        
        if len(confirmed) < len(tx_hashes):
            time.sleep(2)
    
    return len(confirmed)


def generate_transactions(w3, sender, num_transactions, rate, amount_wei, gas_price=None):
    """Generate and send transactions at specified rate"""
    print(f"\n🚀 Generating {num_transactions} transactions...")
    print(f"   Rate: {rate} tx/s")
    print(f"   Amount: {Web3.from_wei(amount_wei, 'ether')} ETH per transaction")
    
    tx_hashes = []
    interval = 1.0 / rate if rate > 0 else 0.1
    
    # Create multiple receiver accounts
    receivers = [Account.create().address for _ in range(min(100, num_transactions))]
    
    start_time = time.time()
    
    for i in range(num_transactions):
        receiver = receivers[i % len(receivers)]
        tx_hash = send_transaction(w3, sender, receiver, amount_wei, gas_price)
        
        if tx_hash:
            tx_hashes.append(tx_hash)
            if (i + 1) % 10 == 0:
                print(f"   Sent {i + 1}/{num_transactions} transactions...")
        
        # Rate limiting
        if i < num_transactions - 1:
            time.sleep(interval)
    
    elapsed = time.time() - start_time
    print(f"\n✅ Sent {len(tx_hashes)} transactions in {elapsed:.2f}s")
    print(f"   Average rate: {len(tx_hashes) / elapsed:.2f} tx/s")
    
    return tx_hashes


def print_statistics():
    """Print current statistics"""
    with stats['lock']:
        print(f"\n📊 Statistics:")
        print(f"   Sent: {stats['sent']}")
        print(f"   Confirmed: {stats['confirmed']}")
        print(f"   Pending: {stats['pending']}")
        print(f"   Failed: {stats['failed']}")
        if stats['confirmed'] > 0:
            avg_gas = stats['total_gas_used'] / stats['confirmed']
            print(f"   Avg gas per tx: {avg_gas:,.0f}")
            print(f"   Total gas used: {stats['total_gas_used']:,}")


def main():
    parser = argparse.ArgumentParser(
        description='Generate complex blocks by sending many transactions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument('--rpc-url', help='Execution layer RPC URL')
    parser.add_argument('--transactions', type=int, default=DEFAULT_TRANSACTIONS,
                       help=f'Number of transactions to send (default: {DEFAULT_TRANSACTIONS})')
    parser.add_argument('--rate', type=float, default=DEFAULT_RATE,
                       help=f'Transactions per second (default: {DEFAULT_RATE})')
    parser.add_argument('--amount', type=float, default=DEFAULT_AMOUNT_ETH,
                       help=f'Amount per transaction in ETH (default: {DEFAULT_AMOUNT_ETH})')
    parser.add_argument('--duration', type=int,
                       help='Run for specified duration in seconds (overrides --transactions)')
    parser.add_argument('--private-key', default=DEFAULT_PRIVATE_KEY,
                       help='Private key of funded account')
    parser.add_argument('--gas-price', type=float,
                       help='Gas price in Gwei (default: auto)')
    
    args = parser.parse_args()
    
    # Determine RPC URL
    if args.rpc_url:
        rpc_url = args.rpc_url
    else:
        port = find_kurtosis_rpc_port()
        if port:
            rpc_url = f"http://127.0.0.1:{port}"
            print(f"🔍 Auto-detected RPC port: {port}")
        else:
            print("❌ Could not auto-detect RPC port. Please specify --rpc-url")
            print("   Example: --rpc-url http://127.0.0.1:8545")
            sys.exit(1)
    
    # Connect to network
    w3 = connect_to_network(rpc_url)
    if not w3:
        sys.exit(1)
    
    # Setup sender
    sender = setup_sender(w3, args.private_key)
    if not sender:
        sys.exit(1)
    
    # Convert amount to Wei
    amount_wei = Web3.to_wei(args.amount, 'ether')
    
    # Set gas price
    gas_price = None
    if args.gas_price:
        gas_price = Web3.to_wei(args.gas_price, 'gwei')
    
    # Determine number of transactions
    if args.duration:
        num_transactions = int(args.duration * args.rate)
        print(f"\n⏱️  Running for {args.duration} seconds at {args.rate} tx/s")
        print(f"   Will send approximately {num_transactions} transactions")
    else:
        num_transactions = args.transactions
    
    # Generate transactions
    tx_hashes = generate_transactions(w3, sender, num_transactions, args.rate, 
                                      amount_wei, gas_price)
    
    # Monitor confirmations
    if tx_hashes:
        confirmed = monitor_transactions(w3, tx_hashes)
        print(f"\n✅ Confirmed {confirmed}/{len(tx_hashes)} transactions")
    
    # Print final statistics
    print_statistics()
    
    # Show block information
    try:
        latest_block = w3.eth.get_block('latest', full_transactions=True)
        print(f"\n📦 Latest Block:")
        print(f"   Number: {latest_block['number']}")
        print(f"   Transactions: {len(latest_block['transactions'])}")
        print(f"   Gas used: {latest_block['gasUsed']:,} / {latest_block['gasLimit']:,}")
        print(f"   Gas utilization: {latest_block['gasUsed'] / latest_block['gasLimit'] * 100:.1f}%")
    except Exception as e:
        print(f"⚠️  Could not get latest block info: {e}")


if __name__ == "__main__":
    main()

