#!/usr/bin/env python3
import argparse
import glob
import os
import re

import pandas as pd


def extract_test_id(filename):
    # Extrahiere aus "result-<test_id>-<run_counter>.csv" die Test-ID
    m = re.search(r"result-(\d+)-.*\.csv", os.path.basename(filename))
    return m.group(1) if m else None

def main():
    parser = argparse.ArgumentParser(
        description="Aggregate performance CSV files from hey CLI and output a LaTeX table for response-time."
    )
    parser.add_argument("directory", help="Directory containing the CSV files")
    args = parser.parse_args()
    directory = args.directory

    # Suche alle CSV-Dateien, die dem Schema entsprechen
    csv_files = glob.glob(os.path.join(directory, "result-*-*.csv"))
    if not csv_files:
        print("No CSV files found in the provided directory.")
        return

    # Lies alle CSV-Dateien ein und füge die Test-ID (aus dem Dateinamen) als Spalte hinzu
    df_list = []
    for file in csv_files:
        test_id = extract_test_id(file)
        if test_id is None:
            continue
        try:
            df = pd.read_csv(file)
            df["test_id"] = test_id
            df_list.append(df)
        except Exception as e:
            print(f"Error reading {file}: {e}")

    if not df_list:
        print("No valid data could be loaded.")
        return

    # Kombiniere alle Datenframes
    all_data = pd.concat(df_list, ignore_index=True)

    # Gruppiere die Daten nach test_id und berechne für response-time die gewünschten Statistiken
    groups = all_data.groupby("test_id")["response-time"]
    summary = groups.agg(
        avg = "mean",
        fastest = "min",
        slowest = "max",
        median = "median"
    )
    # 1%- und 90%-Quantil berechnen
    summary["1%"] = groups.quantile(0.01)
    summary["90%"] = groups.quantile(0.90)

    # Erzeuge die LaTeX-Tabelle
    header = "\\begin{tabular}{lrrrrrr}\n\\hline\nTest ID & Avg & Fastest & Slowest & 1\\% & Median & 90\\% \\\\\n\\hline"
    footer = "\\hline\n\\end{tabular}"
    rows = []
    for test_id, row in summary.iterrows():
        rows.append(f"{test_id} & {row['avg']:.3f} & {row['fastest']:.3f} & {row['slowest']:.3f} & {row['1%']:.3f} & {row['median']:.3f} & {row['90%']:.3f} \\\\")
    table = "\n".join([header] + rows + [footer])
    print(table)

if __name__ == "__main__":
    main()
