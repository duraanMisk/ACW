#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.agent_stack import CFDOptimizationAgentStack
from stacks.orchestration_stack import OrchestrationStack
from stacks.step_functions_stack import StepFunctionsStack
from stacks.storage_stack import CFDOptimizationStorageStack

app = cdk.App()

# Environment
env = cdk.Environment(
    account='120569639479',
    region='us-east-1'
)

# Stack 1: S3 Storage (deploy this first)
storage_stack = CFDOptimizationStorageStack(
    app,
    "CFDOptimizationStorageStack",
    env=env,
    description="S3 bucket for persistent optimization results storage"
)

# Stack 2: Tool Lambda Functions (depends on storage)
agent_stack = CFDOptimizationAgentStack(
    app,
    "CFDOptimizationAgentStack",
    results_bucket=storage_stack.results_bucket,
    env=env,
    description="Lambda functions for CFD optimization tools"
)
agent_stack.add_dependency(storage_stack)

# Stack 3: Orchestration Lambda Functions (depends on storage)
orchestration_stack = OrchestrationStack(
    app,
    "CFDOptimizationOrchestrationStack",
    results_bucket=storage_stack.results_bucket,
    env=env,
    description="Lambda functions for orchestration"
)
orchestration_stack.add_dependency(storage_stack)

# Stack 4: Step Functions State Machine (depends on orchestration)
step_functions_stack = StepFunctionsStack(
    app,
    "CFDOptimizationStepFunctionsStack",
    orchestration_stack=orchestration_stack,
    env=env,
    description="Step Functions state machine for autonomous optimization"
)
step_functions_stack.add_dependency(orchestration_stack)

app.synth()