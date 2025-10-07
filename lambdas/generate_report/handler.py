# lambdas/generate_report/handler.py
"""
Generate Optimization Report - No External Dependencies

Purpose: Create comprehensive summary of optimization results
- Read design_history.csv and results.csv
- Calculate overall statistics
- Identify best design
- Format results for display
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
    Generate final optimization report.

    Args:
        event: {
            'reason': 'Convergence reason from check_convergence',
            'cl_min': 0.30,
            'best_cd': 0.01234,  # Optional, will read from CSV
            'iteration': 5  # Optional, will read from CSV
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
        logger.info("Generating optimization report...")
        logger.info(f"Input event: {json.dumps(event)}")

        # CSV paths
        design_path = '/tmp/data/design_history.csv'
        results_path = '/tmp/data/results.csv'

        # Check if files exist
        if not os.path.exists(design_path) or not os.path.exists(results_path):
            logger.warning("CSV files not found")
            return {
                'statusCode': 200,
                'body': {
                    'message': 'No optimization data available',
                    'status': 'INCOMPLETE'
                }
            }

        # Read design history
        designs = []
        with open(design_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                designs.append(row)

        # Read results
        results = []
        with open(results_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                results.append(row)

        logger.info(f"Read {len(designs)} designs and {len(results)} iterations")

        if len(results) == 0:
            logger.warning("No results to report")
            return {
                'statusCode': 200,
                'body': {
                    'message': 'No optimization results to report',
                    'status': 'INCOMPLETE'
                }
            }

        # Get best result from last iteration
        best_result = results[-1]
        best_geometry_id = best_result['best_geometry_id']

        # Find corresponding design
        best_design = None
        for design in designs:
            if design['geometry_id'] == best_geometry_id:
                best_design = design
                break

        if best_design is None:
            logger.error(f"Could not find design {best_geometry_id} in history")
            # Use last design as fallback
            best_design = designs[-1] if designs else {}

        # Calculate statistics
        total_iterations = len(results)
        total_designs_evaluated = len(designs)

        # Get improvement from first to last iteration
        if len(results) > 1:
            initial_cd = float(results[0]['best_cd'])
            final_cd = float(best_result['best_cd'])
            total_improvement = ((initial_cd - final_cd) / initial_cd) * 100
        else:
            initial_cd = float(best_result['best_cd'])
            final_cd = float(best_result['best_cd'])
            total_improvement = 0.0

        # Extract constraint
        cl_min = float(event.get('cl_min', 0.30))
        best_cl = float(best_design.get('Cl', 0))
        constraint_satisfied = best_cl >= cl_min

        # Create structured report
        report = {
            'optimization_summary': {
                'status': 'COMPLETE',
                'total_iterations': int(total_iterations),
                'designs_evaluated': int(total_designs_evaluated),
                'convergence_reason': event.get('reason', 'Optimization complete'),
                'timestamp': datetime.now().isoformat()
            },
            'best_design': {
                'geometry_id': str(best_geometry_id),
                'Cd': round(float(best_design.get('Cd', 0)), 5),
                'Cl': round(float(best_design.get('Cl', 0)), 4),
                'L_D': round(float(best_design.get('L_D', 0)), 2),
                'thickness': round(float(best_design.get('thickness', 0)), 4),
                'max_camber': round(float(best_design.get('max_camber', 0)), 4),
                'camber_position': round(float(best_design.get('camber_position', 0)), 4),
                'alpha': round(float(best_design.get('alpha', 0)), 2)
            },
            'performance': {
                'initial_cd': round(initial_cd, 5),
                'final_cd': round(final_cd, 5),
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
  Initial Cd:        {report['performance']['initial_cd']:.5f}
  Final Cd:          {report['performance']['final_cd']:.5f}
  Improvement:       {report['performance']['improvement_pct']:.2f}%

  Constraint (Cl >= {report['performance']['constraint_cl_min']}):
    {'✓ SATISFIED' if report['performance']['constraint_satisfied'] else '✗ VIOLATED'}
    Achieved Cl: {report['performance']['achieved_cl']:.4f}

{'=' * 60}
        """

        # Log the report
        logger.info(report_text)

        # Add text to response
        report['report_text'] = report_text.strip()

        return {
            'statusCode': 200,
            'body': report
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