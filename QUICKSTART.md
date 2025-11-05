# Quick Start Guide - Lighthouse Kurtosis Testing

## 🚀 Fastest Way to Test (Automated)

```bash
# Run everything automatically
./run_test.sh
```

This will:
1. Start Kurtosis network (if not running)
2. Get the RPC endpoint
3. Send a test transaction
4. Verify block creation and validation

---

## 📋 Manual Testing

### 1. Start Network

```bash
kurtosis run github.com/kurtosis-tech/ethereum-package --args-file kurtosis-config.yaml
```

### 2. Get RPC Endpoint

```bash
./get_rpc_endpoint.sh
```

or manually:

```bash
kurtosis enclave ls  # Get enclave name
kurtosis enclave inspect <enclave-name>  # Look for el-1-geth-lighthouse -> rpc
```

### 3. Update and Run Test

```bash
# Edit tester.py and update RPC_URL
python3 tester.py
```

---

## 💸 Send Custom Transactions

```bash
# Send 1 ETH to a new account
./send_transaction.py

# Send 5 ETH to specific address
./send_transaction.py --amount 5 --to 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb

# Send multiple transactions (stress test)
./send_transaction.py --amount 0.1 --multiple 10

# Use different RPC endpoint
./send_transaction.py --rpc-url http://127.0.0.1:9545
```

---

## 🔍 Monitor Your Network

### View Logs

```bash
# List services
kurtosis enclave inspect <enclave-name>

# Beacon node logs (your Lighthouse patches)
kurtosis service logs <enclave-name> cl-1-lighthouse-geth

# Validator logs
kurtosis service logs <enclave-name> vc-1-lighthouse-geth

# Execution layer (Geth) logs
kurtosis service logs <enclave-name> el-1-geth-lighthouse

# Follow logs in real-time
kurtosis service logs <enclave-name> cl-1-lighthouse-geth -f
```

### Check Status

```bash
# Get RPC endpoint and call it
RPC_URL=$(kurtosis enclave inspect <enclave-name> | grep "rpc:" | head -n 1 | awk '{print $2}')

# Current block number
curl -X POST $RPC_URL -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}'

# Get latest block
curl -X POST $RPC_URL -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_getBlockByNumber","params":["latest", false],"id":1}'

# Check sync status
curl -X POST $RPC_URL -H "Content-Type: application/json" \
  --data '{"jsonrpc":"2.0","method":"eth_syncing","params":[],"id":1}'
```

### Beacon Chain API

```bash
# Get beacon API endpoint
BEACON_URL=$(kurtosis enclave inspect <enclave-name> | grep "http:" | grep "4000" | head -n 1 | awk '{print $2}')

# Node health
curl $BEACON_URL/eth/v1/node/health

# Current head
curl $BEACON_URL/eth/v1/beacon/headers/head

# Validator status
curl $BEACON_URL/eth/v1/beacon/states/head/validators
```

---

## 🌐 Web Interfaces

Your network includes web explorers:

```bash
# Get URLs
kurtosis enclave inspect <enclave-name> | grep -E "(dora|blockscout)"
```

**Dora Explorer** - View beacon chain activity:
- Block production
- Validator performance
- Attestations

**Blockscout** - View execution layer:
- Transactions
- Contracts
- Account balances

---

## 🧹 Cleanup

```bash
# Stop network (keeps data)
kurtosis enclave stop <enclave-name>

# Remove network
kurtosis enclave rm <enclave-name>

# Clean everything
kurtosis clean -a
```

---

## 🐛 Troubleshooting

### Sender Has No Balance

If you see "Sender balance: 0 ETH":

```bash
# Find accounts with funds
./find_funded_accounts.py
```

This will scan your network and show you which accounts have balances. Copy the private key and update `tester.py`:

```python
DEFAULT_PRIVATE_KEY = "0x..." # Use the key from find_funded_accounts.py
```

### Connection Issues

```bash
# Check if network is running
kurtosis enclave ls

# Check service status
kurtosis enclave inspect <enclave-name>

# Restart a specific service
kurtosis service stop <enclave-name> cl-1-lighthouse-geth
kurtosis service start <enclave-name> cl-1-lighthouse-geth
```

### Logs Not Showing Your Changes

```bash
# Verify custom image is being used
kurtosis enclave inspect <enclave-name> | grep "Image:"

# Force pull latest image
docker pull docker.io/giobbe/poc-lighthouse:latest

# Restart network with clean state
kurtosis clean -a
kurtosis run github.com/kurtosis-tech/ethereum-package --args-file kurtosis-config.yaml
```

### Transaction Not Mining

```bash
# Check if validators are attesting
kurtosis service logs <enclave-name> vc-1-lighthouse-geth | grep -i "attest"

# Check beacon chain is progressing
curl $BEACON_URL/eth/v1/beacon/headers/head

# View Dora explorer for real-time status
```

---

## 📦 Configuration

Edit `kurtosis-config.yaml` to customize:

- **Participants**: Number of nodes and validators
- **Network params**: Block time, chain ID, gas limit
- **Preloaded accounts**: Addresses with initial balances
- **Custom images**: Your Lighthouse and genesis generator images

After changing config:

```bash
kurtosis clean -a  # Clean old state
kurtosis run github.com/kurtosis-tech/ethereum-package --args-file kurtosis-config.yaml
```

---

## 🎯 Common Testing Scenarios

### Test Basic Block Production

```bash
./run_test.sh
```

### Stress Test with Multiple Transactions

```bash
./send_transaction.py --amount 0.1 --multiple 100
```

### Test Smart Contract Deployment

```python
# Use send_transaction.py as template
# Add contract deployment code (see TESTING_GUIDE.md)
```

### Monitor Attestations and Finality

```bash
# Watch validator logs
kurtosis service logs <enclave-name> vc-1-lighthouse-geth -f | grep -E "(attest|finali)"

# Check finality via API
curl $BEACON_URL/eth/v1/beacon/states/head/finality_checkpoints
```

---

## 📚 Files Reference

- `kurtosis-config.yaml` - Network configuration
- `run_test.sh` - Automated test runner
- `tester.py` - Basic transaction test
- `send_transaction.py` - Interactive transaction sender
- `find_funded_accounts.py` - Find accounts with balances
- `get_rpc_endpoint.sh` - Get RPC URL helper
- `TESTING_GUIDE.md` - Detailed testing guide

---

## 💡 Tips

1. **Keep logs open** while testing to see your Lighthouse patches in action
2. **Use Dora** for visual feedback on block production
3. **Start simple** with basic transactions before complex contracts
4. **Clean state** between major test changes
5. **Check validators** are actually attesting before debugging

---

## 🆘 Need Help?

- Full guide: `TESTING_GUIDE.md`
- Kurtosis docs: https://docs.kurtosis.com
- Lighthouse docs: https://lighthouse-book.sigmaprime.io
- Ethereum package: https://github.com/kurtosis-tech/ethereum-package

