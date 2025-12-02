#!/usr/bin/env python3
"""
Comprehensive performance testing script for comparing native PoS vs TEE consensus layers.
Automatically varies parameters and collects metrics for analysis.

Usage:
    python3 performance_test.py [options]

Options:
    --config-type TYPE     Run only 'native' or 'tee' (default: both)
    --validator-count N    Run only specific validator count (default: all)
    --node-count N         Run only specific node count (default: all)
    --slot-time N          Run only specific slot time in seconds (default: all)
    --duration N           Metrics collection duration in seconds (default: 300)
    --sample-interval N     Metrics sampling interval in seconds (default: 12)
    --help                 Show this help message
"""

import os
import argparse
import sys
import json
import csv
import time
import re
import subprocess
import requests
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import statistics
import threading

# Configuration
VALIDATOR_COUNTS = [1, 5, 10, 15]
NODE_COUNTS = [3, 5, 10, 15]
SECONDS_PER_SLOT = [6, 12, 24]
CONFIG_TYPES = ['native', 'tee']
CONFIG_FILES = {
    'native': 'kurtosis-config-native.yaml',
    'tee': 'kurtosis-config.yaml'
}
RESULTS_DIR = Path('results')
KURTOSIS_PACKAGE = 'github.com/dzobbe/PoTE-ethereum-package'
METRICS_COLLECTION_DURATION = 300  # 5 minutes of metrics collection
METRICS_SAMPLE_INTERVAL = 12  # Sample every 12 seconds
STABILIZATION_WAIT = 60  # Wait 60 seconds after kurtosis starts before collecting metrics
COMPLEX_BLOCKS_SCRIPT = 'generate_complex_blocks.py'  # Path to complex blocks generator


@dataclass
class TestConfig:
    """Configuration for a single test run"""
    config_type: str  # 'native' or 'tee'
    validator_count: int
    node_count: int
    seconds_per_slot: int
    total_validators: int  # validator_count * node_count


@dataclass
class MetricsSample:
    """Single metrics sample"""
    timestamp: float
    slot: Optional[int]
    epoch: Optional[int]
    head_slot: Optional[int]
    finalized_slot: Optional[int]
    sync_status: Optional[str]
    connected_peers: Optional[int]
    block_production_rate: Optional[float]
    attestation_count: Optional[int]
    attestation_pool_size: Optional[int]
    validator_count: Optional[int]
    active_validators: Optional[int]
    cpu_usage: Optional[float]
    memory_usage: Optional[float]
    network_bytes_received: Optional[int]
    network_bytes_sent: Optional[int]
    propagation_delay: Optional[float]
    finalization_progression: Optional[float]
    # New TEE-specific metrics
    block_acceptance_latency_ms: Optional[float]  # Time from slot start to block acceptance
    block_verification_time_ms: Optional[float]  # Time taken to verify block consensus
    block_execution_time_ms: Optional[float]  # Time taken to verify block with execution layer
    time_to_finality_seconds: Optional[float]  # Time from block creation to finalization
    block_delay_total_ms: Optional[float]  # Total delay from slot start to head


class ComplexBlocksGenerator:
    """Manages complex block generation during tests"""
    
    def __init__(self, rpc_port: Optional[int] = None, rate: float = 10, 
                 transactions: Optional[int] = None, duration: Optional[int] = None):
        self.rpc_port = rpc_port
        self.rate = rate
        self.transactions = transactions
        self.duration = duration
        self.process = None
        self.thread = None
    
    def start(self):
        """Start generating complex blocks in background"""
        if not self.rpc_port:
            print("⚠️  No RPC port provided, skipping complex block generation")
            return False
        
        if not os.path.exists(COMPLEX_BLOCKS_SCRIPT):
            print(f"⚠️  Complex blocks script not found: {COMPLEX_BLOCKS_SCRIPT}")
            return False
        
        rpc_url = f"http://127.0.0.1:{self.rpc_port}"
        
        # Build command
        cmd = ['python3', COMPLEX_BLOCKS_SCRIPT, '--rpc-url', rpc_url, '--rate', str(self.rate)]
        
        if self.duration:
            cmd.extend(['--duration', str(self.duration)])
        elif self.transactions:
            cmd.extend(['--transactions', str(self.transactions)])
        else:
            # Default: run for test duration + buffer
            if self.duration is None:
                cmd.extend(['--duration', str(METRICS_COLLECTION_DURATION + 120)])
        
        print(f"🚀 Starting complex block generator: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            print(f"✅ Complex block generator started (PID: {self.process.pid})")
            return True
        except Exception as e:
            print(f"❌ Failed to start complex block generator: {e}")
            return False
    
    def stop(self):
        """Stop the complex block generator"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=10)
                print("✅ Complex block generator stopped")
            except subprocess.TimeoutExpired:
                self.process.kill()
                print("⚠️  Force killed complex block generator")
            except Exception as e:
                print(f"⚠️  Error stopping complex block generator: {e}")
            finally:
                self.process = None


class KurtosisManager:
    """Manages Kurtosis operations"""
    
    @staticmethod
    def clean_all():
        """Clean all Kurtosis enclaves"""
        print("🧹 Cleaning all Kurtosis enclaves...")
        try:
            # Try ./kurtosis first, fallback to kurtosis
            kurtosis_cmd = './kurtosis' if os.path.exists('./kurtosis') else 'kurtosis'
            result = subprocess.run(
                [kurtosis_cmd, 'clean', '--all'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                print(f"⚠️  Warning: kurtosis clean returned {result.returncode}")
                print(result.stderr)
            else:
                print("✅ Kurtosis cleaned successfully")
            time.sleep(5)  # Give it time to clean up
        except subprocess.TimeoutExpired:
            print("⚠️  Warning: kurtosis clean timed out")
        except Exception as e:
            print(f"⚠️  Warning: Error cleaning kurtosis: {e}")
    
    @staticmethod
    def run(config_file: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """
        Run Kurtosis with the given config file.
        Returns (enclave_name, beacon_port, metrics_exporter_port)
        """
        print(f"🚀 Starting Kurtosis with {config_file}...")
        try:
            # Try ./kurtosis first, fallback to kurtosis
            kurtosis_cmd = './kurtosis' if os.path.exists('./kurtosis') else 'kurtosis'
            result = subprocess.run(
                [kurtosis_cmd, 'run', KURTOSIS_PACKAGE,
                 '--args-file', config_file,
                 '--image-download', 'always'],
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            if result.returncode != 0:
                print(f"❌ Kurtosis run failed with return code {result.returncode}")
                print(result.stderr)
                return None, None, None
            
            # Extract enclave name from output
            enclave_match = re.search(r'Enclave name: (\S+)', result.stdout)
            if not enclave_match:
                # Try alternative pattern
                enclave_match = re.search(r'Created enclave (\S+)', result.stdout)
            
            enclave = enclave_match.group(1) if enclave_match else None
            
            # Extract beacon port
            beacon_port = KurtosisManager._extract_beacon_port(result.stdout)
            
            if not beacon_port:
                # Try inspecting the enclave
                if enclave:
                    beacon_port = KurtosisManager._get_beacon_port_from_inspect(enclave)
            
            # Extract metrics exporter port
            metrics_exporter_port = KurtosisManager._extract_metrics_exporter_port(result.stdout)
            
            print(f"✅ Kurtosis started successfully")
            if enclave:
                print(f"   Enclave: {enclave}")
            if beacon_port:
                print(f"   Beacon port: {beacon_port}")
            else:
                print("   ⚠️  Could not determine beacon port")
            if metrics_exporter_port:
                print(f"   Metrics exporter port: {metrics_exporter_port}")
            
            return enclave, beacon_port, metrics_exporter_port
            
        except subprocess.TimeoutExpired:
            print("❌ Kurtosis run timed out")
            return None, None, None
        except Exception as e:
            print(f"❌ Error running Kurtosis: {e}")
            return None, None, None
    
    @staticmethod
    def _extract_beacon_port(output: str) -> Optional[int]:
        """Extract beacon port from kurtosis run output"""
        # Look for patterns like: http: 4000/tcp -> http://127.0.0.1:32784
        # or cl-1-lighthouse-geth with http port mapping
        patterns = [
            r'cl-1-lighthouse[^\n]*http[^\n]*->\s*http://127\.0\.0\.1:(\d+)',
            r'http:\s*4000/tcp\s*->\s*http://127\.0\.0\.1:(\d+)',
            r'beacon[^\n]*http[^\n]*->\s*http://127\.0\.0\.1:(\d+)',
            r'http://127\.0\.0\.1:(\d+).*4000',  # Reverse pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        
        # Try to find any http://127.0.0.1:PORT near "4000" or "lighthouse"
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if '4000' in line or 'lighthouse' in line.lower():
                # Check this line and next few lines for port
                for check_line in lines[i:i+5]:
                    port_match = re.search(r'http://127\.0\.0\.1:(\d+)', check_line)
                    if port_match:
                        try:
                            return int(port_match.group(1))
                        except ValueError:
                            continue
        
        return None
    
    @staticmethod
    def _extract_metrics_exporter_port(output: str) -> Optional[int]:
        """Extract metrics exporter port from kurtosis run output"""
        # Look for patterns like: ethereum-metrics-exporter-3-lighthouse-geth http: 9090/tcp -> http://127.0.0.1:32795
        patterns = [
            r'ethereum-metrics-exporter[^\n]*http[^\n]*->\s*http://127\.0\.0\.1:(\d+)',
            r'http:\s*9090/tcp\s*->\s*http://127\.0\.0\.1:(\d+)',
            r'metrics-exporter[^\n]*http[^\n]*->\s*http://127\.0\.0\.1:(\d+)',
            r'http://127\.0\.0\.1:(\d+).*9090',  # Reverse pattern
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output)
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        
        # Try to find any http://127.0.0.1:PORT near "9090" or "metrics"
        lines = output.split('\n')
        for i, line in enumerate(lines):
            if '9090' in line or 'metrics-exporter' in line.lower() or 'metrics' in line.lower():
                # Check this line and next few lines for port
                for check_line in lines[i:i+5]:
                    port_match = re.search(r'http://127\.0\.0\.1:(\d+)', check_line)
                    if port_match:
                        try:
                            return int(port_match.group(1))
                        except ValueError:
                            continue
        
        return None
    
    @staticmethod
    def _get_beacon_port_from_inspect(enclave: str) -> Optional[int]:
        """Get beacon port by inspecting the enclave"""
        try:
            # Try ./kurtosis first, fallback to kurtosis
            kurtosis_cmd = './kurtosis' if os.path.exists('./kurtosis') else 'kurtosis'
            result = subprocess.run(
                [kurtosis_cmd, 'enclave', 'inspect', enclave],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Look for http URL with port 4000 (beacon HTTP port)
                # Pattern: grep "http:" | grep "4000" | extract URL
                lines = result.stdout.split('\n')
                for line in lines:
                    if '4000' in line and 'http://' in line:
                        # Extract URL
                        url_match = re.search(r'http://127\.0\.0\.1:(\d+)', line)
                        if url_match:
                            try:
                                return int(url_match.group(1))
                            except ValueError:
                                continue
                
                # Fallback to general extraction
                return KurtosisManager._extract_beacon_port(result.stdout)
        except Exception as e:
            print(f"⚠️  Could not inspect enclave: {e}")
        
        return None
    
    @staticmethod
    def _find_rpc_port_from_docker() -> Optional[int]:
        """Find RPC port from docker ps (fallback method)"""
        try:
            result = subprocess.run(
                ['docker', 'ps', '--format', '{{.Names}}\t{{.Ports}}'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                first_match = None
                
                for line in lines:
                    if 'el-' in line and 'geth-lighthouse' in line and '8545/tcp' in line:
                        pattern = r'0\.0\.0\.0:(\d+)->8545/tcp'
                        match = re.search(pattern, line)
                        if match:
                            port = int(match.group(1))
                            if 'el-1-' in line:
                                return port
                            if first_match is None:
                                first_match = port
                
                if first_match is not None:
                    return first_match
        except Exception:
            pass
        
        return None


class ConfigModifier:
    """Modifies Kurtosis config files"""
    
    @staticmethod
    def modify_config(config_file: str, validator_count: int, 
                     node_count: int, seconds_per_slot: int):
        """Modify the config file with new parameters"""
        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            # Modify parameters
            if 'participants' in config and len(config['participants']) > 0:
                config['participants'][0]['validator_count'] = validator_count
                config['participants'][0]['count'] = node_count
            
            if 'network_params' in config:
                config['network_params']['seconds_per_slot'] = seconds_per_slot
            
            # Write back with proper formatting
            with open(config_file, 'w') as f:
                # Use default_flow_style=False to preserve block style
                # Use allow_unicode=True for better compatibility
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, 
                         allow_unicode=True, width=1000)
            
            print(f"   ✓ Modified {config_file}: validators={validator_count}, nodes={node_count}, slot_time={seconds_per_slot}s")
            return True
            
        except Exception as e:
            print(f"❌ Error modifying config: {e}")
            import traceback
            traceback.print_exc()
            return False


class MetricsCollector:
    """Collects metrics from the beacon API"""
    
    def __init__(self, beacon_url: str, seconds_per_slot: int = 12, metrics_exporter_port: Optional[int] = None):
        self.beacon_url = beacon_url.rstrip('/')
        self.session = requests.Session()
        self.session.timeout = 5
        self.seconds_per_slot = seconds_per_slot
        self.metrics_exporter_port = metrics_exporter_port
        # Track when blocks were first seen by slot
        self.block_first_seen: Dict[int, float] = {}
        # Track when slots started (estimated)
        self.slot_start_times: Dict[int, float] = {}
        # Track when blocks were created (by slot) for finality calculation
        self.block_creation_times: Dict[int, float] = {}
    
    def collect_sample(self) -> MetricsSample:
        """Collect a single metrics sample"""
        sample = MetricsSample(
            timestamp=time.time(),
            slot=None,
            epoch=None,
            head_slot=None,
            finalized_slot=None,
            sync_status=None,
            connected_peers=None,
            block_production_rate=None,
            attestation_count=None,
            attestation_pool_size=None,
            validator_count=None,
            active_validators=None,
            cpu_usage=None,
            memory_usage=None,
            network_bytes_received=None,
            network_bytes_sent=None,
            propagation_delay=None,
            finalization_progression=None,
            block_acceptance_latency_ms=None,
            block_verification_time_ms=None,
            block_execution_time_ms=None,
            time_to_finality_seconds=None,
            block_delay_total_ms=None
        )
        
        try:
            # Get head block
            head_data = self._get_head_block()
            if head_data:
                sample.slot = head_data.get('slot')
                sample.head_slot = head_data.get('slot')
                sample.epoch = head_data.get('slot', 0) // 32 if head_data.get('slot') else None
            
            # Get finality checkpoints
            finalized = self._get_finalized_checkpoint()
            if finalized:
                sample.finalized_slot = finalized
            
            # Calculate finalization progression
            if sample.head_slot and sample.finalized_slot:
                sample.finalization_progression = (sample.finalized_slot / sample.head_slot) * 100 if sample.head_slot > 0 else 0
            
            # Get sync status
            sample.sync_status = self._get_sync_status()
            
            # Get peers
            sample.connected_peers = self._get_peer_count()
            
            # Get attestation pool
            attestations = self._get_attestation_pool()
            if attestations is not None:
                sample.attestation_pool_size = len(attestations)
                sample.attestation_count = len(attestations)
            
            # Get validators
            validators_data = self._get_validators()
            if validators_data:
                sample.validator_count = validators_data.get('total')
                sample.active_validators = validators_data.get('active')
            
            # Get health metrics (CPU, memory, network)
            health = self._get_health()
            if health:
                sample.cpu_usage = health.get('cpu_usage')
                sample.memory_usage = health.get('memory_usage')
                sample.network_bytes_received = health.get('network_bytes_received')
                sample.network_bytes_sent = health.get('network_bytes_sent')
            
            # Get Prometheus metrics for block delays and verification times
            prometheus_metrics = self._get_prometheus_metrics()
            if prometheus_metrics:
                sample.block_verification_time_ms = prometheus_metrics.get('consensus_verification_time_ms')
                sample.block_execution_time_ms = prometheus_metrics.get('execution_time_ms')
                sample.block_delay_total_ms = prometheus_metrics.get('block_delay_total_ms')
            
            # Calculate block acceptance latency and propagation delay
            if sample.slot is not None:
                current_time = sample.timestamp
                # Track when we first see a slot
                if sample.slot not in self.block_first_seen:
                    self.block_first_seen[sample.slot] = current_time
                    # Estimate slot start: use the first time we see the slot as a reference
                    # and estimate backwards. For a more accurate calculation, we assume
                    # the slot started at the beginning of the current slot period
                    # Calculate which slot period we're in based on current time
                    slot_period = int(current_time / self.seconds_per_slot)
                    estimated_slot_start = slot_period * self.seconds_per_slot
                    self.slot_start_times[sample.slot] = estimated_slot_start
                
                # Calculate propagation delay (time from slot start to when we first saw the block)
                if sample.slot in self.slot_start_times and sample.slot in self.block_first_seen:
                    slot_start = self.slot_start_times[sample.slot]
                    first_seen = self.block_first_seen[sample.slot]
                    # Propagation delay: time from slot start to first observation
                    delay = (first_seen - slot_start) * 1000  # Convert to ms
                    if delay >= 0:  # Only record positive delays
                        sample.propagation_delay = delay
                    # Block acceptance latency: time from slot start to current observation
                    latency = (current_time - slot_start) * 1000  # Convert to ms
                    if latency >= 0:
                        sample.block_acceptance_latency_ms = latency
            
            # Track block creation times for finality calculation
            if sample.slot is not None and sample.slot not in self.block_creation_times:
                # Use slot start time if available, otherwise use current time
                if sample.slot in self.slot_start_times:
                    self.block_creation_times[sample.slot] = self.slot_start_times[sample.slot]
                else:
                    self.block_creation_times[sample.slot] = sample.timestamp
            
            # Calculate time to finality
            # Finalization requires 2 epochs (64 slots in mainnet, 32 slots per epoch)
            if sample.head_slot and sample.finalized_slot is not None and sample.finalized_slot > 0:
                # Check if we have the creation time for the finalized slot
                if sample.finalized_slot in self.block_creation_times:
                    block_creation_time = self.block_creation_times[sample.finalized_slot]
                    time_to_finality = sample.timestamp - block_creation_time
                    if time_to_finality >= 0:
                        sample.time_to_finality_seconds = time_to_finality
                elif sample.finalized_slot in self.slot_start_times:
                    # Fallback to slot start time
                    finalized_slot_start = self.slot_start_times[sample.finalized_slot]
                    time_to_finality = sample.timestamp - finalized_slot_start
                    if time_to_finality >= 0:
                        sample.time_to_finality_seconds = time_to_finality
            
        except Exception as e:
            print(f"⚠️  Error collecting metrics: {e}")
        
        return sample
    
    def _get_head_block(self) -> Optional[Dict]:
        """Get head block information"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/beacon/headers/head")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and 'header' in data['data']:
                    message = data['data']['header'].get('message', {})
                    return {
                        'slot': int(message.get('slot', 0)) if message.get('slot') else None
                    }
        except Exception:
            pass
        return None
    
    def _get_finalized_checkpoint(self) -> Optional[int]:
        """Get finalized checkpoint slot"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/beacon/states/head/finality_checkpoints")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and 'finalized' in data['data']:
                    # Get the block at finalized root to get slot
                    finalized_root = data['data']['finalized'].get('root')
                    if finalized_root:
                        # Try to get block by root
                        block_response = self.session.get(
                            f"{self.beacon_url}/eth/v1/beacon/blocks/{finalized_root}"
                        )
                        if block_response.status_code == 200:
                            block_data = block_response.json()
                            if 'data' in block_data and 'message' in block_data['data']:
                                return int(block_data['data']['message'].get('slot', 0))
        except Exception:
            pass
        
        # Fallback: estimate from epoch
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/beacon/states/head/finality_checkpoints")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and 'finalized' in data['data']:
                    # Estimate slot from epoch (32 slots per epoch)
                    epoch = data['data']['finalized'].get('epoch')
                    if epoch:
                        return int(epoch) * 32
        except Exception:
            pass
        
        return None
    
    def _get_sync_status(self) -> Optional[str]:
        """Get sync status"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/node/syncing")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    if data['data'].get('is_syncing'):
                        return 'syncing'
                    else:
                        return 'synced'
        except Exception:
            pass
        return None
    
    def _get_peer_count(self) -> Optional[int]:
        """Get connected peer count"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/node/peers")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    return len(data['data'])
        except Exception:
            pass
        
        # Try lighthouse-specific endpoint
        try:
            response = self.session.get(f"{self.beacon_url}/lighthouse/peers")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return len(data)
        except Exception:
            pass
        
        return None
    
    def _get_attestation_pool(self) -> Optional[List]:
        """Get attestation pool"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/beacon/pool/attestations")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    return data['data']
        except Exception:
            pass
        return None
    
    def _get_validators(self) -> Optional[Dict]:
        """Get validator information"""
        try:
            response = self.session.get(f"{self.beacon_url}/eth/v1/beacon/states/head/validators")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    validators = data['data']
                    active = sum(1 for v in validators if v.get('status', '').startswith('active'))
                    return {
                        'total': len(validators),
                        'active': active
                    }
        except Exception:
            pass
        return None
    
    def _get_health(self) -> Optional[Dict]:
        """Get health metrics (CPU, memory, network)"""
        try:
            response = self.session.get(f"{self.beacon_url}/lighthouse/health")
            if response.status_code == 200:
                data = response.json()
                if 'data' in data:
                    d = data['data']
                    return {
                        'cpu_usage': d.get('sys_loadavg_1'),
                        'memory_usage': d.get('pid_mem_resident_set_size'),
                        'network_bytes_received': d.get('network_node_bytes_total_received'),
                        'network_bytes_sent': d.get('network_node_bytes_total_transmit')
                    }
        except Exception:
            pass
        return None
    
    def _get_prometheus_metrics(self) -> Optional[Dict]:
        """Get Prometheus metrics for block delays and verification times from metrics exporter"""
        metrics = {}
        
        # Try multiple endpoints:
        # 1. Metrics exporter (typically on port 9090, but mapped to different local port)
        # 2. Direct beacon API /metrics endpoint
        # 3. Try to extract metrics exporter port from beacon_url if possible
        
        # Build list of endpoints to try
        endpoints_to_try = []
        
        # First priority: use the metrics exporter port if we have it
        if self.metrics_exporter_port:
            endpoints_to_try.append(f"http://127.0.0.1:{self.metrics_exporter_port}/metrics")
        
        # Extract base URL and port from beacon_url
        # beacon_url is like http://127.0.0.1:PORT
        base_url_match = re.match(r'(http://127\.0\.0\.1:)(\d+)', self.beacon_url)
        if base_url_match:
            base = base_url_match.group(1)
            beacon_port = int(base_url_match.group(2))
            # Try metrics exporter on common ports (9090 is typical, but mapped differently)
            metrics_ports_to_try = [
                9090,  # Default metrics exporter port
                beacon_port + 1,  # Sometimes next to beacon port
                beacon_port - 1,
            ]
            endpoints_to_try.extend([f"{base}{port}/metrics" for port in metrics_ports_to_try])
        else:
            # Fallback: just try 9090
            endpoints_to_try.append("http://127.0.0.1:9090/metrics")
        
        # Also try direct beacon API metrics endpoint
        endpoints_to_try.append(f"{self.beacon_url}/metrics")
        
        for endpoint in endpoints_to_try:
            try:
                response = self.session.get(endpoint, timeout=2)
                if response.status_code == 200:
                    metrics_text = response.text
                    
                    # Check if we got valid Prometheus format (should have some metrics)
                    if not metrics_text or len(metrics_text) < 100:
                        continue
                    
                    # Parse Prometheus format metrics
                    # Prometheus format can be: metric_name{labels} value or metric_name value
                    # Values can be integers or floats
                    
                    # beacon_block_delay_consensus_verification_time (IntGauge, milliseconds)
                    patterns = [
                        r'beacon_block_delay_consensus_verification_time\{[^}]*\}\s+([\d.]+)',
                        r'beacon_block_delay_consensus_verification_time\s+([\d.]+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, metrics_text)
                        if match:
                            metrics['consensus_verification_time_ms'] = float(match.group(1))
                            break
                    
                    # beacon_block_delay_execution_time
                    patterns = [
                        r'beacon_block_delay_execution_time\{[^}]*\}\s+([\d.]+)',
                        r'beacon_block_delay_execution_time\s+([\d.]+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, metrics_text)
                        if match:
                            metrics['execution_time_ms'] = float(match.group(1))
                            break
                    
                    # beacon_block_delay_total
                    patterns = [
                        r'beacon_block_delay_total\{[^}]*\}\s+([\d.]+)',
                        r'beacon_block_delay_total\s+([\d.]+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, metrics_text)
                        if match:
                            metrics['block_delay_total_ms'] = float(match.group(1))
                            break
                    
                    # beacon_block_delay_gossip_verification
                    patterns = [
                        r'beacon_block_delay_gossip_verification\{[^}]*\}\s+([\d.]+)',
                        r'beacon_block_delay_gossip_verification\s+([\d.]+)',
                    ]
                    for pattern in patterns:
                        match = re.search(pattern, metrics_text)
                        if match:
                            metrics['gossip_verification_ms'] = float(match.group(1))
                            break
                    
                    # If we found any metrics, return them
                    if metrics:
                        return metrics
            except Exception:
                # Continue to next endpoint
                continue
        
        return None if not metrics else metrics
    
    def collect_metrics_over_time(self, duration: int, interval: int) -> List[MetricsSample]:
        """Collect metrics over a period of time"""
        samples = []
        start_time = time.time()
        end_time = start_time + duration
        
        print(f"📊 Collecting metrics for {duration} seconds (sampling every {interval}s)...")
        
        last_slot = None
        last_timestamp = None
        
        while time.time() < end_time:
            sample = self.collect_sample()
            
            # Calculate block production rate
            if last_slot is not None and last_timestamp is not None:
                if sample.slot and sample.slot > last_slot:
                    time_diff = sample.timestamp - last_timestamp
                    slot_diff = sample.slot - last_slot
                    if time_diff > 0:
                        sample.block_production_rate = slot_diff / time_diff
            
            samples.append(sample)
            last_slot = sample.slot
            last_timestamp = sample.timestamp
            
            # Progress indicator
            elapsed = time.time() - start_time
            remaining = duration - elapsed
            if len(samples) % 5 == 0:
                print(f"   Collected {len(samples)} samples ({elapsed:.0f}s/{duration}s)")
            
            time.sleep(interval)
        
        print(f"✅ Collected {len(samples)} metrics samples")
        return samples


class ResultsManager:
    """Manages saving test results"""
    
    @staticmethod
    def save_results(test_config: TestConfig, samples: List[MetricsSample], 
                    results_dir: Path):
        """Save results to CSV and JSON"""
        # Create results directory
        results_dir.mkdir(exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"{test_config.config_type}_v{test_config.validator_count}_n{test_config.node_count}_s{test_config.seconds_per_slot}_{timestamp}"
        
        # Calculate statistics
        stats = ResultsManager._calculate_statistics(samples)
        
        # Save JSON
        json_path = results_dir / f"{base_name}.json"
        json_data = {
            'test_config': asdict(test_config),
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_samples': len(samples),
                'duration_seconds': samples[-1].timestamp - samples[0].timestamp if len(samples) > 1 else 0
            },
            'statistics': stats,
            'metrics': [asdict(s) for s in samples]
        }
        
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2)
        
        print(f"   💾 Saved JSON: {json_path}")
        
        # Save CSV
        csv_path = results_dir / f"{base_name}.csv"
        if samples:
            fieldnames = list(asdict(samples[0]).keys())
            with open(csv_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for sample in samples:
                    writer.writerow(asdict(sample))
        
        print(f"   💾 Saved CSV: {csv_path}")
        
        return json_path, csv_path
    
    @staticmethod
    def _calculate_statistics(samples: List[MetricsSample]) -> Dict:
        """Calculate statistics from samples"""
        if not samples:
            return {}
        
        stats = {}
        
        # Extract numeric values
        block_rates = [s.block_production_rate for s in samples if s.block_production_rate is not None]
        peer_counts = [s.connected_peers for s in samples if s.connected_peers is not None]
        attestation_counts = [s.attestation_count for s in samples if s.attestation_count is not None]
        validator_counts = [s.validator_count for s in samples if s.validator_count is not None]
        finalization_progressions = [s.finalization_progression for s in samples if s.finalization_progression is not None]
        cpu_usages = [s.cpu_usage for s in samples if s.cpu_usage is not None]
        memory_usages = [s.memory_usage for s in samples if s.memory_usage is not None]
        
        # New TEE-specific metrics
        block_acceptance_latencies = [s.block_acceptance_latency_ms for s in samples if s.block_acceptance_latency_ms is not None]
        block_verification_times = [s.block_verification_time_ms for s in samples if s.block_verification_time_ms is not None]
        block_execution_times = [s.block_execution_time_ms for s in samples if s.block_execution_time_ms is not None]
        time_to_finalities = [s.time_to_finality_seconds for s in samples if s.time_to_finality_seconds is not None]
        block_delay_totals = [s.block_delay_total_ms for s in samples if s.block_delay_total_ms is not None]
        propagation_delays = [s.propagation_delay for s in samples if s.propagation_delay is not None]
        
        if block_rates:
            stats['avg_block_production_rate'] = statistics.mean(block_rates)
            stats['max_block_production_rate'] = max(block_rates)
            stats['min_block_production_rate'] = min(block_rates)
        
        if peer_counts:
            stats['avg_connected_peers'] = statistics.mean(peer_counts)
            stats['max_connected_peers'] = max(peer_counts)
            stats['min_connected_peers'] = min(peer_counts)
        
        if attestation_counts:
            stats['avg_attestation_count'] = statistics.mean(attestation_counts)
            stats['max_attestation_count'] = max(attestation_counts)
            stats['min_attestation_count'] = min(attestation_counts)
        
        if validator_counts:
            stats['avg_validator_count'] = statistics.mean(validator_counts)
        
        if finalization_progressions:
            stats['avg_finalization_progression'] = statistics.mean(finalization_progressions)
        
        if cpu_usages:
            stats['avg_cpu_usage'] = statistics.mean(cpu_usages)
            stats['max_cpu_usage'] = max(cpu_usages)
        
        if memory_usages:
            stats['avg_memory_usage'] = statistics.mean(memory_usages)
            stats['max_memory_usage'] = max(memory_usages)
        
        # TEE-specific metrics statistics
        if block_acceptance_latencies:
            stats['avg_block_acceptance_latency_ms'] = statistics.mean(block_acceptance_latencies)
            stats['max_block_acceptance_latency_ms'] = max(block_acceptance_latencies)
            stats['min_block_acceptance_latency_ms'] = min(block_acceptance_latencies)
        
        if block_verification_times:
            stats['avg_block_verification_time_ms'] = statistics.mean(block_verification_times)
            stats['max_block_verification_time_ms'] = max(block_verification_times)
            stats['min_block_verification_time_ms'] = min(block_verification_times)
        
        if block_execution_times:
            stats['avg_block_execution_time_ms'] = statistics.mean(block_execution_times)
            stats['max_block_execution_time_ms'] = max(block_execution_times)
            stats['min_block_execution_time_ms'] = min(block_execution_times)
        
        if time_to_finalities:
            stats['avg_time_to_finality_seconds'] = statistics.mean(time_to_finalities)
            stats['max_time_to_finality_seconds'] = max(time_to_finalities)
            stats['min_time_to_finality_seconds'] = min(time_to_finalities)
        
        if block_delay_totals:
            stats['avg_block_delay_total_ms'] = statistics.mean(block_delay_totals)
            stats['max_block_delay_total_ms'] = max(block_delay_totals)
            stats['min_block_delay_total_ms'] = min(block_delay_totals)
        
        if propagation_delays:
            stats['avg_propagation_delay_ms'] = statistics.mean(propagation_delays)
            stats['max_propagation_delay_ms'] = max(propagation_delays)
            stats['min_propagation_delay_ms'] = min(propagation_delays)
        
        stats['total_samples'] = len(samples)
        
        return stats


def run_test(test_config: TestConfig, duration: int = None, interval: int = None, 
             generate_complex_blocks: bool = False, tx_rate: float = 10) -> bool:
    """Run a single test configuration"""
    print("\n" + "="*80)
    print(f"🧪 Running test: {test_config.config_type.upper()}")
    print(f"   Validators per node: {test_config.validator_count}")
    print(f"   Number of nodes: {test_config.node_count}")
    print(f"   Total validators: {test_config.total_validators}")
    print(f"   Seconds per slot: {test_config.seconds_per_slot}")
    print("="*80)
    
    # Get config file
    config_file = CONFIG_FILES[test_config.config_type]
    if not os.path.exists(config_file):
        print(f"❌ Config file not found: {config_file}")
        return False
    
    # Modify config
    if not ConfigModifier.modify_config(
        config_file, 
        test_config.validator_count,
        test_config.node_count,
        test_config.seconds_per_slot
    ):
        return False
    
    # Clean Kurtosis
    KurtosisManager.clean_all()
    
    # Run Kurtosis
    enclave, beacon_port, metrics_exporter_port = KurtosisManager.run(config_file)
    if not beacon_port:
        print("❌ Could not determine beacon port, skipping test")
        return False
    
    # Find RPC port for complex block generation
    rpc_port = None
    if generate_complex_blocks:
        # Try to find RPC port from docker
        rpc_port = KurtosisManager._find_rpc_port_from_docker()
        if rpc_port:
            print(f"🔍 Found RPC port: {rpc_port}")
        else:
            print("⚠️  Could not auto-detect RPC port for complex block generation")
            print("   Complex blocks will not be generated")
            generate_complex_blocks = False
    
    # Wait for stabilization and verify beacon API is ready
    print(f"⏳ Waiting {STABILIZATION_WAIT} seconds for network to stabilize...")
    time.sleep(STABILIZATION_WAIT)
    
    # Start complex block generator if requested
    block_generator = None
    if generate_complex_blocks and rpc_port:
        block_generator = ComplexBlocksGenerator(
            rpc_port=rpc_port,
            rate=tx_rate,
            duration=duration if duration else METRICS_COLLECTION_DURATION + 60
        )
        if not block_generator.start():
            print("⚠️  Failed to start complex block generator, continuing without it")
            block_generator = None
        else:
            # Give it a moment to start sending transactions
            time.sleep(5)
    
    # Collect metrics
    beacon_url = f"http://127.0.0.1:{beacon_port}"
    
    # Wait for beacon API to be ready (with retries)
    print("🔍 Verifying beacon API is ready...")
    max_retries = 10
    retry_delay = 5
    api_ready = False
    
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{beacon_url}/eth/v1/node/version", timeout=5)
            if response.status_code == 200:
                api_ready = True
                print("✅ Beacon API is ready")
                break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"   Attempt {attempt + 1}/{max_retries}: API not ready yet, waiting {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"⚠️  Warning: Beacon API may not be fully ready: {e}")
    
    if not api_ready:
        print("⚠️  Warning: Proceeding with metrics collection despite API readiness check failure")
    
    collector = MetricsCollector(beacon_url, seconds_per_slot=test_config.seconds_per_slot, 
                                 metrics_exporter_port=metrics_exporter_port)
    
    # Use provided duration/interval or defaults
    test_duration = duration if duration is not None else METRICS_COLLECTION_DURATION
    test_interval = interval if interval is not None else METRICS_SAMPLE_INTERVAL
    
    samples = collector.collect_metrics_over_time(
        test_duration,
        test_interval
    )
    
    if not samples:
        print("❌ No metrics collected, skipping save")
        return False
    
    # Stop complex block generator if running
    if block_generator:
        block_generator.stop()
    
    # Save results
    ResultsManager.save_results(test_config, samples, RESULTS_DIR)
    
    print("✅ Test completed successfully")
    return True


def main():
    """Main test execution"""
    parser = argparse.ArgumentParser(
        description='PoTE Lighthouse Performance Testing Suite',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--config-type', choices=['native', 'tee'],
                       help='Run only specific config type (default: both)')
    parser.add_argument('--validator-count', type=int,
                       help='Run only specific validator count per node')
    parser.add_argument('--node-count', type=int,
                       help='Run only specific node count')
    parser.add_argument('--slot-time', type=int,
                       help='Run only specific slot time in seconds')
    parser.add_argument('--duration', type=int, default=METRICS_COLLECTION_DURATION,
                       help=f'Metrics collection duration in seconds (default: {METRICS_COLLECTION_DURATION})')
    parser.add_argument('--sample-interval', type=int, default=METRICS_SAMPLE_INTERVAL,
                       help=f'Metrics sampling interval in seconds (default: {METRICS_SAMPLE_INTERVAL})')
    parser.add_argument('--generate-complex-blocks', action='store_true',
                       help='Generate complex blocks (transactions) during test')
    parser.add_argument('--tx-rate', type=float, default=10.0,
                       help='Transaction rate per second for complex block generation (default: 10)')
    
    args = parser.parse_args()
    
    # Get duration and interval from args
    test_duration = args.duration
    test_interval = args.sample_interval
    
    # Filter configurations based on arguments
    config_types = [args.config_type] if args.config_type else CONFIG_TYPES
    validator_counts = [args.validator_count] if args.validator_count else VALIDATOR_COUNTS
    node_counts = [args.node_count] if args.node_count else NODE_COUNTS
    seconds_per_slot = [args.slot_time] if args.slot_time else SECONDS_PER_SLOT
    
    print("="*80)
    print("🚀 PoTE Lighthouse Performance Testing Suite")
    print("="*80)
    print(f"Test configurations:")
    print(f"  Validator counts per node: {validator_counts}")
    print(f"  Node counts: {node_counts}")
    print(f"  Seconds per slot: {seconds_per_slot}")
    print(f"  Config types: {config_types}")
    total_tests = len(validator_counts) * len(node_counts) * len(seconds_per_slot) * len(config_types)
    print(f"  Total test runs: {total_tests}")
    print(f"  Metrics collection: {test_duration}s (sampling every {test_interval}s)")
    print("="*80)
    
    # Create results directory
    RESULTS_DIR.mkdir(exist_ok=True)
    
    # Generate all test configurations
    test_configs = []
    for config_type in config_types:
        for validator_count in validator_counts:
            for node_count in node_counts:
                for seconds_per_slot_val in seconds_per_slot:
                    test_configs.append(TestConfig(
                        config_type=config_type,
                        validator_count=validator_count,
                        node_count=node_count,
                        seconds_per_slot=seconds_per_slot_val,
                        total_validators=validator_count * node_count
                    ))
    
    if not test_configs:
        print("❌ No test configurations generated. Check your filter arguments.")
        return
    
    print(f"\n📋 Generated {len(test_configs)} test configurations")
    print("Starting test execution...\n")
    
    # Run tests
    successful = 0
    failed = 0
    
    for i, test_config in enumerate(test_configs, 1):
        print(f"\n[{i}/{len(test_configs)}] ", end="")
        if run_test(test_config, test_duration, test_interval, 
                   generate_complex_blocks=args.generate_complex_blocks,
                   tx_rate=args.tx_rate):
            successful += 1
        else:
            failed += 1
        
        # Clean up before next test
        KurtosisManager.clean_all()
    
    # Summary
    print("\n" + "="*80)
    print("📊 Test Suite Summary")
    print("="*80)
    print(f"Total tests: {len(test_configs)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Results saved in: {RESULTS_DIR.absolute()}")
    print("="*80)


if __name__ == "__main__":
    main()

