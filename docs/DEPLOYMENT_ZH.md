# DataLink 与 Product Streamer：中文说明与部署指南

更新日期：2026 年 10 月 8 日。本文依据当前实验代码及已记录测试编写，供理解系统、维护现有虚拟机和在新服务器复现使用。

## 1. 系统实现了什么

本实验验证从数据标识符（DID）到文件下载和完整性校验的流程：

```text
用户输入 DID
    ↓
DataLink 查询产品信息，返回 VOTable 链接及服务描述
    ↓
客户端发现 Product Streamer 下载地址，并提交产品描述
    ↓
Product Streamer 在服务器上读取文件，发送文件字节或 TAR 数据集
    ↓
客户端检查接收长度、内容和 SHA-256
```

**DataLink** 是数据链接与服务描述标准，本实验使用的 SKA 服务负责解析 DID，并告诉客户端数据在哪里、通过什么服务获取。

**Product Streamer** 是服务器端的数据交付软件，不是运行在下载端的一种独立下载协议。它通过 HTTP 交付文件；浏览器或 Python 脚本是客户端。

**测试网站** 是我们开发的实验门户，负责登录、展示响应、代理请求和执行测试。门户调用官方软件，并模拟它们依赖的部分服务。

## 2. 软件来源与固定版本

| 软件 | 本次实验版本 | 官方代码仓库 |
|---|---|---|
| DataLink | `ska-src-dm-datalink 0.1.5` | [SKA GitLab：DataLink](https://gitlab.com/ska-telescope/src/src-dm/ska-src-dm-datalink) |
| Product Streamer | `ska-src-dm-product-streamer-api 0.1.2` | [SKA GitLab：Product Streamer](https://gitlab.com/ska-telescope/src/src-dm/ska-src-dm-product-streamer-api) |

固定提交：

- DataLink：`997dfb03944b9c44283411264ca1c07b48b03a8e`。
- Product Streamer：`27df8cb247105faf67a6d278dd9819528f211dd3`。

网站集成、部署和测试代码：[guotsuan/datalink-streamer-lab](https://github.com/guotsuan/datalink-streamer-lab)。这个 GitHub 仓库不重新分发官方项目源码；环境准备脚本从官方来源安装固定版本。

记录的服务器环境为 Rocky Linux 10.2、Python 3.13.15。门户使用 FastAPI 0.141.1、Uvicorn 0.53.0、HTTPX 0.28.1；官方服务环境使用 FastAPI 0.124.4、Uvicorn 0.34.3、HTTPX 0.28.1。三个 Python 环境相互独立，具体依赖见 `lab/requirements-*.lock.txt`。

这些依赖文件是历史版本清单，不是带完整包哈希的跨平台安装锁文件。

## 3. 部署结构与测试范围

| 组件 | 现有虚拟机上的地址 | 作用 |
|---|---|---|
| 公网登录网关 | `http://64.176.188.89:18080` | 登录、访问控制和转发 |
| 门户及模拟服务 | `127.0.0.1:18080` | 网页、DMAPI／IAM／PAPI 模拟接口 |
| 官方 DataLink | `127.0.0.1:18081` | DID 解析、VOTable 链接及服务描述 |
| 官方 Product Streamer | `127.0.0.1:18082` | 文件及 TAR 交付 |
| 临时 iperf3 | TCP 5201 | 测试时启动，结束后关闭 |

公网网关与门户使用相同端口，但分别绑定公网 IP 和回环地址，因此能够共存。DataLink 和 Streamer 的原始端口只在服务器内部使用。

DataLink、Streamer、VOTable、文件流和 TAR 生成是真实运行的；DMAPI、IAM、PAPI 和同节点服务发现使用模拟数据。当前没有接入真实 SCAPI、Rucio、StoRM 或 CNSRC／SRCNet 节点。

测试数据包括四个小文件和一个可选的大文件。大文件 DID 为 `lab.test:large-1tb.fits`，逻辑大小 **1,000,000,005,120 字节**；其中像素数据为十进制 1 TB，其余为 FITS 文件头及填充。它是零填充稀疏文件，记录的服务器磁盘占用为 4 KB，但实际下载仍会传输相应数量的网络字节。

10 GB 测试下载的是这个大文件的前 10,000,000,000 字节，不是另外生成的完整 10 GB FITS 图像。该测速反映网络和服务交付能力；稀疏数据不能用于评估真实磁盘顺序读取性能。

## 4. 关键代码与目录

| 路径 | 用途 |
|---|---|
| `lab/app.py` | 门户、模拟依赖服务和请求代理 |
| `lab/public_gateway.py` | 公网登录网关 |
| `lab/supervise.py` | 启动和管理门户、DataLink、Streamer 三个进程 |
| `lab/fixtures.py` | 生成四个确定性小文件及其参考哈希 |
| `lab/large_fixture.py` | 生成约 1 TB 的稀疏 FITS |
| `lab/static/` | 网页、浏览器校验和测速功能 |
| `lab/test_public_e2e.py` | 公网功能测试与结果导出 |
| `lab/static/download_large.py` | iperf、下载测速和 SHA-256 比较 |
| `scripts/prepare_environment.py` | 新服务器的依赖环境准备 |
| `scripts/build_speed_report.py` | 从测速 JSON 生成英文 PDF 和 Markdown 报告 |
| `docs/` | 说明、测试报告和经过检查的结果 JSON |

目录区别非常重要：

```text
现有虚拟机：/home/gq/datalink-streamer-lab/
            app.py、supervise.py、static/、storage/ 等直接位于这里

GitHub 克隆：datalink-streamer-lab/
            lab/app.py、lab/supervise.py、lab/static/、lab/storage/ 等
```

因此不能直接把 GitHub 中的 systemd 示例或固定路径照搬到另一台服务器。

## 5. 使用与维护现有测试服务器

### 5.1 打开网站

在浏览器打开 [测试网站](http://64.176.188.89:18080)，输入实验口令。

口令没有上传到 GitHub。服务器口令文件是：

```text
/home/gq/datalink-streamer-lab/public-access-credentials.txt
```

文件中的 `Password:` 一行是网站口令；SSH 登录使用已有 SSH 密钥，两者不同。当前公网入口使用 HTTP，只使用实验口令和合成数据。

### 5.2 检查服务与日志

```sh
ssh gq@64.176.188.89
systemctl --user status datalink-streamer-lab.service
systemctl --user status datalink-streamer-public.service
journalctl --user -u datalink-streamer-lab.service -n 50 --no-pager
```

服务日志位于：

```text
/home/gq/datalink-streamer-lab/logs/18080.log
/home/gq/datalink-streamer-lab/logs/18081.log
/home/gq/datalink-streamer-lab/logs/18082.log
/home/gq/datalink-streamer-lab/logs/public.log
```

确认需要重启时，可运行：

```sh
systemctl --user restart datalink-streamer-lab.service
systemctl --user restart datalink-streamer-public.service
```

这是用户级 systemd 服务；管理时使用 `systemctl --user`。现有网站按此前设置持续运行，普通测速不需要调整网站的开放时间。

## 6. 在新服务器部署私有实验环境

以下步骤用于一台新的 Linux 实验服务器，要求 Python 3.13、Git、venv/pip，并能访问相关官方包源和 GitLab。环境准备脚本已通过语法及 dry-run 检查，但尚未完整验证从空白服务器重建的全过程。

### 6.1 下载代码与准备环境

```sh
git clone https://github.com/guotsuan/datalink-streamer-lab.git
cd datalink-streamer-lab
python3.13 scripts/prepare_environment.py --dry-run
python3.13 scripts/prepare_environment.py
```

脚本创建 `lab/.venv`、`lab/.venv-datalink`、`lab/.venv-streamer`，安装记录的依赖和固定提交。目标环境已存在时会拒绝覆盖。安装失败时，先检查 Python 版本、包源访问权限和依赖兼容性。

### 6.2 启动服务

```sh
lab/.venv/bin/python lab/supervise.py
```

这个命令在前台启动三个服务，并自动初始化小文件；先保持该终端运行，完成初步检查。

在服务器另一个终端验证：

```sh
curl http://127.0.0.1:18080/lab/status
curl -X POST http://127.0.0.1:18080/lab/run
```

`/lab/status` 应报告两个官方服务可达；内部测试中的 MIME 诊断差异仍可能存在，需要查看具体结果。

### 6.3 从自己的电脑访问

在客户端电脑上执行，把 `USER@SERVER` 换成新服务器账号和地址：

```sh
ssh -N -L 127.0.0.1:18080:127.0.0.1:18080 USER@SERVER
```

打开 `http://localhost:18080`。这是未启用公网网关的新私有部署，访问权限由 SSH 提供，不需要网站实验口令。保持转发终端运行。

### 6.4 生成大文件

在服务器仓库根目录执行：

```sh
lab/.venv/bin/python lab/large_fixture.py
```

文件生成在 `lab/storage/lab.test/large-1tb.fits`。程序会检查逻辑大小及稀疏分配；已有文件则验证其大小和文件头，不直接覆盖。小文件测试和三文件 TAR 不包含这个大文件。

### 6.5 设置常驻运行

先编辑 `lab/datalink-streamer-lab.service`，将 `WorkingDirectory` 和 `ExecStart` 改为新服务器的真实绝对路径，且包含 GitHub 布局中的 `lab/`。例如仓库位于 `/home/USER/datalink-streamer-lab` 时：

```ini
WorkingDirectory=/home/USER/datalink-streamer-lab/lab
ExecStart=/home/USER/datalink-streamer-lab/lab/.venv/bin/python /home/USER/datalink-streamer-lab/lab/supervise.py
```

把 `USER` 替换为真实账号。退出前台服务后，将修改过的单位文件安装到该账号的 `~/.config/systemd/user/`；如果同名文件已存在，先检查原配置。然后执行：

```sh
systemctl --user daemon-reload
systemctl --user enable --now datalink-streamer-lab.service
systemctl --user status datalink-streamer-lab.service
```

若需要用户退出 SSH 后继续运行，由管理员按服务器管理要求配置 user lingering。

## 7. 新服务器公网入口的配置要点

现有公网配置针对 `64.176.188.89`，不是直接适用于任意服务器的安装包。新服务器要公网访问时，需要同步调整以下项目：

| 文件／配置 | 要调整的内容 |
|---|---|
| `lab/provision_public.py` | `origin` 改为新的访问地址 |
| `lab/public_gateway.py` | `TrustedHostMiddleware` 的主机白名单 |
| `lab/datalink-streamer-public.service` | 工作目录、Python 路径、日志路径和绑定 IP |
| HTTPS／反向代理 | 对外地址、证书和转发规则，与 origin 保持一致 |
| 服务器及云平台防火墙 | 允许指定入口，官方服务端口保持回环绑定 |
| `lab/static/download_large.py` | 目标 origin、SSH 账号／地址、iperf 绑定地址及源文件路径 |

在这些配置审核并匹配后，`lab/provision_public.py` 才用于生成新网关的口令、签名密钥和配置；它默认设置 24 小时窗口，且拒绝覆盖已有配置。`persist_public_access.py` 是原实验环境的持续开放操作，不属于新部署的默认步骤。

网关通过 `public-access.json` 获取 origin，门户会据此生成外部链接。因此修改后需要重启相关服务，使网页地址、DataLink 返回的地址和登录请求 Origin 一致。新公网部署优先配置 HTTPS；不要复制或提交口令、签名密钥和运行时配置。

## 8. 运行功能测试

在自己电脑的 GitHub 仓库根目录执行：

```sh
python3 lab/test_public_e2e.py --base-url http://64.176.188.89:18080
```

输入网站实验口令。脚本检查登录、健康状态、DID 和地址发现、小文件下载、TAR 成员、SHA-256、Range 和错误响应，结果保存在 `lab/evidence/public-e2e/`。

退出码 `0` 表示功能检查通过，但仍应阅读 WARN；`1` 表示失败或依赖跳过；使用 `--strict` 时，诊断警告会返回 `2`。这套脚本期待公网网关登录流程，不适用于直接访问无登录网关的私有门户。

## 9. 运行 iperf、下载测速与 SHA-256 校验

### 9.1 准备条件

客户端需要 Python 3.9+、iperf3 和 SSH，当前自动测速流程支持 macOS/Linux。现有服务器需要 Python 3、iperf3、`timeout` 以及配置临时防火墙规则所需的免密码 sudo 权限。

若 iperf3 尚未安装，可按系统包管理方式安装，例如：

```sh
# macOS 客户端（已安装 Homebrew 时）
brew install iperf3

# Rocky Linux 服务器
sudo dnf install iperf3
```

客户端应能用已有密钥执行 `ssh gq@64.176.188.89`。测速代码固定针对现有虚拟机；换服务器需要按第 7 节调整。

### 9.2 测试流程

1. 登录网站，解析 DID，并取得 Streamer 服务描述。
2. 通过 SSH 读取服务器源文件的指定字节范围，独立计算参考 SHA-256。
3. 临时启动 iperf3，运行 10 秒单流反向 TCP 测速：服务器发、客户端收。
4. 关闭临时 iperf 服务及规则，再通过 HTTP 下载相同范围；逐块计算 SHA-256。
5. 比较接收长度、文件头／零数据和 SHA-256，输出速度对比及 JSON 结果。

默认 iperf 端口为 5201，只临时允许当前 SSH 客户端 IP，规则 60 秒后自动过期，正常测试结束即清理。iperf 的数据直接走 TCP；SSH 只负责启动和清理，不承载 iperf 测速数据。

### 9.3 常用命令

在客户端仓库根目录运行：

```sh
# 默认下载 1 GB，没有下载总时长上限
python3 lab/static/download_large.py --report comparison_1GB.json

# 下载 10 GB，并校验相同源范围的 SHA-256
python3 lab/static/download_large.py --bytes 10000000000 --report comparison_10GB.json

# 保存实际收到的 10 GB 范围；文件名必须不存在
python3 lab/static/download_large.py --bytes 10000000000 --output sample_10GB.bin --report comparison_10GB_saved.json
```

下载默认接收后丢弃，不在内存中保存整份数据。`--output` 才写入磁盘。已有输出文件或报告文件不会被覆盖，重复测试应使用新的名称。10 GB 范围文件不应当作完整 FITS 图像使用。

脚本保留 10 秒的单次 socket 等待超时，用于发现连接卡住；持续下载没有总时间上限。按 Ctrl+C 可停止。GB 使用十进制单位；`--mib 1024` 则是 1 GiB，即 1,073,741,824 字节。

`--skip-iperf` 跳过网络基准；参考哈希默认仍从 SSH 获取。只有另外提供可信的 `--expected-sha256`，才不需要 SSH 计算参考值。

### 9.4 判断结果

| JSON 字段 | 含义 |
|---|---|
| `bytes` / `expected` | 实际收到与要求收到的字节数 |
| `complete` | 长度、内容及哈希检查完成并通过 |
| `sha256` | 接收数据的 SHA-256 |
| `sha256_reference.sha256` | 独立计算的服务器源范围 SHA-256 |
| `sha256_matches` | 两个哈希是否一致 |
| `average_Mbit_s` / `average_MiB_s` | 下载累计平均速度 |
| `iperf.Mbit_s` | iperf 接收端平均速度 |
| `download_to_iperf_percent` | 下载速度除以 iperf 速度 |

下载计时不包含登录、发现、参考哈希计算和 iperf，但包含 Streamer 请求建立及接收、哈希和内容检查。测试时间及端口不同，比例略高于 100% 也可能出现。

浏览器页面的大文件测速是另一条操作路径：256 MiB 样本有 30 秒上限，1 GiB 样本有 120 秒上限，可手动停止；浏览器这部分不执行 iperf 或大范围 SHA-256 比较。需要可复现的速度及完整性结果时，使用上述 Python 脚本。

## 10. 已记录的 10 GB 结果

2026 年 10 月 5 日，对临时 VM 到客户端的路径测试：

| 项目 | 结果 |
|---|---:|
| iperf3 接收端 | 137.746 Mbps |
| Streamer 下载 | 138.757 Mbps / 16.541 MiB/s |
| 下载字节数 | 10,000,000,000 |
| 下载耗时 | 576.548 秒 |
| SHA-256 比较 | 一致，通过 |

哈希：`84b841e5ef821e36864a1c02573d509d879aeea3d9c32ed06b69faddc391e032`。

详见仓库中的 [10 GB 英文 PDF 报告](https://github.com/guotsuan/datalink-streamer-lab/blob/main/docs/DataLink_Streamer_10GB_SHA256_Report_EN.pdf) 和 [公开结果 JSON](https://github.com/guotsuan/datalink-streamer-lab/blob/main/docs/evidence/10GB_SHA256_20261005.json)。这次验证覆盖完整 10 GB 范围；尚未完成整份 1 TB 传输。

## 11. 常见问题

| 现象 | 优先检查 |
|---|---|
| `Laboratory login required` | 当前浏览器／脚本是否成功登录；浏览器之间不会自动共享 Cookie |
| `Cross-origin requests denied` | 地址、端口、协议与配置 origin 是否一致 |
| `Missing access token` | Streamer 请求是否包含实验用 Bearer 身份；仅在地址栏直接打开下载 URL 不会自动携带它 |
| `502 Bad Gateway` | 门户及官方服务进程、回环端口和服务日志 |
| iperf 启动或连接失败 | SSH 密钥、两端 iperf3、免密码 sudo、临时防火墙规则及云平台入站策略 |
| SHA-256 不一致 | 参考值是否对应同一范围，源文件是否变化，下载是否完整；本次结果应按失败处理 |
| 新服务器下载链接仍指向旧 IP | 固定 origin、SSH 目标、绑定地址和数据路径是否全部调整并重启 |

现有诊断还记录了 MIME 类型、缺少 `standardID` INFO 和模拟认证发现地址等问题。真实身份服务集成、CNSRC 部署、并发与恢复测试需要另行验证。
