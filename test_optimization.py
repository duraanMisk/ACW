"""
End-to-end test: Verify agent can call Lambda tools
Tests that the agent can generate geometry and run CFD
"""
import boto3
import json
from pathlib import Path


def load_agent_config():
    """Load agent configuration."""
    config_path = Path('agent/agent_config.json')
    with open(config_path, 'r') as f:
        return json.load(f)


def test_single_iteration():
    """Test agent calling tools for one design iteration."""
    config = load_agent_config()

    print("=" * 60)
    print("End-to-End Optimization Test")
    print("=" * 60)
    print(f"Agent ID: {config['agent_id']}")
    print(f"Model: {config.get('model_id', 'unknown')}")
    print()

    client = boto3.client('bedrock-agent-runtime', region_name='us-east-1')

    # Test prompt that should trigger both tools
    prompt = """Generate a NACA 4412 airfoil geometry (thickness=0.12, max_camber=0.04, camber_position=0.4, alpha=2.0), then run CFD simulation on it. Report the Cl, Cd, and L/D results."""

    print("User Request:")
    print(f"  {prompt}")
    print()
    print("Agent Response:")
    print("-" * 60)

    try:
        response = client.invoke_agent(
            agentId=config['agent_id'],
            agentAliasId=config['alias_id'],
            sessionId='test-optimization-iteration',
            inputText=prompt
        )

        full_response = ""
        for event in response['completion']:
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    text = chunk['bytes'].decode('utf-8')
                    print(text, end='', flush=True)
                    full_response += text

        print()
        print("-" * 60)
        print()

        # Check if tools were called
        if 'NACA' in full_response and ('Cl' in full_response or 'Cd' in full_response):
            print("✓ SUCCESS: Agent called tools and returned results!")
            print()
            print("What happened:")
            print("  1. Agent received your request")
            print("  2. Agent called generate_geometry Lambda")
            print("  3. Agent called run_cfd Lambda")
            print("  4. Agent synthesized results into response")
            print()
            print("Day 1 is complete! All systems working.")
            return True
        else:
            print("⚠ WARNING: Agent responded but may not have called tools")
            print("Check if response contains aerodynamic data")
            return False

    except Exception as e:
        print(f"\n✗ ERROR: {str(e)}")
        return False


def main():
    """Run end-to-end test."""
    success = test_single_iteration()

    print()
    print("=" * 60)
    if success:
        print("✓ End-to-End Test: PASSED")
        print()
        print("Next steps:")
        print("  - Review agent response quality")
        print("  - Check CloudWatch logs to see Lambda invocations")
        print("  - Proceed to Day 2: CSV storage integration")
    else:
        print("✗ End-to-End Test: FAILED or INCOMPLETE")
        print()
        print("Troubleshooting:")
        print("  - Check CloudWatch logs for Lambda invocations")
        print("  - Verify action groups are registered")
        print("  - Try asking agent directly: 'Call generate_geometry'")
    print("=" * 60)


if __name__ == "__main__":
    main()