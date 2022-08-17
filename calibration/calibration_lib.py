# This code is part of Tergite
#
# (C) Johan Blomberg, Gustav Grännsjö 2020
# (C) Copyright Miroslav Dobsicek 2020, 2021
# (C) Copyright David Wahlstedt 2022
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import asyncio
import datetime
import json
from pathlib import Path
from random import random
import settings
from tempfile import gettempdir
from uuid import uuid4

import redis
import requests

import config
import calibration.measurement_jobs as meas_jobs
from calibration.calibration_common import JobDoneEvent, DataStatus

# Set up Redis connection
red = redis.Redis(decode_responses=True)

# Settings
BCC_MACHINE_ROOT_URL = settings.BCC_MACHINE_ROOT_URL

REST_API_MAP = {"jobs": "/jobs"}

# -------------------------------------------------------------------------
# Mapping of measurement mk_job_ functions. Just maps strings to their
# corresponding function symbols. Maybe this can be replaced with some
# form of reflection: ast.literal_eval does not apply on function symbols.

MK_JOB_FNS = {
    "mk_job_check_sig_demod": meas_jobs.mk_job_check_sig_demod,
    "mk_job_calibrate_sig_demod": meas_jobs.mk_job_calibrate_sig_demod,
}

# -------------------------------------------------------------------------
# Check data procedures

# This function is just a template for a future implementation
# check_data will do something like this:
async def check_dummy(node, job_done_evt) -> DataStatus:
    #  This key should be found in the node, but The signal
    # demodulation measurement is used as a dummy here.
    mk_job_fn = MK_JOB_FNS.get("mk_job_check_sig_demod")
    job = mk_job_fn()

    job_id = job["job_id"]
    print(f"Requesting check job with {job_id=} for {node=} ...")
    await request_job(job, job_done_evt)

    cal_params = red.lrange(f"m_params:{node}", 0, -1)
    for cal_param in cal_params:
        # Fetch the values we got from the measurement's postprocessing
        # here you can use the cal_param
        result_key = f"postproc:results:{job_id}"
        result = red.get(result_key)
        print(
            f"check_data: For {cal_param=}, from Redis we read {result_key} from postprocessing: {result}"
        )
        if result == None:
            print(f"Warning: no entry found for key {result_key}")
        # TODO ensure value is within thresholds

    # TODO return status based on the above param checks instead of deciding at random
    num = random()
    if num < 0.8:  # remove this later :-)
        print(f"Check_data for {node} gives IN_SPEC")
        return DataStatus.in_spec
    if num < 0.95:  # remove this later :-)
        print(f"Check_data for {node} gives OUT_OF_SPEC")
        return DataStatus.out_of_spec
    print(f"Check_data for {node} gives BAD_DATA")
    return DataStatus.bad_data

# To be used by calibration nodes that don't yet have check_data implemented
def out_of_spec(node):
    print(f"check_data not implemented for {node}, forcing calibration ...")
    return DataStatus.out_of_spec


# -------------------------------------------------------------------------
# Calibration procedures

async def calibrate_dummy(node, job_done_evt):
    #  This key should be found in the node, but The signal
    # demodulation measurement is used as a dummy here.
    mk_job_fn = MK_JOB_FNS.get("mk_job_calibrate_sig_demod")
    job = mk_job_fn()

    job_id = job["job_id"]
    print(f"Requesting calibration job with {job_id=} for {node=} ...")
    await request_job(job, job_done_evt)

    print("")

    cal_params = red.lrange(f"m_params:{node}", 0, -1)
    for cal_param in cal_params:
        # Fetch unit and parameter lifetime
        # TODO: this will be changed in a coming pull-request
        unit = red.hget(f"m_params:{node}:{cal_param}", "unit")
        lifetime = red.hget(f"m_params:{node}:{cal_param}", "timeout")

        # Fetch the values we got from the calibration's postprocessing
        # TODO: this will be changed in a coming pull-request
        result_key = f"postproc:results:{job_id}"
        result = red.get(result_key)
        print(
            f"For {cal_param=}, from Redis we read {result_key} from postprocessing: {result}"
        )
        if result == None:
            print(f"Warning: no entry found for key {result_key}")
            result = "not found"  # should investigate why this happens

        red.hset(f"param:{cal_param}", "name", cal_param)
        red.hset(
            f"param:{cal_param}",
            "date",
            datetime.datetime.now().replace(microsecond=0).isoformat() + "Z",
        )
        red.hset(f"param:{cal_param}", "unit", unit)
        red.hset(f"param:{cal_param}", "value", result)

        # Set expiry date
        # TODO replace with flagging system to mark outdated nodes
        red.expire(f"param:{cal_param}", lifetime)


# -------------------------------------------------------------------------
# Misc heplers

# DW: This method is not calibration specific: maybe it this should be
# available for all of BCC, so that all the job requests done the same
# way, with the same entry point?
async def request_job(job, job_done_evt):
    job_id = job["job_id"]

    # Updating for handle_message to accept only this job_id:
    job_done_evt.requested_job_id = job_id

    tmpdir = gettempdir()
    file = Path(tmpdir) / str(uuid4())
    with file.open("w") as dest:
        json.dump(job, dest)

    with file.open("r") as src:
        files = {"upload_file": src}
        url = str(BCC_MACHINE_ROOT_URL) + REST_API_MAP["jobs"]
        response = requests.post(url, files=files)

        # Right now the Labber Connector sends a response *after*
        # executing the scenario i.e., the POST request is *blocking*
        # until after the measurement execution this will change in
        # the future; it should just ack a succesful upload of a
        # scenario and nothing more

        if response:
            file.unlink()
            print("Job has been successfully sent")
        else:
            print("request_job failed")
            return

    # Wait until reply arrives(the one with our job_id).
    await job_done_evt.event.wait()
    job_done_evt.event.clear()

    print("")


