#!/usr/bin/env python3
"""
Script to extract and visualize performance metrics from result files.
Creates comparison graphs for native vs TEE execution across different validator counts.
"""

import json
import os
import csv
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend


def parse_filename(filename: str) -> Dict[str, str]:
    """Parse filename to extract configuration info."""
    # Format: {type}_v{validator_count}_n{node_count}_s{seconds_per_slot}_{timestamp}.json
    parts = filename.replace('.json', '').split('_')
    if len(parts) < 5:
        return {}
    
    return {
        'config_type': parts[0],  # native or tee
        'validator_count': parts[1].replace('v', ''),
        'node_count': parts[2].replace('n', ''),
        'seconds_per_slot': parts[3].replace('s', ''),
    }


def load_results(results_dir: Path) -> Dict[str, List[Dict]]:
    """Load all JSON result files and organize by execution type and total_validators."""
    data = defaultdict(list)
    
    for json_file in results_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                result = json.load(f)
            
            config = result.get('test_config', {})
            stats = result.get('statistics', {})
            
            config_type = config.get('config_type', 'unknown')
            total_validators = config.get('total_validators', 0)
            seconds_per_slot = config.get('seconds_per_slot', 0)
            
            # Only include 12s slot time results
            if config_type in ['native', 'tee'] and total_validators > 0 and seconds_per_slot == 12:
                data[config_type].append({
                    'total_validators': total_validators,
                    'validator_count': config.get('validator_count', 0),
                    'node_count': config.get('node_count', 0),
                    'seconds_per_slot': config.get('seconds_per_slot', 0),
                    'avg_propagation_delay_ms': stats.get('avg_propagation_delay_ms'),
                    'avg_block_delay_total_ms': stats.get('avg_block_delay_total_ms'),
                    'avg_block_verification_time_ms': stats.get('avg_block_verification_time_ms'),
                    'avg_block_acceptance_latency_ms': stats.get('avg_block_acceptance_latency_ms'),
                    'avg_block_production_rate': stats.get('avg_block_production_rate'),
                    'avg_attestation_count': stats.get('avg_attestation_count'),
                    'avg_cpu_usage': stats.get('avg_cpu_usage'),
                    'max_memory_usage': stats.get('max_memory_usage'),
                    'filename': json_file.name
                })
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
            continue
    
    return data


def aggregate_data(data: Dict[str, List[Dict]]) -> Dict[str, Dict[str, Dict[int, float]]]:
    """Aggregate data by total_validators, taking average if multiple runs exist.
    
    Returns: Dict[config_type][metric_name][total_validators] = value
    """
    aggregated = {
        'native': defaultdict(list),
        'tee': defaultdict(list)
    }
    
    for config_type in ['native', 'tee']:
        for entry in data.get(config_type, []):
            total_validators = entry['total_validators']
            
            if entry['avg_propagation_delay_ms'] is not None:
                aggregated[config_type]['propagation_delay'].append(
                    (total_validators, entry['avg_propagation_delay_ms'])
                )
            if entry['avg_block_delay_total_ms'] is not None:
                aggregated[config_type]['block_delay_total'].append(
                    (total_validators, entry['avg_block_delay_total_ms'])
                )
            if entry['avg_block_verification_time_ms'] is not None:
                aggregated[config_type]['block_verification_time'].append(
                    (total_validators, entry['avg_block_verification_time_ms'])
                )
            if entry['avg_block_acceptance_latency_ms'] is not None:
                aggregated[config_type]['block_acceptance_latency'].append(
                    (total_validators, entry['avg_block_acceptance_latency_ms'])
                )
            if entry['avg_block_production_rate'] is not None:
                aggregated[config_type]['block_production_rate'].append(
                    (total_validators, entry['avg_block_production_rate'])
                )
            if entry['avg_attestation_count'] is not None:
                aggregated[config_type]['attestation_count'].append(
                    (total_validators, entry['avg_attestation_count'])
                )
            if entry['avg_cpu_usage'] is not None:
                aggregated[config_type]['cpu_usage'].append(
                    (total_validators, entry['avg_cpu_usage'])
                )
            if entry['max_memory_usage'] is not None:
                aggregated[config_type]['memory_usage'].append(
                    (total_validators, entry['max_memory_usage'])
                )
    
    # Average values for same total_validators
    result = {
        'native': {},
        'tee': {}
    }
    
    for config_type in ['native', 'tee']:
        for metric_name in ['propagation_delay', 'block_delay_total', 
                           'block_verification_time', 'block_acceptance_latency',
                           'block_production_rate', 'attestation_count',
                           'cpu_usage', 'memory_usage']:
            if metric_name not in result[config_type]:
                result[config_type][metric_name] = {}
            
            # Group by total_validators
            by_validators = defaultdict(list)
            for validators, value in aggregated[config_type][metric_name]:
                by_validators[validators].append(value)
            
            # Average values
            for validators, values in by_validators.items():
                result[config_type][metric_name][validators] = sum(values) / len(values)
    
    return result


def create_graphs(data: Dict[str, Dict[str, Dict[int, float]]], output_dir: Path):
    """Create comparison graphs for each metric."""
    metrics = {
        'propagation_delay': {
            'title': 'Average Propagation Delay (12s slot)',
            'ylabel': 'Delay (ms)',
            'key': 'propagation_delay'
        },
        'block_delay_total': {
            'title': 'Average Block Delay Total (12s slot)',
            'ylabel': 'Delay (ms)',
            'key': 'block_delay_total'
        },
        'block_verification_time': {
            'title': 'Average Block Verification Time (12s slot)',
            'ylabel': 'Time (ms)',
            'key': 'block_verification_time'
        },
        'block_acceptance_latency': {
            'title': 'Average Block Acceptance Latency (12s slot)',
            'ylabel': 'Latency (ms)',
            'key': 'block_acceptance_latency'
        },
        'block_production_rate': {
            'title': 'Average Block Production Rate (12s slot)',
            'ylabel': 'Rate (blocks/second)',
            'key': 'block_production_rate'
        },
        'attestation_count': {
            'title': 'Average Attestation Count per Slot (12s slot)',
            'ylabel': 'Attestations per slot',
            'key': 'attestation_count'
        },
        'cpu_usage': {
            'title': 'Average CPU Usage (12s slot)',
            'ylabel': 'CPU Usage (%)',
            'key': 'cpu_usage'
        },
        'memory_usage': {
            'title': 'Maximum Memory Usage (12s slot)',
            'ylabel': 'Memory Usage (MB)',
            'key': 'memory_usage'
        }
    }
    
    for metric_name, metric_info in metrics.items():
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Extract data for native and tee
        native_data = data['native'].get(metric_info['key'], {})
        tee_data = data['tee'].get(metric_info['key'], {})
        
        if not native_data and not tee_data:
            print(f"No data available for {metric_name}")
            plt.close(fig)
            continue
        
        # Get all validator counts
        all_validators = set(native_data.keys()) | set(tee_data.keys())
        if not all_validators:
            print(f"No validator data for {metric_name}")
            plt.close(fig)
            continue
        
        sorted_validators = sorted(all_validators)
        
        # Extract values in order
        native_values = [native_data.get(v, None) for v in sorted_validators]
        tee_values = [tee_data.get(v, None) for v in sorted_validators]
        
        # Convert memory usage from bytes to MB if needed
        if metric_name == 'memory_usage':
            native_values = [v / (1024 * 1024) if v is not None else None for v in native_values]
            tee_values = [v / (1024 * 1024) if v is not None else None for v in tee_values]
        
        # Plot lines
        if any(v is not None for v in native_values):
            native_validators = [v for i, v in enumerate(sorted_validators) if native_values[i] is not None]
            native_vals = [v for v in native_values if v is not None]
            ax.plot(native_validators, native_vals, 'o-', label='Native', linewidth=2, markersize=8, color='#2E86AB')
        
        if any(v is not None for v in tee_values):
            tee_validators = [v for i, v in enumerate(sorted_validators) if tee_values[i] is not None]
            tee_vals = [v for v in tee_values if v is not None]
            ax.plot(tee_validators, tee_vals, 's-', label='TEE', linewidth=2, markersize=8, color='#A23B72')
        
        ax.set_xlabel('Total Validators', fontsize=12, fontweight='bold')
        ax.set_ylabel(metric_info['ylabel'], fontsize=12, fontweight='bold')
        ax.set_title(metric_info['title'], fontsize=14, fontweight='bold')
        ax.legend(fontsize=11, loc='best')
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.set_xlim(left=0)
        
        # Format y-axis to show values nicely
        ax.tick_params(axis='both', which='major', labelsize=10)
        
        plt.tight_layout()
        
        # Save figure
        output_file = output_dir / f"{metric_name}_comparison.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"Saved graph: {output_file}")
        plt.close(fig)


def export_to_csv(data: Dict[str, Dict[str, Dict[int, float]]], output_dir: Path):
    """Export aggregated data to CSV files."""
    for config_type in ['native', 'tee']:
        csv_file = output_dir / f"{config_type}_aggregated_data.csv"
        
        # Get all validator counts
        all_validators = set()
        for metric_data in data[config_type].values():
            all_validators.update(metric_data.keys())
        
        if not all_validators:
            continue
        
        sorted_validators = sorted(all_validators)
        
        # Write CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['total_validators', 
                           'avg_propagation_delay_ms',
                           'avg_block_delay_total_ms',
                           'avg_block_verification_time_ms',
                           'avg_block_acceptance_latency_ms',
                           'avg_block_production_rate',
                           'avg_attestation_count',
                           'avg_cpu_usage',
                           'max_memory_usage_bytes'])
            
            for validators in sorted_validators:
                row = [validators]
                for metric_name in ['propagation_delay', 'block_delay_total', 
                                   'block_verification_time', 'block_acceptance_latency',
                                   'block_production_rate', 'attestation_count',
                                   'cpu_usage', 'memory_usage']:
                    value = data[config_type].get(metric_name, {}).get(validators, '')
                    if isinstance(value, (int, float)):
                        if metric_name == 'block_production_rate':
                            row.append(f"{value:.6f}")
                        elif metric_name == 'attestation_count':
                            row.append(f"{value:.2f}")
                        elif metric_name == 'cpu_usage':
                            row.append(f"{value:.2f}")
                        elif metric_name == 'memory_usage':
                            row.append(f"{int(value)}")
                        else:
                            row.append(f"{value:.2f}")
                    else:
                        row.append('')
                writer.writerow(row)
        
        print(f"Exported CSV: {csv_file}")


def print_summary(data: Dict[str, Dict[str, Dict[int, float]]]):
    """Print a summary of the extracted data."""
    print("\n" + "="*80)
    print("DATA SUMMARY (12s slot time only)")
    print("="*80)
    
    for config_type in ['native', 'tee']:
        print(f"\n{config_type.upper()} Execution:")
        print("-" * 80)
        
        for metric_name in ['propagation_delay', 'block_delay_total', 
                           'block_verification_time', 'block_acceptance_latency',
                           'block_production_rate', 'attestation_count',
                           'cpu_usage', 'memory_usage']:
            metric_data = data[config_type].get(metric_name, {})
            if metric_data:
                print(f"\n  {metric_name.replace('_', ' ').title()}:")
                for validators in sorted(metric_data.keys()):
                    value = metric_data[validators]
                    if metric_name == 'block_production_rate':
                        print(f"    {validators} validators: {value:.6f} blocks/s")
                    elif metric_name == 'attestation_count':
                        print(f"    {validators} validators: {value:.2f} attestations/slot")
                    elif metric_name == 'cpu_usage':
                        print(f"    {validators} validators: {value:.2f}%")
                    elif metric_name == 'memory_usage':
                        print(f"    {validators} validators: {value / (1024 * 1024):.2f} MB")
                    else:
                        print(f"    {validators} validators: {value:.2f} ms")


def main():
    """Main function."""
    results_dir = Path('/home/azureuser/PoTE-lighthouse/results')
    output_dir = Path('/home/azureuser/PoTE-lighthouse/results/graphs')
    
    if not results_dir.exists():
        print(f"Results directory not found: {results_dir}")
        return
    
    output_dir.mkdir(exist_ok=True)
    
    print("Loading results from:", results_dir)
    raw_data = load_results(results_dir)
    
    print(f"\nFound {len(raw_data.get('native', []))} native results")
    print(f"Found {len(raw_data.get('tee', []))} TEE results")
    
    print("\nAggregating data...")
    aggregated_data = aggregate_data(raw_data)
    
    print_summary(aggregated_data)
    
    print("\nExporting data to CSV...")
    export_to_csv(aggregated_data, output_dir)
    
    print("\nGenerating graphs...")
    create_graphs(aggregated_data, output_dir)
    
    print("\n" + "="*80)
    print("Analysis complete!")
    print(f"  - Graphs saved to: {output_dir}")
    print(f"  - CSV files saved to: {output_dir}")
    print("="*80)


if __name__ == '__main__':
    main()

