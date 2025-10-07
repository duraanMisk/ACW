"""
Quick test script for Bedrock Agent
Tests basic invocation and tool recognition
"""
import boto3
import json
from pathlib import Path


def load_agent_config():
    """Load agent configuration."""
    config_path = Path('../agent/agent_config.json')
    if not config_path.exists():
        print("Error: agent_config.json not found")
        print("Have you run setup_bedrock_agent.py?")
        exit(1)

    with open(config_path, 'r') as f:
        return json.load(f)


def invoke_agent(agent_id, alias_id, prompt, session_id="test-session"):
    """
    Invoke Bedrock Agent and print streaming response.
    """
    bedrock_runtime = boto3.client('bedrock-agent-runtime')

    print(f"\n{'=' * 60}")
    print(f"User: {prompt}")
    print(f"{'=' * 60}\n")
    print("Agent: ", end='', flush=True)

    try:
        response = bedrock_runtime.invoke_agent(
            agentId=agent_id,
            agentAliasId=alias_id,
            sessionId=session_id,
            inputText=prompt
        )

        # Stream response
        full_response = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    text = chunk['bytes'].decode('utf-8')
                    print(text, end='', flush=True)
                    full_response += text

        print("\n")
        return full_response

    except Exception as e:
        print(f"\nError: {str(e)}")
        return None


def main():
    """Run test suite."""
    print("CFD Optimization Agent - Quick Test")
    print("=" * 60)

    # Load config
    config = load_agent_config()
    agent_id = config['agent_id']
    alias_id = config['alias_id']

    print(f"Agent ID: {agent_id}")
    print(f"Alias ID: {alias_id}")

    # Test 1: Basic greeting
    print("\n\nTest 1: Basic Invocation")
    invoke_agent(
        agent_id,
        alias_id,
        "Hello! Can you introduce yourself and explain your purpose?",
        "test-1"
    )

    # Test 2: Tool recognition
    print("\n\nTest 2: Tool Recognition")
    invoke_agent(
        agent_id,
        alias_id,
        "What tools do you have available? List them with brief descriptions.",
        "test-2"
    )

    # Test 3: Workflow explanation
    print("\n\nTest 3: Workflow Understanding")
    invoke_agent(
        agent_id,
        alias_id,
        "Explain your optimization workflow step by step.",
        "test-3"
    )

    print("\n" + "=" * 60)
    print("✓ Basic tests complete!")
    print("\nIf all tests showed reasonable responses, Day 1 is successful!")
    print("\nNext steps:")
    print("  - Review agent responses for quality")
    print("  - Check CloudWatch logs for any errors")
    print("  - Proceed to Day 2: Mock data implementation")


if __name__ == "__main__":
    main()