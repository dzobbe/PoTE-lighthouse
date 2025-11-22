# Consensus Layer Performance Testing

This directory contains scripts for measuring and analyzing the performance of the Lighthouse consensus layer in your Kurtosis blockchain network.

## Scripts

### 1. `measure_consensus_performance.py`

Main script for collecting consensus layer metrics from a running Lighthouse beacon node.

**Usage:**
```bash
python scripts/measure_consensus_performance.py [OPTIONS]
```

**Options:**
- `--beacon-url`: Base URL for beacon node API (default: `http://localhost:5052`)
- `--metrics-port`: Port for Prometheus metrics (default: `5054`)
- `--duration`: Duration to collect metrics in seconds (default: `300`)
- `--interval`: Interval between metric collections in seconds (default: `12`)
- `--slots-per-epoch`: Number of slots per epoch (default: `32`)
- `--output-csv`: Output CSV file path
- `--output-json`: Output JSON file path
- `--verbose`: Print verbose output

**Example:**
```bash
# Basic measurement
python scripts/measure_consensus_performance.py --duration 600 --interval 12

# With custom output files
python scripts/measure_consensus_performance.py \
    --beacon-url http://localhost:5052 \
    --duration 300 \
    --output-csv results.csv \
    --output-json results.json \
    --verbose
```

**Metrics Collected:**
- Slot and epoch information
- Sync status
- Connected peers count
- Block production rate (blocks per minute)
- Attestation count and inclusion rates
- Validator counts (active, total)
- System metrics (CPU, memory, network)
- Prometheus metrics

### 2. `run_performance_tests.py`

Runs multiple performance tests with varying parameters to compare different configurations.

**Usage:**
```bash
python scripts/run_performance_tests.py [OPTIONS]
```

**Options:**
- `--beacon-url`: Base URL for beacon node API (default: `http://localhost:5052`)
- `--config`: Path to Kurtosis configuration file (for parameter variation)
- `--scenarios`: Path to JSON file with test scenarios (default: uses built-in scenarios)
- `--duration`: Duration per test in seconds (default: `300`)
- `--interval`: Metric collection interval in seconds (default: `12`)
- `--output-dir`: Output directory for test results (default: `performance_results`)
- `--wait-between-tests`: Wait time between tests in seconds (default: `60`)
- `--verbose`: Verbose output
- `--dry-run`: Print test scenarios without running them

**Example:**
```bash
# Run default test scenarios
python scripts/run_performance_tests.py --duration 600

# Use custom scenarios file
python scripts/run_performance_tests.py \
    --scenarios custom_scenarios.json \
    --output-dir my_results \
    --verbose

# Dry run to see what tests would be executed
python scripts/run_performance_tests.py --dry-run
```

## Test Scenarios

### Built-in Scenarios

The script includes several built-in test scenarios:

1. **baseline**: Standard configuration (12s slots, 5 validators)
2. **fast_slots**: Faster slot time (6 seconds)
3. **slow_slots**: Slower slot time (24 seconds)
4. **more_validators**: More validators per node (10 validators)
5. **fewer_validators**: Fewer validators per node (3 validators)

### Custom Scenarios

Create a JSON file with custom scenarios:

```json
[
  {
    "name": "my_test",
    "description": "Custom test description",
    "params": {
      "seconds_per_slot": 8,
      "validator_count": 7
    }
  }
]
```

## Output Files

### CSV Output
Contains time-series data with all collected metrics:
- `timestamp`: Unix timestamp
- `slot`: Current slot number
- `epoch`: Current epoch number
- `sync_status`: Sync status (synced/syncing)
- `connected_peers`: Number of connected peers
- `block_production_rate`: Blocks per minute
- `attestation_count`: Number of attestations in pool
- `validator_count`: Total validator count
- `active_validators`: Active validator count
- `cpu_usage`: CPU usage (if available)
- `memory_usage`: Memory usage in bytes (if available)
- `network_bytes_received`: Network bytes received (if available)
- `network_bytes_sent`: Network bytes sent (if available)

### JSON Output
Contains:
- Metadata (timestamp, sample count)
- Statistics (averages, min/max values)
- Full metrics array

### Test Summary
When running multiple tests, a `test_summary.json` file is created with:
- Test execution summary
- Comparison of all test results
- Scenario configurations

## Workflow

### 1. Start Your Kurtosis Network

```bash
# Start your Kurtosis network with your configuration
kurtosis run github.com/kurtosis-tech/ethereum-package --enclave my-testnet
```

### 2. Find Beacon Node URL

The beacon node API is typically available at:
- `http://localhost:5052` (if port-forwarded)
- Or check your Kurtosis service endpoints

### 3. Run Performance Tests

**Single measurement:**
```bash
python scripts/measure_consensus_performance.py \
    --beacon-url http://localhost:5052 \
    --duration 600 \
    --verbose
```

**Multiple scenarios:**
```bash
python scripts/run_performance_tests.py \
    --beacon-url http://localhost:5052 \
    --duration 600 \
    --output-dir results
```

### 4. Analyze Results

The scripts output CSV and JSON files that can be analyzed with:
- Python pandas
- Excel/LibreOffice
- Custom analysis scripts
- Visualization tools (matplotlib, plotly, etc.)

## Parameter Variation

To test different network configurations:

1. **Modify Kurtosis Config**: Edit `kurtosis-config-native.yaml` with different parameters:
   ```yaml
   network_params:
     seconds_per_slot: 6  # Try different values: 6, 12, 24
   
   participants:
     - validator_count: 10  # Try different values: 3, 5, 10, 20
   ```

2. **Restart Network**: Restart your Kurtosis network with the new configuration

3. **Run Tests**: Run performance tests with the new configuration

4. **Compare Results**: Compare the output files to see how parameters affect performance

## Key Metrics to Monitor

### Consensus Performance
- **Block Production Rate**: How many blocks are produced per minute
- **Slot Progression**: Whether slots are progressing at expected rate
- **Finalization**: How quickly epochs are finalized

### Network Health
- **Sync Status**: Whether nodes are synced
- **Peer Count**: Number of connected peers
- **Network Throughput**: Bytes sent/received

### Validator Performance
- **Active Validators**: Number of active validators
- **Attestation Rate**: Attestation production and inclusion
- **Validator Participation**: How many validators are participating

### System Resources
- **CPU Usage**: CPU consumption
- **Memory Usage**: Memory consumption
- **Network I/O**: Network bandwidth usage

## Troubleshooting

### Connection Errors
- Ensure the beacon node is running and accessible
- Check the `--beacon-url` parameter
- Verify port forwarding if using Kurtosis

### Missing Metrics
- Ensure Prometheus metrics are enabled (`--metrics` flag)
- Check that metrics port is accessible
- Some metrics may not be available immediately after startup

### No Blocks Produced
- Ensure validators are running and have deposits
- Check that the network has progressed past genesis
- Verify validator keys are properly configured

## Example Analysis Script

```python
import pandas as pd
import matplotlib.pyplot as plt

# Load CSV data
df = pd.read_csv('consensus_metrics_20240101_120000.csv')

# Plot block production rate over time
df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
plt.figure(figsize=(12, 6))
plt.plot(df['datetime'], df['block_production_rate'])
plt.xlabel('Time')
plt.ylabel('Blocks per Minute')
plt.title('Block Production Rate Over Time')
plt.grid(True)
plt.savefig('block_production_rate.png')
```

## Requirements

- Python 3.7+
- `requests` library: `pip install requests`
- `pyyaml` library (for run_performance_tests.py): `pip install pyyaml`

Install dependencies:
```bash
pip install requests pyyaml
```

