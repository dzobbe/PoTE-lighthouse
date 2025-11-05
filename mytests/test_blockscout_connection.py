#!/usr/bin/env python3
"""
Test Blockscout connectivity and indexing status
"""

import sys
import requests
import subprocess
import json
from web3 import Web3

def get_kurtosis_info():
    """Get enclave and service info from Kurtosis"""
    try:
        result = subprocess.run(
            ['kurtosis', 'enclave', 'ls'],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.strip().split('\n')
        for line in lines:
            if 'Name' not in line and '====' not in line and line.strip():
                enclave = line.split()[0]
                return enclave
        return None
    except Exception as e:
        print(f"❌ Error getting enclave: {e}")
        return None

def get_service_url(enclave, service_grep, port_name):
    """Get service URL from kurtosis inspect"""
    try:
        result = subprocess.run(
            ['kurtosis', 'enclave', 'inspect', enclave],
            capture_output=True,
            text=True
        )
        
        lines = result.stdout.split('\n')
        in_service = False
        for i, line in enumerate(lines):
            if service_grep in line:
                in_service = True
            if in_service and port_name in line:
                parts = line.split()
                for part in parts:
                    if 'http://' in part:
                        return part.strip()
        return None
    except Exception as e:
        print(f"❌ Error getting service URL: {e}")
        return None

def check_rpc_node(rpc_url):
    """Check if RPC node is working and has blocks"""
    print(f"\n🔍 Checking RPC node at {rpc_url}")
    
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            print("❌ Cannot connect to RPC")
            return False
        
        block_number = w3.eth.block_number
        chain_id = w3.eth.chain_id
        
        print(f"✅ RPC is working")
        print(f"   Chain ID: {chain_id}")
        print(f"   Current block: {block_number}")
        
        if block_number > 0:
            latest_block = w3.eth.get_block('latest')
            print(f"   Latest block hash: {latest_block['hash'].hex()}")
            print(f"   Transactions in latest: {len(latest_block['transactions'])}")
        
        return True
    except Exception as e:
        print(f"❌ RPC Error: {e}")
        return False

def check_blockscout_api(blockscout_url):
    """Check Blockscout API endpoints"""
    print(f"\n🔍 Checking Blockscout at {blockscout_url}")
    
    # Try the API
    api_url = blockscout_url.rstrip('/') + '/api'
    
    endpoints = [
        ('/', 'Main page'),
        ('/api', 'API root'),
        ('/api/v2/stats', 'Network stats'),
        ('/api/v2/blocks', 'Recent blocks'),
        ('/api/v2/transactions', 'Recent transactions'),
    ]
    
    for endpoint, description in endpoints:
        url = blockscout_url.rstrip('/') + endpoint
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                print(f"✅ {description}: {response.status_code}")
                
                # Try to parse JSON for API endpoints
                if endpoint.startswith('/api'):
                    try:
                        data = response.json()
                        if endpoint == '/api/v2/stats':
                            print(f"   Total blocks: {data.get('total_blocks', 'N/A')}")
                            print(f"   Total transactions: {data.get('total_transactions', 'N/A')}")
                        elif endpoint == '/api/v2/blocks':
                            items = data.get('items', [])
                            print(f"   Blocks returned: {len(items)}")
                            if items:
                                print(f"   Latest indexed block: {items[0].get('height', 'N/A')}")
                    except:
                        pass
            else:
                print(f"⚠️  {description}: {response.status_code}")
        except requests.exceptions.Timeout:
            print(f"⏱️  {description}: Timeout")
        except Exception as e:
            print(f"❌ {description}: {str(e)[:50]}")

def check_blockscout_logs(enclave):
    """Check recent Blockscout logs for issues"""
    print(f"\n🔍 Recent Blockscout logs:")
    print("=" * 60)
    
    try:
        result = subprocess.run(
            ['kurtosis', 'service', 'logs', enclave, 'blockscout', '--follow=false'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        lines = result.stdout.split('\n')
        # Show last 30 lines
        for line in lines[-30:]:
            if line.strip():
                # Highlight errors and important info
                if 'error' in line.lower() or 'fail' in line.lower():
                    print(f"🔴 {line}")
                elif 'warn' in line.lower():
                    print(f"🟡 {line}")
                elif 'block' in line.lower() or 'transaction' in line.lower():
                    print(f"🔵 {line}")
                else:
                    print(f"   {line}")
    except Exception as e:
        print(f"❌ Could not fetch logs: {e}")

def main():
    print("=" * 60)
    print("🔍 Blockscout Connection Test")
    print("=" * 60)
    
    # Get enclave info
    enclave = get_kurtosis_info()
    if not enclave:
        print("❌ No Kurtosis enclave found")
        return 1
    
    print(f"📦 Enclave: {enclave}")
    
    # Get RPC URL
    rpc_url = get_service_url(enclave, 'el-1-geth-lighthouse', 'rpc')
    if not rpc_url:
        print("❌ Could not find RPC URL")
        return 1
    
    # Get Blockscout URL
    blockscout_url = get_service_url(enclave, 'blockscout', 'http')
    if not blockscout_url:
        print("❌ Could not find Blockscout URL")
        print("\nIs Blockscout enabled in kurtosis-config.yaml?")
        return 1
    
    # Check RPC
    rpc_ok = check_rpc_node(rpc_url)
    
    # Check Blockscout
    check_blockscout_api(blockscout_url)
    
    # Check logs
    check_blockscout_logs(enclave)
    
    print("\n" + "=" * 60)
    print("📋 Summary")
    print("=" * 60)
    print(f"RPC URL: {rpc_url}")
    print(f"Blockscout URL: {blockscout_url}")
    
    if not rpc_ok:
        print("\n❌ RPC node has issues - fix this first")
        return 1
    
    print("\n💡 Troubleshooting tips:")
    print("1. Blockscout may take 1-2 minutes to start indexing")
    print("2. Check if there are blocks with transactions")
    print("3. View full logs: kurtosis service logs", enclave, "blockscout -f")
    print("4. Restart Blockscout if needed:")
    print(f"   kurtosis service stop {enclave} blockscout")
    print(f"   kurtosis service start {enclave} blockscout")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

