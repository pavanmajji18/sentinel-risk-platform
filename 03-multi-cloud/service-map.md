# SENTINEL Multi-Cloud Service Map

This document defines the cross-cloud infrastructure mapping and operational architecture for deploying the Sentinel Risk Platform across major cloud providers (AWS, Azure, and Google Cloud Platform).

---

## 1. Cloud Provider Component Mapping

| Functional Layer | AWS Implementation | Azure Implementation | GCP Implementation |
| :--- | :--- | :--- | :--- |
| **Compute Engine** | Amazon EC2 (`t3.micro` / `p3.2xlarge`) | Azure Virtual Machines (`Standard_B1s` / `Standard_NC6s_v3`) | Google Compute Engine (`e2-micro` / `a2-highgpu-1g`) |
| **Networking & Subnets** | Amazon VPC (Public Subnets across 2 AZs) | Azure Virtual Network (vNet + Subnets) | Google Cloud VPC Network (Custom Subnet) |
| **Traffic Distribution** | Application Load Balancer (ALB) | Azure Application Gateway | Google Cloud External HTTP(S) Load Balancer |
| **Access Control & Firewall** | Security Groups (`sentinel-alb-sg`, `sentinel-ec2-sg`) | Network Security Groups (NSG Inbound/Outbound Rules) | VPC Firewall Rules (`allow-http`, `allow-ssh`) |
| **Object Storage** | Amazon S3 (`sentinel-corpus-bucket`) | Azure Blob Storage (Storage Account + Container) | Google Cloud Storage (Standard Bucket) |
| **Identity & IAM** | IAM Role, Instance Profile & Least-Privilege Policy | Managed Identity & RBAC Role Assignment | Service Account & IAM Roles |
| **Observability** | Amazon CloudWatch Logs & Metrics | Azure Monitor & Log Analytics Workspace | Google Cloud Logging & Cloud Monitoring |

---

## 2. Shared Operational Standards

* **Stateless API Runtime:** Each compute instance runs the containerized FastAPI service exposing `/health`, `/v1/score`, and `/v2/score`.
* **Zero Shared Credentials:** Cross-cloud deployments avoid hardcoded credentials, utilizing provider-native instance identities and environment variables.
* **Network Isolation:** Compute nodes never expose internal ports directly to the public internet; traffic ingress is channeled through verified load balancers.
* **Corpus & Compliance Storage:** Regulatory documents and artifact hashes are verified across cloud object stores with secure presigned access URLs.

