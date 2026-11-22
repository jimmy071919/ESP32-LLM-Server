# 非中國化（S2）部署與回退手冊

適用版本：Liquibase changeset `202611221800` 之後的程式碼。本手冊只寫通用步驟；實際主機、Agent ID、金鑰、端點不要寫進公開倉庫。

## 0. 這次改了什麼（摘要）

| 範圍 | 變更 | 對既有資料的影響 |
|---|---|---|
| LLM／VLLM／ASR 預設 | 新增 `LLM_OpenAIOfficial`、`VLLM_OpenAIVision`、`VLLM_GeminiVision`；預設改為 OpenAI＋Groq Whisper | **只在原預設是中國服務時**才切換；角色範本同步切換 |
| 中國模型 | 未被任何角色／範本／輔助 LLM 引用者 `is_enabled=0`（不刪除） | 仍被引用者保持啟用，既有角色照常運作 |
| 既有角色 | **不修改**模型、Prompt、聲音、記憶 | 需依第 5 節逐一取得同意後遷移 |
| 天氣 | 和風天氣 → Open-Meteo；不再猜城市、不再以 IP 自動定位 | 外掛映射移除 `api_host`／`api_key`，`广州` 預設清空 |
| 新聞 | newsnow／中新網 → `get_news_rss`（RSS 白名單） | 舊映射轉為 RSS 映射，預設 BBC 中文／DW 中文／BBC World／NPR |
| 搜尋 | 移除秘塔；只允許 tavily／serply | 使用秘塔的映射改 tavily 且**清空金鑰**，需重新填寫 |
| IP 定位 | 移除 pconline；新增 `geolocation.provider`（預設 `none`） | 預設不送出任何使用者 IP |
| 文案 | 移除他牌喚醒詞、陸用錯誤訊息／結束語（只改仍為上游預設者） | 自訂內容不變 |
| 映像 | 基底改 ghcr.io（同 digest）、原始碼打包進映像、移除阿里雲 PyPI | 新映像 tag `xiaozhi-server-sv:non-cn-20261122`，舊 tag 保留以便回退 |
| Compose | 移除 `seccomp:unconfined`；8000/8003 預設只綁 127.0.0.1；DB 密碼改由 `.env` 提供 | **需要 `.env`**，見第 1 節 |

## 1. 部署前檢查（必做）

1. **備份資料庫與設定**（備份檔含個資與金鑰，存放於受保護位置）：

   ```bash
   cd main/xiaozhi-server
   docker exec xiaozhi-esp32-server-db sh -c 'exec mysqldump --single-transaction -uroot -p"$MYSQL_ROOT_PASSWORD" xiaozhi_esp32_server' > ~/backup/xiaozhi-$(date +%Y%m%d-%H%M).sql
   sudo tar czf ~/backup/xiaozhi-data-$(date +%Y%m%d).tgz data/
   docker image ls | grep xiaozhi   # 記下目前使用的 image tag，回退要用
   ```

2. **建立 `.env`**（`main/xiaozhi-server/.env`，權限 600）：參考 `.env.example`。
   - 既有部署的 `MYSQL_ROOT_PASSWORD` 先填**目前正在使用的密碼**（`MYSQL_ROOT_PASSWORD` 只在第一次初始化資料目錄時生效，改這個值不會改資料庫密碼）。
   - 保留原本的 `CODEX_OAUTH_ENCRYPTION_KEY`。

3. **確認裝置怎麼連線**，決定 `XIAOZHI_BIND_ADDR`：在後台「參數管理」或執行 `docs/migration/audit.sql` 第 6 段，查看 `server.websocket` 與 `server.vision_explain`。
   - 若指向 `…:8002/xiaozhi/v1/`、`wss://網域/xiaozhi/v1/` 等經由反向代理的位址：維持預設 `127.0.0.1`。
   - 若直接指向 `:8000` 或 `:8003`：設定 `XIAOZHI_BIND_ADDR=0.0.0.0`（或區網網卡 IP），或改後台參數讓裝置走 8002 代理（`nginx-aiot.conf` 已新增 `/mcp/vision/` 轉發）。

4. 準備金鑰：OpenAI（LLM／VLLM）、Groq（ASR）、Tavily（搜尋）。Open-Meteo 非商業使用不需金鑰。

## 2. 建置

```bash
cd main/xiaozhi-server
GIT_SHA=$(git rev-parse HEAD)
docker compose -f docker-compose_all.yml build \
  --build-arg GIT_SHA=$GIT_SHA \
  --build-arg VUE_APP_WEB_CHAT_ALLOWED_HOSTS="你的管理網域,你的私有IP"
```

- `VUE_APP_WEB_CHAT_ALLOWED_HOSTS` 留空表示工作台接受任何 HTTPS origin（由反向代理控制可達性）。
- 若 compose 對 web 服務沒有傳入 build-arg，可改用 `docker build -f Dockerfile-web --build-arg VUE_APP_WEB_CHAT_ALLOWED_HOSTS=... -t <tag> ../..`。
- 建置後確認：`docker inspect xiaozhi-server-sv:non-cn-20261122 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'` 等於 `$GIT_SHA`。

## 3. 上線與資料庫遷移

```bash
docker compose -f docker-compose_all.yml up -d
docker logs -f xiaozhi-esp32-server-web   # 等待 Liquibase 套用 202611221800
```

Liquibase 在 manager-api 啟動時自動套用 `202611221800.sql`。之後清除 manager-api 的設定快取並重啟 Python 服務，讓新設定生效：

```bash
docker exec xiaozhi-esp32-server-redis redis-cli DEL server:config sys:params
docker exec xiaozhi-esp32-server-redis sh -c "redis-cli --scan --pattern 'model:*' | xargs -r redis-cli DEL"
docker restart xiaozhi-esp32-server
```

驗證遷移結果（唯讀，金鑰已遮蔽）：

```bash
docker exec -i xiaozhi-esp32-server-db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xiaozhi_esp32_server' < ../../docs/migration/audit.sql
```

預期：範本 `asr/llm/vllm` 為 `ASR_GroqASR / LLM_OpenAIOfficial / VLLM_OpenAIVision`；外掛映射沒有 `legacy_qweather_host=1`、沒有 newsnow／中新網／metaso。

## 4. 後台設定

1. 「模型配置」：`OpenAI 官方 API`、`OpenAI 官方視覺`、`Groq语音识别` 填入金鑰；`model_name` 改為實測過的模型（LLM 需支援 function calling，VLLM 需支援影像）。
2. 角色的「外掛」：
   - 天氣：`default_location` 填英文城市名（例如 `Taipei`）或留空（模型會詢問使用者）。
   - 網路搜尋：填入 Tavily 金鑰（原秘塔金鑰已清空）。
   - RSS 新聞：確認來源清單與各來源 RSS 使用條款。
3. （選用）「參數管理」：`geolocation.provider` 改 `ipinfo`／`ipwhois` 才會以 IP 推估位置；會把使用者 IP 送給該服務。
4. 建立一個**測試角色**（新角色會套用新範本），用 Web 工作台與一台測試裝置完成第 7 節驗收後，再遷移既有角色。

## 5. 既有角色遷移（需擁有者同意，逐一進行）

- 優先在後台角色頁面切換模型（會自動處理快取）。
- 批次 SQL 只在取得同意並備份後使用，**只改模型欄位**：

  ```sql
  UPDATE ai_agent SET llm_model_id  = 'LLM_OpenAIOfficial' WHERE id = '<agent_id>' AND llm_model_id  = 'LLM_ChatGLMLLM';
  UPDATE ai_agent SET vllm_model_id = 'VLLM_OpenAIVision'  WHERE id = '<agent_id>' AND vllm_model_id = 'VLLM_ChatGLMVLLM';
  UPDATE ai_agent SET asr_model_id  = 'ASR_GroqASR'        WHERE id = '<agent_id>' AND asr_model_id  = 'ASR_FunASR';
  ```

  執行後依第 3 節清除快取。
- 每遷移一個角色就記錄：Agent ID、原模型、新模型、時間、同意人。
- `audit.sql` 第 4 段變成 0 筆後，可在後台把剩下的中國模型停用；確認不再需要 FunASR 後，可移除 compose 中 `SenseVoiceSmall/model.pt` 的掛載。

## 6. 資料庫密碼輪替與最小權限帳號

```bash
NEW=$(openssl rand -base64 24)
docker exec -it xiaozhi-esp32-server-db mysql -uroot -p
```

```sql
-- 建議：manager-api 專用帳號
CREATE USER 'xiaozhi_app'@'%' IDENTIFIED BY '<NEW_APP_PASSWORD>';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, DROP, REFERENCES, CREATE TEMPORARY TABLES
  ON xiaozhi_esp32_server.* TO 'xiaozhi_app'@'%';
-- root 改強密碼
ALTER USER 'root'@'%' IDENTIFIED BY '<NEW_ROOT_PASSWORD>';
ALTER USER 'root'@'localhost' IDENTIFIED BY '<NEW_ROOT_PASSWORD>';
FLUSH PRIVILEGES;
```

更新 `.env`（`MYSQL_ROOT_PASSWORD`、`MYSQL_APP_USER`、`MYSQL_APP_PASSWORD`）後 `docker compose -f docker-compose_all.yml up -d`。（Liquibase 需要 DDL 權限，因此 app 帳號含 CREATE／ALTER。）

另外：舊版設定檔與 Git 歷史中曾出現和風天氣共用金鑰，從檔案刪除不會抹掉歷史；若曾自行申請金鑰，請到供應商後台撤銷。

## 7. 驗收

| 項目 | 方法 | 合格 |
|---|---|---|
| 對話／工具呼叫 | 測試角色對話 20 輪，含天氣、新聞、搜尋、音樂、退出 | 無錯誤；工具結果帶來源 |
| 天氣 | 「台北天氣」「明天東京會下雨嗎」「天氣如何」（未設定預設地點） | 前兩者有資料並標示 Open-Meteo；最後一題會詢問城市 |
| 新聞 | 「來點國際新聞」「講第一則細節」 | 列出 RSS 標題與來源；細節只依摘要 |
| 搜尋 | 一般查詢 | Tavily 結果；TTS 不唸網址 |
| 語音 | 中文／英文各 20 句 | 辨識結果合理；繁體輸出（Groq prompt） |
| 圖片 | 裝置拍照提問 | VLLM 回覆，語言跟隨提問 |
| 工作台 | 正式網域 HTTPS 開啟 Web Chat | 可連線；非允許主機會被拒絕（有設定清單時） |
| 出口流量 | 見下方 | 無中國服務主機 |

出口流量稽核（24–72 小時，正式切換前）：

```bash
# 以 Python 容器的網路命名空間擷取 DNS 查詢
PID=$(docker inspect -f '{{.State.Pid}}' xiaozhi-esp32-server)
sudo nsenter -t $PID -n tcpdump -l -n -i any 'udp port 53' 2>/dev/null \
  | grep -oE 'A\? [^ ]+' | sort | uniq -c | sort -rn
```

對照 `docs/migration/endpoint-inventory.csv`；出現 `bigmodel.cn`、`aliyuncs.com`、`volces.com`、`qweather`、`metaso.cn`、`pconline.com.cn`、`chinanews.com.cn`、`newsnow` 等即為未完成（通常是仍有角色指派中國模型），需追查。

## 8. 回退

1. **映像回退**：把 `docker-compose_all.yml` 的 server image 改回原 tag（例如 `xiaozhi-server-sv:deps-20261028`），web image 改回原 tag，`docker compose up -d`。舊 server 映像依賴逐檔掛載，需同時恢復舊版 compose（`git checkout <舊提交> -- main/xiaozhi-server/docker-compose_all.yml`）。
2. **資料庫回退（完整）**：停止 web 服務後匯入第 1 節的備份：

   ```bash
   docker stop xiaozhi-esp32-server-web
   docker exec -i xiaozhi-esp32-server-db sh -c 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" xiaozhi_esp32_server' < ~/backup/xiaozhi-YYYYMMDD-HHMM.sql
   ```

   注意：若程式碼仍是新版，manager-api 啟動時會再次套用 `202611221800`；完整回退請同時回退映像。
3. **部分回退（只恢復某個中國模型可選用）**：後台「模型配置」重新啟用即可，不需要回退整個遷移。
4. 回退後依第 3 節清除 Redis 快取並重啟 Python 服務。

## 9. 已知限制與未完成項目

- **ESP32 韌體不在本倉庫**：OTA 預設網址、BluFi 名稱、喚醒模型、簡體字資源需另開韌體分支處理；後端完成不代表裝置完成。
- **上游 adapter 仍在程式碼中**（ChatGLM、豆包、阿里、騰訊、訊飛等）：預設不使用且未被引用時停用，但管理員仍可手動啟用。`tests/test_non_cn_policy.py` 只守 YAML 預設與啟用中的工具程式碼。
- **Aliyun 簡訊模組**：`server.enable_mobile_register` 預設 `false`；若要開放手機註冊需改接非中國簡訊供應商或改用 Email／TOTP。
- **工作台 WebSocket token 仍以 query string 傳遞**（瀏覽器 WebSocket 無法自訂 header）。`nginx-aiot.conf` 已對 `/xiaozhi/v1/` 關閉 access log；若前面還有其他反向代理（Caddy、雲端 LB 等）也需各自關閉或遮蔽查詢字串。token 的有效期限尚未核實；改為一次性票券需同時修改 Python WebSocket 認證，留待後續。
- **Edge TTS** 為非官方端點、無 SLA；正式產品改用 Azure Speech 或 OpenAI TTS。
- **Open-Meteo 免費 API 限非商業使用**；商用需購買並填 `api_key`。
- **Codex OAuth**：保留為選用；正式商用前需確認服務條款，正式產品優先使用 API 計費管道。
- **CI**：依專案先前決定（commit `c13a1d86` 移除 GitHub Actions），未重新加入工作流程；品質關卡以 `make test` 與 `make audit-non-cn` 在本機執行。
