# lambdas/check_convergence/handler.py
"""
Check Optimization Convergence - No External Dependencies

Purpose: Determine if optimization should continue or stop
- Read results.csv to analyze progress
- Calculate improvement percentage between iterations
- Check if max iterations reached
- Return convergence decision
"""

import json
import csv
from datetime import datetime
import logging
import os

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Check if optimization has converged.

    Args:
        event: {
            'max_iter': 8,
            'cl_min': 0.30,
            'iteration': 2  # Optional, will read from CSV if not provided
        }

    Returns:
        {
            'converged': True/False,
            'iteration': 3,
            'reason': 'explanation',
            'best_cd': 0.01234,
            'best_geometry_id': 'NACA4412_a2.5',
            'improvement_pct': 1.2
        }
    """

    try:
        logger.info("Checking convergence...")
        logger.info(f"Input event: {json.dumps(event)}")

        # CSV path
        results_path = '/tmp/data/results.csv'

        # Check if results file exists
        if not os.path.exists(results_path):
            logger.warning("Results file does not exist yet")
            return {
                'statusCode': 200,
                'body': {
                    'converged': False,
                    'iteration': 0,
                    'reason': 'No iterations completed yet',
                    'best_cd': None,
                    'improvement_pct': None
                }
            }

        # Read results history
        results = []
        with open(results_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)

        logger.info(f"Read {len(results)} results from CSV")

        # If no results yet, definitely not converged
        if len(results) == 0:
            logger.info("No results in CSV yet")
            return {
                'statusCode': 200,
                'body': {
                    'converged': False,
                    'iteration': 0,
                    'reason': 'No iterations completed yet',
                    'best_cd': None,
                    'improvement_pct': None
                }
            }

        # Get current iteration
        current_iteration = len(results)
        max_iter = int(event.get('max_iter', 8))

        logger.info(f"Current iteration: {current_iteration}/{max_iter}")

        # Get latest result
        best_row = results[-1]
        best_cd = float(best_row['best_cd'])
        best_geometry_id = str(best_row['best_geometry_id'])

        # Check if max iterations reached
        if current_iteration >= max_iter:
            logger.info(f"Max iterations ({max_iter}) reached")
            return {
                'statusCode': 200,
                'body': {
                    'converged': True,
                    'iteration': current_iteration,
                    'reason': f'Maximum iterations ({max_iter}) reached',
                    'best_cd': best_cd,
                    'best_geometry_id': best_geometry_id,
                    'improvement_pct': 0.0,
                    'timestamp': datetime.now().isoformat()
                }
            }

        # Need at least 2 iterations to check improvement
        if len(results) < 2:
            logger.info("Only 1 iteration complete, need more data")
            return {
                'statusCode': 200,
                'body': {
                    'converged': False,
                    'iteration': current_iteration,
                    'reason': 'Need at least 2 iterations to assess convergence',
                    'best_cd': best_cd,
                    'best_geometry_id': best_geometry_id,
                    'improvement_pct': None,
                    'timestamp': datetime.now().isoformat()
                }
            }

        # Calculate improvement from last two iterations
        cd_prev = float(results[-2]['best_cd'])
        cd_current = float(results[-1]['best_cd'])

        # Improvement percentage (positive = getting better, i.e., Cd decreasing)
        improvement_pct = ((cd_prev - cd_current) / cd_prev) * 100

        logger.info(f"Improvement: {improvement_pct:.3f}% (prev: {cd_prev:.5f}, current: {cd_current:.5f})")

        # Check convergence criteria: improvement < 0.5%
        converged = improvement_pct < 0.5

        if converged:
            reason = f'Converged: improvement {improvement_pct:.2f}% < 0.5% threshold'
            logger.info(reason)
        else:
            reason = f'Continuing: improvement {improvement_pct:.2f}% >= 0.5%'
            logger.info(reason)

        return {
            'statusCode': 200,
            'body': {
                'converged': converged,
                'iteration': current_iteration,
                'reason': reason,
                'best_cd': best_cd,
                'best_geometry_id': best_geometry_id,
                'improvement_pct': round(improvement_pct, 3),
                'timestamp': datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error checking convergence: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'converged': False,
                'iteration': event.get('iteration', 0),
                'message': 'Error checking convergence'
            }
        }