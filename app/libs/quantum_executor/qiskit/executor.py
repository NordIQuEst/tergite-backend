# This code is part of Tergite
#
# (C) Stefan Hill (2024)
#
# This code is licensed under the Apache License, Version 2.0. You may
# obtain a copy of this license in the LICENSE.txt file in the root directory
# of this source tree or at http://www.apache.org/licenses/LICENSE-2.0.
#
# Any modifications or derivative works of this code must retain this
# copyright notice, and modified files need to carry a notice indicating
# that they have been altered from the originals.

from functools import partial

import xarray
from qiskit.qobj import PulseQobj

import app.libs.storage_file as storagefile
from app.libs.quantum_executor.base.executor import QuantumExecutor
from app.libs.quantum_executor.base.experiment import BaseExperiment
from app.libs.quantum_executor.qiskit.experiment import QiskitDynamicsExperiment
from app.libs.quantum_executor.utils.channel import Channel
from app.libs.quantum_executor.utils.instruction import Instruction
from .backend import FakeOpenPulse1Q
from .transpile import transpile


class QiskitDynamicsExecutor(QuantumExecutor):
    def __init__(self, config_file):
        super().__init__()

        self.backend = FakeOpenPulse1Q()

    def run(self, experiment: BaseExperiment, /) -> xarray.Dataset:
        job = self.backend.run(experiment.schedule)
        result = job.result()
        return result.data()["memory"]
    def construct_experiments(self, qobj: PulseQobj, /):
        # storage array
        tx = list()
        for experiment_index, experiment in enumerate(qobj.experiments):
            # TODO SIM: This whole thing to translate everything into a wrapper object for the instruction is not necessary
            # - We can directly take the qobj as it is
            # - In the qobj there is a list of experiments
            # - We have to iterate over the experiments and create a schedule for each of them

            instructions = map(
                partial(Instruction.from_qobj, config=qobj.config),
                experiment.instructions,
            )
            instructions = [item for sublist in instructions for item in sublist]

            # create a nice name for the experiment.
            experiment.header.name = storagefile.StorageFile.sanitized_name(
                experiment.header.name, experiment_index + 1
            )

            # convert OpenPulse experiment to Qiskit Dynamics schedule
            # TODO SIM: If we wanted to get rid of this overly complicated notation of the Experiment object, we would have to check where it is used in the storage file as well
            tx.append(
                QiskitDynamicsExperiment(
                    header=experiment.header,
                    instructions=instructions,
                    config=qobj.config,
                    channels=frozenset(
                        Channel(
                            clock=i.channel,
                            frequency=0.0,
                        )
                        for i in instructions
                    ),
                    logger=self.logger,
                )
            )

        self.logger.info(f"Translated {len(tx)} OpenPulse experiments.")
        return tx

    def close(self):
        pass

class QiskitDynamicsPulseSimulator1Q(QuantumExecutor):
    
    def __init__(self, config_file):
        super().__init__()
        self.backend = FakeOpenPulse1Q(
            meas_level=1, 
            meas_return="single"
            )
    

    def run(self, experiment: BaseExperiment, /) -> xarray.Dataset:
        job = self.backend.run(experiment)
        result = job.result()
 
        return result.data()["memory"]
        # if results.success:
        #     return result.results[0]
        # else:
        #     # raise error 
        #     print("Job failed")
        #     return {}
        # TODO: return xarray Dataset with Data for each acquisition channel corresponding to a qubit 
        # Example of Dataset init 
        # ds = xr.Dataset(
        #     data_vars=dict(
        #         temperature=(["loc", "instrument", "time"], temperature),
        #         precipitation=(["loc", "instrument", "time"], precipitation),
        #     ),
        #     coords=dict(
        #         lon=("loc", lon),
        #         lat=("loc", lat),
        #         instrument=instruments,
        #         time=time,
        #         reference_time=reference_time,
        #     ),
        #     attrs=dict(description="Weather related data."),
        # )



    
    def construct_experiments(self, qobj: PulseQobj, /):
        
         # TODO SIM: If we wanted to get rid of this overly complicated notation of the Experiment object, we would have to check where it is used in the storage file as well
         # TODO SIM: Some shortcuts were implemented to return readout values to client directly in Storage and here we compile qobj directly 

        qobj_dict = qobj.to_dict()
        tx = transpile(qobj_dict)

        self.logger.info(f"Translated {len(tx)} OpenPulse experiments.")
        return tx
    
    def close(self):
        pass 


