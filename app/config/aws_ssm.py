import boto3
from botocore.exceptions import ClientError

_ssm = boto3.client("ssm", region_name="ap-south-1")

def get_param(name: str, decrypt: bool = True, default: str | None = None) -> str:
    try:
        response = _ssm.get_parameter(
            Name=name,
            WithDecryption=decrypt
        )
        return response["Parameter"]["Value"]
    except ClientError as e:
        if default is not None and e.response["Error"]["Code"] == "ParameterNotFound":
            return default
        raise
