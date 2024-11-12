import redis

from .utils.env import (
    TEST_DEFAULT_PREFIX,
    TEST_DEFAULT_PREFIX_SIM_1Q,
    TEST_DEFAULT_PREFIX_SIM_2Q,
    TEST_LOGFILE_DOWNLOAD_POOL_DIRNAME,
    TEST_MSS_MACHINE_ROOT_URL,
    TEST_STORAGE_PREFIX_DIRNAME,
    TEST_STORAGE_ROOT,
    setup_test_env,
    TEST_SIMQ1_BACKEND_SETTINGS_FILE,
    TEST_SIMQ2_BACKEND_SETTINGS_FILE,
    TEST_BACKEND_SETTINGS_FILE,
    TEST_REDIS_HOST,
    TEST_REDIS_PORT,
    TEST_REDIS_DB,
)

# set up the environment before any other import
setup_test_env()

import logging
import os
import shutil
from pathlib import Path
from typing import Dict

import pytest
import numpy as np
from fakeredis import FakeStrictRedis
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest_lazyfixture import lazy_fixture
from redis.client import Redis
from rq import SimpleWorker

from ..utils.queues import QueuePool
from .utils.fixtures import load_fixture
from .utils.http import MockHttpResponse, MockHttpSession
from .utils.analysis import MockLinearDiscriminantAnalysis
from .utils.modules import remove_modules
from .utils.rq import get_rq_worker
from ..libs.properties import DeviceCalibrationV2


_lda_parameters_fixture = load_fixture("lda_parameters.json")
_test_backend_props_fixture = load_fixture("test_backend_props.json")
_test_backend_sim1q_props_fixture = load_fixture("test_backend_sim1q_props.json")
_test_backend_sim2q_props_fixture = load_fixture("test_backend_sim2q_props.json")
_real_redis = redis.Redis(
    host=TEST_REDIS_HOST,
    port=TEST_REDIS_PORT,
    db=TEST_REDIS_DB,
)
_fake_redis = FakeStrictRedis()
_async_queue_pool = QueuePool(
    prefix=TEST_DEFAULT_PREFIX, connection=_real_redis, is_async=True
)
_sync_queue_pool = QueuePool(
    prefix=TEST_DEFAULT_PREFIX, connection=_fake_redis, is_async=False
)

MOCK_NOW = "2023-11-27T12:46:48.851656+00:00"
TEST_APP_TOKEN_STRING = "eecbf107ad103f70187923f49c1a1141219da95f1ab3906f"

FASTAPI_CLIENTS = [
    lazy_fixture("async_fastapi_client"),
    lazy_fixture("async_fastapi_client_with_qiskit_simulator"),
    lazy_fixture("async_fastapi_client_with_qiskit_simulator_2_qubit")
    # FIXME: inform-job-location-stage logic is non-deterministic
    # lazy_fixture("sync_fastapi_client"),
]
BLACKLISTED_FASTAPI_CLIENTS = [
    lazy_fixture("blacklisted_async_fastapi_client"),
    lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator"),
    lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator_2_qubit"),
    # FIXME: inform-job-location-stage logic is non-deterministic
    # lazy_fixture("blacklisted_sync_fastapi_client"),
]

CLIENTS = [
    (lazy_fixture("async_fastapi_client"), lazy_fixture("real_redis_client")),
    (
        lazy_fixture("async_fastapi_client_with_qiskit_simulator"),
        lazy_fixture("real_redis_client"),
    ),
    (
        lazy_fixture("async_fastapi_client_with_qiskit_simulator_2_qubit"),
        lazy_fixture("real_redis_client"),
    ),
    # FIXME: inform-job-location-stage logic is non-deterministic
    # (lazy_fixture("sync_fastapi_client"), lazy_fixture("fake_redis_client")),
]

BLACKLISTED_CLIENTS = [
    (
        lazy_fixture("blacklisted_async_fastapi_client"),
        lazy_fixture("real_redis_client"),
    ),
    (
        lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator"),
        lazy_fixture("real_redis_client"),
    ),
    (
        lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator_2_qubit"),
        lazy_fixture("real_redis_client"),
    ),
    # FIXME: inform-job-location-stage logic is non-deterministic
    # (lazy_fixture("blacklisted_sync_fastapi_client"), lazy_fixture("fake_redis_client")),
]

CLIENT_AND_RQ_WORKER_TUPLES = [
    (
        lazy_fixture("async_fastapi_client"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    (
        lazy_fixture("async_fastapi_client_with_qiskit_simulator"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    (
        lazy_fixture("async_fastapi_client_with_qiskit_simulator_2_qubit"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    # FIXME: inform-job-location-stage logic is non-deterministic
    # (
    #     lazy_fixture("sync_fastapi_client"),
    #     lazy_fixture("fake_redis_client"),
    #     lazy_fixture("sync_rq_worker"),
    # ),
    # (
    #     lazy_fixture("sync_fastapi_client_with_qiskit_simulator"),
    #     lazy_fixture("fake_redis_client"),
    #     lazy_fixture("sync_rq_worker"),
    # ),
]

BLACKLISTED_CLIENT_AND_RQ_WORKER_TUPLES = [
    (
        lazy_fixture("blacklisted_async_fastapi_client"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    (
        lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    (
        lazy_fixture("blacklisted_async_fastapi_client_with_qiskit_simulator_2_qubit"),
        lazy_fixture("real_redis_client"),
        lazy_fixture("async_rq_worker"),
    ),
    # FIXME: inform-job-location-stage logic is non-deterministic
    # (
    #     lazy_fixture("blacklisted_sync_fastapi_client"),
    #     lazy_fixture("fake_redis_client"),
    #     lazy_fixture("sync_rq_worker"),
    # ),
    # (
    #     lazy_fixture("blacklisted_sync_fastapi_client_with_qiskit_simulator"),
    #     lazy_fixture("fake_redis_client"),
    #     lazy_fixture("sync_rq_worker"),
    # ),
]

_mock_linear_discriminant_analysis = MockLinearDiscriminantAnalysis(
    result={
        "intercept_": np.array([0.70658014]),
        "coef_": np.array([[-24.30078533, 22.61843697]]),
    }
)

_mock_linear_discriminant_analysis_sim2q = MockLinearDiscriminantAnalysis(
    result={
        "intercept_": np.array([-0.3046965737769689, -0.38509625914248247]),
        "coef_": np.array(
            [
                [-33.678566762457024, 20.606250322051658],
                [-37.36457774060694, 22.99757458442274],
            ]
        ),
    }
)


def mock_post_requests(url: str, **kwargs):
    """Mock POST requests for testing"""
    if url == f"{TEST_MSS_MACHINE_ROOT_URL}/timelog":
        return MockHttpResponse(status_code=200)


def mock_mss_get_requests(url: str, **kwargs):
    """Mock GET requests sent to MSS for testing"""
    if url.endswith("properties/lda_parameters"):
        return MockHttpResponse(status_code=200, json=_lda_parameters_fixture)
    if url.endswith(f"backends/{TEST_DEFAULT_PREFIX}"):
        return MockHttpResponse(status_code=200, json=_test_backend_props_fixture)
    if url.endswith(f"backends/{TEST_DEFAULT_PREFIX_SIM_1Q}"):
        return MockHttpResponse(status_code=200, json=_test_backend_sim1q_props_fixture)
    if url.endswith(f"backends/{TEST_DEFAULT_PREFIX_SIM_2Q}"):
        return MockHttpResponse(status_code=200, json=_test_backend_sim2q_props_fixture)


def mock_mss_put_requests(url: str, **kwargs):
    """Mock PUT requests sent to MSS for testing"""
    payload = kwargs.get("json", {})
    is_jobs_update_url = url.startswith(f"{TEST_MSS_MACHINE_ROOT_URL}/jobs")

    if is_jobs_update_url and "timestamps" in payload:
        return MockHttpResponse(status_code=200)
    if is_jobs_update_url and "result" in payload:
        return MockHttpResponse(status_code=200)
    if url.startswith(f"{TEST_MSS_MACHINE_ROOT_URL}/v2/devices"):
        return MockHttpResponse(status_code=200)

    return MockHttpResponse(status_code=405)


def mock_mss_post_requests(url: str, **kwargs):
    """Mock POST requests sent to MSS for testing"""
    payload = kwargs.get("json", [])

    if url.startswith(f"{TEST_MSS_MACHINE_ROOT_URL}/v2/calibrations"):
        try:
            _parsed_payload = [DeviceCalibrationV2(**props) for props in payload]
            return MockHttpResponse(status_code=200)
        except Exception as exp:
            logging.error(exp)
            return MockHttpResponse(status_code=400)

    return MockHttpResponse(status_code=405)


@pytest.fixture
def real_redis_client() -> Redis:
    """A mock redis client"""
    yield _real_redis
    _real_redis.flushall()


@pytest.fixture
def fake_redis_client() -> Redis:
    """A mock redis client"""
    yield _fake_redis
    _fake_redis.flushall()


@pytest.fixture
def async_rq_worker() -> SimpleWorker:
    """Get the rq worker for running async tasks asynchronously"""
    yield get_rq_worker(_async_queue_pool)


@pytest.fixture
def sync_rq_worker() -> SimpleWorker:
    """Get the rq worker for running tasks synchronously"""
    yield get_rq_worker(_sync_queue_pool)


@pytest.fixture
def async_fastapi_client(mocker) -> TestClient:
    """A test client for fast api when rq is running asynchronously"""
    remove_modules(["app", "settings"])
    _patch_async_client(mocker)
    os.environ["EXECUTOR_TYPE"] = "quantify"
    os.environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


@pytest.fixture
def async_fastapi_client_with_qiskit_simulator(mocker) -> TestClient:
    """A test client for fast api when rq is running asynchronously"""
    remove_modules(["app", "settings"])
    _patch_async_client(mocker)
    os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_1q"
    os.environ["DEFAULT_PREFIX"] = "qiskit_pulse_1q"
    os.environ["BACKEND_SETTINGS"] = TEST_SIMQ1_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


@pytest.fixture
def async_fastapi_client_with_qiskit_simulator_2_qubit(mocker) -> TestClient:
    """A test client for fast api when rq is running asynchronously"""
    remove_modules(["app", "settings"])
    _patch_async_client_sim2q(mocker)
    os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_2q"
    os.environ["DEFAULT_PREFIX"] = "qiskit_pulse_2q"
    os.environ["BACKEND_SETTINGS"] = TEST_SIMQ2_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


@pytest.fixture
def async_standalone_backend_client(mocker) -> TestClient:
    """A test client for fast api when rq is running asynchronously and backend is standalone"""
    remove_modules(["app", "settings"])

    mocker.patch("redis.Redis", return_value=_real_redis)
    mocker.patch("app.utils.queues.QueuePool", return_value=_async_queue_pool)

    os.environ["EXECUTOR_TYPE"] = "quantify"
    os.environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE
    os.environ["IS_STANDALONE"] = "True"

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


# @pytest.fixture
# def sync_fastapi_client(mocker) -> TestClient:
#     """A test client for fast api when rq is running synchronously"""
#     remove_modules(["app", "settings"])
#     _patch_sync_client(mocker)
#     os.environ["EXECUTOR_TYPE"] = "quantify"
#     os.environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE
#
#     from app.api import app
#
#     with freeze_time(MOCK_NOW):
#         yield TestClient(app)

# @pytest.fixture
# def sync_fastapi_client_with_qiskit_simulator(mocker) -> TestClient:
#     """A test client for fast api when rq is running synchronously when qiskit-dynamics is executor"""
#     remove_modules(["app", "settings"])
#     _patch_sync_client(mocker)
#     os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_1q"
#     os.environ["BACKEND_SETTINGS"] = TEST_SIMQ1_BACKEND_SETTINGS_FILE
#
#     from app.api import app
#
#     with freeze_time(MOCK_NOW):
#         yield TestClient(app)


@pytest.fixture
def blacklisted_async_fastapi_client(mocker) -> TestClient:
    """A test client with black listed ip for fast api when rq is running asynchronously"""
    remove_modules(["app", "settings"])
    _patch_async_client(mocker)
    os.environ["BLACKLISTED"] = "True"
    os.environ["EXECUTOR_TYPE"] = "quantify"
    os.environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


@pytest.fixture
def blacklisted_async_fastapi_client_with_qiskit_simulator(mocker) -> TestClient:
    """A test client with black listed ip for fast api when rq is running asynchronously
    when qiskit dynamics is executor"""
    remove_modules(["app", "settings"])
    _patch_async_client(mocker)
    os.environ["BLACKLISTED"] = "True"
    os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_1q"
    os.environ["BACKEND_SETTINGS"] = TEST_SIMQ1_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


@pytest.fixture
def blacklisted_async_fastapi_client_with_qiskit_simulator_2_qubit(
    mocker,
) -> TestClient:
    """A test client with black listed ip for fast api when rq is running asynchronously
    when qiskit dynamics is executor"""
    remove_modules(["app", "settings"])
    _patch_async_client(mocker)
    os.environ["BLACKLISTED"] = "True"
    os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_2q"
    os.environ["BACKEND_SETTINGS"] = TEST_SIMQ2_BACKEND_SETTINGS_FILE

    from app.api import app

    with freeze_time(MOCK_NOW):
        yield TestClient(app)


# @pytest.fixture
# def blacklisted_sync_fastapi_client(mocker) -> TestClient:
#     """A test client for fast api when rq is running synchronously and its IP is blacklisted"""
#     remove_modules(["app", "settings"])
#     _patch_sync_client(mocker)
#     os.environ["BLACKLISTED"] = "True"
#     os.environ["EXECUTOR_TYPE"] = "quantify"
#     os.environ["BACKEND_SETTINGS"] = TEST_BACKEND_SETTINGS_FILE
#
#     from app.api import app
#
#     with freeze_time(MOCK_NOW):
#         yield TestClient(app)

# @pytest.fixture
# def blacklisted_sync_fastapi_client_with_qiskit_simulator(mocker) -> TestClient:
#     """A test client for fast api when rq is running synchronously and its IP is blacklisted when
#     qiskit dynamics is executor"""
#     remove_modules(["app", "settings"])
#     _patch_sync_client(mocker)
#     os.environ["BLACKLISTED"] = "True"
#     os.environ["EXECUTOR_TYPE"] = "qiskit_pulse_1q"
#     os.environ["BACKEND_SETTINGS"] = TEST_SIMQ1_BACKEND_SETTINGS_FILE
#
#     from app.api import app
#
#     with freeze_time(MOCK_NOW):
#         yield TestClient(app)


@pytest.fixture
def client_jobs_folder() -> Path:
    """A temporary folder for the client where jobs can be saved"""
    folder_path = Path("./tmp/jobs")
    folder_path.mkdir(parents=True, exist_ok=True)

    yield folder_path
    shutil.rmtree(folder_path, ignore_errors=True)


@pytest.fixture
def logfile_download_folder() -> Path:
    """A temporary folder for the server where logfiles can be downloaded from"""
    folder_path = (
        Path(TEST_STORAGE_ROOT)
        / TEST_STORAGE_PREFIX_DIRNAME
        / TEST_LOGFILE_DOWNLOAD_POOL_DIRNAME
    )
    folder_path.mkdir(parents=True, exist_ok=True)

    yield folder_path
    shutil.rmtree(folder_path, ignore_errors=True)


@pytest.fixture
def storage_root():
    """root where files are stored temporarily"""
    path = Path(TEST_STORAGE_ROOT)
    path.mkdir(parents=True, exist_ok=True)
    yield path
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def app_token_header() -> Dict[str, str]:
    """the authorization header with the app token"""

    yield {"Authorization": f"Bearer {TEST_APP_TOKEN_STRING}"}


def _patch_async_client(mocker):
    """Patches the async client"""
    mss_client = MockHttpSession(
        put=mock_mss_put_requests,
        get=mock_mss_get_requests,
        post=mock_mss_post_requests,
    )

    mocker.patch("redis.Redis", return_value=_real_redis)
    mocker.patch("app.utils.queues.QueuePool", return_value=_async_queue_pool)
    mocker.patch("requests.post", side_effect=mock_post_requests)
    mocker.patch("requests.Session", return_value=mss_client)
    mocker.patch(
        "sklearn.discriminant_analysis.LinearDiscriminantAnalysis",
        return_value=_mock_linear_discriminant_analysis,
    )
    os.environ["BLACKLISTED"] = ""


def _patch_async_client_sim2q(mocker):
    """Patches the async client"""
    mss_client = MockHttpSession(
        put=mock_mss_put_requests,
        get=mock_mss_get_requests,
        post=mock_mss_post_requests,
    )

    mocker.patch("redis.Redis", return_value=_real_redis)
    mocker.patch("app.utils.queues.QueuePool", return_value=_async_queue_pool)
    mocker.patch("requests.post", side_effect=mock_post_requests)
    mocker.patch("requests.Session", return_value=mss_client)
    mocker.patch(
        "sklearn.discriminant_analysis.LinearDiscriminantAnalysis",
        return_value=_mock_linear_discriminant_analysis_sim2q,
    )
    os.environ["BLACKLISTED"] = ""


def _patch_sync_client(mocker):
    """Patches the sync client"""
    mss_client = MockHttpSession(
        put=mock_mss_put_requests,
        get=mock_mss_get_requests,
        post=mock_mss_post_requests,
    )

    mocker.patch("redis.Redis", return_value=_fake_redis)
    mocker.patch("app.utils.queues.QueuePool", return_value=_sync_queue_pool)
    mocker.patch("requests.post", side_effect=mock_post_requests)
    mocker.patch("requests.Session", return_value=mss_client)
    mocker.patch(
        "sklearn.discriminant_analysis.LinearDiscriminantAnalysis",
        return_value=_mock_linear_discriminant_analysis,
    )
    os.environ["BLACKLISTED"] = ""
