"""
Storage module for CFD optimization data.
Supports both local /tmp/ storage (for Lambda speed) and S3 (for persistence).
"""

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional
import boto3
import json


class StorageConfig:
    """Configuration for storage locations."""

    def __init__(self):
        # S3 bucket from environment variable
        self.s3_bucket = os.environ.get('RESULTS_BUCKET', '')
        self.use_s3 = bool(self.s3_bucket)

        # Local paths (Lambda /tmp/)
        self.local_data_dir = '/tmp/data'
        self.design_history_path = f'{self.local_data_dir}/design_history.csv'
        self.results_path = f'{self.local_data_dir}/results.csv'

        # S3 client (lazy initialization)
        self._s3_client = None

        # Session ID for organizing S3 files
        self.session_id = os.environ.get('SESSION_ID', 'default-session')

    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None:
            self._s3_client = boto3.client('s3')
        return self._s3_client

    def s3_key(self, filename: str) -> str:
        """Generate S3 key for a file."""
        return f'{self.session_id}/{filename}'


class DesignHistoryStorage:
    """
    Manages design_history.csv - stores every CFD evaluation.

    Schema: timestamp, geometry_id, thickness, max_camber, camber_position,
            alpha, Cl, Cd, L_D, converged, reynolds, iterations, computation_time
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self._ensure_local_directory()
        self._initialize_csv()

    def _ensure_local_directory(self):
        """Create local data directory if it doesn't exist."""
        os.makedirs(self.config.local_data_dir, exist_ok=True)

    def _initialize_csv(self):
        """Create CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.config.design_history_path):
            headers = [
                'timestamp', 'geometry_id', 'thickness', 'max_camber',
                'camber_position', 'alpha', 'Cl', 'Cd', 'L_D',
                'converged', 'reynolds', 'iterations', 'computation_time'
            ]

            # Write locally
            with open(self.config.design_history_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            # Upload to S3 if enabled
            if self.config.use_s3:
                self._upload_to_s3('design_history.csv')

    def write_design(self, data: Dict) -> None:
        """
        Write a single design evaluation to storage.

        Args:
            data: Dictionary containing design parameters and CFD results
        """
        # Add timestamp if not present
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Write to local CSV
        row = [
            data['timestamp'],
            data['geometry_id'],
            data['thickness'],
            data['max_camber'],
            data['camber_position'],
            data['alpha'],
            data['Cl'],
            data['Cd'],
            data['L_D'],
            data['converged'],
            data['reynolds'],
            data['iterations'],
            data['computation_time']
        ]

        with open(self.config.design_history_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

        # Upload to S3 if enabled
        if self.config.use_s3:
            self._upload_to_s3('design_history.csv')

    def read_design_history(self) -> List[Dict]:
        """
        Read all design evaluations from storage.

        Returns:
            List of dictionaries, one per design evaluation
        """
        # Try to download from S3 first (most recent data)
        if self.config.use_s3:
            self._download_from_s3('design_history.csv')

        if not os.path.exists(self.config.design_history_path):
            return []

        designs = []
        with open(self.config.design_history_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                designs.append(row)

        return designs

    def get_best_design(self, constraint_cl_min: float = 0.30) -> Optional[Dict]:
        """
        Find the design with lowest Cd that satisfies constraints.

        Args:
            constraint_cl_min: Minimum lift coefficient required

        Returns:
            Dictionary with best design data, or None if no valid designs
        """
        designs = self.read_design_history()

        # Filter designs that meet constraint and converged
        valid_designs = [
            d for d in designs
            if float(d['Cl']) >= constraint_cl_min and d['converged'] == 'True'
        ]

        if not valid_designs:
            return None

        # Sort by Cd (ascending) and return best
        best = min(valid_designs, key=lambda d: float(d['Cd']))
        return best

    def get_latest_designs(self, n: int = 10) -> List[Dict]:
        """Get the n most recent design evaluations."""
        designs = self.read_design_history()
        return designs[-n:] if designs else []

    def _upload_to_s3(self, filename: str):
        """Upload local file to S3."""
        try:
            local_path = f'{self.config.local_data_dir}/{filename}'
            s3_key = self.config.s3_key(filename)

            self.config.s3_client.upload_file(
                local_path,
                self.config.s3_bucket,
                s3_key
            )
        except Exception as e:
            print(f"Warning: Failed to upload {filename} to S3: {e}")

    def _download_from_s3(self, filename: str):
        """Download file from S3 to local storage."""
        try:
            local_path = f'{self.config.local_data_dir}/{filename}'
            s3_key = self.config.s3_key(filename)

            self.config.s3_client.download_file(
                self.config.s3_bucket,
                s3_key,
                local_path
            )
        except self.config.s3_client.exceptions.NoSuchKey:
            # File doesn't exist in S3 yet, that's okay
            pass
        except Exception as e:
            print(f"Warning: Failed to download {filename} from S3: {e}")


class ResultsStorage:
    """
    Manages results.csv - stores iteration summaries.

    Schema: timestamp, iteration, candidate_count, best_cd, best_geometry_id,
            strategy, trust_radius, confidence, notes
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self._ensure_local_directory()
        self._initialize_csv()

    def _ensure_local_directory(self):
        """Create local data directory if it doesn't exist."""
        os.makedirs(self.config.local_data_dir, exist_ok=True)

    def _initialize_csv(self):
        """Create CSV file with headers if it doesn't exist."""
        if not os.path.exists(self.config.results_path):
            headers = [
                'timestamp', 'iteration', 'candidate_count', 'best_cd',
                'best_geometry_id', 'strategy', 'trust_radius',
                'confidence', 'notes'
            ]

            # Write locally
            with open(self.config.results_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(headers)

            # Upload to S3 if enabled
            if self.config.use_s3:
                self._upload_to_s3('results.csv')

    def write_result(self, data: Dict) -> None:
        """
        Write iteration summary to storage.

        Args:
            data: Dictionary containing iteration results
        """
        # Add timestamp if not present
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Write to local CSV
        row = [
            data['timestamp'],
            data['iteration'],
            data['candidate_count'],
            data['best_cd'],
            data['best_geometry_id'],
            data.get('strategy', ''),
            data.get('trust_radius', ''),
            data.get('confidence', ''),
            data.get('notes', '')
        ]

        with open(self.config.results_path, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(row)

        # Upload to S3 if enabled
        if self.config.use_s3:
            self._upload_to_s3('results.csv')

    def read_results(self) -> List[Dict]:
        """
        Read all iteration results from storage.

        Returns:
            List of dictionaries, one per iteration
        """
        # Try to download from S3 first (most recent data)
        if self.config.use_s3:
            self._download_from_s3('results.csv')

        if not os.path.exists(self.config.results_path):
            return []

        results = []
        with open(self.config.results_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)

        return results

    def get_latest_iteration(self) -> Optional[Dict]:
        """Get the most recent iteration results."""
        results = self.read_results()
        return results[-1] if results else None

    def calculate_improvement(self) -> Optional[float]:
        """
        Calculate improvement percentage from previous iteration.

        Returns:
            Improvement percentage, or None if < 2 iterations
        """
        results = self.read_results()

        if len(results) < 2:
            return None

        previous_cd = float(results[-2]['best_cd'])
        current_cd = float(results[-1]['best_cd'])

        improvement = ((previous_cd - current_cd) / previous_cd) * 100
        return round(improvement, 2)

    def _upload_to_s3(self, filename: str):
        """Upload local file to S3."""
        try:
            local_path = f'{self.config.local_data_dir}/{filename}'
            s3_key = self.config.s3_key(filename)

            self.config.s3_client.upload_file(
                local_path,
                self.config.s3_bucket,
                s3_key
            )
        except Exception as e:
            print(f"Warning: Failed to upload {filename} to S3: {e}")

    def _download_from_s3(self, filename: str):
        """Download file from S3 to local storage."""
        try:
            local_path = f'{self.config.local_data_dir}/{filename}'
            s3_key = self.config.s3_key(filename)

            self.config.s3_client.download_file(
                self.config.s3_bucket,
                s3_key,
                local_path
            )
        except self.config.s3_client.exceptions.NoSuchKey:
            # File doesn't exist in S3 yet, that's okay
            pass
        except Exception as e:
            print(f"Warning: Failed to download {filename} from S3: {e}")