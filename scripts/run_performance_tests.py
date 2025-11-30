#!/usr/bin/env python3
"""
Parameterized Performance Testing Script

This script runs multiple performance tests with varying parameters
to measure consensus layer performance under different configurations.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
import yaml


def detect_metrics_port(beacon_url: str, default_port: int = 5054) -> int:
    """
    Auto-detect metrics port from beacon URL.
    For Kurtosis setups, metrics port is typically API port + 1.
    Falls back to default_port if detection fails.
    """
    try:
        parsed = urlparse(beacon_url)
        api_port = parsed.port
        
        # If no port specified, use default
        if api_port is None:
            return default_port
        
        # For Kurtosis-style high ports (typically > 30000), metrics port is +1
        # For standard ports (5052), metrics port is 5054
        if api_port > 30000:
            # Kurtosis port-forwarded: metrics port is API port + 1
            metrics_port = api_port + 1
            # Verify it's accessible (optional check)
            try:
                import requests
                test_url = f"http://{parsed.hostname}:{metrics_port}/metrics"
                response = requests.get(test_url, timeout=2)
                if response.status_code == 200:
                    return metrics_port
            except:
                # If check fails, still use +1 as it's the pattern
                pass
            return metrics_port
        elif api_port == 5052:
            # Standard Lighthouse setup
            return 5054
        else:
            # Unknown setup, try +1 or use default
            return api_port + 1 if api_port < 10000 else default_port
    except Exception:
        return default_port


def load_kurtosis_config(config_path: str) -> Dict[str, Any]:
    """Load Kurtosis configuration file"""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def update_kurtosis_config(config: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    """Update Kurtosis configuration with new parameters"""
    updated = config.copy()
    
    if 'seconds_per_slot' in kwargs:
        updated.setdefault('network_params', {})['seconds_per_slot'] = kwargs['seconds_per_slot']
    
    if 'validator_count' in kwargs:
        for participant in updated.get('participants', []):
            participant['validator_count'] = kwargs['validator_count']
    
    if 'participant_count' in kwargs:
        for participant in updated.get('participants', []):
            participant['count'] = kwargs['participant_count']
    
    return updated


def save_config(config: Dict[str, Any], output_path: str):
    """Save configuration to file"""
    with open(output_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def run_performance_test(
    beacon_url: str,
    test_name: str,
    duration: int,
    interval: int,
    output_dir: Path,
    metrics_port: int = 5054,
    **kwargs
) -> Dict[str, Any]:
    """Run a single performance test"""
    print(f"\n{'='*60}")
    print(f"Running test: {test_name}")
    print(f"{'='*60}")
    
    # Prepare output files
    csv_file = output_dir / f"{test_name}_metrics.csv"
    json_file = output_dir / f"{test_name}_results.json"
    
    # Run the measurement script
    cmd = [
        sys.executable,
        'scripts/measure_consensus_performance.py',
        '--beacon-url', beacon_url,
        '--metrics-port', str(metrics_port),
        '--duration', str(duration),
        '--interval', str(interval),
        '--output-csv', str(csv_file),
        '--output-json', str(json_file),
    ]
    
    if kwargs.get('verbose'):
        cmd.append('--verbose')
    
    print(f"Command: {' '.join(cmd)}")
    
    try:
        # Stream output in real-time instead of buffering
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Print output line by line as it comes
        output_lines = []
        for line in process.stdout:
            print(line, end='', flush=True)
            output_lines.append(line)
        
        # Wait for process to complete
        return_code = process.wait()
        
        if return_code != 0:
            output_text = ''.join(output_lines)
            raise subprocess.CalledProcessError(return_code, cmd, output_text)
        
        # Load results
        with open(json_file, 'r') as f:
            results = json.load(f)
        
        return {
            'test_name': test_name,
            'success': True,
            'results': results,
            'csv_file': str(csv_file),
            'json_file': str(json_file),
        }
    except subprocess.CalledProcessError as e:
        print(f"Test failed with return code {e.returncode}: {e}", file=sys.stderr)
        if e.stdout:
            print("Output:", e.stdout, file=sys.stderr)
        return {
            'test_name': test_name,
            'success': False,
            'error': str(e),
        }


def create_test_scenarios() -> List[Dict[str, Any]]:
    """Create default test scenarios"""
    scenarios = [
        {
            'name': 'baseline',
            'description': 'Baseline configuration',
            'params': {
                'seconds_per_slot': 12,
                'validator_count': 5,
            }
        },
        {
            'name': 'fast_slots',
            'description': 'Faster slot time (6 seconds)',
            'params': {
                'seconds_per_slot': 6,
                'validator_count': 5,
            }
        },
        {
            'name': 'slow_slots',
            'description': 'Slower slot time (24 seconds)',
            'params': {
                'seconds_per_slot': 24,
                'validator_count': 5,
            }
        },
        {
            'name': 'more_validators',
            'description': 'More validators per node',
            'params': {
                'seconds_per_slot': 12,
                'validator_count': 10,
            }
        },
        {
            'name': 'fewer_validators',
            'description': 'Fewer validators per node',
            'params': {
                'seconds_per_slot': 12,
                'validator_count': 3,
            }
        },
    ]
    return scenarios


def main():
    parser = argparse.ArgumentParser(
        description='Run parameterized performance tests for consensus layer'
    )
    parser.add_argument(
        '--beacon-url',
        default='http://localhost:5052',
        help='Base URL for beacon node API (default: http://localhost:5052)'
    )
    parser.add_argument(
        '--metrics-port',
        type=int,
        default=5054,
        help='Port for Prometheus metrics endpoint (default: 5054)'
    )
    parser.add_argument(
        '--config',
        help='Path to Kurtosis configuration file (for parameter variation)'
    )
    parser.add_argument(
        '--scenarios',
        help='Path to JSON file with test scenarios (default: use built-in scenarios)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=300,
        help='Duration per test in seconds (default: 300)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=12,
        help='Metric collection interval in seconds (default: 12)'
    )
    parser.add_argument(
        '--output-dir',
        default='performance_results',
        help='Output directory for test results (default: performance_results)'
    )
    parser.add_argument(
        '--wait-between-tests',
        type=int,
        default=60,
        help='Wait time between tests in seconds (default: 60)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Verbose output'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print test scenarios without running them'
    )
    
    args = parser.parse_args()
    
    # Auto-detect metrics port if not explicitly provided
    if args.metrics_port == 5054:  # Only auto-detect if using default
        detected_port = detect_metrics_port(args.beacon_url, args.metrics_port)
        if detected_port != args.metrics_port:
            print(f"Auto-detected metrics port: {detected_port} (from beacon URL: {args.beacon_url})")
            args.metrics_port = detected_port
    
    # Load scenarios
    if args.scenarios:
        with open(args.scenarios, 'r') as f:
            scenarios = json.load(f)
    else:
        scenarios = create_test_scenarios()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Test Configuration:")
    print(f"  Beacon URL: {args.beacon_url}")
    print(f"  Duration per test: {args.duration} seconds")
    print(f"  Collection interval: {args.interval} seconds")
    print(f"  Output directory: {output_dir}")
    print(f"  Number of scenarios: {len(scenarios)}")
    print()
    
    if args.dry_run:
        print("Test Scenarios (dry run):")
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n{i}. {scenario['name']}")
            print(f"   Description: {scenario.get('description', 'N/A')}")
            print(f"   Parameters: {scenario.get('params', {})}")
        return
    
    # Run tests
    results = []
    for i, scenario in enumerate(scenarios, 1):
        test_name = scenario['name']
        params = scenario.get('params', {})
        
        print(f"\n[{i}/{len(scenarios)}] Test: {test_name}")
        if 'description' in scenario:
            print(f"Description: {scenario['description']}")
        print(f"Parameters: {params}")
        
        # If config file provided, update it
        if args.config:
            config = load_kurtosis_config(args.config)
            updated_config = update_kurtosis_config(config, **params)
            config_output = output_dir / f"{test_name}_kurtosis_config.yaml"
            save_config(updated_config, str(config_output))
            print(f"Updated config saved to: {config_output}")
            print("⚠ Note: You need to restart Kurtosis with the new config for changes to take effect")
        
        # Run performance test
        result = run_performance_test(
            beacon_url=args.beacon_url,
            test_name=test_name,
            duration=args.duration,
            interval=args.interval,
            output_dir=output_dir,
            metrics_port=args.metrics_port,
            verbose=args.verbose,
        )
        
        results.append(result)
        
        # Wait between tests (except for the last one)
        if i < len(scenarios) and args.wait_between_tests > 0:
            print(f"\nWaiting {args.wait_between_tests} seconds before next test...")
            time.sleep(args.wait_between_tests)
    
    # Save summary
    summary = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_tests': len(scenarios),
        'successful_tests': sum(1 for r in results if r.get('success')),
        'failed_tests': sum(1 for r in results if not r.get('success')),
        'scenarios': scenarios,
        'results': results,
    }
    
    summary_file = output_dir / 'test_summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)
    
    # Print final summary
    print(f"\n{'='*60}")
    print("Test Summary")
    print(f"{'='*60}")
    print(f"Total tests: {len(scenarios)}")
    print(f"Successful: {summary['successful_tests']}")
    print(f"Failed: {summary['failed_tests']}")
    print(f"\nSummary saved to: {summary_file}")
    
    # Print comparison if multiple successful tests
    successful_results = [r for r in results if r.get('success')]
    if len(successful_results) > 1:
        print("\n=== Performance Comparison ===")
        print(f"{'Test Name':<20} {'Avg Blocks/min':<15} {'Avg Peers':<12} {'Avg Validators':<15}")
        print("-" * 65)
        for result in successful_results:
            stats = result.get('results', {}).get('statistics', {})
            name = result['test_name']
            blocks_per_min = stats.get('avg_block_production_rate', 0)
            peers = stats.get('avg_connected_peers', 0)
            validators = stats.get('avg_validator_count', 0)
            print(f"{name:<20} {blocks_per_min:<15.2f} {peers:<12.1f} {validators:<15.1f}")


if __name__ == '__main__':
    main()

