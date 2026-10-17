from datetime import datetime
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.db import get_connection

router = APIRouter()


class InvestigationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


LOCAL_LOG = "local_log"


class Evidence(BaseModel):
    id: int
    origin: str
    content: str
    created_at: datetime


class EvidenceCreate(BaseModel):
    content: str = Field(min_length=1)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class Investigation(BaseModel):
    id: int
    title: str
    created_at: datetime
    evidence: list[Evidence] = []


def create_investigation(connection: psycopg.Connection, title: str) -> Investigation:
    row = connection.execute(
        """
        INSERT INTO investigations (title)
        VALUES (%s)
        RETURNING id, title, created_at
        """,
        (title,),
    ).fetchone()
    return Investigation.model_validate(row)


def list_evidence(
    connection: psycopg.Connection, investigation_id: int
) -> list[Evidence]:
    rows = connection.execute(
        """
        SELECT id, origin, content, created_at
        FROM evidence
        WHERE investigation_id = %s
        ORDER BY id
        """,
        (investigation_id,),
    ).fetchall()
    return [Evidence.model_validate(row) for row in rows]


def get_investigation(
    connection: psycopg.Connection, investigation_id: int
) -> Investigation | None:
    row = connection.execute(
        """
        SELECT id, title, created_at
        FROM investigations
        WHERE id = %s
        """,
        (investigation_id,),
    ).fetchone()
    if row is None:
        return None
    investigation = Investigation.model_validate(row)
    investigation.evidence = list_evidence(connection, investigation_id)
    return investigation


def attach_local_log(
    connection: psycopg.Connection, investigation_id: int, content: str
) -> Evidence | None:
    investigation = connection.execute(
        "SELECT id FROM investigations WHERE id = %s",
        (investigation_id,),
    ).fetchone()
    if investigation is None:
        return None
    row = connection.execute(
        """
        INSERT INTO evidence (investigation_id, origin, content)
        VALUES (%s, %s, %s)
        RETURNING id, origin, content, created_at
        """,
        (investigation_id, LOCAL_LOG, content),
    ).fetchone()
    return Evidence.model_validate(row)


@router.post(
    "/investigations",
    response_model=Investigation,
    status_code=status.HTTP_201_CREATED,
)
def post_investigation(
    body: InvestigationCreate,
    connection: Annotated[psycopg.Connection, Depends(get_connection)],
) -> Investigation:
    return create_investigation(connection, body.title)


@router.post(
    "/investigations/{investigation_id}/evidence",
    response_model=Evidence,
    status_code=status.HTTP_201_CREATED,
)
def post_local_log(
    investigation_id: int,
    body: EvidenceCreate,
    connection: Annotated[psycopg.Connection, Depends(get_connection)],
) -> Evidence:
    attached = attach_local_log(connection, investigation_id, body.content)
    if attached is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return attached


@router.get("/investigations/{investigation_id}", response_model=Investigation)
def get_investigation_by_id(
    investigation_id: int,
    connection: Annotated[psycopg.Connection, Depends(get_connection)],
) -> Investigation:
    found = get_investigation(connection, investigation_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return found
