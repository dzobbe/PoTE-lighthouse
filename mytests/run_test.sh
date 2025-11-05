#!/bin/bash
# Complete automated test script for Lighthouse in Kurtosis

set -e

echo "============================================================"
echo "🚀 Lighthouse Kurtosis Automated Test"
echo "============================================================"
echo ""

# Check if Kurtosis is installed
if ! command -v kurtosis &> /dev/null; then
    echo "❌ Kurtosis CLI not found"
    echo "Install it from: https://docs.kurtosis.com/install"
    exit 1
fi

# Check if network is already running
ENCLAVE=$(kurtosis enclave ls 2>/dev/null | grep -v "Name" | grep -v "=====" | head -n 1 | awk '{print $1}')

if [ -z "$ENCLAVE" ]; then
    echo "📦 No running Kurtosis network found"
    echo "Starting new network (this may take a few minutes)..."
    echo ""
    
    # Start Kurtosis network
    kurtosis run github.com/kurtosis-tech/ethereum-package --args-file kurtosis-config.yaml
    
    # Get the new enclave name
    ENCLAVE=$(kurtosis enclave ls | grep -v "Name" | grep -v "=====" | head -n 1 | awk '{print $1}')
    
    echo ""
    echo "⏳ Waiting 30 seconds for network to stabilize..."
    sleep 30
else
    echo "✅ Found running network: $ENCLAVE"
fi

echo ""
echo "📋 Getting RPC endpoint..."

# Extract RPC URL from kurtosis inspect
RPC_LINE=$(kurtosis enclave inspect $ENCLAVE 2>/dev/null | grep -A 30 "el-1-geth-lighthouse" | grep "rpc:" | head -n 1)
RPC_URL="http://127.0.0.1:55707"

echo "   RPC URL: $RPC_URL"
echo ""

# Update tester.py with the correct RPC URL
echo "📝 Updating tester.py with RPC URL..."
sed -i.bak "s|RPC_URL = \".*\"|RPC_URL = \"$RPC_URL\"|g" tester.py

# Check if web3 is installed
if ! python3 -c "import web3" 2>/dev/null; then
    echo "❌ Python web3 library not found"
    echo "Install it with: pip install web3 eth-account"
    exit 1
fi

# Run the test
echo "🧪 Running test..."
echo ""
python3 tester.py

# Capture exit code
TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "============================================================"
    echo "✅ All tests passed!"
    echo "============================================================"
    echo ""
    echo "📊 View the network:"
    echo "   Enclave: $ENCLAVE"
    echo "   Inspect: kurtosis enclave inspect $ENCLAVE"
    echo ""
    echo "🔍 View logs:"
    echo "   Beacon: kurtosis service logs $ENCLAVE cl-1-lighthouse-geth"
    echo "   Validator: kurtosis service logs $ENCLAVE vc-1-lighthouse-geth"
    echo ""
    echo "🧹 Cleanup when done:"
    echo "   kurtosis enclave stop $ENCLAVE"
    echo "   kurtosis enclave rm $ENCLAVE"
else
    echo "============================================================"
    echo "❌ Test failed"
    echo "============================================================"
    echo ""
    echo "🔍 Debug:"
    echo "   View logs: kurtosis service logs $ENCLAVE cl-1-lighthouse-geth"
    echo "   Inspect: kurtosis enclave inspect $ENCLAVE"
fi

exit $TEST_EXIT_CODE

