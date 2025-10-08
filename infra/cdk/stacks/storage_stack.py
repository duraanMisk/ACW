from aws_cdk import (
    Stack,
    Duration,
    aws_s3 as s3,
    aws_iam as iam,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct


class CFDOptimizationStorageStack(Stack):
    """
    S3 bucket for storing optimization results and design history.
    Replaces ephemeral Lambda /tmp/ storage with persistent S3 storage.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create S3 bucket for optimization results
        self.results_bucket = s3.Bucket(
            self,
            "ResultsBucket",
            bucket_name=f"cfd-optimization-results-{self.account}",
            # Lifecycle management
            versioned=False,  # We don't need versioning for this use case
            encryption=s3.BucketEncryption.S3_MANAGED,  # Encrypt at rest
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,  # No public access

            # For MVP/dev: auto-delete when stack is destroyed
            # For production: change to RETAIN
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,

            # Lifecycle rules to manage costs
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldResults",
                    enabled=True,
                    expiration=Duration.days(90),  # Delete results older than 90 days
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
                s3.LifecycleRule(
                    id="TransitionToIA",
                    enabled=True,
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(30),  # Move to cheaper storage after 30 days
                        )
                    ],
                ),
            ],
        )

        # Create IAM policy for Lambda functions to access bucket
        self.lambda_s3_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject",
            ],
            resources=[
                self.results_bucket.bucket_arn,
                f"{self.results_bucket.bucket_arn}/*",
            ],
        )

        # Outputs for reference in other stacks
        CfnOutput(
            self,
            "ResultsBucketName",
            value=self.results_bucket.bucket_name,
            description="S3 bucket for optimization results",
            export_name="CFDOptimizationResultsBucket",
        )

        CfnOutput(
            self,
            "ResultsBucketArn",
            value=self.results_bucket.bucket_arn,
            description="ARN of results bucket",
            export_name="CFDOptimizationResultsBucketArn",
        )