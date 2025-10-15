"""
Session Manager for CFD Optimization

Manages session state across Lambda invocations using S3.
Provides a clean interface for:
- Creating new optimization sessions
- Retrieving session metadata
- Tracking session progress
"""

import json
import os
from datetime import datetime
from typing import Dict, Optional
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get S3 bucket from environment
S3_BUCKET = os.environ.get('S3_BUCKET', 'cfd-optimization-data-120569639479-us-east-1')

# Lazy initialization of boto3 client
_s3_client = None


def get_s3_client():
    """Get or create S3 client (lazy initialization)."""
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client('s3')
    return _s3_client


class SessionManager:
    """
    Manages optimization session lifecycle and state.

    Session metadata is stored in S3 at:
    s3://bucket/sessions/{session_id}/session.json
    """

    def __init__(self, session_id: str):
        """
        Initialize session manager.

        Args:
            session_id: Unique identifier for this optimization session
        """
        self.session_id = session_id
        self.bucket = S3_BUCKET
        self.key = f"sessions/{session_id}/session.json"

        logger.info(f"Initialized SessionManager for {session_id}")

    def create_session(self, config: Dict) -> Dict:
        """
        Create a new optimization session.

        Args:
            config: Session configuration dict with:
                - objective: Optimization objective (e.g., 'minimize_cd')
                - cl_min: Minimum lift coefficient constraint
                - reynolds: Reynolds number
                - max_iter: Maximum iterations

        Returns:
            dict: Session metadata
        """
        session_data = {
            'session_id': self.session_id,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'RUNNING',
            'config': config,
            'current_iteration': 0,
            'total_designs_evaluated': 0,
            'best_cd': None,
            'best_geometry_id': None,
            'convergence_reason': None
        }

        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=self.bucket,
                Key=self.key,
                Body=json.dumps(session_data, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Created session {self.session_id}")
            return session_data
        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def get_session(self) -> Optional[Dict]:
        """
        Retrieve session metadata from S3.

        Returns:
            dict: Session metadata, or None if not found
        """
        try:
            s3_client = get_s3_client()
            response = s3_client.get_object(Bucket=self.bucket, Key=self.key)
            session_data = json.loads(response['Body'].read())
            logger.info(f"Retrieved session {self.session_id}")
            return session_data
        except get_s3_client().exceptions.NoSuchKey:
            logger.warning(f"Session {self.session_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session: {e}")
            raise

    def update_session(self, updates: Dict):
        """
        Update session metadata.

        Args:
            updates: dict with fields to update
        """
        # Get current session data
        session_data = self.get_session()

        if session_data is None:
            logger.error(f"Cannot update non-existent session {self.session_id}")
            return

        # Update fields
        session_data.update(updates)
        session_data['updated_at'] = datetime.utcnow().isoformat()

        # Write back to S3
        try:
            s3_client = get_s3_client()
            s3_client.put_object(
                Bucket=self.bucket,
                Key=self.key,
                Body=json.dumps(session_data, indent=2),
                ContentType='application/json'
            )
            logger.info(f"Updated session {self.session_id}")
        except Exception as e:
            logger.error(f"Failed to update session: {e}")
            raise

    def complete_session(self, reason: str):
        """
        Mark session as complete.

        Args:
            reason: Reason for completion (e.g., 'converged', 'max_iterations')
        """
        self.update_session({
            'status': 'COMPLETED',
            'completed_at': datetime.utcnow().isoformat(),
            'convergence_reason': reason
        })
        logger.info(f"Completed session {self.session_id}: {reason}")

    def fail_session(self, error: str):
        """
        Mark session as failed.

        Args:
            error: Error message
        """
        self.update_session({
            'status': 'FAILED',
            'failed_at': datetime.utcnow().isoformat(),
            'error': error
        })
        logger.error(f"Failed session {self.session_id}: {error}")

    def get_progress(self) -> Dict:
        """
        Get current session progress.

        Returns:
            dict with progress information
        """
        session_data = self.get_session()

        if session_data is None:
            return {
                'exists': False,
                'status': 'NOT_FOUND'
            }

        config = session_data.get('config', {})
        max_iter = config.get('max_iter', 8)
        current_iter = session_data.get('current_iteration', 0)

        progress = {
            'exists': True,
            'status': session_data.get('status'),
            'current_iteration': current_iter,
            'max_iterations': max_iter,
            'progress_pct': (current_iter / max_iter * 100) if max_iter > 0 else 0,
            'total_designs_evaluated': session_data.get('total_designs_evaluated', 0),
            'best_cd': session_data.get('best_cd'),
            'best_geometry_id': session_data.get('best_geometry_id')
        }

        return progress


def list_sessions(max_sessions: int = 10) -> list:
    """
    List recent optimization sessions.

    Args:
        max_sessions: Maximum number of sessions to return

    Returns:
        list of session metadata dicts
    """
    try:
        s3_client = get_s3_client()
        # List all session.json files
        paginator = s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(
            Bucket=S3_BUCKET,
            Prefix='sessions/',
            Delimiter='/'
        )

        sessions = []

        for page in pages:
            # Get session directories
            if 'CommonPrefixes' not in page:
                continue

            for prefix in page['CommonPrefixes']:
                session_dir = prefix['Prefix']
                session_id = session_dir.split('/')[1]

                # Try to load session metadata
                try:
                    manager = SessionManager(session_id)
                    session_data = manager.get_session()
                    if session_data:
                        sessions.append(session_data)
                except:
                    continue

                if len(sessions) >= max_sessions:
                    break

            if len(sessions) >= max_sessions:
                break

        # Sort by creation date (most recent first)
        sessions.sort(key=lambda s: s.get('created_at', ''), reverse=True)

        return sessions[:max_sessions]

    except Exception as e:
        logger.error(f"Failed to list sessions: {e}")
        return []


def get_active_sessions() -> list:
    """
    Get all currently running optimization sessions.

    Returns:
        list of active session metadata dicts
    """
    all_sessions = list_sessions(max_sessions=100)
    active = [s for s in all_sessions if s.get('status') == 'RUNNING']
    return active