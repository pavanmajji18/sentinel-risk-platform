"""
SENTINEL Cloud Operations — AWS
================================
Demonstrates least-privilege IAM with a live S3 bucket:
  - create_corpus_bucket     : create the sentinel-corpus bucket
  - upload_documents         : upload sample corpus files
  - list_documents           : list objects with sizes
  - generate_presigned_url   : 15-minute presigned URL
  - list_ec2_families        : EC2 instance families and recommendations
  - cleanup                  : delete all objects and the bucket

Requires .env with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION.
"""

import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv

# ── Load environment ────────────────────────────────────────────────
load_dotenv()

BUCKET_NAME = os.getenv("BUCKET_NAME", "sentinel-corpus-main")
REGION = os.getenv("AWS_REGION", "us-east-1")
CORPUS_DIR = Path(__file__).parent / "sentinel_corpus"


def _s3_client():
    """Return an S3 client from environment credentials."""
    try:
        return boto3.client("s3", region_name=REGION)
    except NoCredentialsError:
        print("ERROR: AWS credentials not found. Set .env or configure AWS CLI.")
        sys.exit(1)


def _ec2_client():
    """Return an EC2 client from environment credentials."""
    try:
        return boto3.client("ec2", region_name=REGION)
    except NoCredentialsError:
        print("ERROR: AWS credentials not found.")
        sys.exit(1)


# ── 1. Create bucket ────────────────────────────────────────────────
def create_corpus_bucket(bucket_name: str) -> str:
    """Create an S3 bucket for the SENTINEL corpus.

    Returns the bucket name on success, or exits on failure.
    """
    s3 = _s3_client()
    try:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": REGION},
            )
        print(f"Bucket created: {bucket_name}")
        return bucket_name
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "BucketAlreadyOwnedByYou":
            print(f"Bucket '{bucket_name}' already exists — reusing it.")
            return bucket_name
        print(f"ERROR creating bucket: {exc}")
        sys.exit(1)


# ── 2. Upload documents ─────────────────────────────────────────────
def upload_documents(bucket_name: str) -> int:
    """Upload every file in sentinel_corpus/ to the bucket.

    Returns the number of files uploaded.
    """
    s3 = _s3_client()
    count = 0
    for file_path in sorted(CORPUS_DIR.iterdir()):
        if file_path.is_file():
            key = file_path.relative_to(Path(__file__).parent).as_posix()
            s3.upload_file(str(file_path), bucket_name, key)
            size = file_path.stat().st_size
            print(f"  Uploaded: {key}  ({size} bytes)")
            count += 1
    print(f"Total: {count} documents uploaded")
    return count


# ── 3. List documents ───────────────────────────────────────────────
def list_documents(bucket_name: str) -> None:
    """List every object in the bucket with its size (paginated)."""
    s3 = _s3_client()
    paginator = s3.get_paginator("list_objects_v2")
    total_size = 0
    total_count = 0
    try:
        for page in paginator.paginate(Bucket=bucket_name):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                size = obj["Size"]
                total_size += size
                total_count += 1
                print(f"  {key}  - {size} bytes")
        print(f"Total: {total_count} objects, {total_size} bytes")
    except ClientError as exc:
        print(f"ERROR listing objects: {exc}")


# ── 4. Presigned URL ────────────────────────────────────────────────
def generate_presigned_url(bucket_name: str, key: str, expires: int = 900) -> str:
    """Return a presigned URL that expires after *expires* seconds (default 15 min)."""
    s3 = _s3_client()
    url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket_name, "Key": key},
        ExpiresIn=expires,
    )
    print(f"  {url}")
    return url


# ── 5. EC2 instance families ────────────────────────────────────────
def list_ec2_families(region: str = "us-east-1") -> None:
    """Query and display EC2 instance families with example sizes."""
    ec2 = _ec2_client()
    # Known representative instance types per family
    families = {
        "general-purpose": "t3.micro",
        "compute-optimized": "c6i.large",
        "memory-optimized": "r6g.large",
        "storage-optimized": "i3.large",
        "accelerated": "p3.2xlarge",
    }

    for family, example in families.items():
        try:
            resp = ec2.describe_instance_types(InstanceTypes=[example])
            info = resp["InstanceTypes"][0]
            vcpu = info["VCpuInfo"]["DefaultVCpus"]
            mem = info["MemoryInfo"]["SizeInMiB"]
            print(
                f"Family: {family:25s} | Example: {example:15s} "
                f"| vCPU: {vcpu}  | Memory: {mem} MiB"
            )
        except ClientError as exc:
            print(f"  Could not describe {example}: {exc}")

    print()
    print(">>> Recommended for SENTINEL API (low traffic, cost-efficient):  t3.micro (general-purpose)")
    print(">>> Recommended for ML training (GPU-accelerated):              p3.2xlarge (accelerated)")


# ── 6. Cleanup ──────────────────────────────────────────────────────
def cleanup(bucket_name: str) -> None:
    """Delete every object in the bucket, then delete the bucket itself."""
    s3 = _s3_client()
    try:
        # Delete all objects
        objects = s3.list_objects_v2(Bucket=bucket_name).get("Contents", [])
        for obj in objects:
            s3.delete_object(Bucket=bucket_name, Key=obj["Key"])
        print(f"  Deleted {len(objects)} objects")

        # Delete the bucket
        s3.delete_bucket(Bucket=bucket_name)
        print(f"  Deleted bucket: {bucket_name}")
    except ClientError as exc:
        print(f"ERROR during cleanup: {exc}")


# ── Main ─────────────────────────────────────────────────────────────
def main():
    print("=== SENTINEL Cloud Operations ===")
    print(f"AWS Region: {REGION}\n")

    # 1. Create bucket
    print(f"--- Creating bucket: {BUCKET_NAME} ---")
    bucket = create_corpus_bucket(BUCKET_NAME)
    print()

    # 2. Upload documents
    print(f"--- Uploading documents from sentinel_corpus/ ---")
    upload_documents(bucket)
    print()

    # 3. List documents
    print(f"--- Listing documents in {bucket} ---")
    list_documents(bucket)
    print()

    # 4. Presigned URL
    print("--- Presigned URL (expires in 15 minutes) ---")
    if CORPUS_DIR.exists():
        first_doc = (CORPUS_DIR / "rbi_guidelines.md").relative_to(Path(__file__).parent)
        generate_presigned_url(bucket, first_doc.as_posix())
    print()

    # 5. EC2 families
    print("--- EC2 Instance Families ---")
    list_ec2_families(REGION)
    print()

    # 6. Cleanup
    print(f"--- Cleanup: deleting bucket {bucket} ---")
    cleanup(bucket)
    print()
    print("=== Done ===")


if __name__ == "__main__":
    main()
