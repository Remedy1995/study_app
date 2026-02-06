#!/usr/bin/env python3
import os
import aws_cdk as cdk
from infrastructure.infrastructure_stack import StudyAppStack

app = cdk.App()

# Get environment context (dev/staging/prod)
env_name = app.node.try_get_context("environment") or "dev"
is_prod = env_name == "prod"

# AWS Account and Region
account = os.getenv('CDK_DEFAULT_ACCOUNT')
region = os.getenv('CDK_DEFAULT_REGION', 'us-east-1')

StudyAppStack(
    app,
    f"StudyAppStack-{env_name}",
    env_name=env_name,
    env=cdk.Environment(account=account, region=region),
)

app.synth()