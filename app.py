"""
ReadyDesk API.   uvicorn app:app --reload    ->  http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from typing import Literal, Union

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gen4.api import common_router
from service import ReadyDeskService

service = ReadyDeskService()
app = FastAPI(title="ReadyDesk", version="2.0.0",
              description="Confidence-gated loan intake: product-specific checklists, document freshness and "
                          "cross-document consistency, resubmission memory, and thresholds tuned by underwriter "
                          "feedback.")
app.include_router(common_router(service, "readydesk"))


class DocumentIn(BaseModel):
    type: str
    issued_on: str | None = None
    valid_until: str | None = None
    period_end: str | None = None
    name_on_doc: str | None = None
    monthly_income: float | None = None


class ApplicationIn(BaseModel):
    application_id: str | None = None
    product: Literal["personal_loan", "two_wheeler", "home_loan"] = "personal_loan"
    applicant_type: Literal["salaried", "self_employed"] = "salaried"
    documents: list[Union[str, DocumentIn]] = Field(default_factory=list)
    fields: dict = Field(default_factory=dict)


class VerdictIn(BaseModel):
    decision_id: str
    actually_complete: bool


@app.get("/", tags=["ops"])
def root():
    return {"service": "ReadyDesk", "docs": "/docs", "flow": "POST /check -> POST /feedback (underwriter verdict)"}


@app.post("/check", tags=["decision"])
def check(body: ApplicationIn):
    app_dict = body.model_dump()
    app_dict["documents"] = [d if isinstance(d, str) else {k: v for k, v in d.items() if v is not None}
                             for d in app_dict["documents"]]
    try:
        return service.check(app_dict)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/feedback", tags=["feedback"])
def feedback(body: VerdictIn):
    try:
        return service.underwriter_verdict(body.decision_id, body.actually_complete)
    except KeyError:
        raise HTTPException(404, "unknown decision_id")


@app.get("/insights", tags=["feedback"])
def insights():
    return {"most_common_issues": service.common_issues(), **service.learn()}
