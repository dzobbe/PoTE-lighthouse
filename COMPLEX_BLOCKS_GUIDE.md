# Guide: Simulating Complex Blocks for Performance Testing

This guide explains how to simulate complex blocks to test TEE vs Native performance differences.

## Overview

Block complexity in Ethereum comes from:
1. **Execution Layer Transactions** - Number and complexity of transactions
2. **Attestations** - Number of validators attesting to blocks
3. **Operations** - Deposits, exits, slashings
4. **Blob Data** - For Deneb+ forks (EIP-4844)

## Methods to Increase Block Complexity

### Method 1: Increase Gas Limit (Recommended)

Edit `kurtosis-config.yaml` or `kurtosis-config-native.yaml`:

```yaml
network_params:
  gas_limit: 45000000  # Increase from 30000000 to allow more transactions
```

**Effect**: Allows more transactions per block (up to gas_limit)

### Method 2: Send Many Transactions

Use the `generate_complex_blocks.py` script to continuously send transactions:

```bash
# Send 100 transactions at 10 tx/s
python3 generate_complex_blocks.py --transactions 100 --rate 10

# Run for 5 minutes at 20 tx/s
python3 generate_complex_blocks.py --duration 300 --rate 20

# Send larger transactions
python3 generate_complex_blocks.py --transactions 200 --amount 0.01
```

**Effect**: Fills blocks with transactions, increasing execution time

### Method 3: Increase Validator Count

More validators = more attestations per block:

```yaml
participants:
- validator_count: 15  # Increase from 5
  count: 10            # More nodes = more validators
```

**Effect**: More attestations to process per block

### Method 4: Combine All Methods

For maximum complexity:

1. **Increase gas limit** in config:
   ```yaml
   network_params:
     gas_limit: 45000000
   ```

2. **Increase validators**:
   ```yaml
   participants:
   - validator_count: 15
     count: 10
   ```

3. **Run transaction generator**:
   ```bash
   python3 generate_complex_blocks.py --duration 600 --rate 30
   ```

## Expected Performance Impact

### Simple Blocks (Current)
- Transactions: 0-5 per block
- Gas used: < 1M
- Execution time: ~1-5ms
- **TEE advantage**: Minimal (verification overhead > execution savings)

### Complex Blocks (Target)
- Transactions: 50-200 per block
- Gas used: 10M-30M
- Execution time: 50-200ms
- **TEE advantage**: Significant (execution savings > verification overhead)

## Testing Workflow

### Step 1: Configure for Complex Blocks

Edit `kurtosis-config.yaml`:
```yaml
network_params:
  gas_limit: 45000000  # Allow more transactions
  seconds_per_slot: 12

participants:
- validator_count: 10  # More validators = more attestations
  count: 5
```

### Step 2: Start Network

```bash
kurtosis run github.com/dzobbe/PoTE-ethereum-package --args-file kurtosis-config.yaml
```

### Step 3: Find RPC Port

```bash
kurtosis enclave inspect
# Look for: cl-1-lighthouse-geth rpc: 8545/tcp -> http://127.0.0.1:PORT
```

### Step 4: Generate Transactions

```bash
# Auto-detect RPC port
python3 generate_complex_blocks.py --transactions 500 --rate 20

# Or specify RPC URL
python3 generate_complex_blocks.py \
  --rpc-url http://127.0.0.1:PORT \
  --transactions 500 \
  --rate 20 \
  --amount 0.001
```

### Step 5: Run Performance Test

While transactions are being generated, run the performance test:

```bash
python3 performance_test.py \
  --config-type tee \
  --validator-count 10 \
  --node-count 5 \
  --duration 300
```

## Monitoring Block Complexity

### Check Block Information

```python
from web3 import Web3

w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:PORT"))
block = w3.eth.get_block('latest', full_transactions=True)

print(f"Block {block['number']}:")
print(f"  Transactions: {len(block['transactions'])}")
print(f"  Gas used: {block['gasUsed']:,} / {block['gasLimit']:,}")
print(f"  Utilization: {block['gasUsed'] / block['gasLimit'] * 100:.1f}%")
```

### Check Beacon Block Complexity

```bash
# Get block from beacon API
curl http://127.0.0.1:BEACON_PORT/eth/v1/beacon/blocks/head

# Check execution payload
curl http://127.0.0.1:BEACON_PORT/eth/v1/beacon/blocks/head | jq '.data.message.body.execution_payload.transactions | length'
```

## Expected Results

### Native Solution
- **Simple blocks**: ~6ms verification + ~1ms execution = ~7ms total
- **Complex blocks**: ~6ms verification + ~100ms execution = ~106ms total

### TEE Solution (Current - Unoptimized)
- **Simple blocks**: ~831ms verification + 0ms execution = ~831ms total ❌
- **Complex blocks**: ~831ms verification + 0ms execution = ~831ms total ✅ (faster than native!)

### TEE Solution (Optimized - Expected)
- **Simple blocks**: ~20ms verification + 0ms execution = ~20ms total
- **Complex blocks**: ~20ms verification + 0ms execution = ~20ms total ✅ (much faster!)

## Tips

1. **Start with moderate complexity**: 50-100 transactions per block
2. **Monitor gas utilization**: Aim for 50-80% gas usage
3. **Use multiple accounts**: Prevents nonce conflicts
4. **Run for sufficient duration**: At least 5-10 minutes to get good statistics
5. **Compare side-by-side**: Run native and TEE tests with same complexity

## Troubleshooting

### Transactions Not Being Included
- **Check gas price**: May need to increase `--gas-price`
- **Check nonce**: Ensure sender has sufficient balance
- **Check gas limit**: Ensure transactions fit within block gas limit

### Blocks Still Simple
- **Increase transaction rate**: Use `--rate 30` or higher
- **Increase gas limit**: Set `gas_limit: 45000000` in config
- **Check network**: Ensure validators are producing blocks

### Performance Test Not Showing Differences
- **Increase complexity**: More transactions, more validators
- **Longer duration**: Run for 10+ minutes
- **Check metrics**: Verify `block_execution_time_ms` is being measured

