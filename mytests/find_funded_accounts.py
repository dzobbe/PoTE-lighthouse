#!/usr/bin/env python3
"""
Helper script to find funded accounts in the Kurtosis network
"""

import sys
from web3 import Web3
from eth_account import Account

RPC_URL = "http://127.0.0.1:51203"  # Update with your RPC endpoint

# Common Ethereum test mnemonics and derivation paths
COMMON_MNEMONICS = [
    "giant issue aisle success illegal bike spike question tent bar rely arctic volcano long crawl hungry vocal artwork sniff fantasy very lucky have athlete",
    "test test test test test test test test test test test junk",
]

# Derivation paths to try (m/44'/60'/0'/0/index)
DERIVATION_INDICES = range(20)  # Check first 20 accounts

def check_preloaded_contracts(w3):
    """Check the preloaded contract addresses from kurtosis config"""
    print("\n🔍 Checking preloaded contracts from config...")
    
    preloaded = [
        "0x1000000000000000000000000000000000000001",
        "0x2000000000000000000000000000000000000002",
        "0x3000000000000000000000000000000000000003",
    ]
    
    for addr in preloaded:
        try:
            balance = w3.eth.get_balance(addr)
            if balance > 0:
                print(f"  ✅ {addr}: {Web3.from_wei(balance, 'ether')} ETH")
            else:
                print(f"  ❌ {addr}: 0 ETH")
        except Exception as e:
            print(f"  ❌ {addr}: Error - {e}")

def try_mnemonic_accounts(w3, mnemonic, name):
    """Try accounts derived from a mnemonic"""
    print(f"\n🔍 Checking accounts from: {name}")
    print(f"   Mnemonic: {mnemonic[:50]}...")
    
    try:
        Account.enable_unaudited_hdwallet_features()
        
        for i in DERIVATION_INDICES:
            try:
                account = Account.from_mnemonic(mnemonic, account_path=f"m/44'/60'/0'/0/{i}")
                balance = w3.eth.get_balance(account.address)
                
                if balance > 0:
                    print(f"  ✅ Index {i}: {account.address}")
                    print(f"     Balance: {Web3.from_wei(balance, 'ether')} ETH")
                    print(f"     Private key: {account.key.hex()}")
                    return account
                    
            except Exception as e:
                pass
        
        print("  ❌ No funded accounts found")
        return None
                
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None

def scan_recent_transactions(w3):
    """Scan recent blocks to find accounts with activity"""
    print("\n🔍 Scanning recent transactions for active accounts...")
    
    try:
        latest_block = w3.eth.block_number
        accounts_with_balance = set()
        
        # Scan last 20 blocks
        for block_num in range(max(0, latest_block - 20), latest_block + 1):
            try:
                block = w3.eth.get_block(block_num, full_transactions=True)
                
                if block and block.transactions:
                    for tx in block.transactions:
                        if 'from' in tx:
                            accounts_with_balance.add(tx['from'])
                        if 'to' in tx and tx['to']:
                            accounts_with_balance.add(tx['to'])
            except:
                pass
        
        if accounts_with_balance:
            print(f"  Found {len(accounts_with_balance)} unique accounts in recent transactions")
            for addr in list(accounts_with_balance)[:10]:  # Show first 10
                balance = w3.eth.get_balance(addr)
                if balance > 0:
                    print(f"  ✅ {addr}: {Web3.from_wei(balance, 'ether')} ETH")
        else:
            print("  ❌ No transactions found in recent blocks")
            
    except Exception as e:
        print(f"  ❌ Error scanning blocks: {e}")

def get_genesis_accounts(w3):
    """Try to get accounts that received genesis allocation"""
    print("\n🔍 Looking for genesis-allocated accounts...")
    
    try:
        # In Ethereum, validator deposit contract and fee recipient accounts often have balances
        # Check some common addresses that might be funded at genesis
        
        common_addresses = [
            "0x0000000000000000000000000000000000000000",  # Zero address
            "0x4242424242424242424242424242424242424242",  # Common fee recipient
            "0x8888888888888888888888888888888888888888",  # Another common address
        ]
        
        # Also check addresses derived from simple patterns
        for i in range(10):
            addr = f"0x{'0' * (39 - len(str(i)))}{i}"
            common_addresses.append(addr)
        
        found_any = False
        for addr in common_addresses:
            try:
                balance = w3.eth.get_balance(Web3.to_checksum_address(addr))
                if balance > 0:
                    print(f"  ✅ {addr}: {Web3.from_wei(balance, 'ether')} ETH")
                    found_any = True
            except:
                pass
        
        if not found_any:
            print("  ❌ No funded addresses found in common patterns")
                
    except Exception as e:
        print(f"  ❌ Error: {e}")

def main():
    print("=" * 70)
    print("🔎 Funded Account Finder")
    print("=" * 70)
    
    # Connect
    print(f"\nConnecting to {RPC_URL}...")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    
    if not w3.is_connected():
        print("❌ Failed to connect")
        print("Update RPC_URL in this script and try again")
        return 1
    
    print(f"✅ Connected (Chain ID: {w3.eth.chain_id}, Block: {w3.eth.block_number})")
    
    # Check preloaded contracts
    check_preloaded_contracts(w3)
    
    # Try common mnemonics
    funded_account = None
    for i, mnemonic in enumerate(COMMON_MNEMONICS):
        account = try_mnemonic_accounts(w3, mnemonic, f"Common mnemonic #{i+1}")
        if account and not funded_account:
            funded_account = account
    
    # Scan recent transactions
    scan_recent_transactions(w3)
    
    # Check genesis addresses
    get_genesis_accounts(w3)
    
    print("\n" + "=" * 70)
    
    if funded_account:
        print("✅ FOUND FUNDED ACCOUNT!")
        print(f"\nUpdate tester.py with:")
        print(f'DEFAULT_PRIVATE_KEY = "{funded_account.key.hex()}"')
        print(f"\nAccount: {funded_account.address}")
        print(f"Balance: {Web3.from_wei(w3.eth.get_balance(funded_account.address), 'ether')} ETH")
        print("=" * 70)
        return 0
    else:
        print("❌ NO FUNDED ACCOUNTS FOUND")
        print("\nTroubleshooting:")
        print("1. Wait a bit longer for the network to initialize")
        print("2. Check kurtosis logs: kurtosis service logs <enclave> el-1-geth-lighthouse")
        print("3. Verify genesis was created correctly")
        print("4. Check if validators are running and producing blocks")
        print("=" * 70)
        return 1

if __name__ == "__main__":
    sys.exit(main())

