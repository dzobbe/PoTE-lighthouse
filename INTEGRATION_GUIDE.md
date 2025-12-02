# Integration Guide: Complex Blocks with Performance Testing

This guide explains how to use the complex block generator together with the performance test suite.

## Quick Start

### Basic Usage with Complex Blocks

Run performance tests with automatic complex block generation:

```bash
# TEE test with complex blocks (10 tx/s)
python3 performance_test.py \
  --config-type tee \
  --validator-count 10 \
  --node-count 5 \
  --generate-complex-blocks \
  --tx-rate 20

# Native test with complex blocks for comparison
python3 performance_test.py \
  --config-type native \
  --validator-count 10 \
  --node-count 5 \
  --generate-complex-blocks \
  --tx-rate 20
```

### High Complexity Testing

For maximum block complexity:

```bash
# High transaction rate (30 tx/s)
python3 performance_test.py \
  --config-type tee \
  --validator-count 15 \
  --node-count 10 \
  --generate-complex-blocks \
  --tx-rate 30 \
  --duration 600
```

## How It Works

1. **Performance test starts** Kurtosis network
2. **Network stabilizes** (60 seconds)
3. **Complex block generator starts** automatically (if `--generate-complex-blocks` is set)
4. **Metrics collection** runs while transactions are being generated
5. **Generator stops** automatically when test completes
6. **Results saved** with complexity metrics included

## Command Line Options

### New Options

- `--generate-complex-blocks`: Enable automatic complex block generation
- `--tx-rate RATE`: Transactions per second (default: 10)

### Example Combinations

```bash
# Moderate complexity
--generate-complex-blocks --tx-rate 15

# High complexity  
--generate-complex-blocks --tx-rate 30

# Very high complexity
--generate-complex-blocks --tx-rate 50
```

## Workflow Examples

### Example 1: Compare TEE vs Native with Complex Blocks

```bash
# Test 1: TEE with complex blocks
python3 performance_test.py \
  --config-type tee \
  --validator-count 10 \
  --node-count 5 \
  --generate-complex-blocks \
  --tx-rate 20 \
  --duration 300

# Test 2: Native with complex blocks (same parameters)
python3 performance_test.py \
  --config-type native \
  --validator-count 10 \
  --node-count 5 \
  --generate-complex-blocks \
  --tx-rate 20 \
  --duration 300
```

### Example 2: Varying Complexity Levels

```bash
# Low complexity (5 tx/s)
python3 performance_test.py \
  --config-type tee \
  --generate-complex-blocks \
  --tx-rate 5

# Medium complexity (15 tx/s)
python3 performance_test.py \
  --config-type tee \
  --generate-complex-blocks \
  --tx-rate 15

# High complexity (30 tx/s)
python3 performance_test.py \
  --config-type tee \
  --generate-complex-blocks \
  --tx-rate 30
```

### Example 3: Manual Control (Advanced)

If you want more control, you can run them separately:

**Terminal 1**: Start performance test
```bash
python3 performance_test.py --config-type tee --duration 600
```

**Terminal 2**: Start complex block generator
```bash
python3 generate_complex_blocks.py --duration 600 --rate 20
```

## What Gets Measured

With complex blocks enabled, the performance test will measure:

1. **Block Verification Time**: How long it takes to verify blocks
   - Should be higher for TEE (attestation verification)
   - Should be lower for native (no attestation overhead)

2. **Block Execution Time**: Time to process execution payload
   - Should be **zero** for TEE (skipped)
   - Should be **high** for native (re-executes all transactions)

3. **Block Delay Total**: Total time from slot start to block acceptance
   - TEE: Verification overhead + propagation
   - Native: Verification + execution + propagation

4. **Gas Utilization**: How full blocks are
   - Check results JSON for transaction counts
   - Higher = more complex blocks

## Expected Results

### Simple Blocks (No `--generate-complex-blocks`)
- **Native**: ~6ms verification + ~1ms execution = **~7ms total**
- **TEE**: ~831ms verification + 0ms execution = **~831ms total** ❌

### Complex Blocks (With `--generate-complex-blocks --tx-rate 20`)
- **Native**: ~6ms verification + ~100ms execution = **~106ms total**
- **TEE**: ~831ms verification + 0ms execution = **~831ms total** ✅ (faster!)

### Complex Blocks (Optimized TEE - Future)
- **Native**: ~6ms verification + ~100ms execution = **~106ms total**
- **TEE**: ~20ms verification + 0ms execution = **~20ms total** ✅✅ (much faster!)

## Troubleshooting

### Complex Block Generator Not Starting

**Problem**: Script can't find RPC port

**Solution**: The script auto-detects from `docker ps`. If it fails:
1. Check `docker ps` shows `el-*-geth-lighthouse` containers
2. Manually specify RPC port in `generate_complex_blocks.py` if needed

### Transactions Not Being Included

**Problem**: Blocks remain simple despite generator running

**Solutions**:
1. **Increase gas limit** in `kurtosis-config.yaml`:
   ```yaml
   network_params:
     gas_limit: 45000000
   ```

2. **Increase transaction rate**:
   ```bash
   --tx-rate 30  # or higher
   ```

3. **Check network is producing blocks**: Ensure validators are active

### Performance Test Hangs

**Problem**: Test doesn't complete

**Solutions**:
1. Check complex block generator is running: `ps aux | grep generate_complex_blocks`
2. Check Kurtosis is running: `kurtosis enclave inspect`
3. Increase timeout if needed

## Best Practices

1. **Start with moderate complexity**: Use `--tx-rate 15` first
2. **Match test duration**: Generator runs for test duration + buffer
3. **Compare side-by-side**: Run TEE and Native with same parameters
4. **Check results**: Verify blocks actually have transactions
5. **Monitor resources**: Complex blocks use more CPU/memory

## Results Analysis

After running tests, check the results JSON:

```json
{
  "statistics": {
    "avg_block_verification_time_ms": 831.5,
    "avg_block_execution_time_ms": 0.0,  // TEE skips execution!
    "avg_block_delay_total_ms": 1906.2
  }
}
```

Compare:
- **block_execution_time_ms**: Should be 0 for TEE, >0 for native
- **block_verification_time_ms**: TEE overhead vs native baseline
- **block_delay_total_ms**: Overall performance difference

## Next Steps

1. Run baseline tests (no complex blocks)
2. Run with moderate complexity (`--tx-rate 15`)
3. Run with high complexity (`--tx-rate 30`)
4. Compare results to see where TEE becomes advantageous
5. Optimize TEE verification to improve performance

