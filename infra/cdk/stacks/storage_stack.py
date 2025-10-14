from aws_cdk import (
    Stack,
    aws_s3 as s3,
    RemovalPolicy,
    Duration,
    CfnOutput
)
from constructs import Construct


class StorageStack(Stack):
    """
    S3 storage for CFD optimization data.

    Bucket naming: cfd-optimization-data-{account}-{region}
    Lifecycle: Test sessions (7 days), prod sessions (30→Glacier, 90→delete)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get account and region for globally unique bucket name
        account_id = Stack.of(self).account
        region = Stack.of(self).region

        # Create S3 bucket
        self.bucket = s3.Bucket(
            self, "OptimizationDataBucket",
            bucket_name=f"cfd-optimization-data-{account_id}-{region}",
            versioned=True,  # Safety for accidental overwrites
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,  # Keep data on stack destroy
            lifecycle_rules=[
                # Test sessions: Auto-delete after 7 days
                s3.LifecycleRule(
                    id="delete-test-sessions",
                    prefix="sessions/opt-test-",
                    expiration=Duration.days(7),
                    enabled=True
                ),
                # Production sessions: Archive to Glacier after 30 days, delete after 90
                s3.LifecycleRule(
                    id="archive-prod-sessions",
                    prefix="sessions/opt-2",  # Matches opt-20251013-...
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.GLACIER,
                            transition_after=Duration.days(30)
                        )
                    ],
                    expiration=Duration.days(90),
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True
                )
            ]
        )

        # Outputs
        CfnOutput(
            self, "BucketName",
            value=self.bucket.bucket_name,
            description="S3 bucket for optimization data",
            export_name="CFDOptimizationBucketName"
        )

        CfnOutput(
            self, "BucketArn",
            value=self.bucket.bucket_arn,
            description="S3 bucket ARN",
            export_name="CFDOptimizationBucketArn"
        )