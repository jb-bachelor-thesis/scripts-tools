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
  THRESHOLD=5  # Termination criterion: if average error rate > 5%

  # Alternative End Criteria:
  #
  # * Fixed Test Duration: Tests run for a predefined time period (e.g., 60 seconds)
  #   and terminate automatically.
  #
  # * Number of Requests: A fixed total number of requests is sent, regardless
  #   of the error rate.
  #
  # * Response Time Threshold: The test is terminated once the average response
  #   time exceeds a defined limit.
  #
  # * Resource Utilization: Monitoring of CPU or memory usage, where the test
  #   is terminated when these values exceed critical thresholds.

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

      for i in 1 2 3; do
          echo "  Run $i:"
          # Run hey and capture output
          output=$(hey -n $requests -c $concurrency "http://localhost:$PORT$URI")

          # Parse key values from the output
          avg_latency=$(echo "$output" | grep "Average:" | awk '{print $2}')
          req_sec=$(echo "$output" | grep "Requests/sec:" | awk '{print $2}')
          non2xx=$(echo "$output" | grep "Non-2xx" | awk '{print $3}')
          if [ -z "$non2xx" ]; then
              non2xx=0
          fi

          # Calculate error rate = (non2xx / requests) * 100
          error_rate=$(echo "scale=2; ($non2xx / $requests) * 100" | bc)
          total_error_rate=$(echo "scale=2; $total_error_rate + $error_rate" | bc)

          # Speichere Ergebnisse als CSV
          csv_file="$OUTDIR/result${run_counter}.csv"
          echo "Requests,Concurrency,Average Latency (ms),Requests/sec,Error Rate (%)" > "$csv_file"
          echo "$requests,$concurrency,$avg_latency,$req_sec,$error_rate" >> "$csv_file"
          echo "    Saved result to $csv_file"
          run_counter=$((run_counter + 1))
      done

      # Durchschnittliche Error Rate über drei Läufe
      avg_error_rate=$(echo "scale=2; $total_error_rate / 3" | bc)
      echo "Average error rate for $requests requests: $avg_error_rate %"

      # Überprüfe, ob das Ende-Kriterium erfüllt ist
      cmp=$(echo "$avg_error_rate > $THRESHOLD" | bc -l)
      if [ "$cmp" -eq 1 ]; then
          echo "Termination criterion met (average error rate > ${THRESHOLD}%). Stopping tests."
          break
      fi

      # Erhöhe Laststufe: Verdopple die Anzahl der Requests
      requests=$((requests * 2))
      echo ""
  done

  echo "Performance tests completed."
