import os
import boto3
from botocore.client import Config

S3_ENDPOINT = os.getenv("S3_ENDPOINT")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")


def get_s3_client():
    if not S3_ENDPOINT:
        # Use default AWS
        return boto3.client('s3')
    return boto3.client(
        's3',
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
        config=Config(signature_version='s3v4')
    )


def ensure_bucket(bucket: str = None):
    bucket = bucket or S3_BUCKET
    if not bucket:
        raise RuntimeError('S3_BUCKET is not configured')
    s3 = get_s3_client()
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)


def upload_file(local_path: str, key: str, bucket: str = None):
    bucket = bucket or S3_BUCKET
    if not bucket:
        raise RuntimeError('S3_BUCKET is not configured')
    s3 = get_s3_client()
    ensure_bucket(bucket)
    s3.upload_file(local_path, bucket, key)
    return key


def get_presigned_url(key: str, expires_in: int = 3600, bucket: str = None):
    bucket = bucket or S3_BUCKET
    if not bucket:
        raise RuntimeError('S3_BUCKET is not configured')
    s3 = get_s3_client()
    return s3.generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=expires_in)
