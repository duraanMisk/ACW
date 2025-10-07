# Quick script to check CSV files exist and are writable
import os
import pandas as pd

print("Checking CSV infrastructure...")
for file in ['data/design_history.csv', 'data/results.csv']:
    if os.path.exists(file):
        df = pd.read_csv(file)
        print(f"✓ {file}: {len(df)} rows")
    else:
        print(f"✗ {file}: Missing!")