#!/bin/bash
# Check Blockscout configuration and connectivity

set -e

echo "============================================================"
echo "🔍 Blockscout Diagnostics"
echo "============================================================"
echo ""

# Get enclave
ENCLAVE=$(kurtosis enclave ls 2>/dev/null | grep -v "Name" | grep -v "=====" | head -n 1 | awk '{print $1}')

if [ -z "$ENCLAVE" ]; then
    echo "❌ No Kurtosis enclave found"
    exit 1
fi

echo "📦 Enclave: $ENCLAVE"
echo ""

# Check if blockscout is running
echo "🔍 Checking Blockscout service..."
if kurtosis enclave inspect $ENCLAVE 2>/dev/null | grep -q "blockscout"; then
    echo "✅ Blockscout service found"
    
    # Get blockscout URL
    BLOCKSCOUT_URL=$(kurtosis enclave inspect $ENCLAVE 2>/dev/null | grep -A 5 "blockscout" | grep "http:" | head -n 1 | awk '{print $2}')
    echo "   URL: $BLOCKSCOUT_URL"
else
    echo "❌ Blockscout service not found"
    exit 1
fi

echo ""
echo "🔍 Checking EL RPC endpoint..."
RPC_URL=$(kurtosis enclave inspect $ENCLAVE 2>/dev/null | grep -A 30 "el-1-geth-lighthouse" | grep "rpc:" | head -n 1 | awk '{print $2}')
echo "   RPC URL: $RPC_URL"

# Test RPC connectivity
echo ""
echo "🔍 Testing RPC connectivity..."
BLOCK_NUMBER=$(curl -s -X POST $RPC_URL \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' | grep -o '"result":"[^"]*"' | cut -d'"' -f4)

if [ -n "$BLOCK_NUMBER" ]; then
    BLOCK_DEC=$((16#${BLOCK_NUMBER:2}))
    echo "✅ RPC is working - Current block: $BLOCK_DEC"
else
    echo "❌ RPC is not responding"
fi

# Check Blockscout logs
echo ""
echo "🔍 Recent Blockscout logs:"
echo "----------------------------------------"
kurtosis service logs $ENCLAVE blockscout --follow=false 2>/dev/null | tail -20

echo ""
echo "============================================================"
echo "📋 Summary"
echo "============================================================"
echo "Blockscout URL: $BLOCKSCOUT_URL"
echo "EL RPC URL: $RPC_URL"
echo ""
echo "If Blockscout shows null blocks, it may not be configured"
echo "to connect to the RPC endpoint properly."
echo ""
echo "To view full logs:"
echo "  kurtosis service logs $ENCLAVE blockscout -f"

