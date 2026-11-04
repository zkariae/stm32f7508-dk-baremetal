<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       ci/README.md
\brief      CI/CD of the project: branch protection, Jenkins pipeline and phase D status.

\author     Z. BEN-AKKA
\version    1.2
\date       04/11/2026

\details
  Reference document of the CI/CD set up in phase D. It records the branch
  model, the GitHub protection rules, the Jenkins pipeline run on the board,
  the infrastructure choices and the progress of each sub-step, so that the
  work can be resumed without any other context. The status table of
  section 8 is updated by every sub-step of the phase.

\section ci_readme_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 03/11/2026 | Z. BEN-AKKA | Initial version. |
| 1.1     | 04/11/2026 | Z. BEN-AKKA | Status of D2 to D7; Java 21, web access and Checkout clean-up from the set-up. |
| 1.2     | 04/11/2026 | Z. BEN-AKKA | Port 8090 and web access through localhost; D8 done. |
****************************
-->

# CI/CD

## 1. Purpose

No regression may enter `main`, `develop` or a phase integration branch.
Every merge into these branches goes through a GitHub pull request, and the
pull request can only be merged once Jenkins has built every image and run
the tests on the STM32F7508-DK board, with all of them passing.

## 2. Branch model

```text
main                    ◄── PR ── develop                 major merges: feature, version, tag
develop                 ◄── PR ── phaseX/integration      end of a phase
phaseX/integration      ◄── PR ── phaseX/<task>           one file per sub-branch
```

| Branch | Role | Receives | Direct push | Deletion |
|:--|:--|:--|:--|:--|
| `main` | Released versions, tagged | PRs from `develop` | blocked (admin bypass) | blocked |
| `develop` | Integration of the finished phases | PRs from `phaseX/integration` | blocked (admin bypass) | blocked |
| `phaseX/integration` | Integration branch of one phase, created from `develop` | PRs from `phaseX/<task>` | blocked (admin bypass) | allowed, deleted at the end of the phase |
| `phaseX/<task>` | One change to one file, created from `phaseX/integration` | — | free | free |

The phase branch is named `phaseX/integration`, not `phaseX`: Git cannot
hold a branch `phaseD-ci` and branches `phaseD-ci/...` at the same time,
because a ref name cannot be both a file and a folder. Phase D uses
`phaseD-ci/integration` and sub-branches such as `phaseD-ci/build-sh`.

## 3. Protection rules

Three GitHub rulesets, one per protected level:

| Ruleset | Target | Rules |
|:--|:--|:--|
| `main` | `refs/heads/main` | common rules, deletion blocked |
| `develop` | `refs/heads/develop` | common rules, deletion blocked |
| `phase-integration` | `refs/heads/phase*/integration` | common rules, deletion allowed |

Common rules:

- A pull request is required, with 0 approvals (single maintainer).
- The status check `continuous-integration/jenkins/pr-merge` is required,
  and the branch must be up to date with its target before merging.
- Allowed merge method: "Merge commit" only, the GitHub equivalent of
  `git merge --no-ff`, which keeps the current history shape.
- Force pushes are blocked.
- Bypass: the *Repository admin* role only, for emergencies.

## 4. Pipeline

`ci/Jenkinsfile` is one declarative pipeline; the stages it runs depend on
what triggered the build.

| Trigger | Stages |
|:--|:--|
| Pull request to `main`, `develop` or `phaseX/integration` | Build → UART T1–T8 → HIL |
| Push to a branch (after a merge) | Build |

| Stage | Script | Content |
|:--|:--|:--|
| Checkout | in the Jenkinsfile | Repository, then the submodule over HTTPS: `git -c url.https://github.com/.insteadOf=git@github.com: submodule update --init` (the submodule is public, no key needed), then removes `work/hil-results/`, so that a build never reports the previous build's tests |
| Build | `ci/scripts/build.sh` | `make all`, `dev/scripts/format_cxx.sh --check`, `pytest -m unit`, `pytest --collect-only` |
| UART T1–T8 | `ci/scripts/rx_check.sh` | `make uart-diag-flash`, `make reset`, `tests/host/rx_check/uart_rx_check.py` |
| HIL | `ci/scripts/hil.sh` | `python3 -m pytest tests/host/hil --junitxml=work/hil-results/junit.xml` (flashes hil-bench) |
| post | in the Jenkinsfile | `junit` report, `archiveArtifacts` of `work/build/**/*.bin` and `work/hil-results/*` |

- The pipeline stops at the first failing stage: a build error never
  reaches the board.
- One build at a time (`disableConcurrentBuilds()`, one executor): the
  board is a single shared resource.
- `uart_rx_check.py` does not flash the board, so `rx_check.sh` flashes
  `uart-diag` first; the HIL stage then flashes `hil-bench` again.

## 5. Infrastructure

```text
GitHub (zkariae/stm32f7508-dk-baremetal)
   ▲  commit status (API, outgoing)            │ scan every 5 minutes (outgoing)
   │                                           ▼
Jenkins on the developer PC (WSL2, Ubuntu 22.04) ── Multibranch job, Script Path = ci/Jenkinsfile
   └── ST-LINK + /dev/ttyACM0 (usbipd) ── STM32F7508-DK
```

| Choice | Decision | Reason |
|:--|:--|:--|
| Jenkins host | Jenkins LTS installed in WSL2 with apt, run by systemd (`systemd=true` in `/etc/wsl.conf`), Java 21 | Same Ubuntu 22.04 as the developer: `arm-none-eabi-gcc` 10.3 and `clang-format` 14 give the same binaries and format check; direct USB access to the board |
| Web access | `http://localhost:8090`, from Windows and inside WSL; port set in a systemd override | Port 8080 is taken by a Windows service on this PC and WSL only relays it over IPv6 (`ci/jenkins/setup.md` sections 2 and 3) |
| Job | Multibranch Pipeline, GitHub Branch Source, Script Path `ci/Jenkinsfile` | All CI files stay in `ci/` |
| Trigger | Periodic scan of GitHub every 5 minutes, no webhook | WSL2 is not reachable from the Internet; every connection goes out from the PC and no port is exposed. A pull request starts within 5 minutes, or at once with "Scan now" |
| Result | Status `continuous-integration/jenkins/pr-merge` published by GitHub Branch Source | It is the check required by the rulesets |
| Credentials | Fine-grained GitHub token, this repository only: Contents read, Pull requests read, Commit statuses write; renewed before it expires (`ci/jenkins/setup.md` section 10) | Least privilege |
| Fork pull requests | Trust "From users with Admin or Write permission" | The Jenkinsfile of an outside fork never runs on the PC that holds the board |
| Executors | 1 | One board |
| Board access | `jenkins` user in the `plugdev` (ST-LINK) and `dialout` (`/dev/ttyACM0`) groups; board attached to WSL with `usbipd` | Same rights as the developer |
| Pull requests | Opened with the `gh` CLI after the developer's agreement, merged by the developer on GitHub | |

## 6. Layout

```text
ci/
├── README.md              # this document
├── Jenkinsfile            # declarative pipeline
├── scripts/
│   ├── build.sh           # checks without the board
│   ├── rx_check.sh        # UART T1–T8 on the board, uart-diag image
│   └── hil.sh             # HIL tests on the board, hil-bench image
└── jenkins/
    └── setup.md           # Jenkins in WSL2, plugins, credentials, job, GitHub rulesets
```

The scripts run from the repository root and return the exit code of the
checks they run, so Jenkins and a developer get the same result.

## 7. Running the checks locally

The same scripts run by hand, before pushing a branch:

```bash
ci/scripts/build.sh      # no board needed
ci/scripts/rx_check.sh   # board connected, flashes uart-diag
ci/scripts/hil.sh        # board connected, flashes hil-bench
```

## 8. Status of phase D

| # | File or action | Status |
|:-:|:--|:--|
| D1 | `ci/README.md` | done |
| D2 | `ci/scripts/build.sh` | done |
| D3 | `ci/scripts/rx_check.sh` | done |
| D4 | `ci/scripts/hil.sh` | done |
| D5 | `ci/Jenkinsfile` | done |
| D6 | `ci/jenkins/setup.md` | done |
| D7 | `work/doc_zak/plan_test_hil.md` (sections 2, 5 and 6) | done |
| D8 | Jenkins installed by the developer; first green build of `phaseD-ci/integration` | done: build #1 of `phaseD-ci/integration` green, status published on GitHub |
| D9 | The three rulesets enabled by the developer | to do |
| D10 | `gh` installed by the developer; PRs `phaseD-ci/integration` → `develop` → `main`, deliberate regressions | to do |

Set-up order:

1. D1 to D7 in the local flow: each `phaseD-ci/<task>` sub-branch is merged
   locally into `phaseD-ci/integration`, since no protection exists yet.
2. D8: Jenkins is installed from `ci/jenkins/setup.md`;
   `phaseD-ci/integration` is pushed and must build green.
3. D9: the three rulesets are enabled.
4. D10: the first protected pull requests close the phase.

End-of-phase checks (D10):

1. A PR `phaseD-ci/<test>` → `phaseD-ci/integration` runs Build, UART T1–T8
   and HIL; the check is green and the merge is allowed.
2. Deliberate build regression: a syntax error in a `.c` file on a throwaway
   branch; Build fails and the merge is blocked.
3. Deliberate functional regression: a wrong value in
   `tests/host/hil/cases/expected.py`; Build passes, HIL fails and the merge
   is blocked.
4. The PRs `phaseD-ci/integration` → `develop` and `develop` → `main` are
   green, with T1–T8 8/8 and 216 HIL tests passed, and can be merged.
5. A direct `git push` to `develop` or `main` is refused (without admin bypass).

## 9. Working rules

- One file per sub-branch; each change bumps the file's `\version` and
  `\date` and adds an English line to its version history.
- A plan is validated before each change, and the checks to run on the
  board are given and passed before each commit.
- Commit messages: `<type>[file] : description`, with the types feat, fix,
  refactor, chore, perf, ci, ops, build, docs, style, revert, test.
- Merges: merge commits only (`--no-ff`), with a message starting with
  `Merge`.
- Once the rulesets are enabled, nothing is pushed directly to `main`,
  `develop` or `phaseX/integration`: every change arrives through a pull
  request.
