<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       ci/jenkins/setup.md
\brief      Set-up of Jenkins in WSL2, of its access to the board and of the GitHub rulesets.

\author     Z. BEN-AKKA
\version    1.0
\date       04/11/2026

\details
  Step-by-step procedure of phase D sub-steps D8 and D9 (ci/README.md
  section 8): the Jenkins service in WSL2, the jenkins user's access to the
  board and to the tools, the GitHub credential, the Multibranch job and the
  three GitHub rulesets. It also records the state found on the developer PC
  on 03/11/2026, so that the set-up can be redone or resumed without any
  other context.

\section ci_jenkins_setup_md_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 04/11/2026 | Z. BEN-AKKA | Initial version. |
****************************
-->

# Jenkins set-up

## 1. Purpose and scope

`ci/README.md` gives the design of the CI: branch model, rulesets, pipeline
and infrastructure. This document is the procedure that puts it in place on
the developer PC:

- sections 2 to 11: Jenkins and the Multibranch job (D8);
- section 12: the GitHub rulesets (D9);
- section 13: the checks that close D8 and D9.

Commands prefixed with `sudo` or run in Windows are run by the developer.

## 2. Jenkins in WSL2

Jenkins runs as a systemd service in the same WSL2 distribution as the
developer, so it uses the same toolchain and sees the same USB devices.

| Item | Value found on 03/11/2026 |
|:--|:--|
| Distribution | Ubuntu 22.04 (WSL2) |
| systemd | enabled: `systemd=true` in the `[boot]` section of `/etc/wsl.conf` |
| Jenkins | 2.568.3 LTS, installed with apt from `pkg.jenkins.io` |
| Java | OpenJDK 21.0.12 |
| Service | `jenkins`, home `/var/lib/jenkins`, port 8080 |

```bash
systemctl is-active jenkins                                   # active
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/login   # 200
```

## 3. Web access from Windows

On this PC another Windows program listens on port 8080:
`http://localhost:8080` in a Windows browser answers
`Access Error: 404 -- Not Found`, not Jenkins. Use the WSL address instead:

```bash
hostname -I        # first address, e.g. 172.29.48.254
```

and open `http://<first address>:8080` in Windows. The address may change
when WSL restarts. Commands run inside WSL (curl, linter) keep using
`http://localhost:8080`.

To find the Windows program, in PowerShell:

```powershell
netstat -ano | findstr :8080
tasklist /fi "PID eq <PID>"
```

## 4. Account recovery

The Jenkins user database holds one account, `zbenakka`. The login is the
`<id>` of `/var/lib/jenkins/users/<login>_<hash>/config.xml`.

Jenkins only stores a bcrypt hash of the password. To set a new one without
disabling security, use a start-up script:

```bash
sudo mkdir -p /var/lib/jenkins/init.groovy.d
sudo nano /var/lib/jenkins/init.groovy.d/reset-password.groovy
```

```groovy
import hudson.model.User
import hudson.security.HudsonPrivateSecurityRealm

def user = User.getById('zbenakka', false)
user.addProperty(HudsonPrivateSecurityRealm.Details.fromPlainPassword('<new password>'))
user.save()
```

```bash
sudo systemctl restart jenkins
sudo rm /var/lib/jenkins/init.groovy.d/reset-password.groovy   # holds the password in clear
```

## 5. Board access

The pipeline flashes the board with OpenOCD (ST-LINK, group `plugdev`) and
talks to it on `/dev/ttyACM0` (group `dialout`). On 03/11/2026 the `jenkins`
user was in neither group.

```bash
sudo usermod -aG plugdev,dialout jenkins
sudo systemctl restart jenkins            # group changes apply to new processes only
id jenkins                                # ... plugdev ... dialout ...
```

The board is attached to WSL with `usbipd`, in an administrator PowerShell:

```powershell
usbipd list                               # BUSID of the ST-LINK
usbipd bind --busid <BUSID>               # once
usbipd attach --wsl --busid <BUSID>       # after each WSL restart or replug
```

```bash
ls -l /dev/ttyACM0                        # expected: crw-rw---- root dialout
sudo -u jenkins test -r /dev/ttyACM0      # then echo $? gives 0
```

Only one program may use the serial port: close miniterm before a build.

## 6. Tools for the jenkins user

| Tool | Location | For jenkins |
|:--|:--|:--|
| `arm-none-eabi-gcc` 10.3 | `/usr/bin` | available |
| `clang-format` 14 | `/usr/bin` | available |
| `openocd` | `/usr/bin` | available |
| `python3` 3.10, `pip` 22.0.2 | `/usr/bin`, system | available |
| pyserial, PyYAML | `/usr/lib/python3/dist-packages` | available |
| pytest ≥ 7.0 (`tests/host/hil/pyproject.toml`) | developer's `~/.local` only | **missing** |

The apt package `python3-pytest` of Ubuntu 22.04 is 6.2.5, below the minimum.
Install pytest in the `jenkins` user's site directory:

```bash
sudo -u jenkins -H python3 -m pip install --user "pytest>=7"
sudo -u jenkins -H python3 -m pytest --version
```

## 7. Executors

One board means one build at a time across all jobs. `disableConcurrentBuilds()`
in the Jenkinsfile only covers the builds of one job; the executor count
covers the others.

*Manage Jenkins → Nodes → Built-In Node → Configure → Number of executors*:
`1` (it was `2` on 03/11/2026).

## 8. Plugins

Needed, all installed on 03/11/2026:

| Plugin | Id | Used for |
|:--|:--|:--|
| Pipeline | `workflow-aggregator` | declarative pipeline |
| Pipeline: Declarative | `pipeline-model-definition` | `pipeline { }`, `when { changeRequest() }`, linter |
| Pipeline: Multibranch | `workflow-multibranch` | one job per branch and pull request |
| GitHub Branch Source | `github-branch-source` | scan, commit status `continuous-integration/jenkins/pr-merge` |
| Git | `git` | `checkout scm` |
| JUnit | `junit` | HIL report |

Apply the pending updates first (*Manage Jenkins → Plugins → Updates*), then
restart Jenkins.

## 9. Jenkinsfile linter

Checks the declarative syntax of `ci/Jenkinsfile` without running it.
Create an API token (*user menu → Security → API Token → Add new Token*),
then, from the repository root:

```bash
curl -s -X POST -u zbenakka -F "jenkinsfile=<ci/Jenkinsfile" http://localhost:8080/pipeline-model-converter/validate
```

Paste the token at the password prompt, so that it does not stay in the
shell history. Expected: `Jenkinsfile successfully validated.` Revoke the
token afterwards.

## 10. GitHub credential

On GitHub, *Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token*:

| Field | Value |
|:--|:--|
| Repository access | Only select repositories: `zkariae/stm32f7508-dk-baremetal` |
| Contents | Read-only |
| Pull requests | Read-only |
| Commit statuses | Read and write |
| Metadata | Read-only (added by GitHub) |

In Jenkins, *Manage Jenkins → Credentials → System → Global credentials →
Add Credentials*:

| Field | Value |
|:--|:--|
| Kind | Username with password |
| Username | `zkariae` |
| Password | the fine-grained token |
| ID | `github-zkariae` |

The submodule `stm32f7508-dk` is public; the Jenkinsfile fetches it over
HTTPS, so it needs no credential.

## 11. Multibranch job

*New Item → Multibranch Pipeline*, name `stm32f7508-dk-baremetal`.

| Setting | Value |
|:--|:--|
| Branch Sources | GitHub, credential `github-zkariae`, repository `https://github.com/zkariae/stm32f7508-dk-baremetal` |
| Discover branches | Exclude branches that are also filed as PRs |
| Discover pull requests from origin | Merging the pull request with the current target branch revision |
| Discover pull requests from forks | Merging the pull request with the current target branch revision; Trust: From users with Admin or Write permission |
| Build Configuration | by Jenkinsfile, Script Path `ci/Jenkinsfile` |
| Scan Multibranch Pipeline Triggers | Periodically if not otherwise run, interval 5 minutes |

No webhook: WSL2 is not reachable from the Internet. A new branch or pull
request is built within 5 minutes, or at once with *Scan Multibranch
Pipeline Now*.

The "merging" strategy is what names the commit status of a pull request
`continuous-integration/jenkins/pr-merge`, the check required in section 12.

## 12. GitHub rulesets (D9)

On GitHub, *repository Settings → Rules → Rulesets → New ruleset → New
branch ruleset*, three times:

| Ruleset name | Target (Include by pattern) | Restrict deletions |
|:--|:--|:--|
| `main` | `main` | yes |
| `develop` | `develop` | yes |
| `phase-integration` | `phase*/integration` | no |

Same settings for the three:

| Setting | Value |
|:--|:--|
| Enforcement status | Active |
| Bypass list | Repository admin, always allow |
| Require a pull request before merging | yes, required approvals 0, allowed merge methods: Merge |
| Require status checks to pass | yes, *Require branches to be up to date before merging*, check `continuous-integration/jenkins/pr-merge` |
| Block force pushes | yes |

The check name can only be picked from the list once Jenkins has published
it at least once: enable the rulesets after the first pull request build, or
type the name by hand.

## 13. Checks

D8, after sections 2 to 11:

1. `git push -u origin phaseD-ci/integration`, then *Scan Multibranch
   Pipeline Now*.
2. The branch build runs Checkout and Build in green; UART T1-T8 and HIL
   show as skipped; the `.bin` files are archived.
3. On GitHub, the branch's last commit carries the status
   `continuous-integration/jenkins/branch` in green.

D9, after section 12:

1. A direct `git push` to `develop` is refused (without admin bypass).
2. The end-of-phase checks of `ci/README.md` section 8 (D10).
