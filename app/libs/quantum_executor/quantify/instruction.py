# This code is part of Tergite
#
# (C) Axel Andersson (2022)
# (C) Martin Ahindura (2025)
# (C) Chalmers Next Labs (2025)
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.
import abc
from typing import Any, Dict, List, Optional
from uuid import uuid4 as uuid

import numpy as np
from qiskit.pulse.library import discrete as qiskit_discrete_lib
from qiskit.qobj import PulseQobjConfig, PulseQobjInstruction
from quantify_scheduler import Operation
from quantify_scheduler.enums import BinMode

from app.libs.quantum_executor.base.quantum_job.dtos import NativeQobjConfig
from app.libs.quantum_executor.quantify.channel import (
    QuantifyChannel,
    QuantifyChannelRegistry,
)

QBLOX_TIMEGRID_INTERVAL = 4e-9  # 4 nanoseconds
"""
Qblox instruments send pulses in a given equidistant time grid.
See https://docs.qblox.com/en/main/cluster/q1_sequence_processor.html#acquisitions for example  

Or see the table of Q1ASM instructions at
https://docs.qblox.com/en/main/cluster/q1_sequence_processor.html#q1-instructions,
where the execution time is always a multiple of 4 as of the time of writing this code.
"""


class BaseInstruction:
    __slots__ = (
        "t0",
        "name",
        "channel",
        "port",
        "duration",
        "frequency",
        "phase",
        "memory_slot",
        "protocol",
        "parameters",
        "pulse_shape",
        "bin_mode",
        "acq_return_type",
        "label",
        "position",
    )

    t0: float
    name: str
    channel: QuantifyChannel
    port: str
    duration: float
    frequency: float
    phase: float
    memory_slot: List[int]
    protocol: str
    parameters: dict
    pulse_shape: str
    bin_mode: BinMode
    acq_return_type: type
    label: str
    position: int

    def __init__(self, **kwargs):
        self.label = str(uuid())
        for k, v in kwargs.items():
            setattr(self, k, v)
        channel: QuantifyChannel = kwargs["channel"]
        self.position = channel.register_instruction(self)

    def __eq__(self, other: object) -> bool:
        self_attrs = set(filter(lambda v: hasattr(self, v), BaseInstruction.__slots__))
        other_attrs = set(
            filter(lambda v: hasattr(other, v), BaseInstruction.__slots__)
        )

        # if they have different attributes, they cannot be equal
        if self_attrs != other_attrs:
            return False

        # label is always unique
        attrs = self_attrs
        attrs.remove("label")

        # if they have the same attributes, they must also all have the same values
        for attr in attrs:
            if getattr(self, attr) != getattr(other, attr):
                return False

        # otherwise, they are the same
        return True

    def __repr__(self) -> str:
        repr_list = [f"BaseInstruction object @ {hex(id(self))}:"]
        for attr in BaseInstruction.__slots__:
            if hasattr(self, attr):
                repr_list.append(f"\t{attr} : {getattr(self, attr)}".expandtabs(4))
        return "\n".join(repr_list)

    @property
    def unique_name(self):
        return f"{self.pretty_name}-{self.channel.clock}-{round(self.t0 * 1e9)}"

    @property
    def pretty_name(self) -> str:
        return self.name

    @property
    def final_timestamp(self) -> float:
        """The final timestamp after the duration of this instruction"""
        return self.t0 + self.duration

    def get_phase_delta(self, channel: QuantifyChannel) -> float:
        """A representation of the change in phase this instruction introduces to its channel"""
        return 0

    def get_frequency_delta(self, channel: QuantifyChannel) -> float:
        """A representation of the change in frequency this instruction introduces to its channel"""
        return 0

    def get_acquisitions_delta(self, channel: QuantifyChannel) -> int:
        """A representation of the change in acquisitions this instruction introduces to its channel"""
        return 0

    @abc.abstractmethod
    def to_operation(self, config: PulseQobjConfig) -> Operation:
        """Gets the equivalent Operation for this instruction on the associated channel

        Args:
            config: the PulseQobjConfig corresponding to the parent experiment of this instruction

        Returns:
            the Operation generated for this instruction
        """
        pass

    @classmethod
    @abc.abstractmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        config: PulseQobjConfig,
        native_config: NativeQobjConfig,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
    ) -> List["BaseInstruction"]:
        """Generates instances of instruction given a PulseQobjInstruction

        Args:
            qobj_inst: the PulseQobjInstruction to convert from
            config: the PulseQobjConfig for the instruction
            native_config: the native configuration for the qobj
            channel_registry: the registry of channels for the current experiment
            hardware_map: the mapping of the layout of the physical device

        Returns:
            instances of this class as derived from the qobj_inst
        """
        pass


class InitialObjectInstruction(BaseInstruction):
    __slots__ = ()

    def __init__(
        self,
        channel: QuantifyChannel = QuantifyChannel(clock="cl0.baseband"),
        t0=0.0,
        duration=0.0,
        **kwargs,
    ):
        kwargs["name"] = "initial_object"
        super().__init__(t0=t0, channel=channel, duration=duration, **kwargs)

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        **kwargs,
    ) -> List["InitialObjectInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        duration = _map_to_qblox_timegrid(qobj_inst.duration * 1e-9)
        channel = channel_registry.get(qobj_inst.ch)

        return [
            cls(
                t0=t0,
                channel=channel,
                duration=duration,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class AcquireInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name 'acquire'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "acquire"
        super().__init__(**kwargs)

    @property
    def pretty_name(self) -> str:
        return self.protocol

    def get_acquisitions_delta(self, channel: QuantifyChannel) -> int:
        return 1

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        native_config: NativeQobjConfig,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["AcquireInstruction"]:
        name = qobj_inst.name
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        duration = _map_to_qblox_timegrid(qobj_inst.duration * 1e-9)

        return [
            cls(
                name=name,
                t0=t0,
                channel=channel_registry.get(f"m{qubit_idx}"),
                port=hardware_map.get(f"m{qubit_idx}", name),
                duration=duration,
                memory_slot=qobj_inst.memory_slot[n],
                protocol=native_config.protocol.value,
                acq_return_type=native_config.acq_return_type,
                bin_mode=native_config.bin_mode,
            )
            for n, qubit_idx in enumerate(qobj_inst.qubits)
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        if self.protocol == "SSBIntegrationComplex":
            waveform_i = {
                "port": self.port,
                "clock": self.channel.clock,
                "t0": 0.0,
                "duration": self.duration,
                "wf_func": "quantify_scheduler.waveforms.square",
                "amp": 1,
            }
            waveform_q = {
                "port": self.port,
                "clock": self.channel.clock,
                "t0": 0.0,
                "duration": self.duration,
                "wf_func": "quantify_scheduler.waveforms.square",
                "amp": 1j,
            }
            weights = [waveform_i, waveform_q]
        elif self.protocol == "trace":
            weights = []

        else:
            raise RuntimeError(
                f"Cannot schedule acquisition with unknown protocol {self.protocol}."
            )

        operation = Operation(name=self.unique_name)
        current_acquisitions = self.channel.get_acquisitions_at_position(self.position)
        operation.data["acquisition_info"] = [
            {
                "waveforms": weights,
                "t0": 0.0,
                "clock": self.channel.clock,
                "port": self.port,
                "duration": self.duration,
                "phase": 0.0,
                # "acq_channel": instruction.memory_slot, # TODO: Fix deranged memory slot readout
                "acq_channel": int(
                    self.channel.clock[1:]
                ),  # FIXME, hardcoded single character parsing
                "acq_index": current_acquisitions - 1,
                "bin_mode": self.bin_mode,
                "acq_return_type": self.acq_return_type,
                "protocol": self.protocol,
            }
        ]

        operation._update()
        return operation


class DelayInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name 'delay'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "delay"
        super().__init__(**kwargs)

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["DelayInstruction"]:
        channel = channel_registry.get(qobj_inst.ch)
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        duration = _map_to_qblox_timegrid(qobj_inst.duration * 1e-9)

        return [
            cls(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel, channel),
                duration=duration,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class SetFreqInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name 'setf'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "setf"
        super().__init__(**kwargs)

    def get_frequency_delta(self, channel: QuantifyChannel) -> float:
        # reset the channel frequency to zero then add the instruction frequency
        return self.frequency - channel.final_frequency

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["SetFreqInstruction"]:
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)
        frequency = qobj_inst.frequency * 1e9
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)

        return [
            SetFreqInstruction(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=0.0,
                frequency=frequency,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class ShiftFreqInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name 'shiftf'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "shiftf"  # 'shiftf' does not work apparently
        super().__init__(**kwargs)

    def get_frequency_delta(self, channel: QuantifyChannel) -> float:
        return self.frequency

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["ShiftFreqInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)
        frequency = qobj_inst.frequency * 1e9

        return [
            ShiftFreqInstruction(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=0.0,
                frequency=frequency,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class SetPhaseInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with names 'setp'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "setp"
        super().__init__(**kwargs)

    def get_phase_delta(self, channel: QuantifyChannel) -> float:
        # reset the channel phase to zero then add the instruction phase
        return self.phase - channel.final_phase

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["SetPhaseInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)

        return [
            SetPhaseInstruction(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=0.0,
                phase=qobj_inst.phase,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class ShiftPhaseInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with names 'fc'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "fc"
        super().__init__(**kwargs)

    def get_phase_delta(self, channel: QuantifyChannel) -> float:
        return self.phase

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["ShiftPhaseInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)

        return [
            ShiftPhaseInstruction(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=0.0,
                phase=qobj_inst.phase,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        operation = Operation(name=self.unique_name)
        operation.data["pulse_info"] = [
            {
                "wf_func": None,
                "t0": 0.0,
                "duration": self.duration,
                "clock": self.channel.clock,
                "port": None,
            }
        ]
        operation._update()
        return operation


class ParamPulseInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name 'parametric_pulse'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "parametric_pulse"
        super().__init__(**kwargs)

    @property
    def pretty_name(self) -> str:
        return self.pulse_shape

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        config: PulseQobjConfig,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> List["ParamPulseInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        duration = _map_to_qblox_timegrid(qobj_inst.parameters["duration"] * 1e-9)
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)

        return [
            cls(
                name=qobj_inst.name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=duration,
                pulse_shape=qobj_inst.pulse_shape,
                parameters=qobj_inst.parameters,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        wf_fn = getattr(qiskit_discrete_lib, str.lower(self.pulse_shape))
        waveform = wf_fn(**self.parameters).samples
        return _generate_numerical_pulse(
            channel=self.channel, instruction=self, waveform=waveform
        )


class PulseLibInstruction(BaseInstruction):
    """Instructions from PulseQobjInstruction with name in pulse config library"""

    __slots__ = ()

    @classmethod
    def list_from_qobj_inst(
        cls,
        qobj_inst: PulseQobjInstruction,
        config: PulseQobjConfig,
        native_config: NativeQobjConfig,
        channel_registry: QuantifyChannelRegistry,
        hardware_map: Optional[Dict[str, Any]] = None,
    ) -> List["PulseLibInstruction"]:
        t0 = _map_to_qblox_timegrid(qobj_inst.t0 * 1e-9)
        channel_name = qobj_inst.ch
        channel = channel_registry.get(channel_name)
        name = qobj_inst.name
        # FIXME: pulse_library seems to be a list but is accessed here as a dict
        pulse_duration = config.pulse_library[name].shape[0]
        duration = _map_to_qblox_timegrid(pulse_duration * 1e-9)

        return [
            PulseLibInstruction(
                name=name,
                t0=t0,
                channel=channel,
                port=hardware_map.get(channel_name, channel_name),
                duration=duration,
            )
        ]

    def to_operation(self, config: PulseQobjConfig) -> Operation:
        try:
            # FIXME: pulse_library seems to be a list but is accessed here as a dict
            waveform = config.pulse_library[self.name]
            return _generate_numerical_pulse(
                channel=self.channel, instruction=self, waveform=waveform
            )
        except KeyError:
            raise RuntimeError(f"Unable to schedule operation {self}.")


def _generate_numerical_pulse(
    channel: QuantifyChannel, instruction: BaseInstruction, waveform: np.ndarray
) -> Operation:
    """Generates a numerical pulse on the given channel for the given instruction given a particular waveform

    Args:
        channel: the channel on which the pulse is to be sent
        instruction: the raw instruction
        waveform: the points that form the samples from which the numerical pulse is to be generated

    Returns:
        Operation representing the numerical pulse
    """
    current_phase = channel.get_phase_at_position(instruction.position)
    waveform *= np.exp(1.0j * current_phase)
    operation = Operation(name=instruction.unique_name)
    operation.data["pulse_info"] = [
        {
            "wf_func": "quantify_scheduler.waveforms.interpolated_complex_waveform",
            "samples": waveform.tolist(),
            "t_samples": np.linspace(0, instruction.duration, len(waveform)).tolist(),
            "duration": instruction.duration,
            "interpolation": "linear",
            "clock": instruction.channel.clock,
            "port": instruction.port,
            "t0": 0.0,
        }
    ]
    operation._update()
    return operation


def _map_to_qblox_timegrid(
    raw_time: float, grid_interval: float = QBLOX_TIMEGRID_INTERVAL
) -> float:
    """Generates the timestamp within the qblox timestamp that corresponds to the raw_timestamp

    Qblox instruments send pulses in a given equidistant time grid.
    See https://docs.qblox.com/en/main/cluster/q1_sequence_processor.html#acquisitions for example
    or see the table of Q1ASM instructions at
    https://docs.qblox.com/en/main/cluster/q1_sequence_processor.html#q1-instructions,
    where the execution time is always a multiple of 4 as of the time of writing this code.

    Args:
        raw_time: the unmapped timestamp or duration
        grid_interval: the shortest possible time between two grid lines

    Returns:
        the timestamp or duration within the qblox time grid that corresponds to the given timestamp
    """
    time_to_next_gridline = (grid_interval - raw_time) % grid_interval
    return raw_time + time_to_next_gridline
