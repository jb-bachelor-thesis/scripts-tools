#!/bin/bash

# Function for decimal calculations
calc() {
    awk "BEGIN { printf \"%.2f\", $1 }"
}

# Usage function
usage() {
    echo "Usage: $0 [-h] [-p port] [-d directory] [-m max_requests] [-t threshold] [-r runs] <URI>"
    echo ""
    echo "Options:"
    echo "  -h              Show this help message."
    echo "  -p port         Set the port (default: 8090)."
    echo "  -d dir          Set the directory for CSV output (default: current directory)."
    echo "  -m max_requests Maximum number of requests (default: 100000)."
    echo "  -t threshold    Error rate threshold in percent (default: 5)."
    echo "  -r runs         Number of complete test runs (default: 3)."
    echo ""
    echo "Argument:"
    echo "  URI            The URI to test (path after the URL, e.g. /compute-primes)"
    exit 1
}

# Defaults
PORT=8090
OUTDIR="."
THRESHOLD=5
MAX_REQUESTS=100000
RUNS=3
START_TIME=$(date '+%Y%m%d_%H%M%S')
LOG_FILE="loadtest_${START_TIME}.log"
TEST_ID="${START_TIME}"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# Cleanup function
cleanup() {
    log "Test interrupted. Cleaning up..."
    exit 1
}

# Signal handler
trap cleanup INT TERM

# Parse options
while getopts "hp:d:m:t:r:" opt; do
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
        m)
            MAX_REQUESTS=$OPTARG
            ;;
        t)
            THRESHOLD=$OPTARG
            ;;
        r)
            RUNS=$OPTARG
            ;;
        *)
            usage
            ;;
    esac
done

shift $((OPTIND -1))

# Input validation
if [ $# -lt 1 ]; then
    log "Error: URI argument required."
    usage
fi

URI=$1

# Check hey installation
if ! command -v hey &> /dev/null; then
    log "Error: 'hey' is not installed. Please install it first."
    exit 1
fi

# Port validation
if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    log "Error: Port must be a number between 1 and 65535"
    exit 1
fi

# URI validation
if [[ ! "$URI" =~ ^/ ]]; then
    log "Error: URI must start with /"
    exit 1
fi

# Directory validation
if [ ! -d "$OUTDIR" ]; then
    mkdir -p "$OUTDIR"
fi

if [ ! -w "$OUTDIR" ]; then
    log "Error: Directory $OUTDIR is not writable"
    exit 1
fi

log "Starting performance tests against http://localhost:$PORT$URI"
log "Test configuration:"
log "- Starting with 200 requests"
log "- Maximum requests: $MAX_REQUESTS"
log "- Error threshold: ${THRESHOLD}%"
log "- Number of runs: $RUNS"
log "- Batch size: 1/4 of total requests"
log ""

# Function to calculate next request size
get_next_size() {
    local current=$1
    if [ "$current" -lt 500 ]; then
        echo 500
    elif [ "$current" -lt 800 ]; then
        echo 800
    elif [ "$current" -lt 1000 ]; then
        echo 1000
    elif [ "$current" -lt 2000 ]; then
        echo 2000
    elif [ "$current" -lt 5000 ]; then
        echo 5000
    else
        echo $((current + 5000))
    fi
}

# Perform complete runs
for run in $(seq 1 $RUNS); do
    log "Starting Run $run"
    requests=200
    batch_counter=1

    while [ "$requests" -le "$MAX_REQUESTS" ]; do
        # Calculate batch size as 1/4 of total requests
        batch_size=$((requests / 4))
        if [ $batch_size -lt 1 ]; then batch_size=1; fi

        log "  Testing with $requests total requests in batches of $batch_size"
        
        csv_file="$OUTDIR/result-${TEST_ID}-${run}-${batch_counter}.csv"
        
        # Execute hey with CSV output
        hey -n "$requests" -c "$batch_size" \
            -o csv \
            "http://localhost:$PORT$URI" > "$csv_file"
        
        log "    Saved CSV result to $csv_file"

        # Calculate error rate from CSV
        total=$(tail -n +2 "$csv_file" | wc -l)
        if [ "$total" -eq 0 ]; then
            log "    No data in CSV, skipping error rate calculation."
            error_rate=0
        else
            error_count=$(tail -n +2 "$csv_file" | awk -F, '{ if ($7 < 200 || $7 >= 300) count++ } END { print count+0 }')
            error_rate=$(calc "$error_count / $total * 100")
            log "    Error rate: $error_rate%"
        fi
        
        # Check error threshold
        if (( $(calc "$error_rate > $THRESHOLD") )); then
            log "  Error threshold exceeded ($error_rate% > $THRESHOLD%). Moving to next run."
            break
        fi

        batch_counter=$((batch_counter + 1))
        requests=$(get_next_size $requests)
        log ""
    done

    log "Completed Run $run"
    log "----------------------------------------"
    log ""
done

log "All performance tests completed."
log "Results and logs can be found in: $OUTDIR"
