"""
CSV storage adapter for CFD optimization data.

Provides simple file-based persistence for:
- Design history (all evaluated geometries and CFD results)
- Iteration results (summary of each optimization iteration)

Designed for easy migration to S3/DynamoDB later.
"""

import os
import csv
import pandas as pd
from pathlib import Path
from typing import Dict, List
from datetime import datetime

# Default paths (relative to project root)
DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'data')
DESIGN_HISTORY_FILE = os.path.join(DEFAULT_DATA_DIR, 'design_history.csv')
RESULTS_FILE = os.path.join(DEFAULT_DATA_DIR, 'results.csv')


class DesignHistoryStorage:
    """
    Manages storage of individual design evaluations.

    Each row represents one geometry evaluation with CFD results.
    """

    def __init__(self, filepath=None):
        """
        Initialize storage adapter.

        Args:
            filepath: Custom path to design_history.csv (optional)
        """
        self.filepath = filepath or DESIGN_HISTORY_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create file with headers if it doesn't exist."""
        # Create directory if needed
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

        # Create file with headers if it doesn't exist
        if not os.path.exists(self.filepath):
            headers = [
                'timestamp',
                'geometry_id',
                'thickness',
                'max_camber',
                'camber_position',
                'alpha',
                'Cl',
                'Cd',
                'L_D',
                'converged',
                'reynolds',
                'iterations',
                'computation_time'
            ]

            with open(self.filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created design_history.csv at {self.filepath}")

    def write_design(self, data: Dict):
        """
        Append a design evaluation to the history.

        Args:
            data: dict with keys matching CSV headers
        """
        # Ensure timestamp exists
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Expected fields in order
        fields = [
            'timestamp',
            'geometry_id',
            'thickness',
            'max_camber',
            'camber_position',
            'alpha',
            'Cl',
            'Cd',
            'L_D',
            'converged',
            'reynolds',
            'iterations',
            'computation_time'
        ]

        # Extract values in correct order
        row = [data.get(field, '') for field in fields]

        # Append to file
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

        print(f"Wrote design {data.get('geometry_id')} to history")

    def read_design_history(self) -> pd.DataFrame:
        """
        Read entire design history as DataFrame.

        Returns:
            pandas DataFrame with all design evaluations
        """
        try:
            df = pd.read_csv(self.filepath)

            # Convert data types
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df['converged'] = df['converged'].astype(bool)

                # Numeric columns
                numeric_cols = ['thickness', 'max_camber', 'camber_position', 'alpha',
                                'Cl', 'Cd', 'L_D', 'reynolds', 'iterations', 'computation_time']
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

            return df
        except Exception as e:
            print(f"Error reading design history: {e}")
            return pd.DataFrame()

    def get_latest_designs(self, n: int = 10) -> pd.DataFrame:
        """
        Get the n most recent design evaluations.

        Args:
            n: Number of recent designs to retrieve

        Returns:
            pandas DataFrame with recent designs
        """
        df = self.read_design_history()
        if df.empty:
            return df
        return df.tail(n)

    def get_best_design(self, constraint_cl_min: float = 0.30) -> Dict:
        """
        Find the best design (lowest Cd) that satisfies constraints.

        Args:
            constraint_cl_min: Minimum Cl requirement

        Returns:
            dict with best design parameters and results, or None
        """
        df = self.read_design_history()

        if df.empty:
            return None

        # Filter for converged designs that meet constraint
        feasible = df[(df['converged'] == True) & (df['Cl'] >= constraint_cl_min)]

        if feasible.empty:
            return None

        # Find design with minimum Cd
        best_idx = feasible['Cd'].idxmin()
        best_row = feasible.loc[best_idx]

        return best_row.to_dict()


class ResultsStorage:
    """
    Manages storage of optimization iteration summaries.

    Each row represents one complete iteration with its best result.
    """

    def __init__(self, filepath=None):
        """
        Initialize storage adapter.

        Args:
            filepath: Custom path to results.csv (optional)
        """
        self.filepath = filepath or RESULTS_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create file with headers if it doesn't exist."""
        # Create directory if needed
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)

        # Create file with headers if it doesn't exist
        if not os.path.exists(self.filepath):
            headers = [
                'timestamp',
                'iteration',
                'candidate_count',
                'best_cd',
                'best_geometry_id',
                'strategy',
                'trust_radius',
                'confidence',
                'notes'
            ]

            with open(self.filepath, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            print(f"Created results.csv at {self.filepath}")

    def write_result(self, data: Dict):
        """
        Append an iteration result to the results file.

        Args:
            data: dict with keys matching CSV headers
        """
        # Ensure timestamp exists
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Expected fields in order
        fields = [
            'timestamp',
            'iteration',
            'candidate_count',
            'best_cd',
            'best_geometry_id',
            'strategy',
            'trust_radius',
            'confidence',
            'notes'
        ]

        # Extract values in correct order
        row = [data.get(field, '') for field in fields]

        # Append to file
        with open(self.filepath, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

        print(f"Wrote iteration {data.get('iteration')} to results")

    def read_results(self) -> pd.DataFrame:
        """
        Read entire results history as DataFrame.

        Returns:
            pandas DataFrame with all iteration results
        """
        try:
            df = pd.read_csv(self.filepath)

            # Convert data types
            if not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])

                # Numeric columns
                numeric_cols = ['iteration', 'candidate_count', 'best_cd',
                                'trust_radius', 'confidence']
                for col in numeric_cols:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')

            return df
        except Exception as e:
            print(f"Error reading results: {e}")
            return pd.DataFrame()

    def get_latest_iteration(self) -> Dict:
        """
        Get the most recent iteration result.

        Returns:
            dict with latest iteration data, or None
        """
        df = self.read_results()

        if df.empty:
            return None

        latest = df.iloc[-1]
        return latest.to_dict()

    def calculate_improvement(self) -> float:
        """
        Calculate improvement percentage between last two iterations.

        Returns:
            float: Improvement percentage, or None if insufficient data
        """
        df = self.read_results()

        if len(df) < 2:
            return None

        last_two = df.tail(2)['best_cd'].values

        if last_two[0] == 0:
            return None

        improvement_pct = (last_two[0] - last_two[1]) / last_two[0] * 100
        return round(improvement_pct, 2)


# Convenience functions for scripts
def clear_all_data():
    """Clear all CSV files (useful for testing)."""
    for filepath in [DESIGN_HISTORY_FILE, RESULTS_FILE]:
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Cleared {filepath}")


def get_optimization_summary() -> Dict:
    """
    Get a summary of the current optimization state.

    Returns:
        dict with summary statistics
    """
    design_storage = DesignHistoryStorage()
    results_storage = ResultsStorage()

    design_df = design_storage.read_design_history()
    results_df = results_storage.read_results()

    summary = {
        'total_designs_evaluated': len(design_df),
        'total_iterations': len(results_df),
        'best_design': design_storage.get_best_design(),
        'latest_iteration': results_storage.get_latest_iteration(),
        'improvement_pct': results_storage.calculate_improvement()
    }

    return summary


# For testing
if __name__ == "__main__":
    print("Testing storage module...")

    # Test design history storage
    print("\n=== Testing Design History Storage ===")
    design_storage = DesignHistoryStorage()

    test_design = {
        'geometry_id': 'NACA4412_a2.0',
        'thickness': 0.12,
        'max_camber': 0.04,
        'camber_position': 0.40,
        'alpha': 2.0,
        'Cl': 0.35,
        'Cd': 0.0142,
        'L_D': 24.6,
        'converged': True,
        'reynolds': 500000,
        'iterations': 230,
        'computation_time': 65.3
    }

    design_storage.write_design(test_design)
    print("✓ Wrote test design")

    history = design_storage.read_design_history()
    print(f"✓ Read history: {len(history)} designs")

    # Test results storage
    print("\n=== Testing Results Storage ===")
    results_storage = ResultsStorage()

    test_result = {
        'iteration': 1,
        'candidate_count': 1,
        'best_cd': 0.0142,
        'best_geometry_id': 'NACA4412_a2.0',
        'strategy': 'baseline',
        'trust_radius': 0.0,
        'confidence': 1.0,
        'notes': 'Initial baseline evaluation'
    }

    results_storage.write_result(test_result)
    print("✓ Wrote test result")

    results = results_storage.read_results()
    print(f"✓ Read results: {len(results)} iterations")

    # Test summary
    print("\n=== Optimization Summary ===")
    summary = get_optimization_summary()
    print(f"Total designs: {summary['total_designs_evaluated']}")
    print(f"Total iterations: {summary['total_iterations']}")

    print("\n✓ All tests passed!")