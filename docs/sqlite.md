# SQLite 資料庫（取代 MySQL）

這個 fork 的智控台後端（manager-api）改用 **SQLite 單一檔案**，不再需要 MySQL 容器。小智主程式（xiaozhi-server）不直接連資料庫，所有資料都經由 manager-api 的 API 存取，所以只有 manager-api 一個程式在寫 SQLite。

## 檔案位置

- 資料庫：`main/xiaozhi-server/sqlite/xiaozhi.db`（容器內 `/data/xiaozhi.db`，已加入 `.gitignore`）
- 連線設定：`main/manager-api/src/main/resources/application-dev.yml`
  - `journal_mode=WAL`、`busy_timeout=10000`
  - `date_class=TEXT` + `date_string_format=yyyy-MM-dd HH:mm:ss`：日期以文字存放
- 結構：`main/manager-api/src/main/resources/db/changelog-sqlite/`
  - `202611230001-baseline.sql` 是 MySQL 跑完所有 changeset 後的結構（由轉換工具產生）
  - 原本的 `db/changelog/`（MySQL 語法）只留作參考，不再執行

## 與 MySQL 行為對齊的處理

- 文字欄位加上 `COLLATE NOCASE`：MySQL 的 `*_ci` 比對不分大小寫（`LLM` = `llm`），SQLite 預設會區分。
- `NOW()` 改為 `datetime('now','localtime')`；`SELECT … FOR UPDATE` 拿掉（SQLite 的寫入交易本來就是單一寫入者）。
- `selectMaps` 取回的日期在 SQLite 是文字，`AgentChatHistoryServiceImpl` 會自行轉成 `LocalDateTime`。
- `docs/docker/start.sh` 只傳入有設定的環境變數並加上引號（JDBC URL 內含空白）。

## 從 MySQL 轉換

`main/manager-api/tools/mysql_to_sqlite.py` 會讀取 MySQL 的實際結構與全部資料，寫成 SQLite 檔並做完整性檢查：

```sh
docker run --rm --network xiaozhi-server_default --user 1000:1000 -e HOME=/tmp \
  -v "$PWD/main/xiaozhi-server/sqlite:/out" -v "$PWD/main/manager-api/tools:/tools:ro" python:3.12-slim \
  sh -c 'pip install -q --user pymysql && python3 /tools/mysql_to_sqlite.py \
    --host xiaozhi-esp32-server-db --user root --password <密碼> --database xiaozhi_esp32_server --out /out/xiaozhi.db'
```

轉換時請先停止 `xiaozhi-esp32-server-web` 與 `xiaozhi-esp32-server`，避免轉換中有新資料寫入。

## 限制

- **全新安裝**：基準結構只有資料表，沒有上游 MySQL changeset 裡的預設資料（參數、模型供應商、字典等）。全新部署請先用上游 MySQL 版初始化一次，再用轉換工具轉成 SQLite。
- **合併上游更新**：上游新增的 MySQL changeset 不會自動套用，需要改寫成 SQLite 語法後，加到 `db/changelog-sqlite/db.changelog-master.yaml`。

## 備份

SQLite 是單一檔案，可用 `sqlite3 xiaozhi.db ".backup backup.db"` 線上備份，或停止 web 容器後直接複製檔案（含 `-wal`、`-shm`）。

## 切回 MySQL

1. `git checkout main/xiaozhi-server/docker-compose_all.yml`（還原 MySQL 版 compose）
2. `docker start xiaozhi-esp32-server-db`（轉換時保留了停止的 MySQL 容器與 `mysql/data`）
3. `docker compose -f docker-compose_all.yml up -d`

注意：切回後，SQLite 期間產生的新資料不會出現在 MySQL。
