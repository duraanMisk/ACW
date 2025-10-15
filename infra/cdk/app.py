#!/usr/bin/env python3
"""
CDK App: CFD Optimization Infrastructure

Deploys all stacks in correct order with dependencies
"""

import aws_cdk as cdk
from stacks.storage_stack import StorageStack
from stacks.agent_stack import AgentStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.step_functions_stack import StepFunctionsStack

app = cdk.App()

# Get environment configuration
env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1"
)

# Stack 1: Storage (S3 bucket)
storage_stack = StorageStack(
    app, "CFDOptimizationStorageStack",
    env=env,
    description="S3 storage for CFD optimization data"
)

# Stack 2: Bedrock Agent with action groups
agent_stack = AgentStack(
    app, "CFDOptimizationAgentStack",
    storage_stack=storage_stack,
    env=env,
    description="Bedrock Agent and Lambda tools for CFD optimization"
)
agent_stack.add_dependency(storage_stack)

# Stack 3: Orchestration Lambda functions
print("Creating Lambda Layer for shared modules...")
orchestration_stack = OrchestrationStack(
    app, "CFDOptimizationOrchestrationStack",
    storage_stack=storage_stack,
    env=env,
    description="Orchestration Lambda functions for Step Functions workflow"
)
orchestration_stack.add_dependency(storage_stack)

# Stack 4: Step Functions State Machine
step_functions_stack = StepFunctionsStack(
    app, "CFDOptimizationStepFunctionsStack",
    orchestration_stack=orchestration_stack,
    agent_stack=agent_stack,  # <-- ADD THIS LINE
    env=env,
    description="Step Functions workflow orchestrating Bedrock Agent"
)
step_functions_stack.add_dependency(orchestration_stack)
step_functions_stack.add_dependency(agent_stack)

app.synth()