import boto3
import json

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1"
)

response = client.invoke_model(
    modelId="amazon.nova-pro-v1:0",
    body=json.dumps({
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "text": "Reply with only: Bedrock Nova Working"
                    }
                ]
            }
        ]
    })
)

result = response["body"].read().decode()

print(result)