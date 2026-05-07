# MediAI — AI Medical Triage & Health Assistant Platform

A full-stack AI-powered medical triage platform using **RAG architecture**, **LangGraph orchestration**, **Groq LLM**, and optional **vision-based symptom image analysis** to deliver knowledge-grounded health assessments.

---

## Architecture Overview

```
Frontend (HTML/Bootstrap/JS)
        ↓  REST / AJAX
PHP Application Layer (Auth, DB, File Management)
        ↓  REST API
FastAPI AI Service (Python)
    ├── LangGraph Workflow
    │     ├── RAG Retrieval Node
    │     ├── Question Generator Node
    │     ├── Triage Engine Node
    │     ├── Explanation Generator Node
    │     └── Report Generator Node
    ├── Groq LLM (llama3-70b-8192)
    ├── Optional Gemini Vision Analysis
    └── FAISS Vector Store
          └── CSV Knowledge Base
                ├── symptoms.csv
                ├── doctors.csv
                └── hospitals.csv
```

---

## Project Structure

```
medical_triage/
├── frontend/
│   ├── index.html                  Landing page
│   ├── css/
│   │   └── main.css                Full design system
│   ├── js/
│   │   ├── main.js                 Utilities & API helpers
│   │   ├── auth.js                 Login / register
│   │   ├── symptom-chat-fixed.js   Core AI chat + symptom image upload
│   │   ├── dashboard.js
│   │   ├── reports.js
│   │   ├── doctors.js
│   │   ├── documents.js
│   │   ├── medications.js
│   │   └── appointments.js
│   └── pages/
│       ├── login.html
│       ├── register.html
│       ├── dashboard.html
│       ├── symptom-chat.html       AI triage chat with rash/cut photo upload
│       ├── reports.html
│       ├── documents.html          Upload & OCR
│       ├── medications.html
│       ├── doctors.html            Doctor finder
│       ├── appointments.html
│       └── hospital-dashboard.html Hospital intake queue
│
├── backend_php/
│   ├── includes/
│   │   └── config.php              DB connection, helpers
│   ├── auth/
│   │   ├── login.php
│   │   └── register.php
│   ├── api/
│   │   ├── dashboard.php
│   │   ├── reports.php
│   │   ├── appointments.php
│   │   ├── medications.php
│   │   └── upload.php
│   └── uploads/                    Uploaded medical files
│
├── fastapi_ai/
│   ├── main.py                     FastAPI entry point
│   ├── workflow.py                 LangGraph pipeline
│   ├── requirements.txt
│   ├── models/
│   │   ├── schemas.py              Pydantic models
│   │   └── llm_client.py           Groq API wrapper
│   ├── prompts/
│   │   └── templates.py            All LLM prompt templates
│   └── routes/
│       ├── triage.py               POST /generate-questions, /generate-report
│       ├── documents.py            POST /analyze-document
│       ├── doctors.py              GET  /doctor-recommendation
│       └── symptom_images.py       POST /analyze-symptom-image
│
├── rag_pipeline/
│   ├── rag_engine.py               FAISS index builder & retriever
│   ├── build_index.py              CLI to build the vector index
│   └── data/
│       ├── symptoms.csv            Symptom → condition → specialist KB
│       ├── doctors.csv             Doctor directory
│       └── hospitals.csv           Hospital directory
│
├── vector_store/                   FAISS index files (auto-generated)
├── database/
│   └── schema.sql                  MySQL schema + seed data
└── .env.example                    Environment variable template
```

---

## Quick Start

### 1. Database setup

```bash
mysql -u root -p < database/schema.sql
```

### 2. PHP backend

Serve `backend_php/` with Apache or Nginx (or PHP built-in server):

```bash
cd backend_php
php -S localhost:8080
```

Update `DB_PASS` in `backend_php/includes/config.php`.

### 3. FastAPI AI service

```bash
cd fastapi_ai

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp ../.env.example ../.env
# Edit .env and set GROQ_API_KEY
# Optional: set GEMINI_API_KEY for rash/cut/wound image analysis

# Build the RAG vector index
cd ..
python rag_pipeline/build_index.py --test

# Start the AI service
cd fastapi_ai
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Frontend

Open `frontend/index.html` in a browser, or serve with any static server:

```bash
cd frontend
python -m http.server 3000
# Open http://localhost:3000
```

---

## API Endpoints (FastAPI)

| Method | Endpoint                 | Description                            |
| ------ | ------------------------ | -------------------------------------- |
| POST   | `/generate-questions`    | RAG retrieval + follow-up questions    |
| POST   | `/generate-report`       | Full triage analysis + report          |
| POST   | `/submit-answers`        | Alias for `/generate-report`           |
| POST   | `/analyze-document`      | OCR + AI extraction from medical docs  |
| POST   | `/analyze-symptom-image` | Supportive rash/cut/wound image review |
| GET    | `/doctor-recommendation` | Filter doctors by specialty/location   |
| GET    | `/health`                | Service health check                   |

### Example: Generate questions

```bash
curl -X POST http://localhost:8000/generate-questions \
  -H "Content-Type: application/json" \
  -d '{"symptom": "high fever and severe headache", "user_id": 1}'
```

### Example: Generate triage report

```bash
curl -X POST http://localhost:8000/generate-report \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "ABC123",
    "symptom": "high fever and severe headache",
    "answers": ["3 days", "8 out of 10", "Also have joint pain and nausea"],
    "user_id": 1
  }'
```

### Example: Analyze a symptom image

```bash
curl -X POST http://localhost:8000/analyze-symptom-image \
  -F "file=@rash_photo.jpg"
```

This endpoint accepts JPG, PNG, or WEBP files up to 8MB. If `GEMINI_API_KEY` is configured, MediAI uses Gemini Flash/Flash-Lite for supportive visual observations. If no vision key is configured, the endpoint returns a low-confidence fallback so the uploaded image can still be included in the triage conversation. Image review is supportive only and does not provide a definitive diagnosis.

---

## LangGraph Workflow

The AI pipeline uses LangGraph to orchestrate a multi-step graph:

```
Phase 1 — Question Generation:
  User symptom (+ optional symptom image) → RAG Retrieval → Generate Questions → Return to frontend

Phase 2 — Report Generation (after user answers):
  Answers + symptom + image observations → Re-retrieve enriched context → Triage Analysis
  → Explanation Generation → Final Report
```

Each node is a pure function operating on a shared `TriageState`:

| Node                   | Input                   | Output                     |
| ---------------------- | ----------------------- | -------------------------- |
| `rag_retrieval`        | symptom text            | retrieved_context          |
| `generate_questions`   | symptom + context       | followup_questions list    |
| `process_answers`      | symptom + answers       | enriched retrieved_context |
| `triage_engine`        | all data + context      | triage_result dict         |
| `generate_explanation` | triage_result + context | explanation string         |
| `generate_report`      | all state               | final report dict          |

### Symptom Image Support

The symptom assessment chat includes an optional image upload control for visible issues such as rashes, cuts, wounds, burns, swelling, pus, or suspected skin infection. Uploaded images are sent to `/analyze-symptom-image`, summarized as supportive observations, and folded into the final triage report. The assistant is prompted to ask for a clear photo when the symptom description suggests a visible affected area.

Safety boundaries:

- Image observations are supportive context only.
- MediAI does not diagnose from an image alone.
- The report recommends clinician review when visual symptoms are worsening, spreading, painful, draining pus, or accompanied by fever.

---

## RAG Knowledge System

Three CSV files form the knowledge base:

| File            | Fields                                                        |
| --------------- | ------------------------------------------------------------- |
| `symptoms.csv`  | symptom, related_conditions, severity, recommended_specialist |
| `doctors.csv`   | doctor_name, specialization, hospital, location, availability |
| `hospitals.csv` | hospital_name, location, emergency_services, beds, contact    |

**To extend the knowledge base:** add rows to the CSVs, then rebuild:

```bash
python rag_pipeline/build_index.py --force
```

**Embedding model:** `all-MiniLM-L6-v2` (Sentence Transformers)
**Vector store:** FAISS IndexFlatL2

---

## PHP API Endpoints

| Method          | File                    | Description         |
| --------------- | ----------------------- | ------------------- |
| POST            | `/auth/register.php`    | User registration   |
| POST            | `/auth/login.php`       | User login          |
| GET             | `/api/dashboard.php`    | Dashboard stats     |
| GET/POST        | `/api/reports.php`      | Triage reports CRUD |
| GET/POST/PUT    | `/api/appointments.php` | Appointments CRUD   |
| GET/POST/DELETE | `/api/medications.php`  | Medications CRUD    |
| GET/POST        | `/api/upload.php`       | Document upload     |

---

## Demo Mode

All frontend pages include **graceful offline fallback** — if the PHP backend or FastAPI service is unreachable, demo data is used automatically. This allows the UI to be fully browseable without any backend running.

---

## Security Checklist

- [x] Passwords hashed with `password_hash()` (bcrypt)
- [x] PDO prepared statements (SQL injection prevention)
- [x] File upload MIME type validation
- [x] File size limits (10MB)
- [x] CORS headers on all API endpoints
- [x] Input sanitization on all PHP endpoints
- [ ] HTTPS (configure in production web server)
- [ ] JWT token authentication (extend from session-based)
- [ ] Rate limiting on AI endpoints

---

## Environment Variables

| Variable       | Description                        |
| -------------- | ---------------------------------- |
| `GROQ_API_KEY` | Your Groq API key                  |
| `GEMINI_API_KEY` | Optional Gemini key for symptom image analysis |
| `GEMINI_VISION_MODEL` | Optional vision model name, default `gemini-2.5-flash-lite` |
| `DB_HOST`      | MySQL host (default: localhost)    |
| `DB_NAME`      | Database name (default: mediai_db) |
| `DB_USER`      | MySQL username                     |
| `DB_PASS`      | MySQL password                     |

Get a free Groq API key at: https://console.groq.com

---

## MVP Development Phases

- **Phase 1** ✅ Authentication + Symptom Chat Interface
- **Phase 2** ✅ RAG Knowledge Retrieval + Triage Engine
- **Phase 3** ✅ Report Generation + Doctor Recommendation
- **Phase 4** ✅ Document Upload + Medication Reminders + Symptom Image Upload
- **Phase 5** 🔜 Telemedicine + Wearable Integration

---

## Tech Stack

| Layer            | Technology                           |
| ---------------- | ------------------------------------ |
| Frontend         | HTML5, CSS3, Bootstrap 5, Vanilla JS |
| Application      | PHP 8.1+, MySQL 8.0+                 |
| AI Service       | Python 3.11+, FastAPI, Uvicorn       |
| LLM              | Groq API (llama3-70b-8192)           |
| Vision Analysis  | Optional Gemini Flash/Flash-Lite     |
| AI Orchestration | LangGraph                            |
| Embeddings       | Sentence Transformers (MiniLM-L6-v2) |
| Vector Store     | FAISS                                |
| OCR              | Tesseract + pdfplumber               |

---

_For informational and educational purposes only. This system does not replace professional medical advice, diagnosis, or treatment._
