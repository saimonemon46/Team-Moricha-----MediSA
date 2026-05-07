# MediAI — Pydantic Models
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class SymptomRequest(BaseModel):
    symptom: str = Field(..., description="Primary symptom description from user")
    user_id: int = Field(..., description="User ID from PHP backend")


class AnswerSubmission(BaseModel):
    session_id: str
    symptom: str
    answers: List[str] = []
    user_id: int


class ReportRequest(BaseModel):
    session_id: str
    symptom: str
    answers: List[str] = []
    user_id: int


class DocumentAnalysisRequest(BaseModel):
    document_id: int
    file_path: str


class DoctorRecommendationRequest(BaseModel):
    specialization: Optional[str] = ""
    location: Optional[str] = ""
    symptom: Optional[str] = ""
    possible_condition: Optional[str] = ""
    report_text: Optional[str] = ""
    urgency: Optional[str] = ""
    conversation: List[Any] = Field(default_factory=list)
    report: Optional[Dict[str, Any]] = None
    user_id: Optional[int] = 0
    limit: int = Field(default=24, ge=1, le=60)


class Medication(BaseModel):
    name: str
    dosage: Optional[str] = ""
    frequency: Optional[str] = ""
    duration: Optional[str] = ""
    instructions: Optional[str] = ""


class TriageReport(BaseModel):
    session_id: str
    possible_condition: str
    urgency: str  # low | medium | high
    recommended_specialist: str
    reasoning: str
    guidance: str
    symptoms_listed: List[str] = []
    generated_at: str


class QuestionResponse(BaseModel):
    session_id: str
    questions: List[str]
    context_summary: Optional[str] = ""


class DocumentAnalysisResult(BaseModel):
    document_type: str
    document_summary: Optional[str] = ""
    medications: List[Medication] = []
    diagnoses: List[str] = []
    lab_results: List[Dict[str, Any]] = []
    abnormal_findings: List[str] = []
    red_flags: List[str] = []
    follow_up: Optional[str] = ""
    recommended_specialist: Optional[str] = ""
    notes: Optional[str] = ""
    raw_text: Optional[str] = ""
