# lambdas/initialize_optimization/handler.py
"""
Initialize CFD Optimization Run - No External Dependencies

Purpose: Set up a fresh optimization session
- Backup existing CSV files
- Create new empty CSV files with correct schemas
- Generate unique session ID
- Return configuration for the optimization loop
"""

import json
import os
import csv
from datetime import datetime
import uuid
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Initialize optimization run.

    Args:
        event: {
            'objective': 'minimize_cd',
            'cl_min': 0.30,
            'reynolds': 500000,
            'max_iter': 8
        }

    Returns:
        {
            'sessionId': 'opt-20251007-143022-a1b2c3d4',
            'objective': 'minimize_cd',
            'cl_min': 0.30,
            'reynolds': 500000,
            'max_iter': 8,
            'iteration': 0,
            'converged': False
        }
    """

    try:
        logger.info("Starting optimization initialization")
        logger.info(f"Input event: {json.dumps(event)}")

        # Generate unique session ID
        session_id = f"opt-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"
        logger.info(f"Generated session ID: {session_id}")

        # Define CSV paths
        csv_dir = '/tmp/data'
        os.makedirs(csv_dir, exist_ok=True)

        design_history_path = os.path.join(csv_dir, 'design_history.csv')
        results_path = os.path.join(csv_dir, 'results.csv')

        # Backup existing CSVs if they exist
        for csv_path in [design_history_path, results_path]:
            if os.path.exists(csv_path):
                backup_path = f"{csv_path}.backup-{session_id}"
                os.rename(csv_path, backup_path)
                logger.info(f"Backed up {csv_path} to {backup_path}")

        # Create design_history.csv with headers
        design_columns = [
            'timestamp', 'geometry_id', 'thickness', 'max_camber',
            'camber_position', 'alpha', 'Cl', 'Cd', 'L_D',
            'converged', 'reynolds', 'iterations', 'computation_time'
        ]
        with open(design_history_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(design_columns)
        logger.info(f"Created {design_history_path}")

        # Create results.csv with headers
        results_columns = [
            'timestamp', 'iteration', 'candidate_count', 'best_cd',
            'best_geometry_id', 'strategy', 'trust_radius',
            'confidence', 'notes'
        ]
        with open(results_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(results_columns)
        logger.info(f"Created {results_path}")

        # Extract optimization parameters from input
        objective = event.get('objective', 'minimize_cd')
        cl_min = float(event.get('cl_min', 0.30))
        reynolds = int(event.get('reynolds', 500000))
        max_iter = int(event.get('max_iter', 8))

        # Prepare response
        response = {
            'sessionId': session_id,
            'objective': objective,
            'cl_min': cl_min,
            'reynolds': reynolds,
            'max_iter': max_iter,
            'iteration': 0,
            'converged': False,
            'message': 'Optimization initialized successfully',
            'timestamp': datetime.now().isoformat()
        }

        logger.info(f"Initialization complete: {json.dumps(response)}")

        return {
            'statusCode': 200,
            'body': response
        }

    except Exception as e:
        logger.error(f"Error initializing optimization: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'message': 'Failed to initialize optimization'
            }
        }