"""
Initialize CFD Optimization Run with S3 Storage - DEBUG VERSION

Shows actual import errors instead of hiding them.
"""

import json
import os
from datetime import datetime
import uuid
import logging
import traceback

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Try to import S3 storage modules - SHOW THE ACTUAL ERROR
S3_ENABLED = False
IMPORT_ERROR = None

try:
    from session_manager import SessionManager

    S3_ENABLED = True
    logger.info("✓ Successfully imported S3 storage modules")
except Exception as e:
    IMPORT_ERROR = str(e)
    logger.error(f"✗ Failed to import S3 modules: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")
    S3_ENABLED = False


def lambda_handler(event, context):
    """
    Initialize optimization run with S3 storage.
    """

    try:
        logger.info("Starting optimization initialization with S3 storage")
        logger.info(f"S3_ENABLED: {S3_ENABLED}")
        if not S3_ENABLED:
            logger.warning(f"Import error was: {IMPORT_ERROR}")

        logger.info(f"Input event: {json.dumps(event)}")

        # Generate unique session ID
        session_id = f"opt-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{str(uuid.uuid4())[:8]}"
        logger.info(f"Generated session ID: {session_id}")

        # Extract optimization parameters from input
        objective = event.get('objective', 'minimize_cd')
        cl_min = float(event.get('cl_min', 0.30))
        reynolds = int(event.get('reynolds', 500000))
        max_iter = int(event.get('max_iter', 8))

        # Prepare session configuration
        config = {
            'objective': objective,
            'cl_min': cl_min,
            'reynolds': reynolds,
            'max_iter': max_iter
        }

        # === CREATE SESSION IN S3 ===
        if S3_ENABLED:
            try:
                manager = SessionManager(session_id)
                session_data = manager.create_session(config)
                logger.info(f"✓ Created session in S3: {session_id}")

                # Log S3 location
                bucket = os.environ.get('S3_BUCKET', 'cfd-optimization-data-120569639479')
                logger.info(f"  S3 Location: s3://{bucket}/sessions/{session_id}/")

            except Exception as s3_error:
                logger.error(f"Failed to create S3 session: {s3_error}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                # Don't fail the function - continue with local-only mode
                logger.warning("Continuing without S3 storage")
        else:
            logger.warning("S3 storage not enabled - running in local mode")
            logger.warning(f"Reason: {IMPORT_ERROR}")

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
            'timestamp': datetime.now().isoformat(),
            's3_enabled': S3_ENABLED,
            'import_error': IMPORT_ERROR if not S3_ENABLED else None
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
                'message': 'Failed to initialize optimization',
                'traceback': traceback.format_exc()
            }
        }