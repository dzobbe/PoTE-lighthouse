#!/usr/bin/env python3
"""
Consensus Layer Performance Measurement Script for Kurtosis Lighthouse Network

This script measures the performance of the consensus layer by:
- Querying beacon node APIs for metrics
- Collecting Prometheus metrics
- Measuring block production, attestation rates, sync status
- Supporting parameter variation (seconds_per_slot, validator_count, etc.)
- Outputting results in CSV/JSON format
"""

import argparse
import json
import csv
import time
import requests
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
from urllib.parse import urlparse
import statistics


@dataclass
class ConsensusMetrics:
    """Container for consensus layer metrics"""
    timestamp: float
    slot: int
    epoch: int
    head_slot: int
    finalized_slot: int
    sync_status: str
    connected_peers: int
    block_production_rate: float  # blocks per minute
    attestation_count: int
    attestation_inclusion_rate: float  # percentage
    validator_count: int
    active_validators: int
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    network_bytes_received: Optional[int] = None
    network_bytes_sent: Optional[int] = None
    block_delay_total_ms: Optional[float] = None  # Time from slot start to block set as head (ms)
    block_delay_observed_ms: Optional[float] = None  # Time from slot start to block observed (ms)
    block_delay_consensus_verification_ms: Optional[float] = None  # Consensus verification time (ms)
    block_delay_execution_ms: Optional[float] = None  # Execution layer verification time (ms)


class BeaconNodeClient:
    """Client for querying Lighthouse beacon node APIs"""
    
    def __init__(self, base_url: str = "http://localhost:5052", metrics_port: int = 5054):
        self.base_url = base_url.rstrip('/')
        # Extract hostname from base_url to use same host for metrics
        parsed_url = urlparse(self.base_url)
        hostname = parsed_url.hostname or 'localhost'
        self.metrics_url = f"http://{hostname}:{metrics_port}/metrics"
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
    
    def get_sync_status(self) -> Dict[str, Any]:
        """Get sync status from /eth/v1/node/syncing"""
        try:
            response = self.session.get(f"{self.base_url}/eth/v1/node/syncing", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting sync status: {e}", file=sys.stderr)
            return {}
    
    def get_genesis(self) -> Dict[str, Any]:
        """Get genesis data"""
        try:
            response = self.session.get(f"{self.base_url}/eth/v1/beacon/genesis", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting genesis: {e}", file=sys.stderr)
            return {}
    
    def get_finality_checkpoints(self, state_id: str = "head") -> Dict[str, Any]:
        """Get finality checkpoints"""
        try:
            response = self.session.get(
                f"{self.base_url}/eth/v1/beacon/states/{state_id}/finality_checkpoints",
                timeout=5
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting finality checkpoints: {e}", file=sys.stderr)
            return {}
    
    def get_block_headers(self, slot: Optional[int] = None, parent_root: Optional[str] = None) -> Dict[str, Any]:
        """Get block headers"""
        try:
            url = f"{self.base_url}/eth/v1/beacon/headers"
            params = {}
            if slot is not None:
                params['slot'] = slot
            if parent_root is not None:
                params['parent_root'] = parent_root
            
            response = self.session.get(url, params=params, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting block headers: {e}", file=sys.stderr)
            return {}
    
    def get_validators(self, state_id: str = "head", validator_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get validator information"""
        try:
            url = f"{self.base_url}/eth/v1/beacon/states/{state_id}/validators"
            if validator_ids:
                url += f"?id={'&id='.join(validator_ids)}"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting validators: {e}", file=sys.stderr)
            return {}
    
    def get_validator_count(self) -> Dict[str, Any]:
        """Get validator count from Lighthouse UI endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/lighthouse/ui/validator_count", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting validator count: {e}", file=sys.stderr)
            return {}
    
    def get_health(self) -> Dict[str, Any]:
        """Get node health from Lighthouse UI endpoint"""
        try:
            response = self.session.get(f"{self.base_url}/lighthouse/ui/health", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting health: {e}", file=sys.stderr)
            return {}
    
    def get_pool_attestations(self) -> Dict[str, Any]:
        """Get attestations from the pool"""
        try:
            response = self.session.get(f"{self.base_url}/eth/v1/beacon/pool/attestations", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting pool attestations: {e}", file=sys.stderr)
            return {}
    
    def get_metrics(self) -> Dict[str, float]:
        """Parse Prometheus metrics"""
        metrics = {}
        try:
            response = requests.get(self.metrics_url, timeout=5)
            response.raise_for_status()
            
            for line in response.text.split('\n'):
                if line.startswith('#') or not line.strip():
                    continue
                
                # Parse Prometheus format: metric_name{labels} value
                if '{' in line:
                    parts = line.split('{', 1)
                    metric_name = parts[0]
                    rest = parts[1].rsplit('}', 1)
                    if len(rest) == 2:
                        value = rest[1].strip()
                    else:
                        continue
                else:
                    parts = line.split()
                    if len(parts) >= 2:
                        metric_name = parts[0]
                        value = parts[1]
                    else:
                        continue
                
                try:
                    metrics[metric_name] = float(value)
                except ValueError:
                    continue
        except Exception as e:
            print(f"Error getting metrics: {e}", file=sys.stderr)
        
        return metrics
    
    def get_config_spec(self) -> Dict[str, Any]:
        """Get consensus spec configuration"""
        try:
            response = self.session.get(f"{self.base_url}/eth/v1/config/spec", timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error getting config spec: {e}", file=sys.stderr)
            return {}


class PerformanceMonitor:
    """Monitor consensus layer performance"""
    
    def __init__(self, client: BeaconNodeClient, slots_per_epoch: int = 32):
        self.client = client
        self.slots_per_epoch = slots_per_epoch
        self.metrics_history: List[ConsensusMetrics] = []
        self.block_timestamps: Dict[int, float] = {}  # slot -> timestamp
        self.attestation_counts: Dict[int, int] = defaultdict(int)  # slot -> count
    
    def collect_metrics(self) -> ConsensusMetrics:
        """Collect current consensus metrics"""
        timestamp = time.time()
        
        # Get sync status
        sync_data = self.client.get_sync_status()
        sync_info = sync_data.get('data', {})
        is_syncing = sync_info.get('is_syncing', True)
        sync_status = "syncing" if is_syncing else "synced"
        
        # Get finality checkpoints
        checkpoints = self.client.get_finality_checkpoints()
        checkpoint_data = checkpoints.get('data', {})
        finalized_slot = 0
        head_slot = 0
        
        if checkpoint_data:
            finalized_epoch = int(checkpoint_data.get('finalized', {}).get('epoch', 0))
            current_epoch = int(checkpoint_data.get('current_justified', {}).get('epoch', 0))
            finalized_slot = finalized_epoch * self.slots_per_epoch
            head_slot = current_epoch * self.slots_per_epoch
        
        # Get block headers to find current slot
        headers = self.client.get_block_headers()
        header_data = headers.get('data', [])
        if header_data:
            head_slot = int(header_data[0].get('header', {}).get('message', {}).get('slot', 0))
            # If we got block headers, there's a block at this slot
            # Track it if it's a new slot we haven't seen
            if head_slot not in self.block_timestamps:
                self.track_block(head_slot)
        
        current_slot = head_slot
        current_epoch = current_slot // self.slots_per_epoch
        
        # Get validator count
        validator_count_data = self.client.get_validator_count()
        validator_info = validator_count_data.get('data', {})
        active_validators = validator_info.get('active_ongoing', 0)
        total_validators = sum([
            validator_info.get('active_ongoing', 0),
            validator_info.get('active_exiting', 0),
            validator_info.get('pending_initialized', 0),
            validator_info.get('pending_queued', 0),
        ])
        
        # Get health info for peers
        health_data = self.client.get_health()
        health_info = health_data.get('data', {})
        connected_peers = health_info.get('connected_peers', 0)
        
        # Calculate block production rate (blocks per minute)
        block_production_rate = 0.0
        # Calculate based on recent blocks (last minute)
        recent_blocks = [(s, t) for s, t in self.block_timestamps.items() 
                       if timestamp - t < 60]  # Last minute
        if len(recent_blocks) > 1:
            time_span = max(t for _, t in recent_blocks) - min(t for _, t in recent_blocks)
            if time_span > 0:
                block_production_rate = (len(recent_blocks) - 1) / (time_span / 60)
        elif len(recent_blocks) == 1:
            # Only one block in the last minute, estimate rate based on slot time
            # Assuming 12 seconds per slot (can be adjusted)
            block_production_rate = 60.0 / 12.0  # 5 blocks per minute theoretical max
        
        # Get attestations
        attestations = self.client.get_pool_attestations()
        attestation_data = attestations.get('data', [])
        attestation_count = len(attestation_data)
        
        # Calculate attestation inclusion rate (simplified - would need historical data)
        attestation_inclusion_rate = 0.0
        
        # Get Prometheus metrics
        prom_metrics = self.client.get_metrics()
        cpu_usage = prom_metrics.get('lighthouse_process_cpu_seconds_total')
        memory_usage = prom_metrics.get('lighthouse_process_resident_set_size_bytes')
        network_bytes_received = prom_metrics.get('lighthouse_network_libp2p_bytes_total_received')
        network_bytes_sent = prom_metrics.get('lighthouse_network_libp2p_bytes_total_transmit')
        
        # Block delay/timing metrics (transaction processing time)
        block_delay_total_ms = prom_metrics.get('beacon_block_delay_total')
        block_delay_observed_ms = prom_metrics.get('beacon_block_delay_observed_slot_start')
        block_delay_consensus_verification_ms = prom_metrics.get('beacon_block_delay_consensus_verification_time')
        block_delay_execution_ms = prom_metrics.get('beacon_block_delay_execution_time')
        
        metrics = ConsensusMetrics(
            timestamp=timestamp,
            slot=current_slot,
            epoch=current_epoch,
            head_slot=head_slot,
            finalized_slot=finalized_slot,
            sync_status=sync_status,
            connected_peers=connected_peers,
            block_production_rate=block_production_rate,
            attestation_count=attestation_count,
            attestation_inclusion_rate=attestation_inclusion_rate,
            validator_count=total_validators,
            active_validators=active_validators,
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            network_bytes_received=int(network_bytes_received) if network_bytes_received else None,
            network_bytes_sent=int(network_bytes_sent) if network_bytes_sent else None,
            block_delay_total_ms=block_delay_total_ms,
            block_delay_observed_ms=block_delay_observed_ms,
            block_delay_consensus_verification_ms=block_delay_consensus_verification_ms,
            block_delay_execution_ms=block_delay_execution_ms,
        )
        
        self.metrics_history.append(metrics)
        return metrics
    
    def track_block(self, slot: int):
        """Track when a block was produced"""
        self.block_timestamps[slot] = time.time()
        # Clean old entries (keep last hour)
        cutoff = time.time() - 3600
        self.block_timestamps = {s: t for s, t in self.block_timestamps.items() if t > cutoff}
    
    def get_statistics(self) -> Dict[str, Any]:
        """Calculate statistics from collected metrics"""
        if not self.metrics_history:
            return {}
        
        stats = {
            'total_samples': len(self.metrics_history),
            'duration_seconds': self.metrics_history[-1].timestamp - self.metrics_history[0].timestamp,
            'avg_block_production_rate': statistics.mean([m.block_production_rate for m in self.metrics_history]),
            'max_block_production_rate': max([m.block_production_rate for m in self.metrics_history]),
            'min_block_production_rate': min([m.block_production_rate for m in self.metrics_history]),
            'avg_connected_peers': statistics.mean([m.connected_peers for m in self.metrics_history]),
            'avg_validator_count': statistics.mean([m.validator_count for m in self.metrics_history]),
            'avg_attestation_count': statistics.mean([m.attestation_count for m in self.metrics_history]),
        }
        
        if any(m.cpu_usage for m in self.metrics_history):
            stats['avg_cpu_usage'] = statistics.mean([m.cpu_usage or 0 for m in self.metrics_history])
        
        if any(m.memory_usage for m in self.metrics_history):
            stats['avg_memory_usage_mb'] = statistics.mean([m.memory_usage or 0 for m in self.metrics_history]) / (1024 * 1024)
        
        # Block delay/timing statistics (transaction processing time)
        block_delays_total = [m.block_delay_total_ms for m in self.metrics_history if m.block_delay_total_ms is not None]
        if block_delays_total:
            stats['avg_block_delay_total_ms'] = statistics.mean(block_delays_total)
            stats['min_block_delay_total_ms'] = min(block_delays_total)
            stats['max_block_delay_total_ms'] = max(block_delays_total)
        
        block_delays_observed = [m.block_delay_observed_ms for m in self.metrics_history if m.block_delay_observed_ms is not None]
        if block_delays_observed:
            stats['avg_block_delay_observed_ms'] = statistics.mean(block_delays_observed)
        
        block_delays_consensus = [m.block_delay_consensus_verification_ms for m in self.metrics_history if m.block_delay_consensus_verification_ms is not None]
        if block_delays_consensus:
            stats['avg_block_delay_consensus_verification_ms'] = statistics.mean(block_delays_consensus)
        
        block_delays_execution = [m.block_delay_execution_ms for m in self.metrics_history if m.block_delay_execution_ms is not None]
        if block_delays_execution:
            stats['avg_block_delay_execution_ms'] = statistics.mean(block_delays_execution)
        
        return stats


def save_csv(metrics_list: List[ConsensusMetrics], filename: str):
    """Save metrics to CSV file"""
    if not metrics_list:
        return
    
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[f.name for f in ConsensusMetrics.__dataclass_fields__.values()])
        writer.writeheader()
        for metrics in metrics_list:
            writer.writerow(asdict(metrics))
    
    print(f"Saved {len(metrics_list)} metrics to {filename}")


def save_json(metrics_list: List[ConsensusMetrics], stats: Dict[str, Any], filename: str):
    """Save metrics and statistics to JSON file"""
    data = {
        'metadata': {
            'generated_at': datetime.now().isoformat(),
            'total_samples': len(metrics_list),
        },
        'statistics': stats,
        'metrics': [asdict(m) for m in metrics_list],
    }
    
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Saved metrics and statistics to {filename}")


def main():
    parser = argparse.ArgumentParser(
        description='Measure consensus layer performance for Kurtosis Lighthouse network'
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
        help='Port for Prometheus metrics (default: 5054)'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=300,
        help='Duration to collect metrics in seconds (default: 300)'
    )
    parser.add_argument(
        '--interval',
        type=int,
        default=12,
        help='Interval between metric collections in seconds (default: 12)'
    )
    parser.add_argument(
        '--slots-per-epoch',
        type=int,
        default=32,
        help='Number of slots per epoch (default: 32)'
    )
    parser.add_argument(
        '--output-csv',
        help='Output CSV file path'
    )
    parser.add_argument(
        '--output-json',
        help='Output JSON file path'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Print verbose output'
    )
    
    args = parser.parse_args()
    
    # Initialize client and monitor
    client = BeaconNodeClient(args.beacon_url, args.metrics_port)
    monitor = PerformanceMonitor(client, args.slots_per_epoch)
    
    print(f"Starting consensus performance measurement...")
    print(f"Beacon URL: {args.beacon_url}")
    print(f"Duration: {args.duration} seconds")
    print(f"Collection interval: {args.interval} seconds")
    print()
    
    # Test connection
    try:
        genesis = client.get_genesis()
        if genesis:
            print("✓ Successfully connected to beacon node")
        else:
            print("⚠ Warning: Could not connect to beacon node, continuing anyway...")
    except Exception as e:
        print(f"⚠ Warning: Connection test failed: {e}")
        print("Continuing anyway...")
    
    # Collect metrics
    start_time = time.time()
    end_time = start_time + args.duration
    sample_count = 0
    
    print("Collecting metrics...")
    while time.time() < end_time:
        try:
            metrics = monitor.collect_metrics()
            sample_count += 1
            
            if args.verbose:
                print(f"[{sample_count}] Slot: {metrics.slot}, "
                      f"Epoch: {metrics.epoch}, "
                      f"Sync: {metrics.sync_status}, "
                      f"Peers: {metrics.connected_peers}, "
                      f"Blocks/min: {metrics.block_production_rate:.2f}, "
                      f"Validators: {metrics.active_validators}")
            else:
                print(f"Sample {sample_count}/{int(args.duration / args.interval)} collected...", end='\r')
            
            time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:
            print(f"\nError collecting metrics: {e}", file=sys.stderr)
            time.sleep(args.interval)
    
    print("\n\nCollection complete!")
    
    # Calculate statistics
    stats = monitor.get_statistics()
    
    # Print summary
    print("\n=== Performance Summary ===")
    print(f"Total samples: {stats.get('total_samples', 0)}")
    print(f"Duration: {stats.get('duration_seconds', 0):.1f} seconds")
    print(f"Average block production rate: {stats.get('avg_block_production_rate', 0):.2f} blocks/min")
    print(f"Average connected peers: {stats.get('avg_connected_peers', 0):.1f}")
    print(f"Average active validators: {stats.get('avg_validator_count', 0):.1f}")
    
    # Block delay/timing metrics (transaction processing time)
    if 'avg_block_delay_total_ms' in stats:
        print(f"\nBlock Processing Time (Transaction Time):")
        print(f"  Average total delay: {stats['avg_block_delay_total_ms']:.2f} ms")
        print(f"  Min delay: {stats.get('min_block_delay_total_ms', 0):.2f} ms")
        print(f"  Max delay: {stats.get('max_block_delay_total_ms', 0):.2f} ms")
        if 'avg_block_delay_observed_ms' in stats:
            print(f"  Average observation delay: {stats['avg_block_delay_observed_ms']:.2f} ms")
        if 'avg_block_delay_consensus_verification_ms' in stats:
            print(f"  Average consensus verification: {stats['avg_block_delay_consensus_verification_ms']:.2f} ms")
        if 'avg_block_delay_execution_ms' in stats:
            print(f"  Average execution verification: {stats['avg_block_delay_execution_ms']:.2f} ms")
    
    if 'avg_cpu_usage' in stats:
        print(f"\nAverage CPU usage: {stats['avg_cpu_usage']:.2f}")
    if 'avg_memory_usage_mb' in stats:
        print(f"Average memory usage: {stats['avg_memory_usage_mb']:.2f} MB")
    
    # Save outputs
    if args.output_csv:
        save_csv(monitor.metrics_history, args.output_csv)
    
    if args.output_json:
        save_json(monitor.metrics_history, stats, args.output_json)
    
    if not args.output_csv and not args.output_json:
        # Default output
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        csv_file = f"consensus_metrics_{timestamp}.csv"
        json_file = f"consensus_metrics_{timestamp}.json"
        save_csv(monitor.metrics_history, csv_file)
        save_json(monitor.metrics_history, stats, json_file)


if __name__ == '__main__':
    main()

