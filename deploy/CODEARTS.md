# CodeArts: repo, build, deploy to ECS, pipeline

Goal for the judges: show that NADI's code lives in **CodeArts Repo** and each push is tested and deployed to **ECS** by a **CodeArts Pipeline**.

Nothing here has been run yet (no Huawei Cloud access until the coupon arrives). Do it in region **CN-Hong Kong (ap-southeast-1)**, the same region as IoTDA.

Files used:

| File | Used by |
|---|---|
| `.cloudbuild/build.yml` | CodeArts Build (unit tests + `nadi.tar.gz`) |
| `deploy/ecs_deploy.sh` | CodeArts Deploy, runs on the ECS host |
| `deploy/nadi.service` | systemd unit installed by `ecs_deploy.sh` |
| `deploy/codearts/pipeline.yml` | CodeArts Pipeline (YAML orchestration) |

## 0. Before you start

- An ECS (Ubuntu 22.04 or 24.04, 2 vCPU / 4 GB is enough) in ap-southeast-1, with security group inbound TCP 22 (your IP only) and 8000 (or put a reverse proxy in front).
- On the ECS, once:
  ```bash
  sudo apt-get update && sudo apt-get install -y python3-venv curl
  sudo mkdir -p /opt/nadi
  sudo nano /opt/nadi/.env     # copy .env.example, set NADI_MODE=huawei, DCS/RDS hosts, ADMIN_TOKEN, SMN, MaaS
  ```
  `ecs_deploy.sh` refuses to deploy until `/opt/nadi/.env` exists. Never put `.env` in the repo.

## 1. CodeArts project

Console > **CodeArts** > create a project, type **Scrum** (or Kanban), name `NADI`.

## 2. CodeArts Repo as a second git remote

1. In the project: **Code > Repo > New Repository**, name `NADI`, empty (no README, no .gitignore).
2. Add your SSH key: avatar > **This Account Settings > Repo > SSH Keys** (paste `~/.ssh/id_ed25519.pub`; create it with `ssh-keygen -t ed25519` if missing).
3. Copy the repo's SSH URL from **Clone/Download**, then on the laptop:
   ```powershell
   git remote add codearts <SSH URL from CodeArts>
   git push codearts main
   ```
   GitHub (`origin`) stays as it is. From then on push to both: `git push origin main; git push codearts main`.
4. Proof for judges: the CodeArts Repo commit list shows the same commits and author as GitHub.

## 3. ECS host group (lets CodeArts reach the server)

**Deploy > Basic Resources > Host Clusters > Create**: OS Linux, name `nadi-ecs`, add the ECS by its IP with SSH key or password auth. Wait for the connectivity check to go green.

## 4. CodeArts Build job

**Build > Create Task**:
- Source: CodeArts Repo `NADI`, branch `main`.
- Build method: **Build with Code** (reads `.cloudbuild/build.yml`). If the console only offers a template, pick **Blank Template** and add a "Run Shell Commands" step with the `command` block from `build.yml`, then an "Upload to Release Repo" step for `nadi.tar.gz`.
- Run it once by hand. Expected log: pytest summary `N passed`, then `nadi.tar.gz` uploaded.
- Copy the job ID from the end of the browser URL (32 characters).

## 5. CodeArts Deploy job

**Deploy > Create Application**, blank template, host cluster `nadi-ecs`, then add steps:
1. **Select Deployment Source**: source = Artifact, package = the `nadi.tar.gz` from step 4, download path `/tmp/nadi`.
2. **Run Shell Commands**: `sudo bash -c 'mkdir -p /tmp/nadi/src && tar -xzf /tmp/nadi/nadi.tar.gz -C /tmp/nadi/src deploy/ecs_deploy.sh && bash /tmp/nadi/src/deploy/ecs_deploy.sh /tmp/nadi/nadi.tar.gz'`

Run it once by hand. The last log lines should be the `/api/info` JSON with `"mode": "huawei"` and `NADI deployed: /opt/nadi/releases/...`. Copy this job's ID too.

## 6. CodeArts Pipeline

**Pipeline > Create Pipeline**:
- Pipeline source **Repo**, repository `NADI`, default branch `main`, orchestration method **YAML**, configuration file **New**.
- Paste `deploy/codearts/pipeline.yml`, replace `REPLACE_WITH_BUILD_JOB_ID` and `REPLACE_WITH_DEPLOY_JOB_ID` with the IDs from steps 4 and 5.
- Click **Preview** to check the build -> deploy graph, then **Save** (it commits the YAML back to the repo).
- **Execution Plan**: enable the **code commit** trigger on `main`, so every push builds, tests and deploys.

## 7. Proof for the judges

1. Make a visible one-line change (e.g. dashboard title), `git push codearts main`.
2. Pipeline page: build (tests pass) -> deploy, both green, with the commit message.
3. Open `http://<ECS public IP>:8000`: the change is live; the footer shows `Mode: huawei` and the Huawei services in use.
4. Screenshot the pipeline run history for the slides, and keep it as backup in case the venue Wi-Fi fails.

## Rollback

On the ECS: `ls /opt/nadi/releases`, then `sudo ln -sfn /opt/nadi/releases/<older> /opt/nadi/current && sudo systemctl restart nadi`. Or re-run the pipeline on an older commit.
