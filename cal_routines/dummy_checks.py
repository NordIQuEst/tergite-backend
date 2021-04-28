from scenario_scripts import qobj_dummy_scenario
from examples.generate_jobs.qobj_stub_single import generate_job
from uuid import uuid4
import random


def check_dummy():
    job_id = uuid4()
    job = generate_job()
    random_shots = random.randint(1, 1024)
    job["params"]["qobj"]["config"]["shots"] = random_shots
    print(f"Adding shots value {random_shots} to check job")
    scenario = qobj_dummy_scenario(job)
    scenario.tags.tags = [job_id, "calibration", "dummy"]
    return scenario