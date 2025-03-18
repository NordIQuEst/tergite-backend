# This code is part of Tergite
#
# (C) Copyright Martin Ahindura 2024
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
import os
from os import environ

from app.tests.utils.fixtures import get_fixture_path

TEST_DEFAULT_PREFIX = "system_test"
TEST_STORAGE_ROOT = "/tmp/jobs"

TEST_DEFAULT_PREFIX_SIM_1Q = "qiskit_pulse_1q"
TEST_DEFAULT_PREFIX_SIM_2Q = "qiskit_pulse_2q"

TEST_LOGFILE_DOWNLOAD_POOL_DIRNAME = "logfile_download_pool"
TEST_LOGFILE_UPLOAD_POOL_DIRNAME = "logfile_upload_pool"
TEST_JOB_UPLOAD_POOL_DIRNAME = "job_upload_pool"
TEST_JOB_EXECUTION_POOL_DIRNAME = "job_execution_pool"
TEST_JOB_PRE_PROC_POOL_DIRNAME = "job_pre_proc_pool"
TEST_STORAGE_PREFIX_DIRNAME = TEST_DEFAULT_PREFIX
TEST_JOB_SUPERVISOR_LOG = "job_supervisor.log"
TEST_EXECUTOR_DATA_DIRNAME = "test_executor_data"

TEST_MSS_MACHINE_ROOT_URL = "http://localhost:8002"
TEST_BCC_MACHINE_ROOT_URL = "http://localhost:8000"
TEST_BCC_PORT = 8000

TEST_MSS_APP_TOKEN = "some-mss-app-token-for-testing"

TEST_QUANTIFY_CONFIG_FILE = get_fixture_path("dummy-quantify-config.json")
TEST_QUANTIFY_METADATA_FILE = get_fixture_path("dummy-quantify-metadata.yml")
TEST_BROKEN_QUANTIFY_METADATA_FILE = get_fixture_path("broken-quantify-config.yml")
TEST_BROKEN_QUANTIFY_CONFIG_FILE = get_fixture_path("broken-quantify-config.json")

TEST_BACKEND_SETTINGS_FILE = get_fixture_path("backend_config.toml")
TEST_SIMQ1_BACKEND_SETTINGS_FILE = get_fixture_path("backend_config.simq1.toml")
TEST_SIMQ2_BACKEND_SETTINGS_FILE = get_fixture_path("backend_config.simq2.toml")

TEST_QUANTIFY_SEED_FILE = get_fixture_path("dummy_quantify.seed.toml")

TEST_QISKIT_1Q_SEED_FILE = get_fixture_path("qiskit_pulse_1q.seed.toml")
TEST_QISKIT_2Q_SEED_FILE = get_fixture_path("qiskit_pulse_2q.seed.toml")

TEST_REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
TEST_REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TEST_REDIS_DB = int(os.getenv("REDIS_DB", "2"))


def setup_test_env():
    """Sets up the test environment.

    It should be run before any imports
    """
    environ["APP_SETTINGS"] = "test"
    environ["DEFAULT_PREFIX"] = TEST_DEFAULT_PREFIX
    environ["STORAGE_ROOT"] = TEST_STORAGE_ROOT
    environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE

    environ["QUANTIFY_CONFIG_FILE"] = TEST_QUANTIFY_CONFIG_FILE
    environ["QUANTIFY_METADATA_FILE"] = TEST_QUANTIFY_METADATA_FILE

    environ["LOGFILE_DOWNLOAD_POOL_DIRNAME"] = TEST_LOGFILE_DOWNLOAD_POOL_DIRNAME
    environ["LOGFILE_UPLOAD_POOL_DIRNAME"] = TEST_LOGFILE_UPLOAD_POOL_DIRNAME
    environ["JOB_UPLOAD_POOL_DIRNAME"] = TEST_JOB_UPLOAD_POOL_DIRNAME
    environ["JOB_EXECUTION_POOL_DIRNAME"] = TEST_JOB_EXECUTION_POOL_DIRNAME
    environ["JOB_PRE_PROC_POOL_DIRNAME"] = TEST_JOB_PRE_PROC_POOL_DIRNAME
    environ["STORAGE_PREFIX_DIRNAME"] = TEST_STORAGE_PREFIX_DIRNAME
    environ["JOB_SUPERVISOR_LOG"] = TEST_JOB_SUPERVISOR_LOG
    environ["EXECUTOR_DATA_DIRNAME"] = TEST_EXECUTOR_DATA_DIRNAME

    environ["MSS_MACHINE_ROOT_URL"] = TEST_MSS_MACHINE_ROOT_URL
    environ["BCC_MACHINE_ROOT_URL"] = TEST_BCC_MACHINE_ROOT_URL
    environ["BCC_PORT"] = f"{TEST_BCC_PORT}"

    environ["MSS_APP_TOKEN"] = TEST_MSS_APP_TOKEN
    environ["QUANTIFY_CONFIG_FILE"] = TEST_QUANTIFY_CONFIG_FILE
    environ["IS_AUTH_ENABLED"] = "True"

    environ["REDIS_HOST"] = TEST_REDIS_HOST
    environ["REDIS_PORT"] = f"{TEST_REDIS_PORT}"
    environ["REDIS_DB"] = f"{TEST_REDIS_DB}"
