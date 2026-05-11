# Verixa Software Bill of Materials (SBOM)

> Generated: **2026-05-11 08:43:38 UTC**
> Generator: `_backup/generate_sbom.py`
> Format: human-readable markdown (Phase 0). Phase 1 will also produce CycloneDX 1.5 JSON.

## How this SBOM is generated

- **Python:** `pip-licenses --format=json --with-urls` run inside the Poetry venv at `.venv/`.
- **Node:** top-level direct + dev deps from every `package.json` in the monorepo (excluding `node_modules` and `.next`).

Transitive deps are not yet enumerated in Phase 0; Phase 1 will add CycloneDX with full transitive closure.

---

## Python dependencies

| Package | Version | Licence | URL |
|---|---|---|---|
| `alembic` | 1.18.4 | MIT | <https://alembic.sqlalchemy.org> |
| `amqp` | 5.3.1 | BSD License | <http://github.com/celery/py-amqp> |
| `annotated-types` | 0.7.0 | MIT License | <https://github.com/annotated-types/annotated-types> |
| `anyio` | 4.13.0 | MIT | <https://anyio.readthedocs.io/en/stable/versionhistory.html> |
| `argon2-cffi` | 25.1.0 | MIT | <https://github.com/hynek/argon2-cffi/blob/main/CHANGELOG.md> |
| `argon2-cffi-bindings` | 25.1.0 | MIT | <https://github.com/hynek/argon2-cffi-bindings/blob/main/CHANGELOG.md> |
| `arrow` | 1.4.0 | Apache Software License | <https://github.com/arrow-py/arrow> |
| `asyncpg` | 0.30.0 | Apache Software License | — |
| `attrs` | 26.1.0 | MIT | <https://www.attrs.org/en/stable/changelog.html> |
| `backoff` | 2.2.1 | MIT License | <https://github.com/litl/backoff> |
| `backports.zstd` | 1.4.0 | PSF-2.0 | <https://github.com/rogdham/backports.zstd> |
| `billiard` | 4.2.4 | BSD License | <https://github.com/celery/billiard> |
| `build` | 1.5.0 | MIT | <https://build.pypa.io> |
| `CacheControl` | 0.14.4 | Apache-2.0 | <https://pypi.org/project/CacheControl/> |
| `celery` | 5.6.3 | BSD-3-Clause | <https://docs.celeryq.dev/> |
| `certifi` | 2026.4.22 | Mozilla Public License 2.0 (MPL 2.0) | <https://github.com/certifi/python-certifi> |
| `cffi` | 2.0.0 | MIT | <https://cffi.readthedocs.io/en/latest/whatsnew.html> |
| `charset-normalizer` | 3.4.7 | MIT | <https://github.com/jawah/charset_normalizer/blob/master/CHANGELOG.md> |
| `cleo` | 2.1.0 | MIT License | <https://github.com/python-poetry/cleo> |
| `click` | 8.3.3 | BSD-3-Clause | <https://github.com/pallets/click/> |
| `click-didyoumean` | 0.3.1 | MIT License | <https://github.com/click-contrib/click-didyoumean> |
| `click-plugins` | 1.1.1.2 | BSD License | <https://github.com/click-contrib/click-plugins> |
| `click-repl` | 0.3.0 | MIT | <https://github.com/untitaker/click-repl> |
| `colorama` | 0.4.6 | BSD License | <https://github.com/tartley/colorama> |
| `coverage` | 7.13.5 | Apache-2.0 | <https://github.com/coveragepy/coveragepy> |
| `crashtest` | 0.4.1 | MIT License | <https://github.com/sdispater/crashtest> |
| `cryptography` | 43.0.3 | Apache Software License; BSD License | <https://github.com/pyca/cryptography> |
| `distlib` | 0.4.0 | Python Software Foundation License | <https://github.com/pypa/distlib> |
| `distro` | 1.9.0 | Apache Software License | <https://github.com/python-distro/distro> |
| `docker` | 7.1.0 | Apache-2.0 | <https://github.com/docker/docker-py> |
| `dulwich` | 1.2.1 | Apache-2.0 OR GPL-2.0-or-later | <https://www.dulwich.io/> |
| `fastapi` | 0.115.14 | MIT License | <https://github.com/fastapi/fastapi> |
| `fastjsonschema` | 2.21.2 | BSD License | <https://github.com/horejsek/python-fastjsonschema> |
| `filelock` | 3.29.0 | MIT | <https://github.com/tox-dev/py-filelock> |
| `findpython` | 0.8.0 | MIT | <https://github.com/frostming/findpython> |
| `fqdn` | 1.5.1 | Mozilla Public License 2.0 (MPL 2.0) | <https://github.com/ypcrts/fqdn> |
| `freezegun` | 1.5.5 | Apache-2.0 | <https://github.com/spulec/freezegun> |
| `graphql-core` | 3.2.8 | MIT License | <https://github.com/graphql-python/graphql-core> |
| `greenlet` | 3.5.0 | MIT AND PSF-2.0 | <https://greenlet.readthedocs.io> |
| `h11` | 0.16.0 | MIT License | <https://github.com/python-hyper/h11> |
| `harfile` | 0.4.0 | MIT | <https://github.com/schemathesis/harfile/blob/main/CHANGELOG.md> |
| `httpcore` | 1.0.9 | BSD-3-Clause | <https://www.encode.io/httpcore/> |
| `httptools` | 0.7.1 | MIT | <https://github.com/MagicStack/httptools> |
| `httpx` | 0.27.2 | BSD-3-Clause | <https://github.com/encode/httpx> |
| `hypothesis` | 6.152.4 | MPL-2.0 | <https://hypothesis.works> |
| `hypothesis-graphql` | 0.12.0 | MIT | <https://github.com/Stranger6667/hypothesis-graphql/blob/master/CHANGELOG.md> |
| `hypothesis-jsonschema` | 0.23.1 | Mozilla Public License 2.0 (MPL 2.0) | <https://github.com/Zac-HD/hypothesis-jsonschema> |
| `idna` | 3.13 | BSD-3-Clause | <https://github.com/kjd/idna> |
| `iniconfig` | 2.3.0 | MIT | <https://github.com/pytest-dev/iniconfig> |
| `installer` | 1.0.0 | MIT | — |
| `isoduration` | 20.11.0 | ISC License (ISCL) | <https://github.com/bolsote/isoduration> |
| `jaraco.classes` | 3.4.0 | MIT License | <https://github.com/jaraco/jaraco.classes> |
| `jaraco.context` | 6.1.2 | MIT | <https://github.com/jaraco/jaraco.context> |
| `jaraco.functools` | 4.4.0 | MIT | <https://github.com/jaraco/jaraco.functools> |
| `jiter` | 0.14.0 | MIT | <https://github.com/pydantic/jiter/> |
| `jsonpointer` | 3.1.1 | BSD License | <https://github.com/stefankoegl/python-json-pointer> |
| `jsonschema` | 4.26.0 | MIT | <https://github.com/python-jsonschema/jsonschema> |
| `jsonschema-specifications` | 2025.9.1 | MIT | <https://github.com/python-jsonschema/jsonschema-specifications> |
| `junit-xml` | 1.9 | Freely Distributable; MIT License | <https://github.com/kyrus/python-junit-xml> |
| `keyring` | 25.7.0 | MIT | <https://github.com/jaraco/keyring> |
| `kombu` | 5.6.2 | BSD-3-Clause | <https://kombu.readthedocs.io> |
| `librt` | 0.10.0 | MIT | <https://github.com/mypyc/librt> |
| `Mako` | 1.3.12 | MIT License | <https://www.makotemplates.org/> |
| `MarkupSafe` | 3.0.3 | BSD-3-Clause | <https://github.com/pallets/markupsafe/> |
| `minio` | 7.2.20 | Apache Software License | <https://github.com/minio/minio-py> |
| `more-itertools` | 11.0.2 | MIT | <https://github.com/more-itertools/more-itertools> |
| `msgpack` | 1.1.2 | Apache-2.0 | <https://msgpack.org/> |
| `multidict` | 6.7.1 | Apache License 2.0 | <https://github.com/aio-libs/multidict> |
| `mypy` | 1.20.2 | MIT | <https://www.mypy-lang.org/> |
| `mypy_extensions` | 1.1.0 | MIT | <https://github.com/python/mypy_extensions> |
| `openai` | 1.109.1 | Apache Software License | <https://github.com/openai/openai-python> |
| `packaging` | 26.2 | Apache-2.0 OR BSD-2-Clause | <https://github.com/pypa/packaging> |
| `pathspec` | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | <https://python-path-specification.readthedocs.io/en/latest/index.html> |
| `pbs-installer` | 2026.5.8 | MIT | <https://github.com/frostming/pbs-installer> |
| `pkginfo` | 1.12.1.2 | MIT License | <https://code.launchpad.net/~tseaver/pkginfo/trunk> |
| `platformdirs` | 4.9.6 | MIT | <https://github.com/tox-dev/platformdirs> |
| `pluggy` | 1.6.0 | MIT License | — |
| `poetry` | 2.4.1 | MIT | <https://python-poetry.org/> |
| `poetry-core` | 2.4.0 | MIT | <https://github.com/python-poetry/poetry-core> |
| `prompt_toolkit` | 3.0.52 | BSD License | <https://github.com/prompt-toolkit/python-prompt-toolkit> |
| `propcache` | 0.5.2 | Apache Software License | <https://github.com/aio-libs/propcache> |
| `pycparser` | 3.0 | BSD-3-Clause | <https://github.com/eliben/pycparser> |
| `pycryptodome` | 3.23.0 | BSD License; Public Domain | <https://www.pycryptodome.org> |
| `pydantic` | 2.13.4 | MIT | <https://github.com/pydantic/pydantic> |
| `pydantic-settings` | 2.14.1 | MIT | <https://github.com/pydantic/pydantic-settings> |
| `pydantic_core` | 2.46.4 | MIT | <https://github.com/pydantic> |
| `Pygments` | 2.20.0 | BSD-2-Clause | <https://pygments.org> |
| `PyJWT` | 2.12.1 | MIT | <https://github.com/jpadilla/pyjwt> |
| `PyNaCl` | 1.6.2 | Apache Software License | <https://github.com/pyca/pynacl> |
| `pyproject_hooks` | 1.2.0 | MIT License | <https://github.com/pypa/pyproject-hooks> |
| `pyrate-limiter` | 3.9.0 | MIT License | <https://github.com/vutran1710/PyrateLimiter> |
| `pytest` | 8.4.2 | MIT License | <https://docs.pytest.org/en/latest/> |
| `pytest-asyncio` | 0.24.0 | Apache Software License | <https://github.com/pytest-dev/pytest-asyncio> |
| `pytest-cov` | 6.3.0 | MIT | <https://github.com/pytest-dev/pytest-cov> |
| `pytest-subtests` | 0.14.2 | MIT License | <https://github.com/pytest-dev/pytest-subtests> |
| `python-dateutil` | 2.9.0.post0 | Apache Software License; BSD License | <https://github.com/dateutil/dateutil> |
| `python-discovery` | 1.3.0 | MIT License | <https://github.com/tox-dev/python-discovery> |
| `python-dotenv` | 1.2.2 | BSD-3-Clause | <https://github.com/theskumar/python-dotenv> |
| `pywin32` | 311 | Python Software Foundation License | <https://github.com/mhammond/pywin32> |
| `pywin32-ctypes` | 0.2.3 | BSD-3-Clause | <https://github.com/enthought/pywin32-ctypes> |
| `PyYAML` | 6.0.3 | MIT License | <https://pyyaml.org/> |
| `RapidFuzz` | 3.14.5 | MIT | <https://github.com/rapidfuzz/RapidFuzz> |
| `redis` | 5.3.1 | MIT License | <https://github.com/redis/redis-py> |
| `referencing` | 0.37.0 | MIT | <https://github.com/python-jsonschema/referencing> |
| `requests` | 2.33.1 | Apache Software License | <https://github.com/psf/requests> |
| `requests-toolbelt` | 1.0.0 | Apache Software License | <https://toolbelt.readthedocs.io/> |
| `rfc3339-validator` | 0.1.4 | MIT License | <https://github.com/naimetti/rfc3339-validator> |
| `rfc3987` | 1.3.8 | GNU General Public License v3 or later (GPLv3+) | <http://pypi.python.org/pypi/rfc3987> |
| `rpds-py` | 0.30.0 | MIT | <https://github.com/crate-py/rpds> |
| `ruff` | 0.7.4 | MIT License | <https://docs.astral.sh/ruff> |
| `schemathesis` | 3.39.16 | MIT | <https://schemathesis.readthedocs.io/en/stable/changelog.html> |
| `shellingham` | 1.5.4 | ISC License (ISCL) | <https://github.com/sarugaku/shellingham> |
| `six` | 1.17.0 | MIT License | <https://github.com/benjaminp/six> |
| `sniffio` | 1.3.1 | Apache Software License; MIT License | <https://github.com/python-trio/sniffio> |
| `sortedcontainers` | 2.4.0 | Apache Software License | <http://www.grantjenks.com/docs/sortedcontainers/> |
| `SQLAlchemy` | 2.0.49 | MIT | <https://www.sqlalchemy.org> |
| `starlette` | 0.46.2 | BSD-3-Clause | <https://github.com/encode/starlette> |
| `starlette-testclient` | 0.4.1 | BSD-3-Clause | <https://github.com/Kludex/starlette-testclient> |
| `structlog` | 24.4.0 | MIT OR Apache-2.0 | <https://github.com/hynek/structlog/blob/main/CHANGELOG.md> |
| `testcontainers` | 4.13.3 | Apache Software License | — |
| `tomli` | 2.4.1 | MIT | <https://github.com/hukkin/tomli> |
| `tomli_w` | 1.2.0 | MIT License | <https://github.com/hukkin/tomli-w> |
| `tomlkit` | 0.15.0 | MIT License | <https://github.com/python-poetry/tomlkit> |
| `tqdm` | 4.67.3 | MPL-2.0 AND MIT | <https://tqdm.github.io> |
| `trove-classifiers` | 2026.5.7.17 | Apache Software License | <https://github.com/pypa/trove-classifiers> |
| `typing-inspection` | 0.4.2 | MIT | <https://github.com/pydantic/typing-inspection> |
| `typing_extensions` | 4.15.0 | PSF-2.0 | <https://github.com/python/typing_extensions> |
| `tzdata` | 2026.2 | Apache-2.0 | <https://github.com/python/tzdata> |
| `tzlocal` | 5.3.1 | MIT License | <https://github.com/regebro/tzlocal/blob/master/CHANGES.txt> |
| `uri-template` | 1.3.0 | MIT License | <https://gitlab.linss.com/open-source/python/uri-template> |
| `urllib3` | 2.7.0 | MIT | <https://github.com/urllib3/urllib3/blob/main/CHANGES.rst> |
| `uvicorn` | 0.32.1 | BSD License | <https://www.uvicorn.org/> |
| `verixa-monorepo` | 0.1.0 | MIT | — |
| `vine` | 5.1.0 | BSD License | <https://github.com/celery/vine> |
| `virtualenv` | 21.3.1 | MIT | <https://github.com/pypa/virtualenv> |
| `watchfiles` | 1.1.1 | MIT License | <https://github.com/samuelcolvin/watchfiles> |
| `webcolors` | 25.10.0 | BSD License | <https://webcolors.readthedocs.io> |
| `websockets` | 16.0 | BSD-3-Clause | <https://github.com/python-websockets/websockets> |
| `Werkzeug` | 3.1.8 | BSD-3-Clause | <https://github.com/pallets/werkzeug/> |
| `wrapt` | 2.1.2 | BSD-2-Clause | <https://github.com/GrahamDumpleton/wrapt> |
| `yarl` | 1.23.0 | Apache-2.0 | <https://github.com/aio-libs/yarl> |

**Total Python packages: 141**

---

## Node dependencies (direct only — Phase 0)

### `apps/control-plane-ui/package.json`

- `@playwright/test@^1.59.1`
- `@types/node@^22.10.0`
- `@types/react-dom@^18.3.1`
- `@types/react@^18.3.12`
- `@verixa/ts@workspace:*`
- `@vitejs/plugin-react@^4.3.4`
- `@vitest/coverage-v8@^2.1.8`
- `happy-dom@^15.11.7`
- `next@^14.2.20`
- `react-dom@^18.3.1`
- `react@^18.3.1`
- `typescript@^5.7.2`
- `vitest@^2.1.8`

### `package.json`

- `@types/node@^22.10.0`
- `@vitest/coverage-v8@^2.1.8`
- `turbo@^2.3.0`
- `typescript@^5.7.2`
- `vitest@^2.1.8`

### `packages/verixa-ts/package.json`

- `@vitest/coverage-v8@^2.1.8`
- `typescript@^5.7.2`
- `vitest@^2.1.8`

**Total Node direct deps across the monorepo: 21**

---

## License summary

| Licence | Package count |
|---|---|
| MIT | 45 |
| MIT License | 27 |
| BSD-3-Clause | 14 |
| Apache Software License | 13 |
| BSD License | 10 |
| Apache-2.0 | 7 |
| Mozilla Public License 2.0 (MPL 2.0) | 4 |
| BSD-2-Clause | 2 |
| PSF-2.0 | 2 |
| Apache Software License; BSD License | 2 |
| Python Software Foundation License | 2 |
| ISC License (ISCL) | 2 |
| Apache-2.0 OR GPL-2.0-or-later | 1 |
| MIT AND PSF-2.0 | 1 |
| MPL-2.0 | 1 |
| Freely Distributable; MIT License | 1 |
| Apache License 2.0 | 1 |
| Apache-2.0 OR BSD-2-Clause | 1 |
| BSD License; Public Domain | 1 |
| GNU General Public License v3 or later (GPLv3+) | 1 |
| Apache Software License; MIT License | 1 |
| MIT OR Apache-2.0 | 1 |
| MPL-2.0 AND MIT | 1 |

---

## Regenerate

```
python _backup/generate_sbom.py
```