# Route Autopsy — Backend

**AI-assisted vehicle-aware route investigation and counterfactual analysis.**

The Route Autopsy backend provides APIs for route calculation, vehicle restrictions, road defect intelligence, counterfactual scenario analysis, and multimodal road evidence processing.

Built with Python, FastAPI, Pydantic, and SQLite.

## Features

### Route Investigation
- Vehicle-aware route calculation.
- Alternative route generation.
- Road restriction evaluation.
- Defect-aware route assessment.
- Route suitability explanations.

### Counterfactual Autopsy Engine
- Road closure simulations.
- Defect severity scenarios.
- Vehicle specification changes.
- Restriction changes.
- Evidence-related scenarios.
- Baseline versus revised route comparison.
- Sensitivity analysis and explanations.

### Multimodal Evidence Processing
- Road image uploads.
- Meta Model API integration.
- Structured AI-generated observations.
- Candidate defect and restriction interpretation.
- Evidence review and confirmation workflow.
- Duplicate image detection.
- Evidence provenance and verification status.

### Vehicle Intelligence
- Vehicle specifications.
- Height, width and weight restrictions.
- Vehicle suitability checks.
- Missing specification handling.

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend programming |
| FastAPI | REST API framework |
| Pydantic | Request and response validation |
| SQLite | Database |
| Uvicorn | ASGI server |
| Requests | External API communication |
| Python-dotenv | Environment configuration |
| Pytest | Automated testing |

## Prerequisites

- Python 3.11 or newer
- pip
- Virtual environment support

## Installation

Navigate to the backend directory:

```bash
cd backend
```

Create a virtual environment:

**Windows PowerShell**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

For development and testing:

```bash
pip install -r requirements-dev.txt
```

## Environment Configuration

Copy the example configuration:

**Windows**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS**

```bash
cp .env.example .env
```

Configure `backend/.env`:

```env
# Database
DATABASE_PATH=

# CORS
CORS_ORIGINS=http://localhost:5180,http://127.0.0.1:5180

# Optional vehicle-source discovery
SERPAPI_API_KEY=
SERPAPI_TIMEOUT_SECONDS=20

# Meta multimodal AI
META_PROVIDER=meta_model_api
META_API_KEY=
META_MODEL=
META_API_BASE_URL=https://api.meta.ai/v1
META_TIMEOUT_SECONDS=45

# Image upload limit: 10 MB
EVIDENCE_MAX_UPLOAD_BYTES=10485760
```

### API configuration

| Variable | Description |
|---|---|
| `DATABASE_PATH` | SQLite database location |
| `CORS_ORIGINS` | Allowed frontend origins |
| `SERPAPI_API_KEY` | Optional vehicle-source discovery key |
| `META_PROVIDER` | Vision provider selection |
| `META_API_KEY` | Meta API authentication |
| `META_MODEL` | Supported image-capable model ID |
| `META_API_BASE_URL` | Meta API base URL |
| `META_TIMEOUT_SECONDS` | Model request timeout |
| `EVIDENCE_MAX_UPLOAD_BYTES` | Maximum image upload size |

Meta credentials must never be exposed to the frontend or committed to version control.

The application can run without Meta credentials for route investigation and counterfactual analysis. Live image analysis requires a configured vision provider.

## Database

The application uses SQLite.

Default database location:

```text
backend/routewise.db
```

A custom location can be configured using:

```env
DATABASE_PATH=C:/RouteAutopsy/data/routewise.db
```

No separate database server is required.

The application initializes its database through its startup process.

To reset the local demo database, stop the backend and delete the SQLite database file. Restart the backend to initialize it again.

**Warning:** Deleting the database permanently removes its stored records.

## Running the Backend

Start the FastAPI server:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The backend will be available at:

http://127.0.0.1:8000

### API Documentation

Swagger UI:

http://127.0.0.1:8000/docs

ReDoc:

http://127.0.0.1:8000/redoc

Health check:

http://127.0.0.1:8000/health

## API Modules

| API | Function |
|---|---|
| `/routes/investigate` | Vehicle-aware route investigation |
| `/autopsy/analyze` | Route counterfactual analysis |
| `/autopsy/scenario` | Scenario execution |
| `/evidence/analyze` | Road image analysis |
| `/evidence/confirm` | Evidence review and confirmation |
| `/vehicles` | Vehicle catalogue |
| `/defects` | Road defect management |
| `/restrictions` | Road restriction information |

For the complete and authoritative API contract, refer to:

`backend/docs/API_CONTRACT.md`

## Testing

Run the complete backend test suite:

```bash
python -m pytest tests -q
```

The project includes tests covering:

- Route candidate evaluation.
- Vehicle restrictions.
- Counterfactual analysis.
- Sensitivity calculations.
- Evidence upload validation.
- AI response parsing.
- Evidence confirmation.
- Duplicate image handling.
- API integration.
- Database safety.

## Meta Integration Verification

Configure a valid Meta API key and image-capable model ID in `.env`.

Then run:

```bash
python scripts/check_meta_live.py photo.jpg
```

A successful local stub test does not prove that live Meta inference works. Report live integration as verified only after a successful real API request.

## Security Considerations

- Store API credentials in backend environment variables.
- Never expose secrets through API responses.
- Validate image uploads and file sizes.
- Validate model responses before accepting observations.
- Keep AI-generated observations separate from verified road facts.
- Protect sensitive evidence-confirmation operations before public deployment.

## Known Limitations

- The seeded Kochi road network is illustrative demo data.
- Route recommendations are not verified real-world navigation.
- Sensitivity scores are not accident probabilities.
- AI-generated observations require appropriate human review.
- Live Meta functionality requires valid credentials and a supported model.
- Authentication and authorized verification workflows are not fully implemented.

## License

Developed for the Meta Global AI Developer Hackathon.
