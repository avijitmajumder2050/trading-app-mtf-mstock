import boto3
import logging

# ── Config ──
REGION = "ap-south-1"
SSM_PARAM_NAME = "/trading-bot-scanner/ec2/launch_template_id"

ec2 = boto3.client("ec2", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def get_launch_template_id():
    """Fetch Launch Template ID from Parameter Store"""
    try:
        response = ssm.get_parameter(Name=SSM_PARAM_NAME)
        lt_id = response['Parameter']['Value']
        logger.info(f"📦 Launch Template ID fetched from SSM: {lt_id}")
        return lt_id
    except Exception as e:
        logger.error(f"❌ Failed to fetch Launch Template ID: {e}")
        return None


def launch_ec2():
    """Launch EC2 using Launch Template ID from SSM"""
    lt_id = get_launch_template_id()
    if not lt_id:
        return {"status": "failed", "error": "Launch Template ID not found"}

    try:
        response = ec2.run_instances(
            LaunchTemplate={"LaunchTemplateId": lt_id, "Version": "$Latest"},
            MinCount=1,
            MaxCount=1
        )
        instance_id = response["Instances"][0]["InstanceId"]
        logger.info(f"✅ EC2 instance launched: {instance_id}")
        return {"status": "success", "instance_id": instance_id}

    except Exception as e:
        logger.error(f"❌ Failed to launch EC2: {e}")
        return {"status": "failed", "error": str(e)}


# ── Lambda Handler ──
def lambda_handler(event, context):
    return launch_ec2()


if __name__ == "__main__":
    print(launch_ec2())
