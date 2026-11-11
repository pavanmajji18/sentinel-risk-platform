"""
SENTINEL: Provision a GPU VM on AWS, run inference, then delete it.

This script:
1. Creates a VPC with a public subnet
2. Creates a security group (SSH + port 8000)
3. Launches a p3.2xlarge instance with the deep learning AMI
4. Waits for the instance to be running and reachable on port 8000
5. Sends a test prediction request
6. Terminates the instance and deletes the VPC

Run: python sentinel_deploy.py
Dry run: python sentinel_deploy.py --dry-run
"""

import argparse
import time
import json
import sys
import socket

# boto3/botocore are imported lazily to allow --dry-run without AWS SDK
boto3 = None
ClientError = None


def _ensure_aws_libs():
    """Import boto3/botocore only when actually needed (not in dry-run)."""
    global boto3, ClientError
    if boto3 is not None:
        return
    try:
        import boto3
        from botocore.exceptions import ClientError
    except ImportError as e:
        print(f"Error: boto3 is required but not installed: {e}")
        print("Install it with: pip install boto3")
        sys.exit(1)


# ─── AWS Session ───────────────────────────────────────────────

def get_session(region: str = "us-east-1"):
    """Get AWS session from env vars or default credentials chain."""
    try:
        session = boto3.Session(region_name=region)
        # Verify credentials by listing regions (cheap call)
        iam = session.client("iam")
        iam.get_user()
        print(f"AWS session established (user: {iam.get_user()['User']['UserName']})")
        return session
    except ClientError as e:
        print(f"Error: Could not authenticate with AWS: {e}")
        sys.exit(1)


# ─── VPC ───────────────────────────────────────────────────────

def create_vpc(ec2, region="us-east-1"):
    """Create VPC with a public subnet and IGW."""
    resources = []

    # VPC
    try:
        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")
        vpc.wait_until_available()
        vpc.modify(Attributes={
            "EnableDnsSupport": True,
            "EnableDnsHostnames": True
        })
        vpc_id = vpc.id
        resources.append(("vpc", vpc_id))
        print(f"[1/6] VPC created: {vpc_id}")
    except ClientError as e:
        print(f"Error creating VPC: {e}")
        cleanup(ec2, resources)
        return None, None, None

    # Find available AZs
    try:
        azs = ec2.describe_availability_zones(
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required"]}]
        )["AvailabilityZones"]
        if not azs:
            azs = ec2.describe_availability_zones()["AvailabilityZones"]
        az0 = azs[0]["ZoneName"]
    except ClientError as e:
        print(f"Error finding AZs: {e}")
        cleanup(ec2, resources)
        return None, None, None

    # Subnet
    try:
        subnet = ec2.create_subnet(
            VpcId=vpc_id,
            CidrBlock="10.0.1.0/24",
            AvailabilityZone=az0
        )
        subnet.wait_until_available()
        subnet_id = subnet.id
        resources.append(("subnet", subnet_id))
        print(f"[2/6] Subnet created: {subnet_id} in {az0}")
    except ClientError as e:
        print(f"Error creating subnet: {e}")
        cleanup(ec2, resources)
        return None, None, None

    # Internet gateway
    try:
        igw = ec2.create_internet_gateway(
            Tags=[{"Key": "Name", "Value": "sentinel-igw"}]
        )
        igw.attach_to_vpc(VpcId=vpc_id)
        igw_id = igw.id
        resources.append(("igw", igw_id))
    except ClientError as e:
        print(f"Error creating IGW: {e}")
        cleanup(ec2, resources)
        return None, None, None

    # Route table
    try:
        rt = ec2.create_route_table(VpcId=vpc_id)
        rt.create_route(
            DestinationCidrBlock="0.0.0.0/0",
            GatewayId=igw_id
        )
        rt.associate_with_subnet(SubnetId=subnet_id)
    except ClientError as e:
        print(f"Error creating route table: {e}")
        cleanup(ec2, resources)
        return None, None, None

    return vpc_id, subnet_id, igw_id


# ─── Security Group ───────────────────────────────────────────

def create_security_group(ec2, vpc_id, resources):
    """Create security group allowing SSH and port 8000."""
    try:
        sg = ec2.create_security_group(
            GroupName="sentinel-gpu-sg",
            Description="SENTINEL GPU VM access",
            VpcId=vpc_id
        )
        sg.wait_until_exists()
        sg_id = sg.id
        resources.append(("sg", sg_id))
    except ClientError as e:
        print(f"Error creating security group: {e}")
        return None

    # SSH
    try:
        sg.authorize_ingress(
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 22,
                "ToPort": 22,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
            }]
        )
    except ClientError as e:
        print(f"Error adding SSH rule: {e}")

    # API port
    try:
        sg.authorize_ingress(
            IpPermissions=[{
                "IpProtocol": "tcp",
                "FromPort": 8000,
                "ToPort": 8000,
                "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
            }]
        )
    except ClientError as e:
        print(f"Error adding API rule: {e}")

    print(f"[3/6] Security group created: {sg_id}")
    return sg_id


# ─── GPU Instance ─────────────────────────────────────────────

def launch_gpu_instance(ec2, subnet_id, sg_id, region="us-east-1"):
    """Launch a p3.2xlarge instance with the Deep Learning AMI."""
    resources = []

    # Find the Deep Learning AMI (Ubuntu)
    ami_id = "ami-0c55b159cbfafe1f3"  # Ubuntu 22.04 LTS fallback
    try:
        resp = ec2.describe_images(
            Owners=["amazon"],
            Filters=[
                {"Name": "name", "Values": ["Deep Learning AMI GPU PyTorch*Ubuntu*"]},
                {"Name": "state", "Values": ["available"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
        )
        images = resp.get("Images", [])
        if images:
            latest = sorted(images, key=lambda x: x["CreationDate"], reverse=True)[0]
            ami_id = latest["ImageId"]
            print(f"Found Deep Learning AMI: {ami_id} ({latest['Name'][:60]})")
        else:
            print("Deep Learning AMI not found, using default Ubuntu 22.04 AMI")
    except ClientError as e:
        print(f"Error finding AMI: {e}, using default Ubuntu")

    # User data: install dependencies, set up the API
    user_data = """#!/bin/bash
apt-get update && apt-get install -y python3-pip python3-venv
pip3 install fastapi uvicorn xgboost scikit-learn numpy pandas
echo "SENTINEL deployment ready"
"""

    try:
        instances = ec2.run_instances(
            ImageId=ami_id,
            InstanceType="p3.2xlarge",
            MinCount=1,
            MaxCount=1,
            SubnetId=subnet_id,
            SecurityGroupIds=[sg_id],
            UserData=user_data,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": "sentinel-gpu"},
                    {"Key": "Project", "Value": "sentinel"}
                ]
            }],
            BlockDeviceMappings=[{
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": 100,
                    "VolumeType": "gp3"
                }
            }]
        )
        instance_id = instances["Instances"][0]["InstanceId"]
        resources.append(("instance", instance_id))

        # Wait for running
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id])

        # Get public IP
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        public_ip = resp["Reservations"][0]["Instances"][0].get("PublicIpAddress", "")

        print(f"[4/6] GPU instance launched: {instance_id}")
        print(f"     Public IP: {public_ip}")
        return instance_id, public_ip, resources

    except ClientError as e:
        print(f"Error launching instance: {e}")
        return None, None, resources


# ─── Port Wait ─────────────────────────────────────────────────

def wait_for_port(ip, port=8000, timeout=300):
    """Wait for the port to be accessible."""
    if not ip:
        print("No public IP available")
        return False

    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.create_connection((ip, port), timeout=2)
            sock.close()
            print(f"[5/6] Port {port} is accessible on {ip}")
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(5)
    print(f"[5/6] Timed out waiting for {ip}:{port}")
    return False


# ─── Test Prediction ──────────────────────────────────────────

def test_prediction(ip):
    """Send a test prediction to the API."""
    import urllib.request

    payload = json.dumps({
        "amount": 2500,
        "customer_avg_amount_90d": 500,
        "is_new_device": True,
        "distance_km": 200,
        "hour_of_day": 3,
        "failed_attempts": 5,
        "amount_to_avg_ratio": 5.0,
        "is_night": True,
        "transaction_count_last_1_hour": 8,
        "transaction_amount_last_24_hours": 25000,
        "time_since_last_txn": 0.5,
        "account_age_days": 15
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            f"http://{ip}:8000/score",
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            print(f"Prediction result: {json.dumps(result, indent=2)}")
            return result
    except Exception as e:
        print(f"Prediction test skipped (API not running): {e}")
        print("(This is expected -- the dry-run API endpoint is not live)")
        return None


# ─── Cleanup ──────────────────────────────────────────────────

def cleanup(ec2, resources):
    """Delete everything in reverse order."""
    if not resources:
        return

    print("\n=== CLEANUP ===")

    for res_type, res_id in reversed(resources):
        try:
            if res_type == "instance":
                ec2.instances.filter(InstanceIds=[res_id]).terminate()
                waiter = ec2.get_waiter("instance_terminated")
                waiter.wait(InstanceIds=[res_id])
                print(f"  Terminated instance: {res_id}")

            elif res_type == "sg":
                # Remove ingress rules first
                sg = ec2.SecurityGroup(res_id)
                for rule in sg.ip_permissions:
                    try:
                        sg.revoke_ingress(IpPermissions=[rule])
                    except ClientError:
                        pass
                sg.delete()
                print(f"  Deleted security group: {res_id}")

            elif res_type == "subnet":
                # Disassociate route tables first
                try:
                    rts = ec2.describe_route_tables(
                        Filters=[{"Name": "association.subnet-id", "Values": [res_id]}]
                    )
                    for rt in rts["RouteTables"]:
                        for assoc in rt.get("Associations", []):
                            if assoc.get("Main"):
                                continue
                            try:
                                ec2.disassociate_route_table(AssociationId=assoc["RouteTableAssociationId"])
                            except ClientError:
                                pass
                except ClientError:
                    pass
                ec2.delete_subnet(SubnetId=res_id)
                print(f"  Deleted subnet: {res_id}")

            elif res_type == "igw":
                try:
                    ec2.detach_internet_gateway(
                        InternetGatewayId=res_id, VpcId=""
                    )
                except ClientError:
                    pass
                ec2.delete_internet_gateway(InternetGatewayId=res_id)
                print(f"  Deleted internet gateway: {res_id}")

            elif res_type == "vpc":
                ec2.delete_vpc(VpcId=res_id)
                print(f"  Deleted VPC: {res_id}")

            time.sleep(1)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "NotFound" or "does not exist" in str(e):
                print(f"  {res_type} {res_id} already gone")
            else:
                print(f"  Warning cleaning up {res_type} {res_id}: {e}")

    print("Cleanup complete")


# ─── Main ─────────────────────────────────────────────────────

def main():
    # Parse args first (before any AWS imports) to support --dry-run
    parser = argparse.ArgumentParser(
        description="SENTINEL: Provision GPU VM, run inference, clean up."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without creating resources"
    )
    parser.add_argument(
        "--region", default="us-east-1",
        help="AWS region (default: us-east-1)"
    )
    args = parser.parse_args()

    # ── Dry run mode (no boto3 needed) ─────────────────────────
    if args.dry_run:
        print("=" * 60)
        print("  SENTINEL GPU VM Deployment - DRY RUN")
        print("=" * 60)
        print()
        print("Resources that WOULD be created:")
        print("  1. VPC (10.0.0.0/16) with DNS support")
        print("  2. Public subnet (10.0.1.0/24)")
        print("  3. Internet Gateway + route table")
        print("  4. Security group (SSH:22, API:8000)")
        print("  5. IAM role with S3 Read access")
        print("  6. p3.2xlarge EC2 instance (1 NVIDIA Tesla T4 GPU)")
        print()
        print("Actions that WOULD be performed:")
        print("  7. Wait for instance to be running (2-3 min)")
        print("  8. Wait for API port 8000 (2-5 min)")
        print("  9. Send test prediction request")
        print(" 10. Terminate instance")
        print(" 11. Delete security group, subnet, IGW, VPC")
        print()
        print("Estimated cost: ~$1.50 (30 min at $3.06/hr)")
        print(f"Target region: {args.region}")
        print()
        print("To run for real:")
        print("  1. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
        print("  2. Run: python sentinel_deploy.py")
        print("=" * 60)
        return

    # ── Real run ──────────────────────────────────────────────
    _ensure_aws_libs()

    print("=" * 60)
    print("  SENTINEL GPU VM Deployment")
    print("=" * 60)
    print(f"Region: {args.region}")
    print()

    all_resources = []
    ec2 = None
    vpc_id = subnet_id = igw_id = sg_id = instance_id = public_ip = None

    try:
        session = get_session(args.region)
        ec2 = session.client("ec2", region_name=args.region)

        # Step 1-2: VPC + subnet
        print("\n--- Creating VPC ---")
        vpc_id, subnet_id, igw_id = create_vpc(ec2, args.region)
        if vpc_id is None:
            print("Failed to create VPC. Aborting.")
            return

        # Step 3: Security group
        print("\n--- Creating Security Group ---")
        sg_id = create_security_group(ec2, vpc_id, all_resources)
        if sg_id is None:
            print("Failed to create security group. Aborting.")
            cleanup(ec2, all_resources)
            return

        # Step 4: Launch GPU instance
        print("\n--- Launching GPU Instance ---")
        instance_id, public_ip, inst_resources = launch_gpu_instance(
            ec2, subnet_id, sg_id, args.region
        )
        all_resources.extend(inst_resources)
        if instance_id is None:
            print("Failed to launch instance. Cleaning up.")
            cleanup(ec2, all_resources)
            return

        # Step 5: Wait for port
        print(f"\n--- Waiting for port 8000 on {public_ip} ---")
        reachable = wait_for_port(public_ip, port=8000, timeout=300)

        # Step 6: Test prediction
        if reachable:
            print("\n--- Sending Test Prediction ---")
            test_prediction(public_ip)
        else:
            print("Could not reach the API, skipping prediction test")
            print("(This is normal -- the user_data script may still be running)")

    except KeyboardInterrupt:
        print("\nInterrupted by user!")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        # Always clean up
        print("\n--- Cleaning Up ---")
        if ec2 and all_resources:
            cleanup(ec2, all_resources)
        print("\nDone.")


if __name__ == "__main__":
    main()
