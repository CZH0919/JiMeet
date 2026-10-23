# Django + PostgreSQL 环境配置手册

本文档只描述步骤，供手工执行。macOS 用于本地验证，Ubuntu 用于服务器部署，两者系统层命令不同，Django 配置层一致。

---

## 0 先决条件与版本约束

| 组件 | 版本要求 | 说明 |
|------|---------|------|
| Python | >= 3.12 | Django 6.1 的 `Requires-Python` 为 `>=3.12`，低于此版本装不上 |
| PostgreSQL | 14+ 均可 | 本项目用到 `JSONB`、部分索引、`LEAST`，14 以上无兼容问题 |
| psycopg | 3.x | 用 `psycopg[binary]`，不要用已停止维护的 `psycopg2` |

**Python 环境管理方式二选一**，不要混用：

- `venv`：Python 自带，无额外依赖，环境目录随项目走，适合单项目。
- `conda`：适合需要非 Python 依赖（如某些科学计算库）或需要频繁切换多版本。本项目无此需求。

两者都能满足要求，选一个即可。下文两条路径都给出。

---

## 1 macOS（本地验证）

### 1.1 安装系统依赖

```bash
brew install python@3.12
brew install postgresql@18
```

`postgresql@18` 是 keg-only，`psql` 等命令可能不在默认 PATH。若 `psql --version` 报找不到：

```bash
echo 'export PATH="/opt/homebrew/opt/postgresql@18/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 1.2 启动 PostgreSQL

```bash
brew services start postgresql@18
pg_isready                      # 期望：/tmp:5432 - accepting connections
```

`brew services start` 会注册开机自启（`~/Library/LaunchAgents/sh.brew.postgresql@18.plist`）。只想临时跑一次可用 `pg_ctl -D /opt/homebrew/var/postgresql@18 start`。

### 1.3 创建数据库与角色

Homebrew 的 `initdb` 会把**当前 macOS 登录用户**建成超级用户，并创建 `postgres` 库，本地认证为 `trust`/`peer`，所以直接 `psql -d postgres` 即可，不需要 `sudo -u postgres`。

```bash
psql -d postgres -c "CREATE ROLE jimeet LOGIN PASSWORD 'jimeet';"
createdb -O jimeet jimeet
```

验证：

```bash
PGPASSWORD=jimeet psql -h 127.0.0.1 -U jimeet -d jimeet -c "select current_user, current_database();"
```

> 口令仅用于本地开发。服务器上必须换成强口令，并通过环境变量注入，不写进代码。

### 1.4 创建 Python 环境

**方式 A：venv**

```bash
cd backend
/opt/homebrew/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -V                       # 期望 3.12.x
```

**方式 B：conda**

```bash
conda create -n jimeet python=3.12 -y
conda activate jimeet
python -V
```

> 不要用 conda 的 `base` 环境装项目依赖。`base` 里的 Python 版本与项目无关，混装后难以复现。

### 1.5 安装 Python 依赖

```bash
pip install --upgrade pip
pip install "Django>=6.1,<6.2" "psycopg[binary]>=3.3,<4"
```

需要从 `.env` 读配置时再加 `python-dotenv`。若不用它，直接读 `os.environ` 也可以。

验证：

```bash
python -c "import django, psycopg; print(django.get_version(), psycopg.__version__)"
```

### 1.6 验证数据库连通性

不依赖 Django，先确认 psycopg 能连上：

```bash
python - <<'PY'
import psycopg
with psycopg.connect(dbname="jimeet", user="jimeet", password="jimeet",
                     host="127.0.0.1", port=5432) as conn:
    print(conn.execute("select version()").fetchone()[0])
PY
```

能打印版本号即说明系统层与驱动层都通了，剩下的只是 Django 配置。

#### 报 `FATAL: role "jimeet" does not exist`：补建角色

这个报错发生在**认证之前**：PostgreSQL 先按连接参数里的 `user` 去查 `pg_roles`，查不到就直接 `FATAL`，根本没走到校验口令那一步。所以它只说明"角色没建"，和口令、`pg_hba.conf` 都无关。同理，库没建时报的是 `database "jimeet" does not exist`。

**不要用 `-U postgres`**：Homebrew 的 `initdb` 只把当前 macOS 登录用户建成超级用户，`postgres` 这个角色通常不存在。下面的命令都不写 `-U`，以默认登录用户身份连 `postgres` 库执行。若 1.3 已经成功执行过，本节只需当作自查。

**1）确认当前身份有建角色的权限，并查看现状**

```bash
psql -d postgres -c "SELECT current_user, rolsuper FROM pg_roles WHERE rolname = current_user;"
psql -d postgres -c "\du"     # 现有角色
psql -d postgres -c "\l"      # 现有数据库
```

`rolsuper` 必须为 `t`，否则没有建角色的权限。

**2）幂等创建角色**（已存在则跳过，可重复执行）

```bash
psql -d postgres <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'jimeet') THEN
    CREATE ROLE jimeet LOGIN PASSWORD 'jimeet';
  END IF;
END
$$;
SQL
```

**3）创建数据库并指定 owner**

```bash
createdb -O jimeet jimeet
```

库已存在时 `createdb` 会报 `already exists`，跳过即可。owner 必须是 `jimeet`：PG 15 起 `public` schema 归 `pg_database_owner`，只有库 owner 才自动拥有写权限；库若由登录用户创建，`migrate` 会报 `permission denied for schema public`。已建错时可以补：

```bash
psql -d postgres -c "ALTER DATABASE jimeet OWNER TO jimeet;"
# 或只补权限、不换 owner
psql -d jimeet -c "GRANT ALL ON SCHEMA public TO jimeet;"
```

**4）验证**

```bash
PGPASSWORD=jimeet psql -h 127.0.0.1 -U jimeet -d jimeet -tAc "select current_user, current_database();"
# 期望输出：jimeet|jimeet
```

也可以直接重跑本节开头的 psycopg 片段。完整的顺序检查见第 5 节。

#### 连通性报错对照表

| 报错 | 含义 | 处理 |
|------|------|------|
| `FATAL: role "jimeet" does not exist` | 角色未创建；或连到了另一个实例 | 按上面第 2 步创建；有多个实例时先核对 `host`、`port` |
| `FATAL: password authentication failed for user "jimeet"` | 角色在，口令不符 | `psql -d postgres -c "ALTER ROLE jimeet PASSWORD 'jimeet';"` |
| `FATAL: database "jimeet" does not exist` | 库未创建 | 第 3 步 `createdb -O jimeet jimeet` |
| `permission denied for schema public` | 库 owner 不是 `jimeet` | 第 3 步的 `ALTER DATABASE ... OWNER TO` |
| `connection ... port 5432 failed: Connection refused` | 服务未启动 | `brew services start postgresql@18` |
| `psql: command not found` | keg-only 未加入 PATH | 见 1.1 |

> 以上口令只用于本地开发。Ubuntu 上超级用户是 `postgres` 系统用户，需 `sudo -u postgres psql`，见 2.3。

---

## 2 Ubuntu（服务器）

### 2.1 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-venv python3-dev \
                    postgresql postgresql-contrib libpq-dev
```

- `python3.12-venv`：Ubuntu 的 Python 默认不带 `venv` 模块，缺了会报 `ensurepip is not available`。
- `libpq-dev`：只有用 `psycopg`（源码包）时才需要；用 `psycopg[binary]` 可省，但装上无副作用。
- 若发行版仓库没有 3.12，用 deadsnakes PPA 或 pyenv，不要降级 Django。

### 2.2 启动 PostgreSQL

```bash
sudo systemctl enable --now postgresql
sudo systemctl status postgresql
```

### 2.3 创建数据库与角色

Ubuntu 的 `initdb` 把 `postgres` 系统用户建成超级用户，本地认证为 `peer`，必须切到该用户：

```bash
sudo -u postgres psql -c "CREATE ROLE jimeet LOGIN PASSWORD '换成强口令';"
sudo -u postgres createdb -O jimeet jimeet
```

验证：

```bash
PGPASSWORD='换成强口令' psql -h 127.0.0.1 -U jimeet -d jimeet -c "select current_user;"
```

### 2.4 创建 Python 环境

```bash
cd /path/to/backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install "Django>=6.1,<6.2" "psycopg[binary]>=3.3,<4"
```

服务器上若用 systemd 托管，注意 `ExecStart` 要写 venv 内的绝对路径，例如 `/path/to/backend/.venv/bin/gunicorn`，不要依赖 `activate`。

---

## 3 macOS 与 Ubuntu 的差异对照

| 项 | macOS (Homebrew) | Ubuntu (apt) |
|---|---|---|
| 安装 Python | `brew install python@3.12` | `apt install python3.12 python3.12-venv` |
| 安装 PostgreSQL | `brew install postgresql@18` | `apt install postgresql postgresql-contrib` |
| 启动服务 | `brew services start postgresql@18` | `systemctl enable --now postgresql` |
| 超级用户 | 当前 macOS 登录用户 | `postgres` 系统用户 |
| 进入管理终端 | `psql -d postgres` | `sudo -u postgres psql` |
| 数据目录 | `/opt/homebrew/var/postgresql@18` | `/var/lib/postgresql/<ver>/main` |
| 认证配置 | `/opt/homebrew/var/postgresql@18/pg_hba.conf` | `/etc/postgresql/<ver>/main/pg_hba.conf` |
| 默认本地认证 | `trust` / `peer` | `peer` |
| 编译依赖 | 一般无需 | `libpq-dev`、`python3-dev` |

**Django 配置层两边完全一致**：`DATABASES` 的 `ENGINE`、`HOST`、`PORT`、`USE_TZ`、`ATOMIC_REQUESTS` 都不因操作系统而变。差异只在系统层命令与认证方式。

---

## 4 Django 侧需要对齐的配置项

以下来自 `backend/file/design_manuscript/database.md` 的通用约定，配置时逐条核对：

| 配置 | 值 | 依据 |
|------|-----|------|
| `ENGINE` | `django.db.backends.postgresql` | 0.1 |
| `USE_TZ` | `True` | 0.2，时间字段一律 `TIMESTAMPTZ` |
| `ATOMIC_REQUESTS` | `False` | 0.8，事务由 service 层显式开启 |
| `DEFAULT_AUTO_FIELD` | `BigAutoField` | 各表主键为 `BIGINT` |
| `AUTH_USER_MODEL` | 自定义用户模型 | 1.1，**必须在首次 `migrate` 前设置** |
| `MEDIA_ROOT` | 独立于 `STATIC_ROOT` | 1.4，简历不得落在公开静态目录 |

`AUTH_USER_MODEL` 是最容易踩的坑：Django 一旦执行过 `migrate`，再切换用户模型就必须删库重建。所以顺序是**先定用户模型，再 `migrate`**。

---

## 5 验证清单

按顺序执行，每步都应通过：

```bash
# 1 服务在跑
pg_isready

# 2 角色与库存在
psql -d postgres -tAc "SELECT rolname FROM pg_roles WHERE rolname='jimeet'"
psql -d postgres -tAc "SELECT datname FROM pg_database WHERE datname='jimeet'"

# 3 能用应用账号登录
PGPASSWORD=jimeet psql -h 127.0.0.1 -U jimeet -d jimeet -c "select 1"

# 4 Python 环境正确
python -V
python -c "import django, psycopg; print(django.get_version(), psycopg.__version__)"

# 5 Django 能连库（需已有 settings.py）
python manage.py check
python manage.py migrate
```

---

## 6 清理与回滚

### 6.1 删除 venv

venv 是自包含目录，删除后不留任何系统级痕迹：

```bash
rm -rf backend/.venv
```

删除后 `python`、`pip` 回到系统版本，已安装的 Django 一并消失。数据库、角色、服务不受影响。

### 6.2 删除 conda 环境

```bash
conda deactivate
conda env remove -n jimeet
```

### 6.3 删除数据库与角色

```bash
dropdb jimeet
psql -d postgres -c "DROP ROLE jimeet;"
```

### 6.4 停止 PostgreSQL

```bash
# macOS
brew services stop postgresql@18

# Ubuntu
sudo systemctl stop postgresql
```

### 6.5 卸载系统包（可选）

```bash
# macOS
brew uninstall postgresql@18 python@3.12

# Ubuntu
sudo apt remove --purge postgresql postgresql-contrib
```

---

## 7 常见问题

**`psql: command not found`（macOS）**
`postgresql@18` 是 keg-only，按 1.1 把 `/opt/homebrew/opt/postgresql@18/bin` 加进 PATH。

**`FATAL: role "xxx" does not exist`**
Homebrew 下默认角色是当前登录用户名，不是 `postgres`。用 `psql -d postgres` 而不是 `psql -U postgres`。

**`ensurepip is not available`（Ubuntu）**
缺 `python3.12-venv`，按 2.1 安装。

**`psycopg.OperationalError: connection refused`**
服务没起，或 `HOST` 写成了 `localhost` 而服务只监听 socket。先 `pg_isready`，再确认 `HOST=127.0.0.1`。

**`django.db.utils.ProgrammingError: permission denied for schema public`**
PostgreSQL 15 起 `public` schema 默认不再对所有人可写。给应用角色授权：

```sql
GRANT ALL ON SCHEMA public TO jimeet;
```

**切换 `AUTH_USER_MODEL` 报 `InconsistentMigrationHistory`**
已经 `migrate` 过。开发期直接删库重建；生产期需要手写迁移，成本很高，所以务必在首次 `migrate` 前定好。

**`pip install psycopg2` 编译失败**
不要用 psycopg2。改用 `psycopg[binary]`，它自带预编译二进制，不需要 `pg_config`。
