# Docker setup on Windows

Docker runs this project's PostgreSQL/pgvector, Redis, migrations, API, Linux Celery worker and web together through the [Compose local stack](phase-02-local.md). It is needed for the documented full-stack verification. Folder cleanup, frontend development and backend unit tests can run without Docker; those checks do not establish real dependency behavior. See the [local runbook](phase-02-local.md) for native alternatives.

## Initial machine findings and support boundary

Read-only checks on 2026-11-16 found 64-bit Windows 10 Pro 22H2, build 19045.7548; `wsl.exe` and `winget.exe` exist. Docker was absent from PATH and the usual machine/per-user installation directories. `wsl --version` printed usage rather than a modern version, so working WSL 2 is unverified. The Windows Server service (`LanmanServer`) was running with Automatic startup. Hardware virtualization and RAM could not be established through the restricted CIM queries.

Docker's current [Windows requirements](https://docs.docker.com/desktop/setup/install/windows-install/) list this Windows build baseline, WSL 2.1.5+, 8 GB RAM, a 64-bit SLAT-capable CPU and BIOS/UEFI virtualization. They also restrict support to Windows versions within Microsoft's servicing timeline. [Windows 10 Home/Pro ordinary support ended on 2025-10-14](https://learn.microsoft.com/en-us/lifecycle/products/windows-10-home-and-pro). This guide does **not** establish Docker support on this host. Prefer a supported Windows 11 installation, or confirm the applicable extended-support arrangement with the vendors before relying on Windows 10.

No software was installed, Windows feature changed, service reconfigured or reboot performed during that cleanup.

After the owner installed Docker, follow-up checks on 2026-11-16 confirmed Docker Desktop 4.99.0, Docker Engine/client 29.9.3, a working `linux/amd64` server in the `desktop-linux` context, Compose 5.7.0 and WSL 3.0.1.0. The working engine establishes local runtime availability, not vendor support eligibility for this Windows 10 host. Project container/integration results are recorded separately in [verification](../testing/phase-02-verification.md).

## Install WSL and Docker Desktop

1. Check Task Manager > Performance > CPU for **Virtualization: Enabled** and Memory for capacity. Enable virtualization in BIOS/UEFI if required; device-specific firmware steps belong to the machine owner.
2. Open **PowerShell as Administrator**, then install WSL and restart Windows when requested:

   ```powershell
   wsl --install --no-distribution
   ```

   A separate Ubuntu installation is optional for using Docker from Windows PowerShell; see Docker's [WSL backend guide](https://docs.docker.com/desktop/features/wsl/). If WSL is already installed, update it instead. After any requested restart, verify it:

   ```powershell
   wsl --update
   wsl --set-default-version 2
   wsl --version
   wsl --status
   ```

   If the commands still show only usage or fail, follow Microsoft's [WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install) before continuing. Do not interpret the presence of `wsl.exe` as proof WSL 2 works.
3. Review the [Docker installation instructions and license terms](https://docs.docker.com/desktop/setup/install/windows-install/). In PowerShell, inspect and install the exact package:

   ```powershell
   winget show --id Docker.DockerDesktop --exact --source winget
   winget install --id Docker.DockerDesktop --exact --source winget --interactive
   ```

   [WinGet's exact ID/source options](https://learn.microsoft.com/en-us/windows/package-manager/winget/install) avoid ambiguous package selection. The current [Microsoft package manifest](https://github.com/microsoft/winget-pkgs/tree/master/manifests/d/Docker/DockerDesktop) uses a machine installation and can request administrator elevation. Docker's official interactive installer also offers per-user installation. Follow installer/restart prompts; installation is a separate machine change from repository cleanup.
4. Launch **Docker Desktop** from Start and complete its initial prompts. Under Settings > General, enable **Use WSL 2 based engine** if shown. Select **Linux containers** if currently using Windows containers. Wait until the engine is running. Open a fresh ordinary PowerShell terminal so PATH changes apply.

## Verify and start this project

```powershell
docker version
docker compose version
docker info --format '{{.OSType}}'
docker run --rm hello-world
```

Expect both Client and Server in `docker version`, Compose v2, `linux`, and a successful test container. Downloads require network access. A client version alone does not prove the engine is running.

From the repository root in ordinary PowerShell (Node.js 24 must be installed):

```powershell
Set-Location D:\projects\RAG
node scripts/bootstrap-local.mjs
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Open <http://localhost:3000> and <http://localhost:8000/docs>. Bootstrap preserves existing credentials; never delete secret files to fix a database that already has a data volume. Startup can exceed the initial wait while images download/build; inspect `docker compose ps` and bounded logs before retrying. The [local runbook](phase-02-local.md) includes worker delivery verification and troubleshooting. Actual Docker builds, migrations and readiness remain unverified until these commands succeed.

Stop the stack while preserving database/Redis volumes:

```powershell
docker compose down
```

Do not add `--volumes` or run volume-pruning commands when retaining local data. Docker Compose here is a development environment; production orchestration, backup/restore and private-data admission remain later work.
