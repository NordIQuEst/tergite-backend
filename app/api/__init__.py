# This code is part of Tergite
#
# (C) Copyright Miroslav Dobsicek 2020, 2021
# (C) Copyright Abdullah-Al Amin 2022
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
#
# Modified:
#
# - Martin Ahindura 2023


import json
import shutil
from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.requests import Request
from fastapi.responses import FileResponse
from redis import Redis
from rq import Worker

import settings

from ..services.auth import service as auth_service
from ..services.jobs import service as jobs_service
from ..services.jobs.workers.postprocessing import (
    logfile_postprocess,
    postprocessing_failure_callback,
    postprocessing_success_callback,
)
from ..services.jobs.workers.postprocessing.dtos import LogfileType
from ..services.jobs.workers.registration import job_register
from ..services.properties import service as props_service
from ..services.random import service as rng_service
from ..utils.api import get_bearer_token
from ..utils.queues import QueuePool
from ..utils.uuid import validate_uuid4_str

# settings
DEFAULT_PREFIX = settings.DEFAULT_PREFIX
STORAGE_ROOT = settings.STORAGE_ROOT
STORAGE_PREFIX_DIRNAME = settings.STORAGE_PREFIX_DIRNAME
LOGFILE_UPLOAD_POOL_DIRNAME = settings.LOGFILE_UPLOAD_POOL_DIRNAME
LOGFILE_DOWNLOAD_POOL_DIRNAME = settings.LOGFILE_DOWNLOAD_POOL_DIRNAME
JOB_UPLOAD_POOL_DIRNAME = settings.JOB_UPLOAD_POOL_DIRNAME


# redis connection
redis_connection = Redis()


# redis queues
rq_queues = QueuePool(prefix=DEFAULT_PREFIX, connection=redis_connection)

# application
app = FastAPI(
    title="Backend Control Computer",
    description="Interfaces Qauntum processor via REST API",
    version="0.0.1",
)


# routing
@app.get("/")
async def root():
    # FIXME: block access to this except for the white-listed IPs
    return {"message": "Welcome to BCC machine"}


@app.post("/auth")
async def register_credentials(body: auth_service.Credentials):
    """Registers the credentials to"""
    try:
        auth_service.save_credentials(redis_connection, payload=body)
    except auth_service.JobAlreadyExists as exp:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{exp}")
    return {"message": "ok"}


@app.post("/jobs")
async def upload_job(request: Request, upload_file: UploadFile = File(...)):
    # get job_id and validate it
    job_dict = json.load(upload_file.file)
    job_id = job_dict.get("job_id", None)
    if job_id is None or validate_uuid4_str(job_id) is False:
        print("The job does not have a valid UUID4 job_id")
        return {"message": "failed"}

    # raise authentication and authorization errors where appropriate
    _authenticate_request(
        request, job_id=job_id, expected_status=auth_service.JobStatus.REGISTERED
    )

    # store the received file in the job upload pool
    file_name = job_id
    file_path = Path(STORAGE_ROOT) / STORAGE_PREFIX_DIRNAME / JOB_UPLOAD_POOL_DIRNAME
    file_path.mkdir(parents=True, exist_ok=True)
    store_file = file_path / file_name

    # save it
    upload_file.file.seek(0)
    with store_file.open("wb") as destination:
        shutil.copyfileobj(upload_file.file, destination)
    upload_file.file.close()

    # enqueue for registration
    rq_queues.job_registration_queue.enqueue(
        job_register, store_file, job_id=job_id + f"_{jobs_service.Location.REG_Q.name}"
    )
    return {"message": file_name}


@app.get("/jobs")
async def fetch_all_jobs():
    # FIXME: block access to this except for the white-listed IPs
    return jobs_service.fetch_all_jobs()


@app.get("/jobs/{job_id}")
async def fetch_job(request: Request, job_id: str):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=job_id)

    job = jobs_service.fetch_job(job_id)
    return {"message": job or f"job {job_id} not found"}


@app.get("/jobs/{job_id}/status")
async def fetch_job_status(request: Request, job_id: str):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=job_id)

    status = jobs_service.fetch_job(job_id, "status", format=True)
    return {"message": status or f"job {job_id} not found"}


@app.get("/jobs/{job_id}/result")
async def fetch_job_result(request: Request, job_id: str):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=job_id)

    job = jobs_service.fetch_job(job_id)

    if not job:
        return {"message": f"job {job_id} not found"}
    elif job["status"]["finished"]:
        return {"message": job["result"]}
    else:
        return {"message": "job has not finished"}


@app.delete("/jobs/{job_id}")
async def remove_job(request: Request, job_id: str):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=job_id)

    jobs_service.remove_job(job_id)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(
    request: Request, job_id: str, reason: Optional[str] = Body(None, embed=False)
):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=job_id)

    print(f"Cancelling job {job_id}")
    jobs_service.cancel_job(job_id, reason)


@app.get("/logfiles/{logfile_id}")
async def download_logfile(request: Request, logfile_id: UUID):
    # raise authentication and authorization errors where appropriate
    _authenticate_request(request, job_id=str(logfile_id))

    file_name = f"{logfile_id}.hdf5"
    file = (
        Path(STORAGE_ROOT)
        / STORAGE_PREFIX_DIRNAME
        / LOGFILE_DOWNLOAD_POOL_DIRNAME
        / file_name
    )

    if file.exists():
        return FileResponse(file)
    else:
        return {"message": "logfile not found"}


@app.post("/logfiles")
def upload_logfile(
    upload_file: UploadFile = File(...),
    logfile_type: str = Form(default="LABBER_LOGFILE"),
):
    # FIXME: block access to this except for the white-listed IPs
    print(f"Received logfile {upload_file.filename}")

    # store the recieved file in the logfile upload pool
    file_name = Path(upload_file.filename).stem

    # Cancels postprocessing if job is labelled as cancelled
    status = jobs_service.fetch_job(file_name, "status")
    if status["cancelled"]["time"]:
        print("Job cancelled, postprocessing halted")
        # FIXME: Probably provide an error message to the client also
        return
    file_path = (
        Path(STORAGE_ROOT) / STORAGE_PREFIX_DIRNAME / LOGFILE_UPLOAD_POOL_DIRNAME
    )
    file_path.mkdir(parents=True, exist_ok=True)
    store_file = file_path / file_name

    with store_file.open("wb") as destination:
        shutil.copyfileobj(upload_file.file, destination)

    upload_file.file.close()

    # enqueue for post-processing
    rq_queues.logfile_postprocessing_queue.enqueue(
        logfile_postprocess,
        on_success=postprocessing_success_callback,
        on_failure=postprocessing_failure_callback,
        job_id=file_name + f"_{jobs_service.Location.PST_PROC_Q.name}",
        args=(store_file,),
        kwargs=dict(logfile_type=LogfileType(logfile_type)),
    )

    # inform supervisor
    jobs_service.inform_location(file_name, jobs_service.Location.PST_PROC_Q)

    return {"message": "ok"}


# FIXME: this endpoint might be unnecessary going forward or might need to return proper JSON data
@app.get("/rq-info")
async def get_rq_info():
    # FIXME: block access to this except for the white-listed IPs
    workers = Worker.all(connection=redis_connection)
    print(str(workers))
    if len(workers) == 0:
        return {"message": "No worker registered"}

    msg = "{"
    for worker in workers:
        msg += "hostname: " + str(worker.hostname) + ","
        msg += "pid: " + str(worker.pid)
    msg += "}"

    return {"message": msg}


# FIXME: this endpoint might be unnecessary
@app.get("/rng/{job_id}")
async def call_rng(job_id: UUID):
    # FIXME: block access to this except for the white-listed IPs
    rng_service.quantify_rng(job_id=job_id)
    return "Requesting RNG Numbers"


@app.get("/backend_properties")
async def create_current_snapshot():
    # FIXME: block access to this except for the white-listed IPs
    return props_service.create_backend_snapshot()


# FIXME: this endpoint might be unnecessary
@app.get("/web-gui")
async def get_snapshot():
    # FIXME: block access to this except for the white-listed IPs
    snapshot = redis_connection.get("current_snapshot")
    return json.loads(snapshot)


# FIXME: this endpoint might be unnecessary
@app.get("/web-gui/config")
async def web_config():
    # FIXME: block access to this except for the white-listed IPs
    snapshot = redis_connection.get("config")
    return json.loads(snapshot)


def _authenticate_request(
    request: Request,
    job_id: str,
    expected_status: Optional[auth_service.JobStatus] = None,
):
    """Authenticates the given request, raising appropriate HTTP errors where necessary

    Args:
        request: the FastAPI request object to authenticate
        job_id: the job id for which authentication is to be done
        expected_status: the status that the job should be at. If None, status does not matter

    Raises:
        HTTPException: status_code=401, detail=job {credentials.job_id} does not exist for current user
        HTTPException: status_code=403, detail=job {credentials.job_id} is already {auth_log.status}
    """
    app_token = get_bearer_token(request, raise_if_error=settings.IS_AUTH_ENABLED)
    credentials = auth_service.Credentials(job_id=job_id, app_token=app_token)
    try:
        auth_service.authenticate(
            redis_connection,
            credentials=credentials,
            expected_status=expected_status,
        )
    except auth_service.AuthenticationError as exp:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"{exp}")
    except auth_service.AuthorizationError as exp:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{exp}")
