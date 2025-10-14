"""
S3-based storage adapter for CFD optimization data.

Replaces local CSV storage with S3 for production use.
Maintains same interface as storage.py for easy migration.
"""

import json
import boto3
import os
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get S3 bucket from environment
S3_BUCKET = os.environ.get('S3_BUCKET', 'cfd-optimization-data-120569639479')

# Lazy initialization of boto3 client
_s3_client = None


def get_s3_client():
    """Get or create S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client('s3')
    return _s3_client


class S3DesignHistoryStorage:
    """
    Manages storage of individual design evaluations in S3.

    Each design is stored as a JSON file in S3:
    s3://bucket/sessions/{session_id}/designs/{geometry_id}.json
    """

    def __init__(self, session_id: str):
        """
        Initialize S3 storage adapter.

        Args:
            session_id: Unique identifier for this optimization session
        """
        self.session_id = session_id
        self.bucket = S3_BUCKET
        self.prefix = f"sessions/{session_id}/designs/"

        logger.info(f"Initialized S3 storage for session {session_id}")

    def write_design(self, data: Dict):
        """
        Write a design evaluation to S3.

        Args:
            data: dict with design parameters and CFD results
        """
        # Ensure timestamp exists
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Generate unique key
        geometry_id = data.get('geometry_id', 'unknown')
        timestamp = data['timestamp'].replace(':', '-').replace('.', '-')
        key = f"{self.prefix}{geometry_id}_{timestamp}.json"

        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Wrote design {geometry_id} to S3: {key}")
        except Exception as e:
            logger.error(f"Failed to write design to S3: {e}")
            raise

    def read_all_designs(self) -> List[Dict]:
        """
        Read all design evaluations for this session from S3.

        Returns:
            List of design dicts
        """
        designs = []

        try:
            s3_client = get_s3_client()
            # List all objects with this prefix
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)

            for page in pages:
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    key = obj['Key']

                    # Skip directories
                    if key.endswith('/'):
                        continue

                    # Read the design data
                    s3_client = get_s3_client()
                    response = s3_client.get_object(Bucket=self.bucket, Key=key)
                    data = json.loads(response['Body'].read())
                    designs.append(data)

            logger.info(f"Read {len(designs)} designs from S3")
            return designs

        except Exception as e:
            logger.error(f"Failed to read designs from S3: {e}")
            return []

    def get_best_design(self, constraint_cl_min: float = 0.30) -> Optional[Dict]:
        """
        Find the best design (lowest Cd) that satisfies constraints.

        Args:
            constraint_cl_min: Minimum Cl requirement

        Returns:
            dict with best design, or None
        """
        designs = self.read_all_designs()

        if not designs:
            return None

        # Filter for converged designs that meet constraint
        feasible = [
            d for d in designs
            if d.get('converged', False) and d.get('Cl', 0) >= constraint_cl_min
        ]

        if not feasible:
            return None

        # Find design with minimum Cd
        best = min(feasible, key=lambda d: d.get('Cd', float('inf')))
        return best

    def get_latest_designs(self, n: int = 10) -> List[Dict]:
        """
        Get the n most recent design evaluations.

        Args:
            n: Number of recent designs to retrieve

        Returns:
            List of design dicts
        """
        designs = self.read_all_designs()

        if not designs:
            return []

        # Sort by timestamp (most recent first)
        designs.sort(key=lambda d: d.get('timestamp', ''), reverse=True)

        return designs[:n]


class S3ResultsStorage:
    """
    Manages storage of optimization iteration summaries in S3.

    Each iteration summary is stored as:
    s3://bucket/sessions/{session_id}/iterations/{iteration}.json
    """

    def __init__(self, session_id: str):
        """
        Initialize S3 storage adapter.

        Args:
            session_id: Unique identifier for this optimization session
        """
        self.session_id = session_id
        self.bucket = S3_BUCKET
        self.prefix = f"sessions/{session_id}/iterations/"

        logger.info(f"Initialized S3 results storage for session {session_id}")

    def write_result(self, data: Dict):
        """
        Write an iteration result to S3.

        Args:
            data: dict with iteration summary
        """
        # Ensure timestamp exists
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().isoformat()

        # Generate key based on iteration number
        iteration = data.get('iteration', 0)
        key = f"{self.prefix}iteration_{iteration:03d}.json"

        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=json.dumps(data, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Wrote iteration {iteration} to S3: {key}")
        except Exception as e:
            logger.error(f"Failed to write result to S3: {e}")
            raise

    def read_all_results(self) -> List[Dict]:
        """
        Read all iteration results for this session from S3.

        Returns:
            List of iteration result dicts
        """
        results = []

        try:
            s3_client = get_s3_client()
            # List all objects with this prefix
            paginator = s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket, Prefix=self.prefix)

            for page in pages:
                if 'Contents' not in page:
                    continue

                for obj in page['Contents']:
                    key = obj['Key']

                    # Skip directories
                    if key.endswith('/'):
                        continue

                    # Read the result data
                    s3_client = get_s3_client()
                    response = s3_client.get_object(Bucket=self.bucket, Key=key)
                    data = json.loads(response['Body'].read())
                    results.append(data)

            # Sort by iteration number
            results.sort(key=lambda r: r.get('iteration', 0))

            logger.info(f"Read {len(results)} iteration results from S3")
            return results

        except Exception as e:
            logger.error(f"Failed to read results from S3: {e}")
            return []

    def get_latest_iteration(self) -> Optional[Dict]:
        """
        Get the most recent iteration result.

        Returns:
            dict with latest iteration data, or None
        """
        results = self.read_all_results()

        if not results:
            return None

        # Results are already sorted by iteration
        return results[-1]

    def calculate_improvement(self) -> Optional[float]:
        """
        Calculate improvement percentage between last two iterations.

        Returns:
            float: Improvement percentage, or None if insufficient data
        """
        results = self.read_all_results()

        if len(results) < 2:
            return None

        last_two = results[-2:]
        cd_prev = last_two[0].get('best_cd')
        cd_current = last_two[1].get('best_cd')

        if cd_prev is None or cd_current is None or cd_prev == 0:
            return None

        improvement_pct = (cd_prev - cd_current) / cd_prev * 100
        return round(improvement_pct, 2)


def get_optimization_summary(session_id: str) -> Dict:
    """
    Get a summary of the current optimization state from S3.

    Args:
        session_id: Unique identifier for this optimization session

    Returns:
        dict with summary statistics
    """
    design_storage = S3DesignHistoryStorage(session_id)
    results_storage = S3ResultsStorage(session_id)

    designs = design_storage.read_all_designs()
    results = results_storage.read_all_results()

    summary = {
        'session_id': session_id,
        'total_designs_evaluated': len(designs),
        'total_iterations': len(results),
        'best_design': design_storage.get_best_design(),
        'latest_iteration': results_storage.get_latest_iteration(),
        'improvement_pct': results_storage.calculate_improvement()
    }

    return summary