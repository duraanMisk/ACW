# infra/cdk/stacks/orchestration_stack.py
"""
Orchestration Stack: Lambda functions for Step Functions workflow

Creates the 3 orchestration Lambda functions:
- initialize_optimization: Set up new optimization run
- check_convergence: Determine if optimization should continue
- generate_report: Generate final summary
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct


class OrchestrationStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create Lambda execution role with proper permissions
        lambda_role = iam.Role(
            self, "OrchestrationLambdaRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for CFD optimization orchestration functions",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ]
        )

        # Optional: Add S3 permissions if we want to persist CSVs to S3 later
        # lambda_role.add_to_policy(iam.PolicyStatement(
        #     actions=["s3:PutObject", "s3:GetObject"],
        #     resources=["arn:aws:s3:::cfd-optimization-data/*"]
        # ))

        # 1. Initialize Optimization Function
        initialize_fn = lambda_.Function(
            self, "InitializeOptimization",
            function_name="cfd-initialize-optimization",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/initialize_optimization"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Initialize CFD optimization run - clear CSVs and set up session",
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        # 2. Check Convergence Function
        check_convergence_fn = lambda_.Function(
            self, "CheckConvergence",
            function_name="cfd-check-convergence",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/check_convergence"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Check optimization convergence criteria - analyze improvement and iteration count",
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        # 3. Generate Report Function
        generate_report_fn = lambda_.Function(
            self, "GenerateReport",
            function_name="cfd-generate-report",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/generate_report"),
            role=lambda_role,
            timeout=Duration.seconds(30),
            memory_size=256,
            description="Generate optimization summary report - final results and statistics",
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )
        # 4. Invoke Bedrock Agent Function (wrapper for Step Functions)
        invoke_agent_fn = lambda_.Function(
            self, "InvokeBedrockAgent",
            function_name="cfd-invoke-bedrock-agent",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/invoke_bedrock_agent"),
            role=lambda_role,
            timeout=Duration.seconds(120),  # Longer timeout for agent
            memory_size=256,
            description="Invoke Bedrock Agent wrapper for Step Functions",
            environment={
                "LOG_LEVEL": "INFO"
            },
            log_retention=logs.RetentionDays.ONE_WEEK
        )

        # Grant Bedrock permissions to this Lambda
        invoke_agent_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            ],
            resources=["*"]
        ))

        # Add output
        CfnOutput(
            self, "InvokeAgentFunctionArn",
            value=invoke_agent_fn.function_arn,
            description="Invoke Bedrock Agent Lambda ARN"
        )

        # Store reference for Step Functions stack
        self.invoke_agent_fn = invoke_agent_fn

        # Outputs
        CfnOutput(
            self, "InitializeFunctionArn",
            value=initialize_fn.function_arn,
            description="Initialize Optimization Lambda ARN"
        )

        CfnOutput(
            self, "CheckConvergenceFunctionArn",
            value=check_convergence_fn.function_arn,
            description="Check Convergence Lambda ARN"
        )

        CfnOutput(
            self, "GenerateReportFunctionArn",
            value=generate_report_fn.function_arn,
            description="Generate Report Lambda ARN"
        )

        CfnOutput(
            self, "LambdaRoleArn",
            value=lambda_role.role_arn,
            description="Lambda Execution Role ARN"
        )

        # Store references for Step Functions stack
        self.initialize_fn = initialize_fn
        self.check_convergence_fn = check_convergence_fn
        self.generate_report_fn = generate_report_fn