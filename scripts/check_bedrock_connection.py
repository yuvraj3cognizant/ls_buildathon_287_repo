import boto3

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1"
)

print("Connected Successfully")