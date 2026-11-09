# Infrastructure

Two ways to run EasyFundraise:

- **Local dev** — `docker-compose.yml` (api + web + worker + a Postgres container). See the root README.
- **AWS (prod)** — Terraform provisions two EC2 boxes; GitHub Actions builds images and deploys to them.

```
infra/
  docker-compose.yml        Local dev stack (unchanged)
  terraform/
    bootstrap/              One-time: S3 state bucket + DynamoDB lock table
    core/                   The prod stack: VPC, core box, db box, DNS
  deploy/
    core-compose.yml        Prod compose for the core box (no db container)
    Caddyfile               TLS + reverse proxy
    core.env.example        Documents every env key the core box needs
```

## Architecture

```
                 efcore.doctra.ai
                        │  (Route53 A -> Elastic IP)
                        ▼
        ┌───────────────────────────────┐        ┌────────────────────────┐
        │  easyfundraise-core  (public) │  5432  │  easyfundraise-db       │
        │  Caddy :443 → web :3000       │ ─────► │  PostgreSQL 16 + pgvector│
        │  web /api/* → api :8000       │        │  DIRECT on host, no Docker│
        │  worker (replies, sending)    │        │  no public ingress       │
        │  Docker + Compose             │        │  SG: 5432 from core only │
        └───────────────────────────────┘        └────────────────────────┘
                public subnet                          data subnet
```

- **easyfundraise-core** (`t3.small` default): runs `api`, `web`, `worker` and `caddy` as containers pulled from GHCR. Public IP + TLS.
- **easyfundraise-db** (`t3.micro` default): PostgreSQL 16 with the `vector` extension installed **directly on the host** (no container). Its security group accepts port 5432 **only from the core box**, and SSH only via the core box (bastion). No public database port.
- AWS account `059898286291`, region `ap-southeast-1` (both overridable).

The database is deliberately isolated on its own instance and its own subnet, so it can be sized, backed up and hardened independently of the app.

## First-time setup

### 0. Prerequisites
- Terraform >= 1.6, AWS CLI configured for account `059898286291`.
- An EC2 key pair:
  ```bash
  aws ec2 create-key-pair --key-name easyfundraise \
    --query KeyMaterial --output text > ~/.ssh/easyfundraise.pem
  chmod 600 ~/.ssh/easyfundraise.pem
  ```
- A Route53 hosted zone for `doctra.ai` in this account (or set `manage_dns = false`).

### 1. Remote-state bootstrap (once per account)
```bash
cd infra/terraform/bootstrap
terraform init
terraform apply
```

### 2. Provision core + db
```bash
cd infra/terraform/core
cp terraform.tfvars.example terraform.tfvars   # edit values
export TF_VAR_db_password='<strong-password>'  # keep it out of the file
terraform init
terraform apply
```
Note the outputs: `core_public_ip`, `db_private_ip`, `app_url`.

### 3. Configure GitHub Actions secrets
In **Settings → Secrets and variables → Actions** add:

| Secret | Value |
|---|---|
| `CORE_SSH_HOST` | `terraform output core_public_ip` |
| `CORE_SSH_USER` | `ubuntu` |
| `CORE_SSH_KEY`  | contents of `~/.ssh/easyfundraise.pem` |
| `CORE_ENV_FILE` | full `.env`, built from `infra/deploy/core.env.example` — set `EF_DATABASE_URL` to `postgresql+psycopg://ef:<pw>@<db_private_ip>:5432/easyfundraise` |

### 4. Deploy
Push to `main` (or run the **Deploy core** workflow manually). It builds the api + web images, pushes them to GHCR, copies the compose bundle + `.env` to the core box, and runs `docker compose up -d`. Migrations and seed run on container boot (idempotent). Caddy issues the TLS cert for `efcore.doctra.ai` on first start.

## Operating

```bash
# App logs (on the core box)
ssh -i ~/.ssh/easyfundraise.pem ubuntu@<core_public_ip>
cd /opt/easyfundraise && docker compose -f core-compose.yml logs -f

# Reach the db box (via the core box as bastion)
ssh -i ~/.ssh/easyfundraise.pem -J ubuntu@<core_public_ip> ubuntu@<db_private_ip>
sudo -u postgres psql easyfundraise
```

## Hardening backlog (left minimal on purpose)

- Lock `ssh_ingress_cidrs` to known IPs (defaults to `0.0.0.0/0`).
- Move the db box fully private: add a NAT gateway, give the data subnet its own route table, and set `db_data_public_ip = false`.
- Back up Postgres (automated `pg_dump` to S3, or move to RDS later).
- Put app secrets in SSM Parameter Store / Secrets Manager instead of the `.env` file.
- Rotate the `db_password` out of EC2 user-data after first boot (it is visible in instance metadata).
