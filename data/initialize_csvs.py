"""
Initialize CSV storage files with proper headers
"""
import csv
import os

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Design history CSV schema
design_history_headers = [
    'iteration',
    'geometry_id',
    'thickness',
    'max_camber',
    'camber_position',
    'alpha',
    'Cl',
    'Cd',
    'L_D',
    'valid',
    'timestamp'
]

# Results CSV schema
results_headers = [
    'iteration',
    'candidate_count',
    'best_cd',
    'best_geometry_id',
    'strategy',
    'improvement_pct',
    'converged',
    'notes'
]

# Initialize design_history.csv
with open('data/design_history.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(design_history_headers)
    print("✓ Created design_history.csv")

# Initialize results.csv
with open('data/results.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(results_headers)
    print("✓ Created results.csv")

print("\nCSV files initialized successfully!")