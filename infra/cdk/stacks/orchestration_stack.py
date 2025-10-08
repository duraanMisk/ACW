"""
Orchestration Stack: Lambda functions for Step Functions workflow

Creates the 4 orchestration Lambda functions:
- initialize_optimization: Set up new optimization run
- check_convergence: Determine if optimization should continue
- generate_report: Generate final summary
- invoke_bedrock_agent: Wrapper for Bedrock Agent invocation

UPDATED: Added S3 bucket integration for persistent storage
"""

from aws_cdk import (
    Stack,
    aws_lambda as lambda_,
    aws_iam as iam,
    aws_logs as logs,
    aws_s3 as s3,
    Duration,
    RemovalPolicy,
    CfnOutput
)
from constructs import Construct


class OrchestrationStack(Stack):
    def __init__(
            self,
            scope: Construct,
            construct_id: str,
            results_bucket: s3.Bucket,
            **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.results_bucket = results_bucket

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

        # Grant S3 permissions
        results_bucket.grant_read_write(lambda_role)

        # Common Lambda configuration
        common_config = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "role": lambda_role,
            "timeout": Duration.seconds(30),
            "memory_size": 256,
            "environment": {
                "LOG_LEVEL": "INFO",
                "RESULTS_BUCKET": results_bucket.bucket_name,
                "AGENT_ID": "MXUZMBTQFV",
                "AGENT_ALIAS_ID": "TSTALIASID"
            },
            "log_retention": logs.RetentionDays.ONE_WEEK
        }

        # 1. Initialize Optimization Function
        initialize_fn = lambda_.Function(
            self, "InitializeOptimization",
            function_name="cfd-initialize-optimization",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/initialize_optimization"),
            description="Initialize CFD optimization run - clear CSVs and set up session",
            **common_config
        )

        # 2. Check Convergence Function
        check_convergence_fn = lambda_.Function(
            self, "CheckConvergence",
            function_name="cfd-check-convergence",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/check_convergence"),
            description="Check optimization convergence criteria - analyze improvement and iteration count",
            **common_config
        )

        # 3. Generate Report Function
        generate_report_fn = lambda_.Function(
            self, "GenerateReport",
            function_name="cfd-generate-report",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/generate_report"),
            description="Generate optimization summary report - final results and statistics",
            **common_config
        )

        # 4. Invoke Bedrock Agent Function (needs longer timeout)
        invoke_agent_config = {**common_config}
        invoke_agent_config["timeout"] = Duration.seconds(120)  # Longer timeout for agent

        invoke_agent_fn = lambda_.Function(
            self, "InvokeBedrockAgent",
            function_name="cfd-invoke-bedrock-agent",
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset("../../lambdas/invoke_bedrock_agent"),
            description="Invoke Bedrock Agent wrapper for Step Functions",
            **invoke_agent_config
        )

        # Grant Bedrock permissions to invoke_agent Lambda
        invoke_agent_fn.add_to_role_policy(iam.PolicyStatement(
            actions=[
                "bedrock:InvokeAgent",
                "bedrock:InvokeModel"
            ],
            resources=["*"]
        ))

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
            self, "InvokeAgentFunctionArn",
            value=invoke_agent_fn.function_arn,
            description="Invoke Bedrock Agent Lambda ARN"
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
        self.invoke_agent_fn = invoke_agent_fn