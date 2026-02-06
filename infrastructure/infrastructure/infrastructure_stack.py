from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_rds as rds,
    aws_elasticache as elasticache,
    aws_s3 as s3,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    aws_secretsmanager as secrets,
    aws_logs as logs,
    aws_certificatemanager as acm,
    aws_ssm as ssm,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_lambda as _lambda,
    aws_servicediscovery as servicediscovery,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_lambda as _lambda,
)
from constructs import Construct
import json
import os


class StudyAppStack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name="dev",
        domain_name=None,
        hosted_zone_id=None,
        **kwargs
    ):
        super().__init__(scope, construct_id, **kwargs)

        self.env_name = env_name
        self.is_prod = env_name == "prod"

        Tags.of(self).add("Project", "StudyApp")
        Tags.of(self).add("Environment", env_name)

        self.create_vpc()
        self.create_security_groups()
        self.create_secrets()
        self.create_database()
        self.create_redis()
        self.create_bucket()
        self.create_ecs_cluster()
        self.create_load_balancer(domain_name)
        # Create a new private DNS namespace with a unique name based on environment
        namespace_id = f"StudyAppServiceDiscovery-{self.env_name}"
        self.namespace = servicediscovery.PrivateDnsNamespace(
            self,
            namespace_id,
            name=f"studyapp-{self.env_name}.local",
            vpc=self.vpc,
            description=f"Service discovery for {self.env_name} environment"
        )
        
        self.create_roles()
        self.create_services()
        self.create_outputs()

    # ---------------- VPC ---------------- #

    def create_vpc(self):
        self.vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=2,
            nat_gateways=1,
        )

    def create_security_groups(self):
        self.app_sg = ec2.SecurityGroup(
            self,
            "AppSG",
            vpc=self.vpc,
            allow_all_outbound=True,
        )

        self.app_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(80))
        self.app_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))
        self.app_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(8000))

    # ---------------- SECRETS ---------------- #

    def create_secrets(self):
        self.db_secret = secrets.Secret(
            self,
            "DBSecret",
            generate_secret_string=secrets.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "postgres"}),
                generate_string_key="password",
                exclude_characters='/@" \\',  # Explicitly exclude problematic characters
                password_length=32,  # Ensure sufficient length
                exclude_punctuation=False  # Allow some special chars but not the problematic ones
            ),
        )

        self.django_secret = secrets.Secret(
            self,
            "DjangoSecret",
            generate_secret_string=secrets.SecretStringGenerator(
                secret_string_template=json.dumps({}),
                generate_string_key="DJANGO_SECRET_KEY",
            ),
        )

    # ---------------- DATABASE ---------------- #

    def create_database(self):
        self.db = rds.DatabaseInstance(
            self,
            "Postgres",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_14
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE3,
                ec2.InstanceSize.MICRO,
            ),
            vpc=self.vpc,
            credentials=rds.Credentials.from_secret(self.db_secret),
            database_name="studyappdb",
            security_groups=[self.app_sg],
            allocated_storage=20,
            removal_policy=RemovalPolicy.DESTROY,
            deletion_protection=False,
        )

    # ---------------- REDIS ---------------- #

    def create_redis(self):
        subnet_group = elasticache.CfnSubnetGroup(
            self,
            "RedisSubnetGroup",
            subnet_ids=[s.subnet_id for s in self.vpc.private_subnets],
            description="Redis subnet group",
        )

        self.redis = elasticache.CfnCacheCluster(
            self,
            "Redis",
            engine="redis",
            cache_node_type="cache.t4g.micro",
            num_cache_nodes=1,
            port=6379,
            cache_subnet_group_name=subnet_group.ref,
            vpc_security_group_ids=[self.app_sg.security_group_id],
        )

    # ---------------- STORAGE ---------------- #

    def create_bucket(self):
        self.bucket = s3.Bucket(
            self,
            "MediaBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            auto_delete_objects=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

    # ---------------- ECS ---------------- #

    def create_ecs_cluster(self):
        # Create a CloudMap namespace for service discovery
        namespace = servicediscovery.PrivateDnsNamespace(
            self,
            "ServiceDiscoveryNamespace",
            vpc=self.vpc,
            name="studyapp.local",
            description="Service discovery namespace for StudyApp"
        )
        
        # Create the ECS cluster with service discovery enabled
        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=self.vpc,
            container_insights=True,
            default_cloud_map_namespace=ecs.CloudMapNamespaceOptions(
                name=namespace.namespace_name,
                vpc=self.vpc
            )
        )

    # ---------------- LOAD BALANCER ---------------- #

    def create_load_balancer(self, domain_name):
        # No longer creating a load balancer
        pass
        self.alb = None
        self.listener = None

    # ---------------- IAM ---------------- #

    def create_roles(self):
        self.execution_role = iam.Role(
            self,
            "ExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )

        self.task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )

        self.bucket.grant_read_write(self.task_role)
        self.db_secret.grant_read(self.task_role)
        self.django_secret.grant_read(self.task_role)

    # ---------------- SERVICES ---------------- #

    def create_celery_worker(self):
        return self.create_task_def(
            "CeleryWorker",
            [
                "celery", "-A", "study_app", "worker",
                "--loglevel=info",
                "--concurrency=2",
                "--task-soft-time-limit=300",
                "--task-time-limit=600",
                "--without-heartbeat",
                "--without-mingle",
                "--without-gossip"
            ],
            environment={
                "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/0",
                "CELERY_RESULT_BACKEND": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
                "CELERYD_PREFETCH_MULTIPLIER": "1",
                "CELERY_ACKS_LATE": "True",
                "CELERYD_MAX_TASKS_PER_CHILD": "100",
                "DB_HOST": self.db.db_instance_endpoint_address,
                "DB_NAME": "studyappdb",
                "DB_USER": "postgres",
                "REDIS_HOST": self.redis.attr_redis_endpoint_address,
                "ENV": self.env_name,
            }
        )

    def create_task_def(self, name, command, environment=None):
        task = ecs.FargateTaskDefinition(
            self,
            name,
            cpu=256,
            memory_limit_mib=1024,  # Increased for better performance
            execution_role=self.execution_role,
            task_role=self.task_role,
        )

        # Base environment variables
        env_vars = {
            "DB_HOST": self.db.db_instance_endpoint_address,
            "DB_NAME": "studyappdb",
            "DB_USER": "postgres",
            "DB_PORT": "5432",
            "REDIS_HOST": self.redis.attr_redis_endpoint_address,
            "REDIS_PORT": "6379",
            "ENV": self.env_name,
            "PYTHONUNBUFFERED": "1",
            "DJANGO_SETTINGS_MODULE": "study_app.settings",
            "ALLOWED_HOSTS": "*",  # For development only, restrict in production
            "DEBUG": "True" if not self.is_prod else "False",
            "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
            "CELERY_RESULT_BACKEND": f"redis://{self.redis.attr_redis_endpoint_address}:6379/2",
        }
        
        # Update with any provided environment variables
        if environment:
            env_vars.update(environment)
        
        # Add the container to the task definition
        container = task.add_container(
            f"{name}Container",
            image=ecs.ContainerImage.from_asset(
                directory=os.path.abspath("../"),
                file="Dockerfile",
                exclude=["infrastructure", ".venv", "cdk.out"],
            ),
            command=command,
            environment=env_vars,
            secrets={
                "DB_PASSWORD": ecs.Secret.from_secrets_manager(
                    self.db_secret, "password"
                ),
                "DJANGO_SECRET_KEY": ecs.Secret.from_secrets_manager(
                    self.django_secret, "DJANGO_SECRET_KEY"
                ),
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix=f"{name.lower()}-logs",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
        )
        
        # Add port mappings
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=8000,
                protocol=ecs.Protocol.TCP,
                name="http"
            )
        )
        
        # Configure container with health check
        # Health checks are configured at the task definition level in this CDK version
        
        return task

    def create_celery_worker(self):
        return self.create_task_def(
            "CeleryWorker",
            [
                "celery", "-A", "study_app", "worker",
                "--loglevel=info",
                "--concurrency=2",
                "--task-soft-time-limit=300",
                "--task-time-limit=600",
                "--without-heartbeat",
                "--without-mingle",
                "--without-gossip"
            ],
            environment={
                "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
                "CELERY_RESULT_BACKEND": f"redis://{self.redis.attr_redis_endpoint_address}:6379/2",
                "DB_HOST": self.db.db_instance_endpoint_address,
                "DB_NAME": "studyappdb",
                "DB_USER": "postgres",
                "REDIS_HOST": self.redis.attr_redis_endpoint_address,
                "ENV": self.env_name,
            }
        )

    def create_services(self):
        # Create a target group for the load balancer
        target_group = elbv2.ApplicationTargetGroup(
            self, "WebTargetGroup",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            vpc=self.vpc,
            health_check=elbv2.HealthCheck(
                path="/health/",
                healthy_threshold_count=2,
                unhealthy_threshold_count=2,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30)
            )
        )

        # Web Service with Daphne for WebSocket support
        web_task = self.create_task_def(
            "WebTask",
            [
                "daphne",
                "-b", "0.0.0.0",
                "-p", "8000",
                "--proxy-headers",
                "study_app.asgi:application"
            ],
            environment={
                "REDIS_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/0",
                "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
                "CHANNEL_LAYERS": json.dumps({
                    "default": {
                        "BACKEND": "channels_redis.core.RedisChannelLayer",
                        "CONFIG": {
                            "hosts": [(self.redis.attr_redis_endpoint_address, 6379)],
                        },
                    },
                }),
            }
        )

        # Create Celery worker service
        celery_task = self.create_celery_worker()
        
        # Create Celery service
        celery_service = ecs.FargateService(
            self,
            "CeleryService",
            cluster=self.cluster,
            task_definition=celery_task,
            desired_count=1,
            security_groups=[self.app_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )
        
        # Create the web service with health check settings
        web_service = ecs.FargateService(
            self,
            "WebService",
            cluster=self.cluster,
            task_definition=web_task,
            desired_count=1,
            security_groups=[self.app_sg],
            assign_public_ip=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            health_check_grace_period=Duration.minutes(5),
        )
        
        # Add the web service to the target group
        web_service.attach_to_application_target_group(target_group)
        
        # Create Application Load Balancer with WebSocket support
        self.alb = elbv2.ApplicationLoadBalancer(
            self, "StudyAppALB",
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.app_sg,
        )
        
        # Add HTTP listener with WebSocket upgrade support
        http_listener = self.alb.add_listener(
            "HttpListener",
            port=80,
            open=True
        )
        
        # Add default action to forward to the target group
        http_listener.add_action(
            "WebSocketUpgradeAction",
            priority=100,
            conditions=[elbv2.ListenerCondition.http_header("Upgrade", ["websocket"])],
            action=elbv2.ListenerAction.forward([target_group])
        )
        
        # Add default action for regular HTTP traffic
        http_listener.add_action(
            "DefaultAction",
            action=elbv2.ListenerAction.forward([target_group])
        )
        
        # Auto Scaling - optional, adjust as needed
        scaling = web_service.auto_scale_task_count(
            min_capacity=1,
            max_capacity=3 if self.is_prod else 1,
        )
        
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(300),
        )

# ---------------- SERVICES ---------------- #

    def create_celery_worker(self):
        return self.create_task_def(
            "CeleryWorker",
            [
                "celery", "-A", "study_app", "worker",
                "--loglevel=info",
                "--concurrency=2",
                "--task-soft-time-limit=300",
                "--task-time-limit=600",
                "--without-heartbeat",
                "--without-mingle",
                "--without-gossip"
            ],
            environment={
                "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/0",
                "CELERY_RESULT_BACKEND": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
                "CELERYD_PREFETCH_MULTIPLIER": "1",
                "CELERY_ACKS_LATE": "True",
                "CELERYD_MAX_TASKS_PER_CHILD": "100",
                "DB_HOST": self.db.db_instance_endpoint_address,
                "DB_NAME": "studyappdb",
                "DB_USER": "postgres",
                "REDIS_HOST": self.redis.attr_redis_endpoint_address,
                "ENV": self.env_name,
            }
        )

    def create_services(self):
        # Web Service with Daphne for WebSocket support
        web_task = self.create_task_def(
            "WebTask",
            [
                "daphne",
                "-b", "0.0.0.0",
                "-p", "8000",
                "--proxy-headers",
                "study_app.asgi:application"
            ],
            environment={
                "REDIS_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/0",
                "CELERY_BROKER_URL": f"redis://{self.redis.attr_redis_endpoint_address}:6379/1",
                "CHANNEL_LAYERS": json.dumps({
                    "default": {
                        "BACKEND": "channels_redis.core.RedisChannelLayer",
                        "CONFIG": {
                            "hosts": [(self.redis.attr_redis_endpoint_address, 6379)],
                        },
                    },
                }),
            }
        )

        # Create Celery worker service
        celery_task = self.create_celery_worker()
        
        # Create Celery service
        self.celery_service = ecs.FargateService(
            self,
            "CeleryService",
            cluster=self.cluster,
            task_definition=celery_task,
            desired_count=1,
            security_groups=[self.app_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
        )
        
        # Create the web service with private networking
        self.web_service = ecs.FargateService(
            self,
            "WebService",
            cluster=self.cluster,
            task_definition=web_task,
            desired_count=1,
            security_groups=[self.app_sg],
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            health_check_grace_period=Duration.minutes(5),
            enable_execute_command=True,
            service_name=f"study-app-web-{self.env_name}",
            cloud_map_options=ecs.CloudMapOptions(
                name="web",
                cloud_map_namespace=self.namespace
            )
        )
        
    def create_outputs(self):
        # Core infrastructure outputs
        outputs = {
            "DBEndpoint": self.db.db_instance_endpoint_address,
            "RedisEndpoint": self.redis.attr_redis_endpoint_address,
            "BucketName": self.bucket.bucket_name
        }

        # Add API Gateway endpoint if it exists
        if hasattr(self, 'api_gateway') and self.api_gateway:
            outputs["ApiGatewayEndpoint"] = self.api_gateway.url

        # Add service discovery endpoint if it exists
        if hasattr(self, 'web_service') and hasattr(self, 'namespace'):
            outputs["ServiceEndpoint"] = f"http://web.{self.namespace.namespace_name}:8000"

        # Create CloudFormation outputs with unique IDs
        for name, value in outputs.items():
            if value:  # Only create output if value is not None
                CfnOutput(self, f"Output{name}", value=str(value))