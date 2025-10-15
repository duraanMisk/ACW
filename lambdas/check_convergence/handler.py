"""
Check Convergence - Read from S3 and determine if optimization should continue

Purpose: Analyze optimization progress and decide whether to continue or stop
- Read design history and iteration results from S3
- Calculate improvement percentage
- Check convergence criteria
- Return decision with reasoning
"""

import json
from datetime import datetime
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Import S3 storage modules
try:
    from storage_s3 import S3DesignHistoryStorage, S3ResultsStorage
    from session_manager import SessionManager
    S3_ENABLED = True
except ImportError:
    logger.warning("S3 storage modules not available")
    S3_ENABLED = False


def lambda_handler(event, context):
    """
    Check if optimization has converged.

    Args:
        event: {
            'sessionId': 'opt-20251007-143022-a1b2c3d4',
            'max_iter': 8,
            'cl_min': 0.30,
            'iteration': 1  # Current iteration number
        }

    Returns directly (no statusCode wrapper):
        {
            'converged': False,
            'reason': 'Still improving',
            'iteration': 1,
            'best_cd': 0.0142,
            'improvement_pct': 2.8
        }
    """

    try:
        logger.info("Checking convergence...")
        logger.info(f"Input event: {json.dumps(event)}")

        session_id = event.get('sessionId')
        max_iter = int(event.get('max_iter', 8))
        cl_min = float(event.get('cl_min', 0.30))
        current_iteration = int(event.get('iteration', 0))

        # === READ FROM S3 ===
        if not S3_ENABLED or not session_id:
            logger.warning("S3 not enabled or no session_id")
            return {
                'converged': False,
                'reason': 'S3 storage not available',
                'iteration': current_iteration
            }

        try:
            # Read results from S3
            results_storage = S3ResultsStorage(session_id)
            results = results_storage.read_all_results()

            logger.info(f"Read {len(results)} iteration results from S3")

            # If no results yet, not converged
            if len(results) == 0:
                logger.info("No results yet - continuing")
                return {
                    'converged': False,
                    'reason': 'No iterations completed yet',
                    'iteration': 0,
                    'best_cd': None,
                    'improvement_pct': None # Add this line
                }

            # Get latest iteration data
            latest = results[-1]
            iteration_number = len(results)
            best_cd = latest.get('best_cd')

            # Check max iterations
            if iteration_number >= max_iter:
                logger.info(f"Max iterations reached: {iteration_number} >= {max_iter}")
                return {
                    'converged': True,
                    'reason': f'Maximum iterations reached ({max_iter})',
                    'iteration': iteration_number,
                    'best_cd': best_cd,
                    'improvement_pct': improvement_pct
                }

            # Check improvement if we have at least 2 iterations
            if len(results) >= 2:
                improvement_pct = results_storage.calculate_improvement()

                logger.info(f"Improvement: {improvement_pct}%")

                # Converged if improvement is small
                if improvement_pct is not None and improvement_pct < 0.5:
                    logger.info("Converged: improvement < 0.5%")
                    return {
                        'converged': True,
                        'reason': f'Improvement below threshold ({improvement_pct:.2f}% < 0.5%)',
                        'iteration': iteration_number,
                        'best_cd': best_cd,
                        'improvement_pct': improvement_pct
                    }

                # Still improving - continue
                return {
                    'converged': False,
                    'reason': f'Still improving ({improvement_pct:.2f}%)',
                    'iteration': iteration_number,
                    'best_cd': best_cd,
                    'improvement_pct': improvement_pct
                }

            # Only 1 iteration - definitely continue
            return {
                'converged': False,
                'reason': 'Only one iteration completed',
                'iteration': iteration_number,
                'best_cd': best_cd,
                'improvement_pct': improvement_pct
            }

        except Exception as s3_error:
            logger.error(f"Error reading from S3: {s3_error}", exc_info=True)
            return {
                'converged': False,
                'reason': f'S3 error: {str(s3_error)}',
                'iteration': current_iteration,
                'error': str(s3_error)
            }

    except Exception as e:
        logger.error(f"Error checking convergence: {str(e)}", exc_info=True)
        return {
            'converged': False,
            'reason': f'Error: {str(e)}',
            'iteration': 0,
            'error': str(e)
        }