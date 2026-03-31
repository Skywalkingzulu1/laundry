# AWS ECS Deployment for LaundryPool

This folder contains the CloudFormation templates and supporting JSON files required to deploy the LaundryPool FastAPI application to AWS ECS using Fargate, an Application Load Balancer (ALB), and automatic scaling.

## Files

| File | Purpose |
|------|---------|
| `ecs_task_definition.json` | ECS task definition describing the container image, resources, networking mode, and logging configuration. |
| `ecs_service.yaml` | CloudFormation stack that creates the ECS cluster, service, ALB, target group, listener, and auto‑scaling resources. |
| `autoscaling_policy.json` | Example JSON representation of the target‑tracking scaling policy (included for reference). |
| `README.md` | This documentation. |

## Deployment Steps

1. **Build & Push Docker Image**  
   ```bash
   docker build -t laundry-api .
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <account-id>.dkr.ecr.<region>.amazonaws.com
   docker tag laundry-api:latest <account-id>.dkr.ecr.<region>.amazonaws.com/laundry-api:latest
   docker push <account-id>.dkr.ecr.<region>.amazonaws.com/laundry-api:latest
   ```

2. **Create IAM Roles**  
   - **ExecutionRoleArn** – Allows ECS to pull images from ECR and write logs to CloudWatch.  
   - **TaskRoleArn** – Grants the container any AWS permissions it needs (e.g., S3, DynamoDB).  

3. **Deploy CloudFormation Stack**  
   ```bash
   aws cloudformation deploy \
     --template-file infra/ecs_service.yaml \
     --stack-name laundrypool-prod \
     --parameter-overrides \
       VpcId=vpc-xxxxxx \
       SubnetIds='subnet-aaa,subnet-bbb' \
       ExecutionRoleArn=arn:aws:iam::123456789012:role/ecsTaskExecutionRole \
       TaskRoleArn=arn:aws:iam::123456789012:role/ecsTaskRole \
       ECRRepositoryUri=123456789012.dkr.ecr.<region>.amazonaws.com/laundry-api
   ```

4. **Verify**  
   - After the stack finishes, locate the `LoadBalancerDNS` output.  
   - Visit `http://<LoadBalancerDNS>/health` – it should return `{"status":"ok"}`.  

5. **Scaling**  
   The service is configured with a target‑tracking scaling policy that keeps average CPU utilization around **50 %**, scaling between **2** and **10** tasks automatically.

## Notes

- Adjust `cpu`, `memory`, and `DesiredCount` in `ecs_task_definition.json` and `ecs_service.yaml` to match your workload.  
- The task definition uses the `awsvpc` network mode, which requires each task to have its own ENI.  
- Security groups for the ALB and tasks should be added to the `SecurityGroups` property of the load balancer and the service’s `AwsvpcConfiguration` as needed.  

--- 

End of documentation.