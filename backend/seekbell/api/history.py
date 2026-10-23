from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from seekbell.api.auth import require_admin
from seekbell.services.history import History, MissingHistory, date_range_window

router = APIRouter(prefix="/api/manage/history", dependencies=[Depends(require_admin)])


def history(request: Request):
    return History(request.app.state.engine)


def paging(
    page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
):
    return {"page": page, "page_size": page_size}


def date_filter(
    discovered_on: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    timezone: str = Query("Asia/Shanghai", max_length=64),
):
    try:
        # Retain single-day API compatibility; mixed semantics must not be ambiguous.
        if discovered_on is not None:
            if date_from is not None or date_to is not None:
                raise ValueError("Conflicting date filters")
            date_from = date_to = discovered_on
        return date_range_window(date_from, date_to, timezone)
    except (ValueError, OverflowError):
        raise HTTPException(422, "日期范围或显示时区无效。") from None


Reader = Annotated[History, Depends(history)]
Paging = Annotated[dict, Depends(paging)]
DateWindow = Annotated[tuple[float, float] | None, Depends(date_filter)]


def found(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except MissingHistory as error:
        raise HTTPException(404, str(error)) from None


@router.get("/options")
def options(reader: Reader):
    return reader.options()


@router.get("/counts")
def counts(reader: Reader):
    return reader.counts()


@router.get("/dates")
def dates(
    reader: Reader,
    scope: Literal["posts", "deliveries", "manual", "tests"] = "posts",
    timezone: str = Query("Asia/Shanghai", max_length=64),
    before: date | None = None,
    limit: int = Query(100, ge=1, le=100),
):
    try:
        return reader.dates(scope, timezone=timezone, before=before, limit=limit)
    except (ValueError, OverflowError, KeyError):
        raise HTTPException(422, "记录日期或显示时区无效。") from None


@router.get("/posts")
def posts(
    params: Paging,
    window: DateWindow,
    reader: Reader,
    q: str = Query("", max_length=200),
    status: Literal[
        "all", "match", "no_match", "insufficient_data", "not_evaluated", "unrecorded"
    ] = "all",
    task_id: str = Query("", max_length=80),
    website_id: str = Query("", max_length=80),
    category: str = Query("", max_length=500),
):
    return reader.list_posts(
        **params,
        window=window,
        q=q,
        status=status,
        task_id=task_id,
        website_id=website_id,
        category=category,
    )


@router.get("/posts/{key}")
def post(key: str, reader: Reader):
    return found(reader.get_post, key)


@router.get("/posts/{key}/evaluations")
def evaluations(
    key: str,
    params: Paging,
    reader: Reader,
    group: Literal["all", "matched", "primary", "other"] = "all",
):
    return found(reader.evaluations, key, group=group, **params)


@router.get("/deliveries")
def deliveries(
    params: Paging,
    window: DateWindow,
    reader: Reader,
    q: str = Query("", max_length=200),
    status: Literal["all", "pending", "retry", "leased", "sent", "failed", "cancelled"] = "all",
    target_id: str = Query("", max_length=80),
    website_id: str = Query("", max_length=80),
    post_id: str = Query("", max_length=400),
    uncertain: bool | None = None,
):
    return found(
        reader.list_deliveries,
        **params,
        window=window,
        q=q,
        status=status,
        target_id=target_id,
        website_id=website_id,
        post_id=post_id,
        uncertain=uncertain,
    )


@router.get("/deliveries/{key}")
def delivery(
    key: str,
    reader: Reader,
    attempt_page: int = Query(1, ge=1, le=100000),
    task_page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
):
    return found(
        reader.get_delivery,
        key,
        attempt_page=attempt_page,
        task_page=task_page,
        page_size=page_size,
    )


@router.get("/tests")
def tests(
    params: Paging,
    window: DateWindow,
    reader: Reader,
    q: str = Query("", max_length=200),
    target_id: str = Query("", max_length=80),
    status: Literal[
        "all", "success", "transient_error", "permanent_error", "unknown", "in_progress"
    ] = "all",
):
    return reader.list_tests(**params, window=window, q=q, status=status, target_id=target_id)


@router.get("/tests/{key}")
def target_test(key: str, reader: Reader):
    return found(reader.get_test, key)


@router.get("/manual")
def manual(
    params: Paging,
    window: DateWindow,
    reader: Reader,
    q: str = Query("", max_length=200),
    target_id: str = Query("", max_length=80),
    source_event_id: str = Query("", max_length=80),
    status: Literal["all", "success", "transient_error", "permanent_error", "unknown"] = "all",
):
    return reader.list_manual(
        **params,
        window=window,
        q=q,
        status=status,
        target_id=target_id,
        source_event_id=source_event_id,
    )


@router.get("/manual/{key}")
def manual_detail(
    key: str,
    reader: Reader,
    task_page: int = Query(1, ge=1, le=100000),
    page_size: int = Query(20, ge=1, le=100),
):
    return found(reader.get_manual, key, task_page=task_page, page_size=page_size)
