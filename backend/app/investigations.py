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


class Investigation(BaseModel):
    id: int
    title: str
    created_at: datetime


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
    return Investigation.model_validate(row)


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


@router.get("/investigations/{investigation_id}", response_model=Investigation)
def get_investigation_by_id(
    investigation_id: int,
    connection: Annotated[psycopg.Connection, Depends(get_connection)],
) -> Investigation:
    found = get_investigation(connection, investigation_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return found
