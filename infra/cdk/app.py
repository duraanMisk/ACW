# infra/cdk/app.py
#!/usr/bin/env python3
"""
CFD Optimization Agent CDK Application

Stacks:
1. AgentStack: Original 3 Lambda tools + Bedrock Agent setup
2. OrchestrationStack: 3 Lambda functions for Step Functions
3. StepFunctionsStack: Step Functions state machine for autonomous optimization
"""

import aws_cdk as cdk
from stacks.agent_stack import AgentStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.step_functions_stack import StepFunctionsStack

app = cdk.App()

# Stack 1: Original agent and tools (already deployed)
agent_stack = AgentStack(
    app,
    "CFDOptimizationAgentStack",
    description="CFD Optimization Agent - Lambda tools and Bedrock Agent configuration"
)

# Stack 2: Orchestration Lambda functions (deployed)
orchestration_stack = OrchestrationStack(
    app,
    "CFDOptimizationOrchestrationStack",
    description="CFD Optimization - Orchestration Lambda functions for Step Functions workflow"
)

# Stack 3: Step Functions state machine (new - deploying now)
step_functions_stack = StepFunctionsStack(
    app,
    "CFDOptimizationStepFunctionsStack",
    orchestration_stack=orchestration_stack,
    description="CFD Optimization - Step Functions state machine for autonomous optimization"
)

app.synth()