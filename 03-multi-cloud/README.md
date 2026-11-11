# SENTINEL — Multi-Cloud Operations & Service Mapping (Module 03)

Cross-cloud infrastructure architecture and operational automation spanning **Amazon Web Services (AWS)**, **Microsoft Azure**, and **Google Cloud Platform (GCP)**.

---

## Architecture & Cross-Cloud Strategy

The Sentinel platform implements provider-agnostic infrastructure patterns ensuring uninterrupted compliance, zero-downtime regional failover, and regulatory compliance.

```
┌────────────────────────────────────────────────────────────────────────┐
│                      SENTINEL MULTI-CLOUD MATRIX                       │
├───────────────────────┬────────────────────────┬───────────────────────┤
│          AWS          │         Azure          │          GCP          │
├───────────────────────┼────────────────────────┼───────────────────────┤
│ • EC2 t3.micro        │ • Virtual Machines     │ • Compute Engine      │
│ • Application LB      │ • Application Gateway  │ • Cloud Load Balancing│
│ • S3 Regulatory Corpus│ • Blob Storage Account │ • Cloud Storage (GCS) │
│ • IAM Least Privilege │ • Managed Identity     │ • Service Accounts    │
│ • CloudWatch Metrics  │ • Azure Monitor        │ • Cloud Logging       │
└───────────────────────┴────────────────────────┴───────────────────────┘
```

For the complete technical breakdown and resource mappings, see [`service-map.md`](service-map.md).

---

## Regulatory Corpus & Storage Operations (`sentinel_cloud.py`)

Financial risk platforms require immutable storage and auditable distribution of regulatory standards, fraud circulars, and compliance playbooks. Module 03 provides an automated operational script (`sentinel_cloud.py`) managing the compliance corpus lifecycle on object storage:

1. **Bucket Provisioning:** Dynamically provisions or connects to an isolated, encrypted S3 bucket.
2. **Corpus Upload:** Ingests markdown playbooks and compliance documentation from `sentinel_corpus/`:
   * `rbi_guidelines.md`: Regulatory mandates and reporting standards.
   * `npci_rules.md`: Transaction velocity limits and chargeback processing rules.
   * `investigator_playbook.md`: Standard operating procedures for fraud investigations.
3. **Paginated Asset Listing:** Uses pagination cursors to inspect stored regulatory documents and byte sizes.
4. **Time-Limited Presigned URLs:** Generates cryptographically signed, expiring URLs (15-minute validity) granting secure, temporary access to investigators without exposing bucket credentials.
5. **Compute Recommendation Matrix:** Evaluates EC2 instance families via the AWS API to provide hardware recommendations (`t3.micro` for stateless API traffic; `p3.2xlarge` for GPU-accelerated gradient boosting).
6. **Audited Cleanup:** Safely purges ephemeral documents and buckets post-deployment.

---

## Local Setup & Execution

### 1. Configure Environment Variables
Copy `.env.example` to `.env` (or link to `02-infra-aws/.env`):
```bash
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
```

### 2. Run Operations Script
```bash
python sentinel_cloud.py
```

### 3. Run Automated Validation Test Suite
Module 03 includes a standalone validation test suite verifying live STS caller identities, S3 authentication, and the full mock lifecycle of document uploading and presigning:
```bash
python validate_module03.py
```

---

## File Structure

```
03-multi-cloud/
├── README.md               # Module architecture & operations guide
├── service-map.md          # Multi-cloud functional cross-reference
├── sentinel_cloud.py       # Cloud SDK storage & instance operations script
├── validate_module03.py    # Automated test suite (STS, S3, lifecycle)
├── iam_policy.json         # Least-privilege IAM policy document
├── requirements.txt        # Python cloud dependencies (boto3, python-dotenv)
├── .env.example            # Environment template for AWS/Azure/GCP
└── sentinel_corpus/        # Regulatory & compliance playbooks
    ├── investigator_playbook.md
    ├── npci_rules.md
    └── rbi_guidelines.md
```
