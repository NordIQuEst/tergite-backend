FROM python:3.9-slim-bullseye

WORKDIR /code

# copy this only so as to increase the chances of the cache being used
# for the pip install step
COPY ./requirements.txt /code/requirements.txt

# Install PyQt5
RUN apt-get update -y; \
    apt-get install -y --no-install-recommends python3-pyqt5;\
    apt-get clean; \
    rm -rf /var/lib/apt/lists/*;

RUN \
    # Extract the core requirements that have a dependency of PyQt5; a difficult package to install
    grep -E '^(quantify-core|quantify-scheduler)' /code/requirements.txt >> core-requirements.txt; \
    # show core-requirements for debugging
    cat core-requirements.txt; \
    # Clean up code/requirements.txt file, remove the dev-dependencies
    sed -i '/^# dev-dependencies/q'  /code/requirements.txt; \
    # comment out the packages that may need PyQt5
    sed -i "s:quantify-core:# quantify-core:" /code/requirements.txt; \
    sed -i "s:quantify-scheduler:# quantify-scheduler:" /code/requirements.txt; \
    # Install the pip dependencies except the core ones
    pip install --no-cache-dir pipdeptree~=2.24.0; \
    pip install --no-cache-dir -r /code/requirements.txt; \
    # Install quantify-core and quantify-scheduler without dependencies
    pip install --no-deps --no-cache-dir -r core-requirements.txt; \
    rm core-requirements.txt; \
    # Extract all the yet-to-be-installed required dependencies
    pipdeptree -w silence -p quantify-core >> pending-requirements.txt; \
    pipdeptree -w silence -p quantify-scheduler >> pending-requirements.txt; \
    pip uninstall -y pipdeptree; \
    # Cleaning up the pending-requirements.txt
    # remove indirect dependencies of quantify-core and quantify-scheduler
    sed -i "s:^│[[:space:]]*├──.*::" pending-requirements.txt; \
    sed -i "s:^│[[:space:]]*└──.*::" pending-requirements.txt; \
    # remove the names: quantify-core, quantify-scheduler
    sed -i "s:^quantify-.*::" pending-requirements.txt; \
    # remove the tree demarcators
    sed -i "s:^├── ::" pending-requirements.txt; \
    sed -i "s:^└── ::" pending-requirements.txt; \
    # remove already installed dependencies
    sed -i "s/.* installed: [0-9].*$//" pending-requirements.txt; \
    # cleanup dependencies whose versions don't matter
    sed -i "s/ \[required: Any,.*$//" pending-requirements.txt; \
    # remove the installation statuses
    sed -i "s/, installed: ?\]$//" pending-requirements.txt; \
    # clean up the version numbers
    sed -i "s/ \[required: //" pending-requirements.txt; \
    # remove pyqt5 dependency
    sed -i "s/^pyqt5[\>\<\=\~\!].*//" pending-requirements.txt; \
    # remove empty lines
    sed -i.bak "/^$/d" pending-requirements.txt; \
    # print the final output for debugging purposes
    cat pending-requirements.txt; \
    # Install all yet-to-be-installed dependencies except pyqt5
    pip install --no-cache-dir -r pending-requirements.txt; \
    rm pending-requirements.txt;

COPY . /code/

RUN chmod +x /code/start_bcc.sh

LABEL org.opencontainers.image.licenses=APACHE-2.0
LABEL org.opencontainers.image.description="The Backend in the Tergite software stack of the WACQT quantum computer."

# Check the dot-env-template.txt for more information about the env variables
ENV ENV_FILE=".env"
ENV IS_SYSTEMD="false"
ENV BACKEND_SETTINGS="backend_config.toml"
ENV DEFAULT_PREFIX="qiskit_pulse_1q"
ENV STORAGE_ROOT="/tmp"
ENV LOGFILE_DOWNLOAD_POOL_DIRNAME="logfile_download_pool"
ENV LOGFILE_UPLOAD_POOL_DIRNAME="logfile_upload_pool"
ENV JOB_UPLOAD_POOL_DIRNAME="job_upload_pool"
ENV JOB_PRE_PROC_POOL_DIRNAME="job_preproc_pool"
ENV JOB_EXECUTION_POOL_DIRNAME="job_execution_pool"
ENV EXECUTOR_DATA_DIRNAME="executor_data"
ENV BCC_MACHINE_ROOT_URL="http://host.docker.internal:8000"
ENV BCC_PORT=8000
ENV MSS_MACHINE_ROOT_URL="http://host.docker.internal:8002"
ENV MSS_PORT=8002
ENV EXECUTOR_TYPE="qiskit_pulse_1q"
ENV QUANTIFY_CONFIG_FILE="quantify-config.yml"
#ENV MSS_APP_TOKEN=""
#ENV IS_AUTH_ENABLED="True"
ENV APP_SETTINGS="production"
ENV IS_STANDALONE="False"
#ENV REDIS_HOST="host.docker.internal"
#ENV REDIS_PORT=6379
#ENV REDIS_USER=""
#ENV REDIS_PASSWORD=""

ENTRYPOINT ["/code/start_bcc.sh"]