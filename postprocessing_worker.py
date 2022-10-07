# This code is part of Tergite
#
# (C) Copyright Miroslav Dobsicek 2020, 2021
# (C) Copyright David Wahlstedt 2021, 2022
# (C) Copyright Abdullah Al Amin 2021, 2022
# (C) Copyright Axel Andersson 2022
# (C) Andreas Bengtsson 2020
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import argparse
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Tuple

import Labber
import redis
import requests
import tqcsf.file
from syncer import sync

import enums
import settings
from analysis import (
    extract_resonance_freqs,
    fit_oscillation_idx,
    fit_resonator,
    fit_resonator_idx,
    gaussian_fit_idx,
)
from job_supervisor import (
    Location,
    fetch_redis_entry,
    inform_failure,
    inform_location,
    inform_result,
)

# Storage settings

STORAGE_ROOT = settings.STORAGE_ROOT
STORAGE_PREFIX_DIRNAME = settings.STORAGE_PREFIX_DIRNAME
LOGFILE_DOWNLOAD_POOL_DIRNAME = settings.LOGFILE_DOWNLOAD_POOL_DIRNAME

# Connectivity settings

MSS_MACHINE_ROOT_URL = settings.MSS_MACHINE_ROOT_URL
BCC_MACHINE_ROOT_URL = settings.BCC_MACHINE_ROOT_URL
CALIBRATION_SUPERVISOR_PORT = settings.CALIBRATION_SUPERVISOR_PORT

LOCALHOST = "localhost"

# REST API

REST_API_MAP = {
    "result": "/result",
    "status": "/status",
    "timelog": "/timelog",
    "jobs": "/jobs",
    "logfiles": "/logfiles",
    "download_url": "/download_url",
}


# Redis connection

red = redis.Redis(decode_responses=True)

# =========================================================================
# Post-processing entry function
# =========================================================================


def logfile_postprocess(
    logfile: Path, *, logfile_type: enums.LogfileType = enums.LogfileType.LABBER_LOGFILE
):

    print(f"Postprocessing logfile {str(logfile)}")

    # Move the logfile to logfile download pool area
    # TODO: This file change should preferably happen _after_ the
    # post-processing.
    new_file_name = Path(logfile).stem  # This is the job_id
    new_file_name_with_suffix = new_file_name + ".hdf5"
    storage_location = Path(STORAGE_ROOT) / STORAGE_PREFIX_DIRNAME

    new_file_path = storage_location / LOGFILE_DOWNLOAD_POOL_DIRNAME
    new_file_path.mkdir(exist_ok=True)
    new_file = new_file_path / new_file_name_with_suffix

    logfile.replace(new_file)

    print(f"Moved the logfile to {str(new_file)}")

    # Inform job supervisor
    inform_location(new_file_name, Location.PST_PROC_W)

    # The return value will be passed to postprocessing_success_callback
    if logfile_type == enums.LogfileType.TQC_STORAGE:
        print("Identified TQC storage file, reading file using tqcsf")
        sf = tqcsf.file.StorageFile(new_file, mode="r")
        return postprocess_tqcsf(sf)
    else:
        # Labber logfile
        # All further post-processing, from this point on, is Labber specific.
        labber_logfile = Labber.LogFile(new_file)
        return postprocess_labber_logfile(labber_logfile)


# =========================================================================
# Post-processing Quantify / Qblox files
# =========================================================================


def postprocess_tqcsf(sf: tqcsf.file.StorageFile) -> str:

    update_mss_and_bcc(memory=[], job_id=sf.job_id)

    if sf.meas_level == tqcsf.file.MeasLvl.DISCRIMINATED:
        pass  # TODO

    elif sf.meas_level == tqcsf.file.MeasLvl.INTEGRATED:
        pass  # TODO

    elif sf.meas_level == tqcsf.file.MeasLvl.RAW:
        pass  # TODO

    else:
        pass

    # job["name"] has already been set to "pulse_schedule"

    return sf.job_id


# =========================================================================
# Post-processing Labber logfiles
# =========================================================================


# =========================================================================
# Post-processing helpers in PROCESSING_METHODS
# labber_logfile: Labber.LogFile
# Dummy post-processing of signal demodulation
def process_demodulation(labber_logfile: Labber.LogFile) -> Any:
    job_id = get_job_id_labber(labber_logfile)
    return job_id


# Qasm job example
def process_qiskit_qasm_runner_qasm_dummy_job(labber_logfile: Labber.LogFile) -> Any:
    job_id = get_job_id_labber(labber_logfile)

    # Extract System state
    memory = extract_system_state_as_hex(labber_logfile)

    update_mss_and_bcc(memory, job_id)

    # DW: I guess something else should be returned? memory or parts of it?
    return job_id


# VNA resonator spectroscopy
def process_res_spect_vna_phase_1(labber_logfile: Labber.LogFile) -> Any:
    return fit_resonator(labber_logfile)


def process_res_spect_vna_phase_2(labber_logfile: Labber.LogFile) -> Any:
    return fit_resonator_idx(labber_logfile, [0, 50])


# Pulsed resonator spectroscopy
def process_pulsed_res_spect(labber_logfile: Labber.LogFile) -> Any:
    return fit_resonator_idx(labber_logfile, [0])


# Two-tone
def process_two_tone(labber_logfile: Labber.LogFile) -> Any:
    # fit qubit spectra
    return gaussian_fit_idx(labber_logfile, [0])


# Rabi
def process_rabi(labber_logfile: Labber.LogFile) -> Any:
    # fit Rabi oscillation
    fits = fit_oscillation_idx(labber_logfile, [0])
    return [res["period"] for res in fits]


# Ramsey
def process_ramsey(labber_logfile: Labber.LogFile) -> Any:
    # fit Ramsey oscillation
    fits = fit_oscillation_idx(labber_logfile, [0])
    return [res["freq"] for res in fits]


# =========================================================================
# Post-processing function mapping

PROCESSING_METHODS = {
    "resonator_spectroscopy": process_res_spect_vna_phase_1,
    "fit_resonator_spectroscopy": process_res_spect_vna_phase_2,
    "pulsed_resonator_spectroscopy": process_pulsed_res_spect,
    "pulsed_two_tone_qubit_spectroscopy": process_two_tone,
    "rabi_qubit_pi_pulse_estimation": process_rabi,
    "ramsey_qubit_freq_correction": process_ramsey,
    "demodulation_scenario": process_demodulation,
    "qiskit_qasm_runner": process_qiskit_qasm_runner_qasm_dummy_job,
    "qasm_dummy_job": process_qiskit_qasm_runner_qasm_dummy_job,
}

# =========================================================================
# Post-processing Labber logfiles


def postprocess_labber_logfile(labber_logfile: Labber.LogFile):

    job_id = get_job_id_labber(labber_logfile)
    (script_name, is_calibration_sup_job) = get_metainfo(job_id)

    postproc_fn = PROCESSING_METHODS.get(script_name)

    print(
        f"Starting postprocessing for script: {script_name}, {job_id=}, {is_calibration_sup_job=}"
    )

    if postproc_fn:
        results = postproc_fn(labber_logfile)
    else:
        print(f"Unknown script name {script_name}")
        print("Postprocessing failed")  # TODO: take care of this case
        results = None

        # Inform job supervisor about failure
        inform_failure(job_id, "Unknown script name")
        return None

    print(
        f"Postprocessing ended for script type: {script_name}, {job_id=}, {is_calibration_sup_job=}"
    )
    red.set(f"postproc:results:{job_id}", str(results))
    return job_id


# =========================================================================
# Post-processing success callback with helper
# =========================================================================


async def notify_job_done(job_id: str):
    reader, writer = await asyncio.open_connection(
        LOCALHOST, CALIBRATION_SUPERVISOR_PORT
    )
    message = ("job_done:" + job_id).encode()
    print(f"notify_job_done: {message=}")
    writer.write(message)
    writer.close()


def postprocessing_success_callback(job, connection, result, *args, **kwargs):
    # From logfile_postprocess:
    job_id = result

    # Inform job supervisor about results
    inform_result(job_id, result)

    (script_name, is_calibration_sup_job) = get_metainfo(job_id)

    print(f"Job with ID {job_id}, {script_name=} has finished")
    if is_calibration_sup_job:
        print(f"Results available in Redis. Notifying calibration supervisor.")
        sync(notify_job_done(job_id))


# =========================================================================
# Labber logfile extraction helpers
# =========================================================================


def extract_system_state_as_hex(logfile: Labber.LogFile):
    raw_data = logfile.getData("State Discriminator 2 States - System state")
    memory = []
    for entry in raw_data:
        memory.append([hex(int(x)) for x in entry])
    return memory


def extract_shots(logfile: Labber.LogFile):
    return int(logfile.getData("State Discriminator 2 States - Shots", 0)[0])


def extract_max_qubits(logfile: Labber.LogFile):
    return int(
        logfile.getData("State Discriminator 2 States - Max no. of qubits used", 0)[0]
    )


def extract_qobj_id(logfile: Labber.LogFile):
    return logfile.getChannelValue("State Discriminator 2 States - QObj ID")

def get_job_id_labber(labber_logfile: Labber.LogFile):
    tags = labber_logfile.getTags()
    if len(tags) == 0:
        print(f"Fatal: no tags in logfile. Can't extract job_id")
    return tags[0]

def get_metainfo(job_id: str) -> Tuple[str, str]:
    entry = fetch_redis_entry(job_id)
    script_name = entry["name"]
    is_calibration_sup_job = entry.get("is_calibration_sup_job", False)
    return (script_name, is_calibration_sup_job)

# =========================================================================
# BCC / MSS updating
# =========================================================================


def update_mss_and_bcc(memory, job_id):

    # Helper printout with first 5 outcomes
    print("Measurement results:")
    for experiment_memory in memory:
        s = str(experiment_memory[:5])
        if experiment_memory[5:6]:
            s = s.replace("]", ", ...]")
        print(s)

    MSS_JOB = str(MSS_MACHINE_ROOT_URL) + REST_API_MAP["jobs"] + "/" + job_id

    # NOTE: When MSS adds support for the 'whole job' update
    # this will be just one PUT request
    # Memory could contain more than one experiment, for now just use index 0
    response = requests.put(MSS_JOB + REST_API_MAP["result"], json=memory)
    if response:
        print("Pushed result to MSS")

    response = requests.post(MSS_JOB + REST_API_MAP["timelog"], json="RESULT")
    if response:
        print("Updated job timelog on MSS")

    response = requests.put(MSS_JOB + REST_API_MAP["status"], json="DONE")
    if response:
        print("Updated job status on MSS to DONE")

    download_url = (
        str(BCC_MACHINE_ROOT_URL) + REST_API_MAP["logfiles"] + "/" + job_id  # correct?
    )
    print(f"Download url: {download_url}")
    response = requests.put(MSS_JOB + REST_API_MAP["download_url"], json=download_url)
    if response:
        print("Updated job download_url on MSS")


# =========================================================================
# Running postprocessing_worker from command-line for testing purposes
# =========================================================================

# Note: files with missing tags may not work
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Postprocessing stand-alone program")
    parser.add_argument("--logfile", "-f", default="", type=str)
    args = parser.parse_args()

    logfile = args.logfile

    results = postprocess_labber_logfile(logfile)

    print(f"{results=}")
