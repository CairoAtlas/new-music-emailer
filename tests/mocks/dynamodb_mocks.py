import boto3

DYNAMODB = boto3.resource('dynamodb', region_name='us-east-1')


def mock_user_favorites_table(table_name):
    return DYNAMODB.create_table(
        AttributeDefinitions=[{'AttributeName': 'email', 'AttributeType': 'S'}],
        KeySchema=[{'KeyType': 'HASH', 'AttributeName': 'email'}],
        ProvisionedThroughput={'WriteCapacityUnits': 1, 'ReadCapacityUnits': 1},
        TableName=table_name
    )
