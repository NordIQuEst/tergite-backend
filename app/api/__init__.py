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

from fastapi import Body, FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from redis import Redis
from rq import Queue, Worker

import settings

from ..services.jobs import service as jobs_service
from ..services.jobs.workers.postprocessing import (
    dtos,
    logfile_postprocess,
    postprocessing_success_callback,
)
from ..services.jobs.workers.postprocessing.dtos import LogfileType
from ..services.jobs.workers.registration import job_register
from ..services.random import service as rng_service
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
rq_job_registration = Queue(
    DEFAULT_PREFIX + "_job_registration", connection=redis_connection
)

rq_logfile_postprocessing = Queue(
    DEFAULT_PREFIX + "_logfile_postprocessing", connection=redis_connection
)

# application
app = FastAPI(
    title="Backend Control Computer",
    description="Controls Pingu qubits via REST API",
    version="0.0.1",
)


# routing
@app.get("/")
async def root():
    return {"message": "Welcome to BCC machine"}


@app.post("/jobs")
async def upload_job(upload_file: UploadFile = File(...)):
    # get job_id and validate it
    job_dict = json.load(upload_file.file)
    job_id = job_dict.get("job_id", None)
    if job_id is None or validate_uuid4_str(job_id) is False:
        print("The job does not have a valid UUID4 job_id")
        return {"message": "failed"}

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
    rq_job_registration.enqueue(
        job_register, store_file, job_id=job_id + f"_{jobs_service.Location.REG_Q.name}"
    )
    return {"message": file_name}


@app.get("/jobs")
async def fetch_all_jobs():
    return jobs_service.fetch_all_jobs()


@app.get("/jobs/{job_id}")
async def fetch_job(job_id: str):
    job = jobs_service.fetch_job(job_id)
    return {"message": job or f"job {job_id} not found"}


@app.get("/jobs/{job_id}/status")
async def fetch_job_status(job_id: str):
    status = jobs_service.fetch_job(job_id, "status", format=True)
    return {"message": status or f"job {job_id} not found"}


@app.get("/jobs/{job_id}/result")
async def fetch_job_result(job_id: str):
    job = jobs_service.fetch_job(job_id)

    if not job:
        return {"message": f"job {job_id} not found"}
    elif job["status"]["finished"]:
        return {"message": job["result"]}
    else:
        return {"message": "job has not finished"}


@app.delete("/jobs/{job_id}")
async def remove_job(job_id: str):
    jobs_service.remove_job(job_id)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, reason: Optional[str] = Body(None, embed=False)):
    print(f"Cancelling job {job_id}")
    jobs_service.cancel_job(job_id, reason)


@app.get("/logfiles/{logfile_id}")
async def download_logfile(logfile_id: UUID):
    file_name = str(logfile_id) + ".hdf5"
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
    print(f"Received logfile {upload_file.filename}")

    # store the recieved file in the logfile upload pool
    file_name = Path(upload_file.filename).stem

    # Cancels postprocessing if job is labelled as cancelled
    status = jobs_service.fetch_job(file_name, "status")
    if status["cancelled"]["time"]:
        print("Job cancelled, postprocessing halted")
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
    rq_logfile_postprocessing.enqueue(
        logfile_postprocess,
        on_success=postprocessing_success_callback,
        job_id=file_name + f"_{jobs_service.Location.PST_PROC_Q.name}",
        args=(store_file,),
        kwargs=dict(logfile_type=LogfileType(logfile_type)),
    )

    # inform supervisor
    jobs_service.inform_location(file_name, jobs_service.Location.PST_PROC_Q)

    return {"message": "ok"}


@app.get("/rq-info")
async def get_rq_info():
    workers = Worker.all(connection=redis_connection)
    print(str(workers))
    if workers == []:
        return {"message": "No worker registered"}

    msg = "{"
    for worker in workers:
        msg += "hostname: " + str(worker.hostname) + ","
        msg += "pid: " + str(worker.pid)
    msg += "}"

    return {"message": msg}


@app.get("/rng/{job_id}")
async def call_rng(job_id: UUID):
    rng_service.quantify_rng(job_id=job_id)
    return "Requesting RNG Numbers"


@app.get("/web-gui")
async def get_snapshot():
    snapshot = redis_connection.get("current_snapshot")
    return json.loads(snapshot)


@app.get("/web-gui/config")
async def web_config():
    snapshot = redis_connection.get("config")
    return json.loads(snapshot)
