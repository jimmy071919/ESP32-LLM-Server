# 非中國服務遷移：配置基線與操作邊界

基準提交：`6371f0eda885467310f8c2b178ae119213113e5c`。本文件只記載可公開的原始碼事實；線上 Agent ID、金鑰、Endpoint 與使用者資料不得寫入公開倉庫。

## 真正的配置來源

1. `main/xiaozhi-server/config/config_loader.py` 讀取 `config.yaml` 和未追蹤的 `data/.config.yaml`。
2. `data/.config.yaml` 設有 `manager-api.url` 時，主設定取自 Manager API；此時修改 `config.yaml` 不能證明線上已切換。
3. 每個裝置連線時還會透過 `get_agent_models` 取得角色專用模型；必須分別核對 `ai_agent` 指派、`ai_model_config` 的啟用狀態及 Provider endpoint。僅翻譯 Provider 名稱不算替換。
4. 已安裝的 SQL migration 不可回頭修改；新增遷移或後台顯式操作才會作用於既有資料。不得自動覆寫既有 Agent 的 Prompt、聲音、記憶、模型或憑證。

## 非中國化（S2）實作狀態

已在原始碼完成（changeset `202611221800`，部署步驟見 [runbook.md](runbook.md)）：

- YAML 預設：`GroqASR`／`OpenAILLM`／`OpenAIVLLM`／`EdgeTTS`；意圖與本地記憶的輔助 LLM 改 `OpenAILLM`；PowerMem 範例改 OpenAI embedding。
- 資料庫：新增非中國模型與範本預設；未被引用的中國模型停用；外掛映射轉為 Open-Meteo／RSS／Tavily；他牌喚醒詞與陸用文案移除（僅限仍為上游預設值者）。既有角色的模型指派刻意不動。
- 工具：`get_weather` 改 Open-Meteo 並共用給提示詞上下文；新增 `get_news_rss`；`web_search` 只允許 tavily／serply；IP 定位移除 pconline、改為可選且預設關閉。
- 提示詞：天氣規則改為「上下文有資料才直接回答，否則呼叫工具或詢問城市」；不再暗示上下文永遠有在地預報。
- 供應鏈：基底映像改 ghcr.io（同 digest）、原始碼打包進映像、移除阿里雲 PyPI 與 zh_CN locale；`.dockerignore` 補上子目錄的 data／.env 排除。
- 部署：移除 `seccomp:unconfined`；8000/8003 預設只綁 127.0.0.1（可由 `XIAOZHI_BIND_ADDR` 調整）；DB 密碼改由 `.env` 提供；nginx 轉送 `X-Real-IP` 並新增 `/mcp/vision/`；WebSocket 位置關閉 access log。
- 工作台：Web Chat 允許主機改由 `VUE_APP_WEB_CHAT_ALLOWED_HOSTS` 於建置時設定。
- 品質關卡：`tests/test_non_cn_policy.py`、`make audit-non-cn`；稽核查詢 `audit.sql`；盤點 `provider-inventory.csv`、`endpoint-inventory.csv`。

尚未完成（需線上環境或另案）：線上部署與 Liquibase 實際套用、既有角色逐一遷移、金鑰填寫、24–72 小時出口流量稽核、ESP32 韌體分支、Aliyun 簡訊模組替換、WebSocket 一次性票券。

## 原始碼風險基線（改造前）

- 原 YAML 範例曾預選 ChatGLM LLM/VLLM 與 FunASR，並包含中國天氣、新聞、搜尋預設；每項都必須由實際路由和配置來驗收，而非以原始碼命中數代替外送次數。
- `Dockerfile-server-deps` 和 `Dockerfile-web-local` 仍依賴 `ghcr.nju.edu.cn`；供應鏈替換需要先重建候選映像並確認模型及執行時資產完整。
- `main/xiaozhi-server/docker-compose_all.yml` 的 MySQL 範例使用固定弱密碼與 root 帳號、server 發布 8000/8003 到所有介面並使用 `seccomp:unconfined`。修改這些項目需要資料庫備份、密碼輪替與反代／裝置相容性驗證，不能只改 YAML 後重啟。
- 歷史提交已有天氣服務 API key 明文；從目前檔案刪除不會抹掉 Git 歷史，部署擁有者必須撤銷並輪替。不要貼出金鑰或包含 `config_json` 的原始 SQL 結果。
- 工作台 token 由 WebSocket query string 傳遞；既有代理及後端可能記錄 URL。改傳輸協議前需先維持 ESP32 與瀏覽器相容，確認短效票券或代理可用。

## 遷移關卡

- **靜態改造**：保留既有函式名稱及裝置協議；替代服務不具憑證時應明確失敗，不得隱藏回退到中國 API。
- **線上切換**：先備份 DB 與 Compose，新增而非覆寫 Provider，先測試 Agent，再取得既有 Agent 遷移授權；完整核對每個 Agent 的 ASR/LLM/VLLM/TTS、工具映射與外連。
- **安全交付**：候選映像與執行映像 ID、掛載、權限、端點、語音／圖片、使用者刪除、回退測試及 24–72 小時 egress 稽核均需通過，才能宣稱 S2 完成。

公開程式碼掃描只能證明預設或可用 adapter，不代表線上使用。模型、語音和供應商切換不能在缺乏金鑰、授權、實機測試及回退方案時當作已完成。
