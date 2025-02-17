#!/usr/bin/env python3
import argparse
import glob
import os
import re
from typing import Dict, List, Tuple

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

def get_implementation_name(variant: int) -> str:
    """Convert implementation variant number to readable name"""
    variants = {
        1: "Imperative",
        2: "Virtual Threads",
        3: "Reactive"
    }
    return variants.get(variant, f"Unknown ({variant})")

def get_test_name(test: int) -> str:
    """Convert test number to readable name"""
    tests = {
        1: "HTTP Status (5s)",
        2: "CPU Prime",
        3: "Database I/O"
    }
    return tests.get(test, f"Test {test}")

def extract_metadata(filename: str) -> Dict[str, any]:
    """Extract metadata from directory name pattern cnc<concurrency>_<test>-<variant>"""
    # Get directory name
    dir_name = os.path.basename(os.path.dirname(filename))
    
    # Extract concurrency, test and variant from directory name
    dir_pattern = r"cnc(\d+)_(\d+)-(\d+)"
    dir_match = re.search(dir_pattern, dir_name)
    if not dir_match:
        return None
        
    # Extract run and batch from filename
    file_pattern = r"result-.*?-(\d+)-(\d+)\.csv"
    file_match = re.search(file_pattern, os.path.basename(filename))
    if not file_match:
        return None
        
    concurrency = int(dir_match.group(1))
    test_num = int(dir_match.group(2))
    variant = int(dir_match.group(3))
    
    return {
        "concurrency": concurrency,
        "test_num": test_num,
        "test_name": get_test_name(test_num),
        "variant": variant,
        "implementation": get_implementation_name(variant),
        "run": int(file_match.group(1)),
        "batch": int(file_match.group(2))
    }

def load_and_process_data(directory: str) -> pd.DataFrame:
    """Load and process all CSV files from the directory"""
    csv_files = glob.glob(os.path.join(directory, "result-*.csv"))
    if not csv_files:
        raise ValueError("No CSV files found in the provided directory.")

    df_list = []
    for file in csv_files:
        metadata = extract_metadata(file)
        if metadata is None:
            continue
        try:
            df = pd.read_csv(file)
            for key, value in metadata.items():
                df[key] = value
            df_list.append(df)
        except Exception as e:
            print(f"Error reading {file}: {e}")

    if not df_list:
        raise ValueError("No valid data could be loaded.")

    return pd.concat(df_list, ignore_index=True)

def calculate_rps(row):
    """Calculate requests per second from total requests and average response time"""
    return (row['total_requests'] / (row['avg_response-time'] / 1000))  # convert ms to seconds

def generate_summary_stats(data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate summary statistics for each batch and run"""
    # Metrics for each combination of run and batch
    metrics = ['response-time', 'Response-delay', 'Response-read', 'Request-write']
    
    # Batch summary
    batch_groups = data.groupby(['test_id', 'run', 'batch'])
    batch_summary = pd.DataFrame()
    
    for metric in metrics:
        stats = batch_groups[metric].agg([
            ('avg_' + metric, 'mean'),
            ('std_' + metric, 'std'),
            ('min_' + metric, 'min'),
            ('max_' + metric, 'max'),
            ('p50_' + metric, 'median'),
            ('p95_' + metric, lambda x: x.quantile(0.95)),
            ('p99_' + metric, lambda x: x.quantile(0.99))
        ])
        if batch_summary.empty:
            batch_summary = stats
        else:
            batch_summary = pd.concat([batch_summary, stats], axis=1)
    
    # Add error rate and request count
    batch_summary['total_requests'] = batch_groups.size()
    batch_summary['error_rate'] = batch_groups.apply(
        lambda x: (x['status-code'] >= 400).mean() * 100
    )
    
    # Calculate requests per second
    batch_summary['rps'] = batch_summary.apply(calculate_rps, axis=1)
    
    # Calculate averages across runs for each batch
    avg_batch_summary = batch_summary.groupby(['test_id', 'batch']).agg({
        'rps': 'mean',
        'avg_response-time': 'mean',
        'error_rate': 'mean',
        'total_requests': 'mean'
    }).reset_index()
    
    # Reset index for easier handling
    batch_summary = batch_summary.reset_index()
    
    # Run summary
    run_summary = batch_summary.groupby('run').agg({
        'avg_response-time': ['mean', 'std'],
        'p99_response-time': 'max',
        'error_rate': 'max',
        'total_requests': 'sum'
    }).round(2)
    
    return batch_summary, run_summary

def generate_latex_tables(batch_summary: pd.DataFrame, run_summary: pd.DataFrame) -> Tuple[str, str]:
    """Generate LaTeX tables for batch and run summaries"""
    # Batch summary table
    batch_header = (
        "\\begin{tabular}{lrrrrrr}\n"
        "\\hline\n"
        "Run & Batch & Requests & Avg Response (ms) & P99 Response (ms) & Error Rate (\\%) & Std Dev \\\\\n"
        "\\hline"
    )
    
    batch_rows = []
    for _, row in batch_summary.iterrows():
        batch_rows.append(
            f"{row['run']} & {row['batch']} & "
            f"{row['total_requests']:.0f} & "
            f"{row['avg_response-time']:.2f} & "
            f"{row['p99_response-time']:.2f} & "
            f"{row['error_rate']:.2f} & "
            f"{row['std_response-time']:.2f} \\\\"
        )
    
    batch_table = "\n".join([batch_header] + batch_rows + ["\\hline\n\\end{tabular}"])
    
    # Run summary table
    run_header = (
        "\\begin{tabular}{lrrrr}\n"
        "\\hline\n"
        "Run & Avg Response (ms) & P99 Max (ms) & Max Error Rate (\\%) & Total Requests \\\\\n"
        "\\hline"
    )
    
    run_rows = []
    for run, row in run_summary.iterrows():
        run_rows.append(
            f"{run} & "
            f"{row[('avg_response-time', 'mean')]:.2f} & "
            f"{row[('p99_response-time', 'max')]:.2f} & "
            f"{row[('error_rate', 'max')]:.2f} & "
            f"{row[('total_requests', 'sum')]:.0f} \\\\"
        )
    
    run_table = "\n".join([run_header] + run_rows + ["\\hline\n\\end{tabular}"])
    
    return batch_table, run_table

def plot_performance_graphs(batch_summary: pd.DataFrame, avg_batch_summary: pd.DataFrame, output_dir: str):
    """Generate performance visualization plots"""
    # Set style
    plt.style.use('seaborn')
    
    # Response time progression by run
    plt.figure(figsize=(12, 6))
    for run in batch_summary['run'].unique():
        run_data = batch_summary[batch_summary['run'] == run]
        plt.plot(run_data['batch'], run_data['avg_response-time'], 
                marker='o', label=f'Run {run}')
        
    plt.title('Average Response Time Progression')
    plt.xlabel('Batch Number')
    plt.ylabel('Response Time (ms)')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, 'response_time_progression.png'))
    plt.close()
    
    # Throughput comparison (RPS vs Batch Size)
    plt.figure(figsize=(10, 6))
    plt.grid(True, which="both", ls="-", alpha=0.2)
    
    # Configure axes
    plt.xlabel('Total Requests')
    plt.ylabel('Requests per Second')
    
    # Set scales
    plt.yscale('log')
    plt.xscale('log', base=2)
    
    # Get unique batch sizes from data for x-axis ticks
    xticks = sorted(avg_batch_summary['batch'].unique())
    plt.xticks(xticks, [str(x) for x in xticks], rotation=45)
    
    # Ensure we show gridlines at our test points
    plt.grid(True, which='major', linestyle='-', alpha=0.3)
    plt.grid(True, which='minor', linestyle=':', alpha=0.2)
    
    # Plotting average RPS for each implementation
    markers = ['s-', 'o-', '^-']  # square, circle, triangle
    colors = ['#1f77b4', '#ff7f0e', '#2ca02c']  # blue, orange, green
    
    # Sort by variant to ensure consistent order
    implementations = sorted(avg_batch_summary['implementation'].unique())
    
    for impl, marker, color in zip(implementations, markers, colors):
        impl_data = avg_batch_summary[avg_batch_summary['implementation'] == impl]
        plt.plot(impl_data['batch'], 
                impl_data['rps'],
                marker,
                label=impl,  # Using the readable implementation name
                color=color,
                linewidth=2,
                markersize=8)
    
    plt.legend()
    # Get test name from first row
    test_name = avg_batch_summary['test_name'].iloc[0]
    plt.title(f'Throughput Comparison - {test_name}')
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, 'throughput_comparison.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # Response components stacked bar
    plt.figure(figsize=(12, 6))
    latest_run = batch_summary[batch_summary['run'] == batch_summary['run'].max()]
    components = ['avg_Request-write', 'avg_Response-delay', 'avg_Response-read']
    
    bottom = np.zeros(len(latest_run))
    for component in components:
        plt.bar(latest_run['batch'], latest_run[component], bottom=bottom, 
                label=component.replace('avg_', ''))
        bottom += latest_run[component]
    
    plt.title('Response Time Components (Latest Run)')
    plt.xlabel('Batch Number')
    plt.ylabel('Time (ms)')
    plt.legend()
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, 'response_components.png'))
    plt.close()
    
    # Error rate progression
    plt.figure(figsize=(12, 6))
    sns.lineplot(data=batch_summary, x='batch', y='error_rate', hue='run', marker='o')
    plt.title('Error Rate Progression')
    plt.xlabel('Batch Number')
    plt.ylabel('Error Rate (%)')
    plt.grid(True)
    plt.savefig(os.path.join(output_dir, 'error_rate.png'))
    plt.close()

def main():
    parser = argparse.ArgumentParser(
        description="Analyze performance test results"
    )
    parser.add_argument("directory", help="Directory containing the CSV files")
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate performance plots"
    )
    args = parser.parse_args()

    try:
        # Load and process data
        data = load_and_process_data(args.directory)
        batch_summary, run_summary = generate_summary_stats(data)
        
        # Generate and print LaTeX tables
        batch_table, run_table = generate_latex_tables(batch_summary, run_summary)
        
        print("\nBatch Summary Table:")
        print(batch_table)
        print("\nRun Summary Table:")
        print(run_table)
        
        # Generate plots if requested
        if args.plot:
            plot_performance_graphs(batch_summary, args.directory)
            print(f"\nPlots saved to {args.directory}")
        
        # Print key findings
        print("\nKey Findings:")
        print(f"- Total number of runs: {data['run'].nunique()}")
        print(f"- Maximum batches in a run: {data.groupby('run')['batch'].max().max()}")
        print(f"- Overall average response time: {data['response-time'].mean():.2f} ms")
        print(f"- Overall P99 response time: {data['response-time'].quantile(0.99):.2f} ms")
        print(f"- Maximum error rate in any batch: {batch_summary['error_rate'].max():.2f}%")
        print(f"- Average network delay: {data['Response-delay'].mean():.2f} ms")
        print(f"- Total requests processed: {data['status-code'].count()}")
        
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    main()