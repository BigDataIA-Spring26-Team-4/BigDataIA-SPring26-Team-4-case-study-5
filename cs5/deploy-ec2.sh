#!/usr/bin/env bash
#
# deploy-ec2.sh — Build Docker image, push to ECR, and deploy on a new EC2 instance.
#
# Prerequisites:
#   - AWS CLI v2 configured (aws configure)
#   - Docker installed locally
#   - An EC2 key pair (.pem file) already created in the target region
#
# Usage:
#   ./deploy-ec2.sh \
#     --key-name my-key       \
#     --key-file ~/.ssh/my-key.pem \
#     --region us-east-1      \
#     --instance-type t3.medium \
#     --env-file src/.env
#
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────
IMAGE_NAME="cs5-dashboard"
IMAGE_TAG="latest"
REGION="us-east-1"
INSTANCE_TYPE="t3.medium"
AMI_ID=""            # resolved automatically if blank
KEY_NAME=""
KEY_FILE=""
ENV_FILE=""
SECURITY_GROUP_NAME="cs5-dashboard-sg"

# ── Parse arguments ──────────────────────────────────────────────
usage() {
  echo "Usage: $0 --key-name NAME --key-file PATH [--region REGION] [--instance-type TYPE] [--env-file PATH]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --key-name)     KEY_NAME="$2";      shift 2 ;;
    --key-file)     KEY_FILE="$2";      shift 2 ;;
    --region)       REGION="$2";        shift 2 ;;
    --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
    --env-file)     ENV_FILE="$2";      shift 2 ;;
    --ami)          AMI_ID="$2";        shift 2 ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$KEY_NAME" ]] && { echo "ERROR: --key-name is required"; usage; }
[[ -z "$KEY_FILE" ]] && { echo "ERROR: --key-file is required"; usage; }
[[ ! -f "$KEY_FILE" ]] && { echo "ERROR: Key file not found: $KEY_FILE"; exit 1; }

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${IMAGE_NAME}"

echo "==> Configuration"
echo "    Region:        $REGION"
echo "    Instance type: $INSTANCE_TYPE"
echo "    ECR repo:      $ECR_REPO"
echo "    Key pair:      $KEY_NAME"
echo ""

# ── Step 1: Create ECR repository (if needed) ───────────────────
echo "==> Step 1: Ensuring ECR repository exists..."
aws ecr describe-repositories --repository-names "$IMAGE_NAME" --region "$REGION" 2>/dev/null \
  || aws ecr create-repository --repository-name "$IMAGE_NAME" --region "$REGION" --output text

# ── Step 2: Build Docker image ───────────────────────────────────
echo "==> Step 2: Building Docker image..."
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

# ── Step 3: Push to ECR ─────────────────────────────────────────
echo "==> Step 3: Authenticating with ECR and pushing image..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${ECR_REPO}:${IMAGE_TAG}"
docker push "${ECR_REPO}:${IMAGE_TAG}"

# ── Step 4: Create security group ───────────────────────────────
echo "==> Step 4: Setting up security group..."
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" --output text --region "$REGION")

SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=${SECURITY_GROUP_NAME}" "Name=vpc-id,Values=${VPC_ID}" \
  --query "SecurityGroups[0].GroupId" --output text --region "$REGION" 2>/dev/null || echo "None")

if [[ "$SG_ID" == "None" || -z "$SG_ID" ]]; then
  SG_ID=$(aws ec2 create-security-group \
    --group-name "$SECURITY_GROUP_NAME" \
    --description "CS5 Dashboard - Streamlit on 8501 + SSH" \
    --vpc-id "$VPC_ID" \
    --query "GroupId" --output text --region "$REGION")

  # SSH access
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
    --protocol tcp --port 22 --cidr 0.0.0.0/0

  # Streamlit port
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --region "$REGION" \
    --protocol tcp --port 8501 --cidr 0.0.0.0/0
fi
echo "    Security group: $SG_ID"

# ── Step 5: Resolve AMI (Amazon Linux 2023) ─────────────────────
if [[ -z "$AMI_ID" ]]; then
  echo "==> Step 5: Resolving latest Amazon Linux 2023 AMI..."
  AMI_ID=$(aws ec2 describe-images \
    --owners amazon \
    --filters "Name=name,Values=al2023-ami-2023.*-x86_64" "Name=state,Values=available" \
    --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" \
    --output text --region "$REGION")
fi
echo "    AMI: $AMI_ID"

# ── Step 6: Build user-data script ──────────────────────────────
echo "==> Step 6: Preparing EC2 user-data..."

# Collect env vars for the container
ENV_ARGS=""
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    # Skip comments and blank lines
    [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
    ENV_ARGS+=" -e ${line}"
  done < "$ENV_FILE"
fi

USER_DATA=$(cat <<USERDATA
#!/bin/bash
set -ex

# Install Docker
dnf install -y docker
systemctl enable docker
systemctl start docker

# Authenticate with ECR
aws ecr get-login-password --region ${REGION} \
  | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

# Pull and run the container
docker pull ${ECR_REPO}:${IMAGE_TAG}
docker run -d --restart unless-stopped \
  --name cs5-dashboard \
  -p 8501:8501 \
  ${ENV_ARGS} \
  ${ECR_REPO}:${IMAGE_TAG}
USERDATA
)

# ── Step 7: Create IAM instance profile for ECR access ──────────
echo "==> Step 7: Setting up IAM role for ECR pull..."
ROLE_NAME="cs5-ec2-ecr-role"
PROFILE_NAME="cs5-ec2-ecr-profile"

# Create role if it doesn't exist
if ! aws iam get-role --role-name "$ROLE_NAME" 2>/dev/null; then
  aws iam create-role --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }'
  aws iam attach-role-policy --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly

  aws iam create-instance-profile --instance-profile-name "$PROFILE_NAME" 2>/dev/null || true
  aws iam add-role-to-instance-profile \
    --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"

  echo "    Waiting for IAM profile propagation..."
  sleep 10
fi

# ── Step 8: Launch EC2 instance ─────────────────────────────────
echo "==> Step 8: Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile "Name=${PROFILE_NAME}" \
  --user-data "$USER_DATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=cs5-dashboard}]" \
  --query "Instances[0].InstanceId" \
  --output text \
  --region "$REGION")

echo "    Instance ID: $INSTANCE_ID"

# ── Step 9: Wait and print access info ──────────────────────────
echo "==> Step 9: Waiting for instance to get a public IP..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query "Reservations[0].Instances[0].PublicIpAddress" \
  --output text --region "$REGION")

echo ""
echo "====================================="
echo "  Deployment complete!"
echo "====================================="
echo ""
echo "  Instance ID:  $INSTANCE_ID"
echo "  Public IP:    $PUBLIC_IP"
echo "  Dashboard:    http://${PUBLIC_IP}:8501"
echo ""
echo "  SSH access:"
echo "    ssh -i $KEY_FILE ec2-user@$PUBLIC_IP"
echo ""
echo "  NOTE: The instance needs 1-2 minutes to install Docker"
echo "  and pull the image. If the dashboard isn't available"
echo "  immediately, wait and try again."
echo ""
