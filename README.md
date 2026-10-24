# MyScoutee SonarQube

One manually operated SonarQube server and PostgreSQL database serve backend,
template, base, components and e-kozig analyses. Each source repository keeps only its
analysis configuration in `config/sonarqube/`. Server identity, Compose project
and port belong to this tool's `server.json`, never to an application config.
Builds and tests run separately; scans share one global execution lock.

All nine registered projects import native test counts, failures, duration and
coverage through their versioned properties. Duplication, reliability, security
and maintainability use the normal source analysis; no rules or duplication
checks are disabled to obtain a clean result.

| Source repository / module | Native execution report | Native coverage report |
| --- | --- | --- |
| backend / backend | `build/junit/test-results/test` | `build/junit/reports/jacoco.xml` |
| template / backend | `build/junit/test-results/test` | `build/junit/reports/jacoco.xml` |
| backend / frontend | `test-results/sonar.xml` | `coverage/myscoutee/lcov.info` |
| template / frontend | `test-results/sonar.xml` | `coverage/myscoutee/lcov.info` |
| backend / microservices | `server/build/microservices/bootstrap-tests/test-results/test` | `server/build/microservices/bootstrap-tests/reports/jacoco.xml` |
| template / microservices | `server/build/microservices/bootstrap-tests/test-results/test` | `server/build/microservices/bootstrap-tests/reports/jacoco.xml` |
| base / backend | `build/sonar-test-results` | `build/reports/jacoco.xml` |
| components / components | `test-results/sonar.xml` | `coverage/components/lcov.info` |
| e-kozig / frontend | `test-results/sonar.xml` | `coverage/e-kozig/lcov.info` |

Paths are relative to the configured module directory. Angular's existing test
builder uses the pinned Vitest Sonar reporter and V8 LCOV provider; Java imports
JUnit XML and JaCoCo XML directly. Reports stay ignored by Git. A focused run
reports only the tests and coverage actually measured by that run; its count is
not the size of the entire suite.

| Document | Version | Links |
| --- | --- | --- |
| SonarQube Guide | 1.2 | [PDF](guides/manuals/MyScoutee_SonarQube_Guide_EN.pdf) · [Editable source](guides/manuals/build-guide.py) |
| Reviewed findings | - | [Review notes](REVIEWED_FINDINGS.md) |

```sh
# Once on a new machine; existing credentials are preserved.
./run.sh ../myscoutee-backend init
./run.sh ../myscoutee-backend up

# Submit each selected project's analysis to that same running server.
./run.sh ../myscoutee-backend scan backend
./run.sh ../myscoutee-template scan frontend
./run.sh ../myscoutee-base scan backend
./run.sh ../myscoutee-components scan components
./run.sh ../e-kozig scan frontend
```

`scan` never starts a server or its dependencies. If the shared server is not
ready, it fails with an explicit startup instruction. `up` addresses the same
Compose project for every source repository and reuses its running services.
`scan all` uses only the selected repository's configured modules. Do not scan
installed library distributions as application source; analyze shared business
code once in base and UI components once in components.

For source fixes when test reports are unavailable and no tests should run, use
`./run.sh ../myscoutee-template scan frontend --source-only`. This explicit mode
skips execution and coverage report imports for that analysis. Test statistics
are consequently absent from that snapshot; the normal scan continues to import
the report paths above. Neither mode runs tests or invents missing reports.

`privateDirectories` in a source repository's `project.json` lists runtime data
that is outside the scanner input. Backend and template declare `server/data`.
The runner overlays an empty, read-only directory inside the scanner for those
paths, because Python package discovery also traverses non-source directories.
It does not modify database files or their permissions. Paths must remain
strictly inside the selected repository and cannot hide its root.

The shared dashboard is **localhost:9000**. Its existing `myscoutee-sonarqube`
Compose identity and named volumes are retained. Credentials stay in the existing
ignored `.state/myscoutee/.env`; `init` never replaces them. An analysis token must
have permission for each selected Sonar project. Reports and preparation remain
separate in `.state/<project-id>/build/`; components now has its own report directory.
Nothing starts automatically.

Old template instance containers, volumes and `.state/template/.env` are retained
as historical data; this runner no longer starts or selects that separate server.
Their analysis history is not automatically merged into the shared database.

For base Java libraries, explicitly run `./gradlew prepareSonar --parallel` from
`../myscoutee-base/server` before scanning. It prepares compiled classes and library
dependencies without tests. The scanner imports that output and rejects missing
or stale preparation; it never launches Gradle. Application Java scans continue
using their existing Spring Boot artifacts.

When fresh base test statistics are required, its existing
`./gradlew :jacocoTestReport prepareSonar --parallel` command also produces the
native aggregate reports. Do not run it merely to refresh source findings.

`status`, `logs`, `stop` and `down` affect the shared server regardless of which
source argument is supplied. `stop` retains containers and data; `down` retains
named data volumes. Do not stop the server between projects in an analysis batch.

Checks: `python3 -m unittest discover -p 'test_*.py'`.
Rebuild the guide: `python3 guides/manuals/build-guide.py` (ReportLab required).
