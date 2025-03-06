# This code is part of Tergite
#
# (C) Copyright Axel Andersson 2022
# (C) Copyright Martin Ahindura 2025
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
import re
from pathlib import Path
from typing import Any, Callable, List, Literal, Match, Type, TypeVar, Union

import h5py
import numpy as np
from numpy import typing as npt
from qiskit.qobj import PulseQobjConfig
from quantify_scheduler.enums import BinMode

from ...utils.general import search_nested
from .dtos import (
    ByteOrder,
    MeasLvl,
    MeasProtocol,
    MeasRet,
    NativeQobjConfig,
    QobjData,
    QobjHeaderMetadata,
    QobjMetadata,
    QobjSweepData,
    QuantumJob,
    SweepParamMetadata,
)
from .typing import (
    QChannel,
    QDataset,
    QExperimentName,
    QJobResult,
    RepetitionsByAcquisitionsMatrix,
)

T = TypeVar("T")

_KEY_DELIMITER = "~"
_HDF5_JOB_RESULTS_PATH_REGEX = re.compile(
    f"experiments/(.*)/slot{_KEY_DELIMITER}(\d+)/measurement"
)
_HDF5_QOBJ_METADATA_PATH = "header/qobj_metadata"
_HDF5_QOBJ_DATA_PATH = "header/qobj_data"
_HDF5_HEADER_METADATA_PATH = "header/qobj/backend"
_HDF5_SWEEP_DATA_PATH = "header/qobj/sweep"


_dec_to_hex = np.frompyfunc(
    hex, nin=1, nout=1
)  # type: Callable[[npt.NDArray[np.int64]], npt.NDArray[np.str_]]
"""Converts a numpy 1D array of decimal numbers to a numpy array of hex strings

Args:
    __number: the numpy array of decimals

Returns:
    the numpy 1D array of hex strings
"""


def read_job_from_hdf5(file: Path) -> QuantumJob:
    """Extract the quantum job from the hdf5 file

    Args:
        file: the path to the file

    Returns:
        the quantum job saved in the hdf5 file
    """
    with h5py.File(file, mode="r") as hdf5_file:
        tuid = hdf5_file.attrs["tuid"]
        meas_return = MeasRet(hdf5_file.attrs["meas_return"])
        meas_level = MeasLvl(hdf5_file.attrs["meas_level"])
        meas_return_cols = hdf5_file.attrs["meas_return_cols"]
        job_id = hdf5_file.attrs.get("job_id")
        local = hdf5_file.attrs.get("local")
        raw_results = _extract_results_from_hdf5(hdf5_file)
        qobj_data = _read_hdf5_attributes(
            hdf5_file, path=_HDF5_QOBJ_DATA_PATH, type_=QobjData
        )
        metadata = _read_hdf5_attributes(
            hdf5_file, path=_HDF5_QOBJ_METADATA_PATH, type_=QobjMetadata
        )
        qobj = qobj_data.to_qobj()

    return QuantumJob(
        tuid=tuid,
        meas_return=meas_return,
        local=local,
        meas_level=meas_level,
        meas_return_cols=meas_return_cols,
        raw_results=raw_results,
        qobj_data=qobj_data,
        metadata=metadata,
        job_id=job_id,
        qobj=qobj,
    )


def save_job_in_hdf5(job: QuantumJob, file: Path):
    """Saves this job to an HDF5 file

    Args:
        job: the QuantumJob to save to HDF5 file.
        file: the path to the file where the data is to be saved
    """
    with h5py.File(file, mode="w") as hdf5_file:
        hdf5_file.attrs["tuid"] = job.tuid
        hdf5_file.attrs["meas_return"] = job.meas_return.value
        hdf5_file.attrs["meas_level"] = job.meas_level.value
        hdf5_file.attrs["meas_return_cols"] = job.meas_return_cols
        hdf5_file.attrs["memory_slot_size"] = job.memory_slot_size
        hdf5_file.attrs["job_id"] = job.job_id
        hdf5_file.attrs["local"] = job.local

        header_dict = job.qobj.header.to_dict()
        _save_qobj_header_to_hdf5(hdf5_file, header_dict=header_dict)
        _save_sweep_data_to_hdf5(hdf5_file, header_dict=header_dict)
        _save_qobj_to_hdf5(hdf5_file, job=job)
        _save_results_to_hdf5(hdf5_file, job.raw_results)


def discriminate_results(
    job: QuantumJob,
    discriminator: Callable[[int, npt.NDArray[np.complexfloating]], int],
    *,
    num_of_states: Union[Literal[2], Literal[3]] = 2,
    byteorder: ByteOrder = ByteOrder.LITTLE_ENDIAN,
    **kwargs,
) -> List[List[str]]:
    """
    Interpret measurement data from experiments as bitstrings.

    The returned hex values corresponds to how the classical slot register
    is read "from right to left" in binary if Little endian and vice versa if big-endian.
    This binary value is returned in base 16 (or hex).

    Args:
        job: quantum job whose results are to be discriminated
        discriminator: a function which takes two arguments "qubit_index" and "iq_points" (an array)
            and returns a binary value (0/1).
        num_of_states: the number of states the discriminator produces; default=2
        byteorder: the byte order of the acquisition channel list; default=ByteOrder.LITTLE_ENDIAN

    Returns:
        Nested list of the hex (base 16) representations of the states e.g. 0, 1.
        Each inner list corresponds to one experiment.
        Each item in the inner list corresponds to a shot number
    """
    assert callable(discriminator)
    discriminated_results_in_hex: List[List[str]] = []

    for expt_dataset in job.raw_results.values():
        no_of_acquisition_channels = len(expt_dataset.data_vars)
        no_of_repetitions = expt_dataset.sizes["repetition"]
        expt_discriminated_results = np.empty(
            (no_of_acquisition_channels, no_of_repetitions), dtype=np.int8
        )

        for acquisition_channel, acquisitions in expt_dataset.items():
            _, no_of_acquisitions = acquisitions.shape
            assert (
                no_of_acquisitions == 1
            ), "Max one acquisition per channel for word readout."

            idx = int(acquisition_channel)
            acquisition_data = acquisitions.data[:, 0]
            expt_discriminated_results[idx] = discriminator(idx, acquisition_data)

        # convert to hex per repetition
        bitarrays_per_rep = expt_discriminated_results.transpose()
        base_10_per_rep = _bitarrays_to_decimal(
            bitarrays_per_rep, base=num_of_states, byteorder=byteorder
        )
        hex_per_rep = _dec_to_hex(base_10_per_rep)
        discriminated_results_in_hex.append(hex_per_rep.tolist())

    return discriminated_results_in_hex


def to_native_qobj_config(config: PulseQobjConfig) -> "NativeQobjConfig":
    """Converts the pulse qobj config to native qobj config

    Args:
        config: the configuration object of the pulse qobj

    Returns:
        NativeQobjConfig instance
    """
    bin_mode = _get_bin_mode(config)
    protocol = _get_meas_protocol(config)
    meas_level = MeasLvl(config.meas_level)

    if bin_mode is BinMode.AVERAGE and protocol is MeasProtocol.SSB_INTEGRATION_COMPLEX:
        return NativeQobjConfig(
            acq_return_type=complex,
            protocol=protocol,
            bin_mode=bin_mode,
            meas_level=meas_level,
            meas_return=MeasRet.AVERAGED,
            meas_return_cols=1,
            shots=config.shots,
        )

    if bin_mode is BinMode.AVERAGE and protocol is MeasProtocol.TRACE:
        return NativeQobjConfig(
            acq_return_type=np.ndarray,
            protocol=protocol,
            bin_mode=bin_mode,
            meas_level=meas_level,
            meas_return=MeasRet.AVERAGED,
            meas_return_cols=16384,  # length of a trace
            shots=config.shots,
        )

    if bin_mode is BinMode.APPEND and protocol is MeasProtocol.SSB_INTEGRATION_COMPLEX:
        return NativeQobjConfig(
            acq_return_type=np.ndarray,
            protocol=MeasProtocol.SSB_INTEGRATION_COMPLEX,
            bin_mode=BinMode.APPEND,
            meas_level=meas_level,
            meas_return=MeasRet.APPENDED,
            meas_return_cols=config.shots,
            shots=config.shots,
        )

    raise RuntimeError(
        f"Combination {(config.meas_return, config.meas_return)} is not supported."
    )


def get_experiment_name(qobj_expt_name: str, expt_index: int):
    """
    Creates a cleaned version of a given experiment name

    Args:
        qobj_expt_name: the name as got from the qobject
        expt_index: the index of the experiment in the list of experiments in the qobject

    Returns:
        a sanitized name to use internally
    """
    name = "".join(x for x in qobj_expt_name if x.isalnum() or x in " -_,.()")
    return f"{name}{_KEY_DELIMITER}{expt_index}"


def _save_qobj_header_to_hdf5(file: h5py.File, header_dict: dict):
    """Saves the Qobj header metadata to the HDF5 file

    Args:
        file: the HDF5 file to save to
        header_dict: the dict from QobjHeader
    """
    # save header backend metadata
    backend_metadata = QobjHeaderMetadata.from_qobj_header(header_dict).dict()
    _save_hdf5_attributes(
        file, path=_HDF5_HEADER_METADATA_PATH, source=backend_metadata
    )


def _save_qobj_to_hdf5(file: h5py.File, job: QuantumJob):
    """Saves the Qobj data and metadata to the HDF5 file

    Args:
        file: the HDF5 file to save to
        job: the quantum job containing the qobj
    """
    # save the raw metadata
    if isinstance(job.metadata, QobjMetadata):
        _save_hdf5_attributes(
            file, path=_HDF5_QOBJ_METADATA_PATH, source=job.metadata.to_dict()
        )

    # save the raw data
    if isinstance(job.qobj_data, QobjData):
        _save_hdf5_attributes(
            file, path=_HDF5_QOBJ_DATA_PATH, source=job.qobj_data.to_dict()
        )


def _save_sweep_data_to_hdf5(file: h5py.File, header_dict: dict):
    """Saves the sweep data and metadata to the HDF5 file

    Args:
        file: the HDF5 file to save to
        header_dict: the dict from QobjHeader
    """
    try:
        sweep_data = QobjSweepData.from_qobj_header(header_dict)
    except ValueError:
        # return early if no sweep data
        return

    # save header sweep metadata
    _save_hdf5_attributes(file, path=_HDF5_SWEEP_DATA_PATH, source=sweep_data.metadata)

    # save the raw sweep data
    sweep_data_dict = sweep_data.dict()
    for path_segments in search_nested(sweep_data_dict, "slots"):
        sweep_group = file.require_group(_HDF5_SWEEP_DATA_PATH)
        slots_path = "/".join(path_segments)
        slots_group = sweep_group.create_group(slots_path)

        # save param metadata
        # -1 is "slots", -2 is parameter name, -3 is "parameters"
        param = path_segments[-2]
        param_group_path = f"{_HDF5_SWEEP_DATA_PATH}/parameters/{param}"
        param_metadata = SweepParamMetadata(
            **sweep_data_dict["parameters"][param]
        ).dict()
        _save_hdf5_attributes(file, path=param_group_path, source=param_metadata)

        slots_dict = _get_value_at_path(sweep_data_dict, path_segments)
        # store all specified sweep parameter data in respective HDF datasets
        for slot_idx, slot_data in slots_dict.items():
            key = f"slot{_KEY_DELIMITER}{slot_idx}"
            slots_group.create_dataset(key, data=np.asarray(slot_data))


def _save_results_to_hdf5(file: h5py.File, results: QJobResult):
    """Saves the experiment results to the HDF5 file

    The results for acquisition channel ``i`` in experiment of name ``name`` are saved at
    path ``experiments/{name}/slot~{i}/measurement`` in the file

    Args:
        file: the HDF5 file to save to
        results: the experiment results to save
    """
    for name, result in results.items():
        path = f"experiments/{name}"

        for acq_index, acq in enumerate(result.data_vars):
            channel = f"slot{_KEY_DELIMITER}{acq}"
            data_path = f"{path}/{channel}/measurement"
            data_array = result[acq]

            h5_dataset = file.require_dataset(
                data_path,
                shape=data_array.shape,
                dtype=data_array.dtype,
            )

            h5_dataset[...] = data_array


def _extract_results_from_hdf5(
    file: h5py.File,
) -> QJobResult:
    """Retrieves the experiment results from the HDF5 file

    Args:
        file: the HDF5 file to save to

    Returns:
        dict of the results with keys as experiment name and values as xarray.Dataset
    """
    measurement_paths = _match_hdf5_paths(file, pattern=_HDF5_JOB_RESULTS_PATH_REGEX)

    results: QJobResult = {}
    for path_match in measurement_paths:
        path = path_match.group(0)
        expt_name = path_match.group(1)
        acq = path_match.group(2)

        xarray_dataset = results.get(expt_name)
        if xarray_dataset is None:
            results[expt_name] = xarray_dataset = QDataset()

        hdf5_dataset: h5py.Dataset = file[path]
        xarray_dataset[acq] = (["repetition", f"acq_index_{acq}"], hdf5_dataset[:])

    return results


def _match_hdf5_paths(file: h5py.File, pattern: re.Pattern) -> List[Match]:
    """Gets the HDF5 paths that match the given pattern

    Args:
        file: the HDF5 file
        pattern: the regex pattern to test against

    Returns:
        the list of path matches for the pattern
    """
    measurement_paths: List[Match] = []

    def collect_path_matches(name: str):
        if match := pattern.match(name):
            measurement_paths.append(match)

    file.visit(collect_path_matches)

    return measurement_paths


def _save_hdf5_attributes(file: h5py.File, path: str, source: dict):
    """Saves the whole dict to HDF5 attributes at the given path

    Args:
        file: the HDF5 file
        path: the /-separated path to the group
        source: the dictionary to copy from
    """
    if len(source) == 0:
        # do nothing if dict is empty
        return

    if path not in file:
        group = file.create_group(path, track_order=True)
    else:
        group = file[path]

    for key, value in source.items():
        group.attrs[key] = value


def _read_hdf5_attributes(file: h5py.File, path: str, type_: Type[T] = dict) -> T:
    """Reads the HDF5 attributes at the given path

    Args:
        file: the HDF5 file
        path: the /-separated path to the group
        type_: the type of the returned instance

    Returns:
        the metadata (attrs) saved at the given path, cast to the given type_

    Raises:
        KeyError: `path`
    """
    group = file[path]
    return type_(**group.attrs)


def _get_value_at_path(data: dict, path: List[str]) -> Any:
    """Retrieves the value at the given path of the nested dict data

    e.g. ["foo", "bar", "py"] return data["foo"]["bar"]["py"]

    Args:
        data: the nested dictionary
        path: the path to the value needed

    Returns:
        the value at the given path
    """
    value = data
    for part in path:
        value = data[part]

    return value


def _get_bin_mode(qobj_conf: PulseQobjConfig) -> BinMode:
    """Gets the BinMode based on the meas_return of the qobj.config

    Args:
        qobj_conf: the qobject config whose bin mode is to be obtained

    Returns:
        the BinMode for the given qobj
    """
    meas_return = qobj_conf.meas_return
    if isinstance(meas_return, int):
        return {
            int(MeasRet.APPENDED): BinMode.APPEND,
            int(MeasRet.AVERAGED): BinMode.AVERAGE,
        }[meas_return]

    # FIXME: For some reason, PulseQobjConfig expects to be an int
    #   yet our fixtures all have strings.
    meas_return = str.lower(qobj_conf.meas_return)
    return {
        "avg": BinMode.AVERAGE,
        "average": BinMode.AVERAGE,
        "averaged": BinMode.AVERAGE,
        "single": BinMode.APPEND,
        "append": BinMode.APPEND,
        "appended": BinMode.APPEND,
    }[meas_return]


def _get_meas_protocol(qobj_conf: PulseQobjConfig) -> "MeasProtocol":
    """Gets the measurement protocol for the given qobject

    Args:
        qobj_conf: the qobject config from which to extract the measurement protocol

    Returns:
        the measurement protocol for the given qobject
    """
    return {
        0: MeasProtocol.TRACE,
        1: MeasProtocol.SSB_INTEGRATION_COMPLEX,
        2: MeasProtocol.SSB_INTEGRATION_COMPLEX,
    }[qobj_conf.meas_level]


def _bitarrays_to_decimal(
    array: npt.NDArray[np.int8],
    base: int,
    byteorder: ByteOrder = ByteOrder.LITTLE_ENDIAN,
):
    """
    Convert a 2D array in any base to integers in base 10 with selectable byte order.

    Parameters:
        array: Input 2D array of integers in the specified base.
        base: The base of the input array (e.g., 2 for binary, 3 for base-3).
        byteorder: 'big-endian' (MSD first), or 'little-endian' (LSD first).

    Returns:
        numpy.ndarray: 1D array of integers representing each row.
    """
    # Flip the array for little-endian (LSD first)
    if byteorder == ByteOrder.LITTLE_ENDIAN:
        array = array[:, ::-1]

    # Compute the powers of the base, e.g. for base 3 => [3^2, 3^1, 3^0]
    powers_of_base = base ** np.arange(array.shape[1] - 1, -1, -1)

    # Convert each row to integers (base 10)
    integers = array @ powers_of_base

    return integers
