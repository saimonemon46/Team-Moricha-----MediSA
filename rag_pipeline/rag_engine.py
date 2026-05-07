# ============================================================
# MediAI — RAG Pipeline
# Builds FAISS vector store from CSV knowledge base
# and provides similarity search retrieval
# ============================================================

import os
import csv
import json
import pickle
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Lazy imports — installed at runtime
try:
    import faiss
    from sentence_transformers import SentenceTransformer
    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False

BASE_DIR   = Path(__file__).parent.parent
DATA_DIR   = BASE_DIR / "rag_pipeline" / "data"
STORE_DIR  = BASE_DIR / "vector_store"
INDEX_PATH = STORE_DIR / "mediai.faiss"
DOCS_PATH  = STORE_DIR / "mediai_docs.pkl"

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"

_model = None
_index = None
_documents: List[str] = []


def get_embed_model():
    global _model
    if _model is None and RAG_AVAILABLE:
        try:
            _model = SentenceTransformer(EMBED_MODEL_NAME, local_files_only=True)
        except Exception:
            try:
                _model = SentenceTransformer(EMBED_MODEL_NAME)
            except Exception as exc:
                print(f"[RAG] Embedding model unavailable; using keyword retrieval. {exc}")
                return None
    return _model


def embed(texts: List[str]) -> Optional[np.ndarray]:
    """Embed a list of texts and return numpy float32 array."""
    model = get_embed_model()
    if model is None:
        return None
    vecs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return vecs.astype("float32")


# ---- Document loading ----

def _normalise_header(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name or "").strip().lower()).strip("_")


def _clean(value) -> str:
    return " ".join(str(value or "").replace("_", " ").replace("\ufeff", "").replace("\ufffd", "").split())


def _row_value(row: dict, *names: str) -> str:
    wanted = {_normalise_header(name) for name in names}
    for key, value in row.items():
        if _normalise_header(key) in wanted:
            return _clean(value)
    return ""


def _read_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def load_severity_weights() -> Dict[str, str]:
    rows = _read_csv(DATA_DIR / "severity_weight.csv")
    weights = {}
    for row in rows:
        symptom = _row_value(row, "symptom")
        weight = _row_value(row, "weight", "severity_weight")
        if symptom and weight:
            weights[symptom.lower()] = weight
    return weights


def load_symptoms_csv() -> List[str]:
    path = DATA_DIR / "symptoms.csv"
    docs = []
    weights = load_severity_weights()
    for row in _read_csv(path):
        symptom = _row_value(row, "symptom")
        if not symptom:
            continue
        related = _row_value(row, "related_conditions", "related conditions", "conditions")
        severity = _row_value(row, "severity")
        specialist = _row_value(row, "recommended_specialist", "recommended specialist", "specialist")
        weight = weights.get(symptom.lower(), "")

        parts = [f"Symptom: {symptom}."]
        if related:
            parts.append(f"Related conditions: {related}.")
        if severity:
            parts.append(f"Severity: {severity}.")
        if weight:
            parts.append(f"Severity weight: {weight}.")
        if specialist:
            parts.append(f"Recommended specialist: {specialist}.")
        if len(parts) == 1:
            parts.append("Known symptom in the medical symptom catalog.")
        docs.append(" ".join(parts).strip())
    return docs


def load_doctors_csv() -> List[str]:
    path = DATA_DIR / "doctors.csv"
    docs = []
    for row in _read_csv(path):
        doctor = _row_value(row, "doctor_name", "doctor name", "name")
        specialty = _row_value(row, "specialization", "speciality", "specialty")
        hospital = _row_value(row, "hospital", "chamber")
        location = _row_value(row, "location")
        availability = _row_value(row, "availability")
        education = _row_value(row, "education")
        experience = _row_value(row, "experience")
        focus = _row_value(row, "concentration", "focus_areas", "focus areas")

        if not doctor and not specialty:
            continue

        parts = [
            f"Doctor: {doctor}.",
            f"Specialization: {specialty}.",
        ]
        if education:
            parts.append(f"Education: {education}.")
        if experience:
            parts.append(f"Experience: {experience} years.")
        if hospital:
            parts.append(f"Hospital or chamber: {hospital}.")
        if location:
            parts.append(f"Location: {location}.")
        if availability:
            parts.append(f"Availability: {availability}.")
        if focus:
            parts.append(f"Clinical focus areas: {focus}.")
        docs.append(" ".join(parts).strip())
    return docs


def load_hospitals_csv() -> List[str]:
    path = DATA_DIR / "hospitals.csv"
    docs = []
    for row in _read_csv(path):
        text = (
            f"Hospital: {_row_value(row, 'hospital_name', 'hospital name', 'hospital')}. "
            f"Location: {_row_value(row, 'location')}. "
            f"Emergency services: {_row_value(row, 'emergency_services', 'emergency services')}. "
            f"Contact: {_row_value(row, 'contact')}."
        )
        docs.append(text.strip())
    return docs


def load_diseases_csv() -> List[str]:
    docs = []
    for row in _read_csv(DATA_DIR / "diseases.csv"):
        disease = _row_value(row, "name", "disease")
        description = _row_value(row, "description")
        if disease:
            docs.append(f"Disease: {disease}. Description: {description}.")
    return docs


def load_disease_specialist_csv() -> List[str]:
    docs = []
    for row in _read_csv(DATA_DIR / "Disease_Specialist.csv"):
        disease = _row_value(row, "disease", "name")
        specialist = _row_value(row, "specialist", "recommended_specialist")
        if disease and specialist:
            docs.append(f"Disease: {disease}. Recommended specialist: {specialist}.")
    return docs


def load_original_dataset_csv() -> List[str]:
    docs = []
    for row in _read_csv(DATA_DIR / "Original_Dataset.csv"):
        disease = _row_value(row, "disease")
        symptoms = [
            _clean(value)
            for key, value in row.items()
            if _normalise_header(key).startswith("symptom") and _clean(value)
        ]
        if disease and symptoms:
            docs.append(f"Disease pattern: {disease}. Symptoms: {', '.join(symptoms)}.")
    return docs


def load_symptom2disease_csv() -> List[str]:
    docs = []
    for row in _read_csv(DATA_DIR / "Symptom2Disease.csv"):
        disease = _row_value(row, "label", "disease")
        text = _row_value(row, "text", "description")
        if disease and text:
            docs.append(f"Patient symptom description suggests: {disease}. Description: {text}.")
    return docs


def load_severity_weight_csv() -> List[str]:
    docs = []
    for symptom, weight in load_severity_weights().items():
        docs.append(f"Symptom severity weight: {symptom}. Weight: {weight}.")
    return docs


def load_knowledge_documents() -> List[str]:
    return (
        load_symptoms_csv()
        + load_diseases_csv()
        + load_disease_specialist_csv()
        + load_original_dataset_csv()
        + load_symptom2disease_csv()
        + load_severity_weight_csv()
        + load_doctors_csv()
        + load_hospitals_csv()
    )


def _csv_sources_newer_than_index() -> bool:
    if not INDEX_PATH.exists() or not DOCS_PATH.exists():
        return True
    csv_files = list(DATA_DIR.glob("*.csv"))
    if not csv_files:
        return False
    latest_csv = max(path.stat().st_mtime for path in csv_files)
    oldest_store = min(INDEX_PATH.stat().st_mtime, DOCS_PATH.stat().st_mtime)
    return latest_csv > oldest_store


# ---- Index management ----

def build_index(force: bool = False) -> None:
    """Build FAISS index from all CSV knowledge sources."""
    if not RAG_AVAILABLE:
        print("[RAG] sentence-transformers / faiss not available. Skipping index build.")
        return

    STORE_DIR.mkdir(parents=True, exist_ok=True)

    if INDEX_PATH.exists() and DOCS_PATH.exists() and not force:
        print("[RAG] Index already exists. Use force=True to rebuild.")
        return

    print("[RAG] Loading CSV knowledge sources...")
    docs = load_knowledge_documents()

    if not docs:
        print("[RAG] No documents found. Creating demo knowledge base...")
        docs = _demo_knowledge()

    print(f"[RAG] Embedding {len(docs)} documents...")
    vectors = embed(docs)
    if vectors is None:
        print("[RAG] Embedding model unavailable. Index was not rebuilt.")
        return

    dim = vectors.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(vectors)

    faiss.write_index(index, str(INDEX_PATH))
    with open(DOCS_PATH, "wb") as f:
        pickle.dump(docs, f)

    print(f"[RAG] Index built: {len(docs)} docs, dim={dim}")


def load_index() -> None:
    global _index, _documents
    if _index is not None:
        return
    if not RAG_AVAILABLE:
        _documents = load_knowledge_documents() or _demo_knowledge()
        return
    if INDEX_PATH.exists() and DOCS_PATH.exists():
        if _csv_sources_newer_than_index():
            print("[RAG] CSV data changed. Rebuilding index...")
            build_index(force=True)
        _index = faiss.read_index(str(INDEX_PATH))
        with open(DOCS_PATH, "rb") as f:
            _documents = pickle.load(f)
        print(f"[RAG] Loaded index: {len(_documents)} documents")
    else:
        print("[RAG] Index not found. Building now...")
        build_index()
        load_index()


def retrieve(query: str, top_k: int = 5) -> List[str]:
    """Retrieve top_k relevant documents for a query."""
    load_index()

    if not _documents:
        return []

    if not RAG_AVAILABLE or _index is None:
        return _keyword_retrieve(query, top_k)

    qvec = embed([query])
    if qvec is None:
        return _keyword_retrieve(query, top_k)
    distances, indices = _index.search(qvec, top_k)
    results = []
    for i in indices[0]:
        if 0 <= i < len(_documents):
            results.append(_documents[i])
    return results


def _keyword_retrieve(query: str, top_k: int) -> List[str]:
    q_lower = query.lower()
    words = [w for w in q_lower.split() if len(w) > 2]
    scored = [(d, sum(1 for w in words if w in d.lower())) for d in _documents]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [d for d, score in scored[:top_k] if score > 0] or _documents[:top_k]


def format_context(docs: List[str]) -> str:
    """Format retrieved docs into a context string for the LLM prompt."""
    if not docs:
        return "No specific knowledge retrieved."
    return "\n".join(f"- {d}" for d in docs)


# ---- Demo knowledge base (used when CSVs are missing) ----

def _demo_knowledge() -> List[str]:
    return [
        "Symptom: fever. Related conditions: viral infection; dengue; typhoid; malaria. Severity: medium. Recommended specialist: General Physician.",
        "Symptom: headache. Related conditions: migraine; tension headache; hypertension; viral infection. Severity: low-medium. Recommended specialist: Neurologist.",
        "Symptom: chest pain. Related conditions: angina; myocardial infarction; GERD; costochondritis. Severity: high. Recommended specialist: Cardiologist.",
        "Symptom: shortness of breath. Related conditions: asthma; COPD; pneumonia; heart failure; anxiety. Severity: high. Recommended specialist: Pulmonologist.",
        "Symptom: cough. Related conditions: viral URI; bronchitis; asthma; pneumonia; tuberculosis. Severity: low-medium. Recommended specialist: General Physician.",
        "Symptom: joint pain. Related conditions: arthritis; dengue; rheumatoid arthritis; gout. Severity: medium. Recommended specialist: Rheumatologist.",
        "Symptom: abdominal pain. Related conditions: gastritis; appendicitis; IBS; food poisoning. Severity: medium-high. Recommended specialist: Gastroenterologist.",
        "Symptom: rash. Related conditions: allergic reaction; chickenpox; eczema; contact dermatitis. Severity: low-medium. Recommended specialist: Dermatologist.",
        "Symptom: sore throat. Related conditions: pharyngitis; tonsillitis; viral URI; strep throat. Severity: low-medium. Recommended specialist: General Physician.",
        "Symptom: dizziness. Related conditions: vertigo; anemia; low blood pressure; ear infection. Severity: medium. Recommended specialist: General Physician.",
        "Symptom: fatigue. Related conditions: anemia; thyroid disorder; diabetes; depression; viral infection. Severity: medium. Recommended specialist: General Physician.",
        "Symptom: nausea and vomiting. Related conditions: gastroenteritis; food poisoning; pregnancy; migraine. Severity: medium. Recommended specialist: General Physician.",
        "Dengue fever: characterized by high fever, severe headache, joint pain, rash. Platelet count falls. Requires hospital monitoring if severe.",
        "Hypertension emergency: severe headache with high BP reading warrants immediate emergency care.",
        "Migraine: unilateral throbbing headache with photophobia, phonophobia and nausea. Duration 4-72 hours.",
        "Doctor: Dr. Rahim Ahmed. Specialization: Cardiologist. Hospital: Dhaka Medical College. Location: Dhaka. Availability: Mon-Fri.",
        "Doctor: Dr. Nasrin Islam. Specialization: General Physician. Hospital: Square Hospital. Location: Dhaka. Availability: Sun-Thu.",
        "Doctor: Dr. Karim Hossain. Specialization: Neurologist. Hospital: BIRDEM General Hospital. Location: Dhaka. Availability: Mon-Wed.",
        "Doctor: Dr. Fatema Begum. Specialization: Pediatrician. Hospital: Shishu Hospital. Location: Chittagong. Availability: Sat-Thu.",
        "Doctor: Dr. Arif Siddiqui. Specialization: Dermatologist. Hospital: Apollo Hospital. Location: Dhaka. Availability: Mon-Sat.",
        "Hospital: Dhaka Medical College Hospital. Location: Dhaka. Emergency services: Yes. Contact: 02-55165088.",
        "Hospital: Square Hospital. Location: Dhaka. Emergency services: Yes. Contact: 02-8159457.",
        "Hospital: Chittagong Medical College Hospital. Location: Chittagong. Emergency services: Yes. Contact: 031-619977.",
    ]
