# This code is part of Tergite
#
# (C) Axel Andersson (2022)
# (C) Martin Ahindura (2025)
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

import enum
from typing import Union, Type, List
from uuid import uuid4 as uuid

import numpy as np
from pydantic import BaseModel
from quantify_scheduler.enums import BinMode

from app.libs.storage_file import MeasLvl, MeasRet


class MeasProtocol(str, enum.Enum):
    SSB_INTEGRATION_COMPLEX = "SSBIntegrationComplex"
    TRACE = "trace"


class MeasSettings(BaseModel):
    """Settings for running measurements"""

    acq_return_type: Union[Type[complex], Type[np.ndarray]]
    protocol: MeasProtocol
    bin_mode: BinMode
    meas_level: MeasLvl
    meas_return: MeasRet
    meas_return_cols: int


class Instruction:
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
    )

    t0: float
    name: str
    channel: str
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

    def __init__(self: object, **kwargs):
        self.label = str(uuid())
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __eq__(self: object, other: object) -> bool:
        self_attrs = set(
            filter(lambda attr: hasattr(self, attr), Instruction.__slots__)
        )
        other_attrs = set(
            filter(lambda attr: hasattr(other, attr), Instruction.__slots__)
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

    def __repr__(self: object) -> str:
        repr_list = [f"Instruction object @ {hex(id(self))}:"]
        for attr in Instruction.__slots__:
            if hasattr(self, attr):
                repr_list.append(f"\t{attr} : {getattr(self, attr)}".expandtabs(4))
        return "\n".join(repr_list)

    @property
    def unique_name(self):
        return f"{self.pretty_name}-{self.channel}-{round(self.t0 * 1e9)}"

    @property
    def pretty_name(self) -> str:
        return self.name


class InitialObjectInstruction(Instruction):
    __slots__ = ()

    def __init__(self, t0=0.0, channel="cl0.baseband", duration=0.0, **kwargs):
        kwargs["name"] = "initial_object"
        super().__init__(t0=t0, channel=channel, duration=duration, **kwargs)


class AcquireInstruction(Instruction):
    """Instructions from PulseQobjInstruction with name 'acquire'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "acquire"
        super().__init__(**kwargs)

    @property
    def pretty_name(self) -> str:
        return self.protocol


class DelayInstruction(Instruction):
    """Instructions from PulseQobjInstruction with name 'delay'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "delay"
        super().__init__(**kwargs)


class FreqInstruction(Instruction):
    """Instructions from PulseQobjInstruction with name 'setf'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        assert kwargs["name"] in ("setf",)  # 'shiftf' does not work apparently
        super().__init__(**kwargs)


class PhaseInstruction(Instruction):
    """Instructions from PulseQobjInstruction with names 'setp', or 'fc'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        assert kwargs["name"] in ("setp", "fc")
        super().__init__(**kwargs)


class ParamPulseInstruction(Instruction):
    """Instructions from PulseQobjInstruction with name 'parametric_pulse'"""

    __slots__ = ()

    def __init__(self, **kwargs):
        kwargs["name"] = "parametric_pulse"
        super().__init__(**kwargs)

    @property
    def pretty_name(self) -> str:
        return self.pulse_shape


class PulseLibInstruction(Instruction):
    """Instructions from PulseQobjInstruction with name in pulse config library"""

    __slots__ = ()
