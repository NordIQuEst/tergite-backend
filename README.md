# Tergite BCC

![CI](https://github.com/tergite/tergite-bcc/actions/workflows/ci.yml/badge.svg)

The Backend Control Computer software that makes QAL 9000 - like quantum computers accessible via the internet.

## Dependencies

- [Python 3.8](https://www.python.org/)
- [Redis](https://redis.io/)
- [Tergite Quantify Connector](https://github.com/tergite/tergite-quantify-connector)
- [Tergite Labber Connector](https://github.com/tergite/tergite-labber-connector)

## Quick Start

- Ensure you have [conda](https://docs.anaconda.com/free/miniconda/index.html) installed. 
 (_You could simply have python +3.8 installed instead._)
- Ensure you have the [Redis](https://redis.io/) server running
- Ensure you have [tergite Quantify Connector](https://github.com/tergite/tergite-quantify-connector) running.
- Clone the repo

```shell
git clone git@github.com:tergite/tergite-bcc.git
```

- Create conda environment

```shell
conda create -n bcc -y python=3.8
conda activate bcc
```

- Install dependencies

```shell
cd tergite-bcc
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple -r requirements.txt
```

- Copy the `dot-env-template.txt` file to `.env` and 
  update the environment variables there appropriately.

```shell
cp dot-env-template.txt .env
```

- Run start script

```shell
./start_bcc.sh --device backend_properties_config/device_default.toml
```

- Open your browser at [http://localhost:8000/docs](http://localhost:8000/docs) to see the interactive API docs

## Documentation

Find more documentation in the [docs folder](./docs)

## Contribution Guidelines

If you would like to contribute, please have a look at our
[contribution guidelines](./CONTRIBUTING.md)

## Authors

This project is a work of
[many contributors](https://github.com/tergite/tergite-bcc/graphs/contributors).

Special credit goes to the authors of this project as seen in the [CREDITS](./CREDITS.md) file.

## ChangeLog

To view the changelog for each version, have a look at
the [CHANGELOG.md](./CHANGELOG.md) file.

## License

[Apache 2.0 License](./LICENSE.txt)

## Acknowledgements

This project was sponsored by:

-   [Knut and Alice Wallenburg Foundation](https://kaw.wallenberg.org/en) under the [Wallenberg Center for Quantum Technology (WAQCT)](https://www.chalmers.se/en/centres/wacqt/) project at [Chalmers University of Technology](https://www.chalmers.se)
-   [Nordic e-Infrastructure Collaboration (NeIC)](https://neic.no) and [NordForsk](https://www.nordforsk.org/sv) under the [NordIQuEst](https://neic.no/nordiquest/) project
-   [European Union's Horizon Europe](https://research-and-innovation.ec.europa.eu/funding/funding-opportunities/funding-programmes-and-open-calls/horizon-europe_en) under the [OpenSuperQ](https://cordis.europa.eu/project/id/820363) project
-   [European Union's Horizon Europe](https://research-and-innovation.ec.europa.eu/funding/funding-opportunities/funding-programmes-and-open-calls/horizon-europe_en) under the [OpenSuperQPlus](https://opensuperqplus.eu/) project
