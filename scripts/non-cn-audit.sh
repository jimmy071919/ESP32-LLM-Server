#!/usr/bin/env bash
# 非中國化靜態稽核（本機品質關卡）。
# 失敗條件只看「預設／啟用中」的路徑：建置檔、預設設定、啟用中的工具程式碼。
# 上游保留但預設未使用的 adapter 與歷史 SQL migration 不算失敗，只在 --inventory 時列出。
set -euo pipefail
cd "$(dirname "$0")/.."

FORBIDDEN='ghcr\.nju\.edu\.cn|mirrors\.aliyun\.com|maven\.aliyun\.com|npmmirror\.com|bigmodel\.cn|dashscope|aliyuncs\.com|volces\.com|deepseek\.com|qweatherapi|qweather\.(com|net)|metaso\.cn|newsnow\.busiyi|chinanews\.com|pconline\.com\.cn'
GATED=(
  Dockerfile-server Dockerfile-server-base Dockerfile-server-deps Dockerfile-web Dockerfile-web-local
  main/xiaozhi-server/docker-compose_all.yml
  main/manager-api/pom.xml
  main/manager-web/.npmrc
  main/manager-web/package-lock.json
  main/xiaozhi-server/plugins_func/functions/get_weather.py
  main/xiaozhi-server/plugins_func/functions/get_news_rss.py
  main/xiaozhi-server/plugins_func/functions/web_search.py
  main/xiaozhi-server/core/utils/geolocation.py
  main/xiaozhi-server/core/utils/util.py
  main/xiaozhi-server/core/utils/prompt_manager.py
)

status=0
echo "== 1. 建置檔與啟用中工具程式碼不得出現中國服務主機 =="
if grep -nEi "$FORBIDDEN" "${GATED[@]}"; then
  echo "FAIL: 上列檔案引用了禁止的主機"; status=1
else
  echo "OK"
fi

echo "== 2. config.yaml 預設模組／外掛／喚醒詞（tests/test_non_cn_policy.py） =="
PY=${PYTHON:-python3}
if (cd main/xiaozhi-server && "$PY" -c 'import yaml' 2>/dev/null); then
  (cd main/xiaozhi-server && "$PY" -m unittest tests.test_non_cn_policy -v 2>&1 | tail -3) || status=1
else
  echo "SKIP: 需要 PyYAML（設定 PYTHON=<venv>/bin/python）"
fi

if [[ "${1:-}" == "--inventory" ]]; then
  echo "== 盤點（不影響結果）：仍存在於程式碼中的中國服務參照 =="
  grep -rnEil "$FORBIDDEN|open\.bigmodel|volcengine|tencentcloudapi|xfyun|siliconflow|coze\.cn|baidubce" \
    main/xiaozhi-server/core main/xiaozhi-server/plugins_func main/xiaozhi-server/config.yaml \
    main/manager-web/src 2>/dev/null | sort || true
fi
exit $status
