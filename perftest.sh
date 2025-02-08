#!/bin/bash

# Usage-Funktion: zeigt Hilfestellung an
usage() {
    echo "Usage: $0 [-h] [-p port] [-d directory] <URI>"
    echo ""
    echo "Options:"
    echo "  -h         Show this help message."
    echo "  -p port    Set the port (default: 8090)."
    echo "  -d dir     Set the directory for CSV output (default: current directory)."
    echo ""
    echo "Argument:"
    echo "  URI        The URI to test (path after the URL, e.g. /api/test)"
    exit 1
}

# Defaults
PORT=8090
OUTDIR="."
THRESHOLD=5  # Termination criterion: average error rate > 5%

# Alternative End Criteria:
#
# * Fixed Test Duration: Tests run for a predefined time period (e.g., 60 seconds)
#   and terminate automatically.
#
# * Number of Requests: A fixed total number of requests is sent.
#
# * Response Time Threshold: The test is terminated once the average response time exceeds a defined limit.
#
# * Resource Utilization: Monitoring CPU or memory usage to abort the test if critical limits are exceeded.

# Parse options
while getopts "hp:d:" opt; do
    case $opt in
        h)
            usage
            ;;
        p)
            PORT=$OPTARG
            ;;
        d)
            OUTDIR=$OPTARG
            ;;
        *)
            usage
            ;;
    esac
done

shift $((OPTIND -1))

if [ $# -lt 1 ]; then
    echo "Error: URI argument required."
    usage
fi

URI=$1

# Create output directory if it doesn't exist
if [ ! -d "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"
fi

# Initialize test parameters
requests=100
run_counter=1

echo "Starting performance tests against http://localhost:$PORT$URI"
echo "Termination criterion: Average error rate (non-2xx responses) > ${THRESHOLD}% over three runs."
echo ""

# Loop over increasing load levels
while true; do
    # Calculate concurrency as Batch Size = requests / 5 (at least 1)
    concurrency=$((requests / 5))
    if [ $concurrency -lt 1 ]; then concurrency=1; fi

    echo "Testing with $requests requests and concurrency of $concurrency"
    total_error_rate=0

    # 3 runs per load level
    for i in 1 2 3; do
        echo "  Run $i:"
        csv_file="$OUTDIR/result-$i-${run_counter}.csv"
        # Run hey with CSV output redirected to file
        hey -n "$requests" -c "$concurrency" -o csv "http://localhost:$PORT$URI" > "$csv_file"
        echo "    Saved CSV result to $csv_file"

        # Calculate error rate from the CSV output
        # CSV header: response-time,DNS+dialup,DNS,Request-write,Response-delay,Response-read,status-code,offset
        total=$(tail -n +2 "$csv_file" | wc -l)
        if [ "$total" -eq 0 ]; then
            echo "    No data in CSV, skipping error rate calculation."
            error_rate=0
        else
            error_count=$(tail -n +2 "$csv_file" | awk -F, '{ if ($7 < 200 || $7 >= 300) count++ } END { print count+0 }')
            error_rate=$(echo "scale=2; ($error_count / $total) * 100" | bc)
            echo "    Error rate for run $i: $error_rate %"
        fi
        total_error_rate=$(echo "scale=2; $total_error_rate + $error_rate" | bc)
        run_counter=$((run_counter + 1))
    done

    avg_error_rate=$(echo "scale=2; $total_error_rate / 3" | bc)
    echo "Average error rate for $requests requests: $avg_error_rate %"

    # Check termination criterion
    cmp=$(echo "$avg_error_rate > $THRESHOLD" | bc -l)
    if [ "$cmp" -eq 1 ]; then
        echo "Termination criterion met (average error rate > ${THRESHOLD}%). Stopping tests."
        break
    fi

    # Increase load level: double the number of requests
    requests=$((requests * 2))
    echo ""
done

echo "Performance tests completed."
