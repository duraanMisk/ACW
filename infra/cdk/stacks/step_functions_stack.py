# infra/cdk/stacks/step_functions_stack.py
"""
Step Functions Stack: Autonomous CFD Optimization Workflow

Creates a state machine that:
1. Initializes optimization session
2. Loops: InvokeAgent → CheckConvergence → Continue or Stop
3. Generates final report

FIXES:
- Iteration counter bug: preserve loop iteration, don't overwrite from CSV
- Add exponential backoff for rate limiting
- Add max iteration safety check
"""

from aws_cdk import (
    Stack,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct
import json


class StepFunctionsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, orchestration_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Reference Lambda functions from orchestration stack
        initialize_fn = orchestration_stack.initialize_fn
        check_convergence_fn = orchestration_stack.check_convergence_fn
        generate_report_fn = orchestration_stack.generate_report_fn
        invoke_agent_fn = orchestration_stack.invoke_agent_fn

        # Define Step Functions tasks

        # 1. Initialize Optimization
        initialize_task = tasks.LambdaInvoke(
            self, "InitializeOptimization",
            lambda_function=initialize_fn,
            payload=sfn.TaskInput.from_object({
                "objective.$": "$.objective",
                "cl_min.$": "$.cl_min",
                "reynolds.$": "$.reynolds",
                "max_iter.$": "$.max_iter"
            }),
            result_path="$.initResult",
            result_selector={
                "body.$": "$.Payload.body"
            }
        )

        # 2. Extract session info for loop
        extract_session = sfn.Pass(
            self, "ExtractSessionInfo",
            parameters={
                "sessionId.$": "$.initResult.body.sessionId",
                "objective.$": "$.initResult.body.objective",
                "cl_min.$": "$.initResult.body.cl_min",
                "reynolds.$": "$.initResult.body.reynolds",
                "max_iter.$": "$.initResult.body.max_iter",
                "iteration": 0,
                "loopCount": 0  # Safety counter
            }
        )

        # 3. Increment iteration counter
        increment_iteration = sfn.Pass(
            self, "IncrementIteration",
            parameters={
                "sessionId.$": "$.sessionId",
                "objective.$": "$.objective",
                "cl_min.$": "$.cl_min",
                "reynolds.$": "$.reynolds",
                "max_iter.$": "$.max_iter",
                "iteration.$": "States.MathAdd($.iteration, 1)",
                "loopCount.$": "States.MathAdd($.loopCount, 1)"
            }
        )

        # 4. Invoke Bedrock Agent (via Lambda wrapper)
        invoke_agent = tasks.LambdaInvoke(
            self, "InvokeBedrockAgent",
            lambda_function=invoke_agent_fn,
            payload=sfn.TaskInput.from_object({
                "sessionId.$": "$.sessionId",
                "inputText": "Continue optimization iteration. Analyze current results and propose next candidates if needed.",
                "iteration.$": "$.iteration"
            }),
            result_path="$.agentResult",
            result_selector={
                "body.$": "$.Payload.body"
            },
            # Add retry with exponential backoff for rate limiting
            retry_on_service_exceptions=True,
            heartbeat_timeout=sfn.Timeout.duration(Duration.seconds(120))  # FIXED
        )

        # Add exponential backoff retry configuration
        invoke_agent.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(10),
            max_attempts=3,
            backoff_rate=2.0
        )

        # Add wait after agent invocation to allow CSV writes
        wait_for_csv = sfn.Wait(
            self, "WaitForCSVWrite",
            time=sfn.WaitTime.duration(Duration.seconds(5))
        )

        # 5. Check Convergence
        check_convergence = tasks.LambdaInvoke(
            self, "CheckConvergence",
            lambda_function=check_convergence_fn,
            payload=sfn.TaskInput.from_object({
                "max_iter.$": "$.max_iter",
                "cl_min.$": "$.cl_min",
                "iteration.$": "$.iteration"
            }),
            result_path="$.convergenceResult",
            result_selector={
                "body.$": "$.Payload.body"
            }
        )

        # 6. Update state with convergence info
        # CRITICAL FIX: Preserve iteration from loop counter, not from CSV!
        update_state = sfn.Pass(
            self, "UpdateState",
            parameters={
                "sessionId.$": "$.sessionId",
                "objective.$": "$.objective",
                "cl_min.$": "$.cl_min",
                "reynolds.$": "$.reynolds",
                "max_iter.$": "$.max_iter",
                "iteration.$": "$.iteration",  # FIXED: Keep loop iteration, don't overwrite!
                "loopCount.$": "$.loopCount",
                "converged.$": "$.convergenceResult.body.converged",
                "reason.$": "$.convergenceResult.body.reason",
                "agentStatus.$": "$.agentResult.body"
            }
        )

        # 7. Generate Final Report
        generate_report = tasks.LambdaInvoke(
            self, "GenerateReport",
            lambda_function=generate_report_fn,
            payload=sfn.TaskInput.from_object({
                "reason.$": "$.reason",
                "cl_min.$": "$.cl_min"
            }),
            result_selector={
                "body.$": "$.Payload.body"
            }
        )

        # 8. Success state
        optimization_complete = sfn.Succeed(
            self, "OptimizationComplete",
            comment="Optimization completed successfully"
        )

        # 9. Failure state for safety limit
        safety_limit_reached = sfn.Fail(
            self, "SafetyLimitReached",
            cause="Loop safety limit reached",
            error="InfiniteLoopPrevention"
        )

        # 10. Choice: Continue or Stop?
        check_if_done = sfn.Choice(self, "ShouldContinue?")

        # Conditions
        is_converged = sfn.Condition.boolean_equals("$.converged", True)
        max_iterations_reached = sfn.Condition.number_greater_than_equals_json_path("$.iteration", "$.max_iter")
        safety_limit = sfn.Condition.number_greater_than(("$.loopCount"), 20)  # Safety: max 20 loops

        # Build the workflow
        definition = (
            initialize_task
            .next(extract_session)
            .next(increment_iteration)
            .next(invoke_agent)
            .next(wait_for_csv)
            .next(check_convergence)
            .next(update_state)
            .next(check_if_done
                  .when(safety_limit, safety_limit_reached)
                  .when(
                sfn.Condition.or_(is_converged, max_iterations_reached),  # FIXED: Combined conditions
                generate_report.next(optimization_complete)
            )
                  .otherwise(increment_iteration)
                  )
        )

        # Create CloudWatch log group for state machine
        log_group = logs.LogGroup(
            self, "StateMachineLogGroup",
            log_group_name="/aws/vendedlogs/states/cfd-optimization",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK
        )

        # Create state machine
        state_machine = sfn.StateMachine(
            self, "CFDOptimizationStateMachine",
            state_machine_name="cfd-optimization-workflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(2),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
                include_execution_data=True
            )
        )

        # Grant Bedrock permissions to state machine role
        state_machine.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            ],
            resources=["*"]
        ))

        # Outputs
        CfnOutput(
            self, "StateMachineArn",
            value=state_machine.state_machine_arn,
            description="Step Functions State Machine ARN"
        )

        CfnOutput(
            self, "StateMachineName",
            value=state_machine.state_machine_name,
            description="Step Functions State Machine Name"
        )

        # Store reference
        self.state_machine = state_machine