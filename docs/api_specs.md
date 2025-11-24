# Totl TPA Ingestion API

This API allows Third-Party Administrators (TPAs) to push real-time data to Totl for eligibility, accumulators, and referral events.

## Authentication
*Currently open for MVP/Demo. In production, use Bearer Token or mTLS.*

## Endpoints

### 1. Ingest Referral Event
Triggers the financial routing logic. If the referral is deemed "net-positive" or "high-risk", the member is engaged via SMS.

- **URL**: `/tpa/ingest/referral`
- **Method**: `POST`
- **Content-Type**: `application/json`

#### Payload
```json
{
  "member_id_str": "M001",
  "cpt_code": "73721",
  "provider_npi": "1234567890",
  "estimated_cost": 2000.0
}
```

#### Response
```json
{
  "status": "engaged",
  "reason": "Exceeds Deductible - Potential Savings"
}
```
OR
```json
{
  "status": "suppressed",
  "reason": "Below Deductible & Low Risk - No Employer Savings"
}
```

### 2. Update Accumulators
Updates the member's deductible and out-of-pocket status.

- **URL**: `/tpa/ingest/accumulators`
- **Method**: `POST`
- **Content-Type**: `application/json`

#### Payload
```json
{
  "member_id_str": "M001",
  "deductible_met": 1500.00,
  "oop_met": 1500.00
}
```

#### Response
```json
{
  "status": "updated"
}
```

## Data Models

### Referral Event
| Field | Type | Description |
|-------|------|-------------|
| `member_id_str` | String | The unique member ID assigned by the TPA/Employer. |
| `cpt_code` | String | The procedure code (e.g., 73721 for MRI). |
| `provider_npi` | String | The NPI of the ordering provider. |
| `estimated_cost` | Float | The estimated cost of the procedure at the current location (optional, defaults to 1000.0). |

### Accumulator
| Field | Type | Description |
|-------|------|-------------|
| `deductible_met` | Float | Amount paid towards deductible YTD. |
| `oop_met` | Float | Amount paid towards Out-of-Pocket Max YTD. |
