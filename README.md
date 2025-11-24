# Totl - Zero-Cost Lab & Imaging Routing

Totl helps self-funded employers steer members to $0-cost labs and imaging facilities using SMS and EOB-based pricing.

## Features
- **Member Flow**: SMS/MMS based. Members text a photo of their referral.
- **AI Processing**: Uses Google Gemini to extract CPT codes from referral images.
- **Smart Routing**: Finds the lowest cost facilities based on historical EOB data.
- **Admin Dashboard**: Simple web UI to manage eligibility, EOBs, and campaigns.

## Prerequisites
- Docker & Docker Compose
- Twilio Account (SID, Token, Phone Number)
- Google AI Studio API Key (Gemini)

## Setup

1. **Clone the repository**
2. **Create .env file**
   Copy `.env.example` to `.env` and fill in your secrets.
   ```bash
   cp .env.example .env
   ```
   *Note: For local docker-compose, `DATABASE_URL` is already set correctly in the compose file, but you can override it.*

3. **Run with Docker Compose**
   ```bash
   docker-compose up --build
   ```
   The app will be available at `http://localhost:8000`.

4. **Access Admin UI**
   - Go to `http://localhost:8000/admin/login`
   - Default credentials (if no users exist): `admin` / `admin`

## Development

### Local Setup (No Docker)
1. Install dependencies: `pip install -r requirements.txt`
2. Run Postgres locally.
3. Set `DATABASE_URL` in `.env`.
4. Run app: `uvicorn app.main:app --reload`

### Twilio Webhook
To test locally, use **ngrok** to expose port 8000:
```bash
ngrok http 8000
```
Configure your Twilio Phone Number's Messaging Webhook to:
`https://<your-ngrok-url>/twilio/webhook`

## Deployment (AWS)

### Elastic Beanstalk / ECS
1. **Environment Variables**: Set all variables from `.env` in the AWS console.
2. **Database**: Use RDS (Postgres). Update `DATABASE_URL` to point to RDS.
3. **Ports**: The container exposes port 8000. Configure the Load Balancer to forward port 80 to 8000.
4. **Twilio**: Update the webhook URL to your production domain.

## Project Structure
- `app/main.py`: Entry point.
- `app/routes/`: API endpoints.
- `app/services/`: Business logic (Gemini, Twilio, Pricing).
- `app/db/`: Database models.
- `app/templates/`: Admin UI templates.

## Testing
Run unit tests:
```bash
pytest
```
