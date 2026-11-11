# SENTINEL Risk API — Application

Core FastAPI application for transaction risk scoring.

---

## Overview

This is the application layer of the Risk API component. It implements:

- **Risk scoring endpoints** for single and batch transaction evaluation
- **Feature engineering pipeline** based on Sentinel rules
- **Model inference** using trained XGBoost model
- **File integrity verification** with SHA-256 hashing

---

## Key Modules

### `main.py`
The main FastAPI application containing:
- Risk scoring engine with multi-factor evaluation
- Feature extraction (velocity, amount, frequency, cross-entity risk)
- Model loading and inference pipeline
- Health check and model info endpoints
- File integrity verification

### `requirements.txt`
Python dependencies: FastAPI, Uvicorn, numpy, pandas, and model-serving libraries.

---

## Running

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The API serves on `http://localhost:8000` by default.

---

See [../README.md](../README.md) for the component-level documentation and
[../../README.md](../../README.md) for the full platform architecture.
