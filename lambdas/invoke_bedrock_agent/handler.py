"""
Invoke Bedrock Agent - Step Functions Wrapper

Purpose: Wrapper Lambda to invoke Bedrock Agent from Step Functions
- Receives session ID and input text
- Calls Bedrock Agent with session context
- Returns agent response
"""

import json
import boto3
import logging

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Bedrock Agent Runtime client
bedrock_agent = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

# Agent configuration
AGENT_ID = "MXUZMBTQFV"
AGENT_ALIAS_ID = "TSTALIASID"


def lambda_handler(event, context):
    """
    Invoke Bedrock Agent with session context.

    Args:
        event: {
            'sessionId': 'opt-20251007-143022-a1b2c3d4',
            'inputText': 'Continue optimization iteration...',
            'iteration': 1
        }

    Returns:
        {
            'statusCode': 200,
            'sessionId': '...',
            'iteration': 1,
            'completion': 'agent response text'
        }
    """

    try:
        session_id = event.get('sessionId')
        input_text = event.get('inputText', 'Continue optimization iteration')
        iteration = event.get('iteration', 0)

        logger.info(f"Invoking Bedrock Agent - Session: {session_id}, Iteration: {iteration}")
        logger.info(f"Input text: {input_text}")

        # Enhanced input text with session context
        # This helps the agent understand which session to work with
        enhanced_input = f"""
{input_text}

Session ID: {session_id}
Current iteration: {iteration}

IMPORTANT: When calling tools (generate_geometry, run_cfd, get_next_candidates), 
always include the session_id parameter with value "{session_id}".
This ensures all data is stored in the correct S3 location.
"""

        # Invoke the agent
        response = bedrock_agent.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=enhanced_input
        )

        # Parse the streaming response
        completion = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    completion += chunk['bytes'].decode('utf-8')

        logger.info(f"Agent response length: {len(completion)} characters")

        return {
            'statusCode': 200,
            'body': {
                'sessionId': session_id,
                'iteration': iteration,
                'completion': completion,
                'message': 'Agent invocation successful'
            }
        }

    except Exception as e:
        logger.error(f"Error invoking Bedrock Agent: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': {
                'error': str(e),
                'message': 'Failed to invoke Bedrock Agent'
            }
        }