"""
Generate Optimization Report with S3 Storage

Purpose: Create comprehensive summary of optimization results
- Read design history and iteration results from S3
- Calculate overall statistics
- Identify best design
- Format results for display
"""

import json
from datetime import datetime
import logging
import os

# Import S3 storage modules
try:
    from storage_s3 import S3DesignHistoryStorage, S3ResultsStorage, get_optimization_summary
    from session_manager import SessionManager

    S3_ENABLED = True
except ImportError:
    print("WARNING: S3 storage modules not available")
    S3_ENABLED = False

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """
    Generate final optimization report from S3 data.

    Args:
        event: {
            'reason': 'Convergence reason from check_convergence',
            'cl_min': 0.30,
            'sessionId': 'opt-20251007-143022-a1b2c3d4'
        }

    Returns:
        {
            'optimization_summary': {...},
            'best_design': {...},
            'performance': {...},
            'report_text': 'formatted string'
        }
    """

    try:
        logger.info("Generating optimization report from S3...")
        logger.info(f"Input event: {json.dumps(event)}")

        session_id = event.get('sessionId')
        cl_min = float(event.get('cl_min', 0.30))
        convergence_reason = event.get('reason', 'Optimization complete')

        # === READ FROM S3 ===
        if not S3_ENABLED or not session_id:
            logger.warning("S3 not enabled or no session_id")
            return {
                'statusCode': 200,
                'body': {
                    'message': 'S3 storage not available - cannot generate report',
                    'status': 'INCOMPLETE'
                }
            }

        try:
            # Get comprehensive optimization summary from S3
            summary = get_optimization_summary(session_id)

            design_storage = S3DesignHistoryStorage(session_id)
            results_storage = S3ResultsStorage(session_id)

            designs = design_storage.read_all_designs()
            results = results_storage.read_all_results()

            logger.info(f"Read {len(designs)} designs and {len(results)} iterations from S3")

            if len(results) == 0:
                logger.warning("No results to report")
                return {
                    'statusCode': 200,
                    'body': {
                        'message': 'No optimization results to report',
                        'status': 'INCOMPLETE'
                    }
                }

            # Get best design
            best_design_data = design_storage.get_best_design(constraint_cl_min=cl_min)

            if best_design_data is None:
                logger.error("Could not find best design")
                best_design_data = designs[-1] if designs else {}

            # Calculate statistics
            total_iterations = len(results)
            total_designs_evaluated = len(designs)

            # Get improvement from first to last iteration
            if len(results) > 1:
                initial_cd = results[0].get('best_cd')
                final_cd = results[-1].get('best_cd')

                if initial_cd and final_cd:
                    total_improvement = ((initial_cd - final_cd) / initial_cd) * 100
                else:
                    total_improvement = 0.0
            else:
                final_cd = results[0].get('best_cd')
                initial_cd = final_cd
                total_improvement = 0.0

            # Extract constraint
            best_cl = best_design_data.get('Cl', 0)
            constraint_satisfied = best_cl >= cl_min

            # Create structured report
            report = {
                'session_id': session_id,
                'optimization_summary': {
                    'status': 'COMPLETE',
                    'total_iterations': int(total_iterations),
                    'designs_evaluated': int(total_designs_evaluated),
                    'convergence_reason': convergence_reason,
                    'timestamp': datetime.now().isoformat()
                },
                'best_design': {
                    'geometry_id': str(best_design_data.get('geometry_id', 'N/A')),
                    'Cd': round(float(best_design_data.get('Cd', 0)), 5),
                    'Cl': round(float(best_design_data.get('Cl', 0)), 4),
                    'L_D': round(float(best_design_data.get('L_D', 0)), 2),
                    'thickness': round(float(best_design_data.get('thickness', 0)), 4),
                    'max_camber': round(float(best_design_data.get('max_camber', 0)), 4),
                    'camber_position': round(float(best_design_data.get('camber_position', 0)), 4),
                    'alpha': round(float(best_design_data.get('alpha', 0)), 2)
                },
                'performance': {
                    'initial_cd': round(initial_cd, 5) if initial_cd else None,
                    'final_cd': round(final_cd, 5) if final_cd else None,
                    'improvement_pct': round(total_improvement, 2),
                    'constraint_cl_min': cl_min,
                    'achieved_cl': round(best_cl, 4),
                    'constraint_satisfied': constraint_satisfied
                }
            }

            # Create formatted text report
            report_text = f"""
{'=' * 60}
CFD OPTIMIZATION REPORT
{'=' * 60}

SESSION: {session_id}
STATUS: {report['optimization_summary']['status']}
Reason: {report['optimization_summary']['convergence_reason']}

ITERATIONS: {report['optimization_summary']['total_iterations']}
Designs Evaluated: {report['optimization_summary']['designs_evaluated']}

BEST DESIGN: {report['best_design']['geometry_id']}
  Cd (drag):         {report['best_design']['Cd']:.5f}
  Cl (lift):         {report['best_design']['Cl']:.4f}
  L/D ratio:         {report['best_design']['L_D']:.2f}

  Thickness:         {report['best_design']['thickness']:.4f}
  Max Camber:        {report['best_design']['max_camber']:.4f}
  Camber Position:   {report['best_design']['camber_position']:.4f}
  Alpha (degrees):   {report['best_design']['alpha']:.2f}

PERFORMANCE:
  Initial Cd:        {report['performance']['initial_cd']:.5f if report['performance']['initial_cd'] else 'N/A'}
  Final Cd:          {report['performance']['final_cd']:.5f if report['performance']['final_cd'] else 'N/A'}
  Improvement:       {report['performance']['improvement_pct']:.2f}%

  Constraint (Cl >= {report['performance']['constraint_cl_min']}):
    {'✓ SATISFIED' if report['performance']['constraint_satisfied'] else '✗ VIOLATED'}
    Achieved Cl: {report['performance']['achieved_cl']:.4f}

S3 LOCATION:
  Bucket: {os.environ.get('S3_BUCKET', 'cfd-optimization-data-120569639479')}
  Path: sessions/{session_id}/

{'=' * 60}
            """

            # Log the report
            logger.info(report_text)

            # Add text to response
            report['report_text'] = report_text.strip()

            # Update session with final status
            try:
                manager = SessionManager(session_id)
                session_data = manager.get_session()
                if session_data and session_data.get('status') != 'COMPLETED':
                    manager.complete_session(convergence_reason)
            except Exception as session_error:
                logger.warning(f"Could not update session status: {session_error}")

            return {
                'statusCode': 200,
                'body': report
            }

        except Exception as s3_error:
            logger.error(f"Error reading from S3: {s3_error}", exc_info=True)
            return {
                'statusCode': 500,
                'body': {
                    'error': str(s3_error),
                    'status': 'ERROR',
                    'message': 'Failed to read optimization data from S3'
                }
            }

    except Exception as e:
        logger.error(f"Error generating report: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'status': 'ERROR',
                'message': 'Failed to generate report'
            }
        }