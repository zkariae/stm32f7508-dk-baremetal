<!-- SPDX-License-Identifier: MIT -->
<!--
****************************
\file       ci/jenkins/setup.md
\brief      Set-up of Jenkins in WSL2, of its access to the board and of the GitHub rulesets.

\author     Z. BEN-AKKA
\version    1.3
\date       05/11/2026

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
| 1.1     | 04/11/2026 | Z. BEN-AKKA | Port 8090, Windows port conflict, token and SSH key findings from D8. |
| 1.2     | 04/11/2026 | Z. BEN-AKKA | Admin bypass for pull requests only; develop brought up to date before the rulesets. |
| 1.3     | 05/11/2026 | Z. BEN-AKKA | Required check is pr-merge, not branch; how to diagnose a blocked pull request. |
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
| Service | `jenkins`, home `/var/lib/jenkins`, port 8090 (systemd override below) |

### Port

The default port 8080 cannot be reached from Windows on this PC
(section 3). The port is set in a systemd override, which survives the
package upgrades:

```bash
sudo systemctl edit jenkins
```

Write these lines between the two `###` comment lines of the editor (text
below them is discarded):

```ini
[Service]
Environment="JENKINS_PORT=8090"
```

```bash
sudo systemctl restart jenkins
systemctl show jenkins -p Environment                         # ... JENKINS_PORT=8090 ...
systemctl is-active jenkins                                   # active
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8090/login   # 200
```

The override is stored in `/etc/systemd/system/jenkins.service.d/override.conf`.

### Ubuntu support

Jenkins announces the end of its support for Ubuntu 22.04 on 01/04/2027.
Upgrading Ubuntu also changes `arm-none-eabi-gcc`, `clang-format` and
Python, so the developer PC and Jenkins are upgraded together, in a
dedicated phase, to keep the same binaries and format check on both.

## 3. Web access from Windows

On this PC the Windows service `ApplicationWebServer.exe` listens on
`0.0.0.0:8080`, while the WSL relay `wslrelay.exe` only forwards the IPv6
loopback `[::1]:8080`. A Windows browser on `http://localhost:8080` reaches
that service and gets `Access Error: 404 -- Not Found`, not Jenkins. Hence
the port 8090 of section 2: `http://localhost:8090` works both in Windows
and in WSL.

To find the program that holds a port, in PowerShell:

```powershell
netstat -ano | findstr :8080       # last column: PID, e.g. 9160
tasklist /fi "PID eq 9160"         # ApplicationWebServer.exe
```

*Manage Jenkins → System → Jenkins URL*: `http://localhost:8090/`. The
warning that this is not a valid host name can be ignored: the URL is only
used by the browser on this PC and in the links Jenkins writes.

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
sudo systemctl restart jenkins            # after usermod: group changes apply to new processes only
id jenkins                                # groups=...(jenkins),20(dialout),46(plugdev)
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
| pytest ≥ 7.0 (`tests/host/hil/pyproject.toml`) | developer's `~/.local` only | **missing** on 03/11/2026; 9.2.0 installed on 04/11/2026 |

The apt package `python3-pytest` of Ubuntu 22.04 is 6.2.5, below the minimum.
Install pytest in the `jenkins` user's site directory:

```bash
sudo -u jenkins -H python3 -m pip install --user "pytest>=7"
sudo -u jenkins -H python3 -m pytest --version             # pytest 9.2.0
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
curl -s -X POST -u zbenakka -F "jenkinsfile=<ci/Jenkinsfile" http://localhost:8090/pipeline-model-converter/validate
```

Paste the token at the password prompt, so that it does not stay in the
shell history. Expected: `Jenkinsfile successfully validated.` Revoke the
token afterwards. An `HTTP ERROR 401 Unauthorized` page means that the
token is revoked or was badly pasted: create a new one.

## 10. GitHub credential

On GitHub, *Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token*:

| Field | Value |
|:--|:--|
| Repository access | Only select repositories: `zkariae/stm32f7508-dk-baremetal`, and no other |
| Contents | Read-only |
| Pull requests | Read-only |
| Commit statuses | Read and write |
| Metadata | Read-only (added by GitHub) |

Before *Generate token*, the summary must read "4 permissions for 1 of your
repositories". Without *Pull requests* the scan finds no pull request, and
without *Commit statuses* Jenkins builds but no check `pr-merge` ever
appears on GitHub, so the rulesets block every merge.

The token has an expiry date (03/01/2027 for the current one). Once it has
expired the scans fail; generate a new token and replace the password of
the credential below before that date.

In Jenkins, *Manage Jenkins → Credentials → System → Global credentials →
Add Credentials*:

| Field | Value |
|:--|:--|
| Kind | Username with password |
| Username | `zkariae` |
| Password | the fine-grained token |
| ID | `github-zkariae` |
| Description | GitHub fine-grained token, stm32f7508-dk-baremetal |

The submodule `stm32f7508-dk` is public; the Jenkinsfile fetches it over
HTTPS, so it needs no credential.

## 11. Multibranch job

*New Item → Multibranch Pipeline*, name `stm32f7508-dk-baremetal`.

| Setting | Value |
|:--|:--|
| Display Name | `STM32F7508-DK bare-metal` |
| Description | Build, UART T1-T8 and HIL tests on the STM32F7508-DK board for every pull request (ci/Jenkinsfile). |
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

Before `phaseD-ci/integration` is pushed, the first scan log reports
`'ci/Jenkinsfile' not found` for `main` and `develop` and ends with
`Finished: SUCCESS`: these branches do not hold the Jenkinsfile yet and get
no job, which is expected.

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
| Bypass list | Repository admin, For pull requests only |
| Require a pull request before merging | yes, required approvals 0, allowed merge methods: Merge |
| Require status checks to pass | yes, *Require branches to be up to date before merging*, check `continuous-integration/jenkins/pr-merge` |
| Block force pushes | yes |

With the bypass mode "Always allow", the admin could still push directly
to a protected branch, past every rule. "For pull requests only" refuses
every direct push, the admin's included; the admin can only merge a pull
request without its check, for an emergency.

A check name can only be picked from the list once Jenkins has published it
at least once. Before the first pull request build, the list only offers
`continuous-integration/jenkins/branch`: do not pick it, type
`continuous-integration/jenkins/pr-merge` by hand. The `branch` check is
never published on a pull request (branches filed as PRs are excluded from
the job, section 11) and only covers the Build stage. Symptom of this
mistake: the pull request stays on "Expected — Waiting for status to be
reported", with *Merge pull request* disabled.

To read the check that a ruleset really requires:

```bash
gh api repos/zkariae/stm32f7508-dk-baremetal/rulesets                  # id of each ruleset
gh api repos/zkariae/stm32f7508-dk-baremetal/rulesets/<id> --jq '.rules'
```

## 13. Checks

### Pushing from WSL

The pushes are made from the developer's WSL terminal over SSH, with a key
dedicated to GitHub. A key already registered on another GitHub account is
refused with "Key is already in use", so a new one is created:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_github -C "<e-mail>"
cat ~/.ssh/id_ed25519_github.pub          # public key only, to paste on GitHub
```

GitHub, *Settings → SSH and GPG keys → New SSH key* (here `Lenovo_WSL_Zak`),
then `~/.ssh/config`:

```text
Host github.com
  IdentityFile ~/.ssh/id_ed25519_github
  IdentitiesOnly yes
```

```bash
ssh -T git@github.com                     # Hi zkariae! You've successfully authenticated ...
```

If the push is refused with `Permission denied (publickey)`, `ssh -vT
git@github.com` shows which key is offered and whether GitHub accepts it.
An `Internal Server Error` or authentications refused only from time to
time come from GitHub itself: check https://www.githubstatus.com (*Git
Operations*) and push again once the incident is resolved.

### D8, after sections 2 to 11

1. `git push -u origin phaseD-ci/integration`, then *Scan Multibranch
   Pipeline Now*.
2. The branch build runs Checkout and Build in green; UART T1-T8 and HIL
   show as skipped; the `.bin` files are archived. The console ends with
   `GitHub has been notified of this commit's build result` and
   `Finished: SUCCESS`.
3. On GitHub, the branch's last commit carries the status
   `continuous-integration/jenkins/branch` in green.

Reached on 04/11/2026 with build #1 of `phaseD-ci/integration`.

### D9, after section 12

1. A direct `git push` to `develop` is refused, also for the admin.
2. The end-of-phase checks of `ci/README.md` section 8 (D10).

`main` held merge commits that `develop` did not have (GitHub showed
`develop` "behind main"), although both had the same content. Since the
rulesets require a branch to be up to date with its target, and a direct
push is refused once they are active, both branches were brought up to date
on 04/11/2026, before the rulesets:

```bash
git push origin main:develop                  # fast-forward, no force push
git branch -f develop main                    # same for the local branch
git checkout phaseD-ci/integration
git merge --no-ff develop -m "Merge develop"  # no file changes
git push origin phaseD-ci/integration
```

The pull requests `phaseD-ci/integration` → `develop` and `develop` →
`main` of D10 are then up to date with their target.
