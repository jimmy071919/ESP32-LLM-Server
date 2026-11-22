-- =====================================================================
-- S2 非中國化：預設模型、外掛與系統參數
-- 原則：
--   * 不刪除、不改寫任何 ai_agent 的 Prompt／聲音／記憶／模型指派。
--   * 只新增非中國模型；中國模型僅在「未被任何角色／範本／意圖／記憶引用」時停用（is_enabled=0），不刪除。
--   * 預設模型只在「目前預設是中國服務」時才改為新模型，尊重管理員已選的非中國預設。
--   * 外掛：天氣改 Open-Meteo（移除和風天氣金鑰）、新聞改 RSS 白名單、搜尋移除秘塔。
--   * 可重複執行；新模型以 INSERT IGNORE 新增，不覆寫管理員填好的金鑰。
-- 回退：見 docs/migration/runbook.md「回退」章節。
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. 新增非中國模型（金鑰留空，由管理員在後台填寫）
-- ---------------------------------------------------------------------
INSERT IGNORE INTO `ai_model_config`
(`id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`, `config_json`, `doc_link`, `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES
('LLM_OpenAIOfficial', 'LLM', 'OpenAIOfficial', 'OpenAI 官方 API', 0, 1,
 JSON_OBJECT('type', 'openai', 'base_url', 'https://api.openai.com/v1', 'model_name', 'gpt-4o-mini',
             'api_key', '', 'temperature', 0.7, 'max_tokens', 500),
 'https://platform.openai.com/docs/models',
 '非中國化預設 LLM。請填入 API 金鑰，並將 model_name 改為實測過、支援 function calling 的模型。',
 1, NULL, NOW(), NULL, NOW()),
('VLLM_OpenAIVision', 'VLLM', 'OpenAIVision', 'OpenAI 官方視覺', 0, 1,
 JSON_OBJECT('type', 'openai', 'base_url', 'https://api.openai.com/v1', 'model_name', 'gpt-4o-mini', 'api_key', ''),
 'https://platform.openai.com/docs/guides/images-vision',
 '非中國化預設視覺模型。請填入 API 金鑰與支援影像輸入的模型。',
 1, NULL, NOW(), NULL, NOW()),
('VLLM_GeminiVision', 'VLLM', 'GeminiVision', 'Google Gemini 視覺（OpenAI 相容端點）', 0, 1,
 JSON_OBJECT('type', 'openai', 'base_url', 'https://generativelanguage.googleapis.com/v1beta/openai/',
             'model_name', 'gemini-2.0-flash', 'api_key', ''),
 'https://ai.google.dev/gemini-api/docs/openai',
 'Gemini 的 OpenAI 相容端點，可作為視覺模型備選。',
 2, NULL, NOW(), NULL, NOW());

-- 既有的非中國模型確保可被選用
UPDATE `ai_model_config` SET `is_enabled` = 1, `update_date` = NOW()
WHERE `id` IN ('ASR_GroqASR', 'ASR_OpenaiASR', 'LLM_GeminiLLM', 'TTS_EdgeTTS', 'TTS_OpenAITTS');

-- Whisper 類 ASR：新增語言／提示詞／逾時欄位（只補缺少的鍵，不覆寫既有值）
UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.prompt', '以下是繁體中文的語音內容。'), `update_date` = NOW()
WHERE `id` = 'ASR_GroqASR' AND JSON_EXTRACT(`config_json`, '$.prompt') IS NULL;

UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.timeout', 30), `update_date` = NOW()
WHERE `id` IN ('ASR_GroqASR', 'ASR_OpenaiASR') AND JSON_EXTRACT(`config_json`, '$.timeout') IS NULL;

UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY_APPEND(`fields`, '$',
      JSON_OBJECT('key', 'language', 'type', 'string', 'label', '語言（ISO-639-1，例如 zh、en；留空自動偵測）')),
    `update_date` = NOW()
WHERE `id` = 'SYSTEM_ASR_OpenaiASR' AND JSON_SEARCH(`fields`, 'one', 'language', NULL, '$[*].key') IS NULL;

UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY_APPEND(`fields`, '$',
      JSON_OBJECT('key', 'prompt', 'type', 'string', 'label', '提示詞（可引導繁體中文輸出）')),
    `update_date` = NOW()
WHERE `id` = 'SYSTEM_ASR_OpenaiASR' AND JSON_SEARCH(`fields`, 'one', 'prompt', NULL, '$[*].key') IS NULL;

UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY_APPEND(`fields`, '$',
      JSON_OBJECT('key', 'timeout', 'type', 'number', 'label', '逾時秒數')),
    `update_date` = NOW()
WHERE `id` = 'SYSTEM_ASR_OpenaiASR' AND JSON_SEARCH(`fields`, 'one', 'timeout', NULL, '$[*].key') IS NULL;

-- ---------------------------------------------------------------------
-- 2. 中國服務／中國來源模型清單（逗號分隔，供 FIND_IN_SET 使用）
-- ---------------------------------------------------------------------
SET @cn_llm  = 'LLM_AliLLM,LLM_AliAppLLM,LLM_DoubaoLLM,LLM_DeepSeekLLM,LLM_ChatGLMLLM,LLM_CozeLLM,LLM_VolcesAiGatewayLLM,LLM_XunfeiSparkLLM';
SET @cn_vllm = 'VLLM_ChatGLMVLLM,VLLM_QwenVLVLLM';
SET @cn_asr  = 'ASR_FunASR,ASR_FunASRServer,ASR_SherpaASR,ASR_DoubaoASR,ASR_DoubaoStreamASR,ASR_DoubaoStreamASRV2,ASR_TencentASR,ASR_AliyunASR,ASR_AliyunStreamASR,ASR_AliyunBLStream,ASR_BaiduASR,ASR_XunfeiStream,ASR_Qwen3Flash';
SET @cn_tts  = 'TTS_DoubaoTTS,TTS_HuoshanDoubleStreamTTS,TTS_HSDSTTS_V2,TTS_CosyVoiceSiliconflow,TTS_CozeCnTTS,TTS_VolcesAiGatewayTTS,TTS_MinimaxTTS,TTS_MinimaxStreamTTS,TTS_AliyunTTS,TTS_AliyunStreamTTS,TTS_AliBLStreamTTS,TTS_TencentTTS,TTS_XunFeiStreamTTS,TTS_GizwitsTTS,TTS_LinkeraiTTS,TTS_ACGNTTS,TTS_TTS302AI,TTS_PaddleSpeechTTS,TTS_IndexStreamTTS,TTS_FishSpeech,TTS_GPT_SOVITS_V2,TTS_GPT_SOVITS_V3';
SET @cn_all  = CONCAT_WS(',', @cn_llm, @cn_vllm, @cn_asr, @cn_tts);

-- ---------------------------------------------------------------------
-- 3. 預設模型：只有目前預設是中國服務（或沒有預設）時才切換
-- ---------------------------------------------------------------------
SET @llm_switch = (SELECT COUNT(*) = 0 FROM `ai_model_config`
                   WHERE `model_type` = 'LLM' AND `is_default` = 1 AND NOT FIND_IN_SET(`id`, @cn_llm));
SET @vllm_switch = (SELECT COUNT(*) = 0 FROM `ai_model_config`
                    WHERE `model_type` = 'VLLM' AND `is_default` = 1 AND NOT FIND_IN_SET(`id`, @cn_vllm));
SET @asr_switch = (SELECT COUNT(*) = 0 FROM `ai_model_config`
                   WHERE `model_type` = 'ASR' AND `is_default` = 1 AND NOT FIND_IN_SET(`id`, @cn_asr));

UPDATE `ai_model_config` SET `is_default` = 0, `update_date` = NOW()
WHERE `is_default` = 1 AND FIND_IN_SET(`id`, @cn_all);

UPDATE `ai_model_config` SET `is_default` = 1, `is_enabled` = 1, `update_date` = NOW()
WHERE (`id` = 'LLM_OpenAIOfficial' AND @llm_switch = 1)
   OR (`id` = 'VLLM_OpenAIVision' AND @vllm_switch = 1)
   OR (`id` = 'ASR_GroqASR' AND @asr_switch = 1);

-- ---------------------------------------------------------------------
-- 4. 角色範本（新建角色的預設）：只替換仍指向中國模型的欄位
--    既有 ai_agent 不在此處修改；請依 runbook 逐一取得授權後遷移。
-- ---------------------------------------------------------------------
UPDATE `ai_agent_template`
SET `llm_model_id`  = IF(FIND_IN_SET(`llm_model_id`, @cn_llm),   'LLM_OpenAIOfficial', `llm_model_id`),
    `vllm_model_id` = IF(FIND_IN_SET(`vllm_model_id`, @cn_vllm), 'VLLM_OpenAIVision',  `vllm_model_id`),
    `asr_model_id`  = IF(FIND_IN_SET(`asr_model_id`, @cn_asr),   'ASR_GroqASR',        `asr_model_id`),
    `updated_at` = NOW()
WHERE FIND_IN_SET(`llm_model_id`, @cn_llm)
   OR FIND_IN_SET(`vllm_model_id`, @cn_vllm)
   OR FIND_IN_SET(`asr_model_id`, @cn_asr);

UPDATE `ai_agent_template`
SET `tts_model_id` = 'TTS_EdgeTTS', `tts_voice_id` = 'TTS_EdgeTTS0012', `tts_language` = '台灣華語', `updated_at` = NOW()
WHERE FIND_IN_SET(`tts_model_id`, @cn_tts);

-- ---------------------------------------------------------------------
-- 5. 意圖識別／本地記憶使用的輔助 LLM：只有指向「未填金鑰」的中國模型時才改指向 OpenAI 官方
-- ---------------------------------------------------------------------
SET @placeholder_cn_llms = (
  SELECT GROUP_CONCAT(`id`) FROM `ai_model_config`
  WHERE FIND_IN_SET(`id`, @cn_llm)
    AND (JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) IS NULL
         OR JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) = ''
         OR JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.api_key')) LIKE '你的%')
);

UPDATE `ai_model_config`
SET `config_json` = JSON_SET(`config_json`, '$.llm', 'LLM_OpenAIOfficial'), `update_date` = NOW()
WHERE `id` IN ('Intent_intent_llm', 'Memory_mem_local_short')
  AND FIND_IN_SET(JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.llm')), IFNULL(@placeholder_cn_llms, ''));

-- ---------------------------------------------------------------------
-- 6. 停用未被引用的中國模型（不刪除；仍被引用者保持啟用，待遷移後再停用）
-- ---------------------------------------------------------------------
SET @llm_refs = (
  SELECT IFNULL(GROUP_CONCAT(DISTINCT JSON_UNQUOTE(JSON_EXTRACT(`config_json`, '$.llm'))), '')
  FROM `ai_model_config` WHERE JSON_EXTRACT(`config_json`, '$.llm') IS NOT NULL
);

UPDATE `ai_model_config` m
SET m.`is_enabled` = 0, m.`update_date` = NOW()
WHERE FIND_IN_SET(m.`id`, @cn_all)
  AND m.`is_default` = 0
  AND NOT FIND_IN_SET(m.`id`, @llm_refs)
  AND NOT EXISTS (
    SELECT 1 FROM `ai_agent` a
    WHERE m.`id` IN (a.`asr_model_id`, a.`llm_model_id`, a.`vllm_model_id`, a.`slm_model_id`, a.`tts_model_id`)
  )
  AND NOT EXISTS (
    SELECT 1 FROM `ai_agent_template` t
    WHERE m.`id` IN (t.`asr_model_id`, t.`llm_model_id`, t.`vllm_model_id`, t.`tts_model_id`)
  );

-- ---------------------------------------------------------------------
-- 7. 天氣外掛：Open-Meteo（移除和風天氣 Host／金鑰與預設城市「广州」）
-- ---------------------------------------------------------------------
UPDATE `ai_model_provider`
SET `name` = '天氣查詢（Open-Meteo）',
    `fields` = JSON_ARRAY(
      JSON_OBJECT('key', 'provider', 'type', 'string', 'label', '天氣服務（僅支援 openmeteo）', 'default', 'openmeteo'),
      JSON_OBJECT('key', 'default_location', 'type', 'string', 'label', '預設查詢地點（例如 Taipei；留空則詢問使用者）', 'default', ''),
      JSON_OBJECT('key', 'country_code', 'type', 'string', 'label', '優先國家代碼（ISO，例如 TW；同名地點時使用，可留空）', 'default', ''),
      JSON_OBJECT('key', 'api_key', 'type', 'string', 'label', 'Open-Meteo 商用 API 金鑰（非商業使用可留空）', 'default', '')
    ),
    `update_date` = NOW()
WHERE `id` = 'SYSTEM_PLUGIN_WEATHER';

UPDATE `ai_agent_plugin_mapping`
SET `param_info` = JSON_SET(
      JSON_REMOVE(`param_info`, '$.api_host', '$.api_key'),
      '$.provider', 'openmeteo',
      '$.api_key', '',
      '$.default_location',
      IF(JSON_UNQUOTE(JSON_EXTRACT(`param_info`, '$.default_location')) IN ('广州', '廣州'),
         '', IFNULL(JSON_UNQUOTE(JSON_EXTRACT(`param_info`, '$.default_location')), ''))
    )
WHERE `plugin_id` = 'SYSTEM_PLUGIN_WEATHER'
  AND (JSON_EXTRACT(`param_info`, '$.api_host') IS NOT NULL
       OR JSON_EXTRACT(`param_info`, '$.provider') IS NULL
       OR JSON_UNQUOTE(JSON_EXTRACT(`param_info`, '$.default_location')) IN ('广州', '廣州'));

DELETE FROM `sys_params` WHERE `param_code` IN ('plugins.get_weather.api_key', 'plugins.get_weather.api_host');
UPDATE `sys_params` SET `param_value` = '' , `remark` = '天氣預設地點（留空則詢問使用者）'
WHERE `param_code` = 'plugins.get_weather.default_location' AND `param_value` IN ('广州', '廣州');

-- ---------------------------------------------------------------------
-- 8. 新聞外掛：新增 RSS 白名單閘道，並把 newsnow／中新網的角色映射轉到 RSS
-- ---------------------------------------------------------------------
SET @default_feeds = 'BBC 中文|https://feeds.bbci.co.uk/zhongwen/trad/rss.xml|zh|world;DW 中文|https://rss.dw.com/rdf/rss-chi-all|zh|world;BBC World|https://feeds.bbci.co.uk/news/world/rss.xml|en|world;NPR News|https://feeds.npr.org/1001/rss.xml|en|world';

INSERT INTO `ai_model_provider`
(`id`, `model_type`, `provider_code`, `name`, `fields`, `sort`, `creator`, `create_date`, `updater`, `update_date`)
VALUES ('SYSTEM_PLUGIN_NEWS_RSS', 'Plugin', 'get_news_rss', 'RSS 新聞',
  JSON_ARRAY(
    JSON_OBJECT('key', 'feeds', 'type', 'string',
                'label', 'RSS 來源（名稱|https 網址|語言|主題，以分號分隔；請確認各來源使用條款）',
                'default', @default_feeds),
    JSON_OBJECT('key', 'max_items', 'type', 'number', 'label', '每次最多則數', 'default', '5'),
    JSON_OBJECT('key', 'max_age_hours', 'type', 'number', 'label', '只保留幾小時內的新聞', 'default', '72')
  ),
  30, 0, NOW(), 0, NOW())
ON DUPLICATE KEY UPDATE `update_date` = NOW();

SET @rss_params = JSON_OBJECT('feeds', @default_feeds, 'max_items', '5', 'max_age_hours', '72');

-- 已同時擁有 RSS 映射的角色，直接移除舊新聞映射（避免唯一鍵衝突）
DELETE old FROM `ai_agent_plugin_mapping` old
JOIN `ai_agent_plugin_mapping` rss
  ON rss.`agent_id` = old.`agent_id` AND rss.`plugin_id` = 'SYSTEM_PLUGIN_NEWS_RSS'
WHERE old.`plugin_id` IN ('SYSTEM_PLUGIN_NEWS_NEWSNOW', 'SYSTEM_PLUGIN_NEWS_CHINANEWS');

-- 同一角色若同時有 newsnow 與中新網，只保留一筆轉換
DELETE cn FROM `ai_agent_plugin_mapping` cn
JOIN `ai_agent_plugin_mapping` nn
  ON nn.`agent_id` = cn.`agent_id` AND nn.`plugin_id` = 'SYSTEM_PLUGIN_NEWS_NEWSNOW'
WHERE cn.`plugin_id` = 'SYSTEM_PLUGIN_NEWS_CHINANEWS';

UPDATE `ai_agent_plugin_mapping`
SET `plugin_id` = 'SYSTEM_PLUGIN_NEWS_RSS', `param_info` = @rss_params
WHERE `plugin_id` IN ('SYSTEM_PLUGIN_NEWS_NEWSNOW', 'SYSTEM_PLUGIN_NEWS_CHINANEWS');

-- 舊外掛已無映射後移除其定義，避免新角色再選用
DELETE p FROM `ai_model_provider` p
WHERE p.`id` IN ('SYSTEM_PLUGIN_NEWS_NEWSNOW', 'SYSTEM_PLUGIN_NEWS_CHINANEWS')
  AND NOT EXISTS (SELECT 1 FROM `ai_agent_plugin_mapping` m WHERE m.`plugin_id` = p.`id`);

DELETE FROM `sys_params` WHERE `param_code` IN ('plugins.get_news.default_rss_url', 'plugins.get_news.category_urls');

-- ---------------------------------------------------------------------
-- 9. 搜尋外掛：移除秘塔，預設 Tavily
-- ---------------------------------------------------------------------
UPDATE `ai_model_provider`
SET `fields` = JSON_ARRAY(
      JSON_OBJECT('key', 'provider', 'type', 'string', 'label', '搜尋來源：tavily / serply', 'default', 'tavily'),
      JSON_OBJECT('key', 'description', 'type', 'string', 'label', '工具描述',
                  'default', '联网搜索工具。当用户明确需要联网搜索问题时使用此工具。'),
      JSON_OBJECT('key', 'max_results', 'type', 'string', 'label', '回傳數量', 'default', '5'),
      JSON_OBJECT('key', 'api_key', 'type', 'string', 'label', 'API 金鑰（Tavily: tvly- 開頭）', 'default', '')
    ),
    `update_date` = NOW()
WHERE `id` = 'SYSTEM_PLUGIN_WEB_SEARCH';

-- 秘塔金鑰無法用於 Tavily，改為空白，需管理員重新填寫
UPDATE `ai_agent_plugin_mapping`
SET `param_info` = JSON_SET(`param_info`, '$.provider', 'tavily', '$.api_key', '')
WHERE `plugin_id` = 'SYSTEM_PLUGIN_WEB_SEARCH'
  AND (LOWER(IFNULL(JSON_UNQUOTE(JSON_EXTRACT(`param_info`, '$.provider')), 'metaso')) = 'metaso'
       OR JSON_UNQUOTE(JSON_EXTRACT(`param_info`, '$.api_key')) LIKE 'mk-%');

-- ---------------------------------------------------------------------
-- 10. IP 定位（預設關閉）；讓管理員可在「參數管理」中設定
-- ---------------------------------------------------------------------
-- 注意：MAX() 聚合在沒有 GROUP BY 時一定回傳一列，因此存在性判斷必須放在外層
INSERT INTO `sys_params` (`id`, `param_code`, `param_value`, `value_type`, `param_type`, `remark`)
SELECT n.`next_id`, 'geolocation.provider', 'none', 'string', 1, 'IP 定位：none（預設，不送出 IP）/ ipinfo / ipwhois'
FROM (SELECT IFNULL(MAX(`id`), 0) + 1 AS `next_id` FROM `sys_params`) n
WHERE NOT EXISTS (SELECT 1 FROM (SELECT `param_code` FROM `sys_params`) s WHERE s.`param_code` = 'geolocation.provider');

INSERT INTO `sys_params` (`id`, `param_code`, `param_value`, `value_type`, `param_type`, `remark`)
SELECT n.`next_id`, 'geolocation.lookup_private_ip_as_server', 'false', 'boolean', 1, '私有 IP 裝置是否以伺服器出口 IP 估計位置'
FROM (SELECT IFNULL(MAX(`id`), 0) + 1 AS `next_id` FROM `sys_params`) n
WHERE NOT EXISTS (SELECT 1 FROM (SELECT `param_code` FROM `sys_params`) s WHERE s.`param_code` = 'geolocation.lookup_private_ip_as_server');

-- ---------------------------------------------------------------------
-- 11. 對話文案與喚醒詞（只改仍為上游預設的值，管理員自訂內容不動）
-- ---------------------------------------------------------------------
-- 移除其他廠商品牌的喚醒詞；ESP32 韌體喚醒模型需同步調整
UPDATE `sys_params`
SET `param_value` = TRIM(BOTH ';' FROM
      REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(
        CONCAT(';', `param_value`, ';'),
        ';小爱同学;', ';'), ';你好小鑫;', ';'), ';你好小新;', ';'), ';小美同学;', ';'),
        ';小龙小龙;', ';'), ';喵喵同学;', ';'), ';小滨小滨;', ';'), ';小冰小冰;', ';'))
WHERE `param_code` = 'wakeup_words';

UPDATE `sys_params` SET `param_value` = '抱歉，我現在有點忙，我們稍後再試一次好嗎？'
WHERE `param_code` = 'system_error_response' AND `param_value` = '主人，小智现在有点忙，我们稍后再试吧。';

UPDATE `sys_params` SET `param_value` = '請用溫暖、簡短、帶點不捨的語氣結束這次對話，使用與對話相同的語言。'
WHERE `param_code` = 'end_prompt.prompt' AND `param_value` LIKE '请你以%时间过得真快%';

UPDATE `sys_params` SET `param_value` = CONCAT(`param_value`, ';關閉')
WHERE `param_code` = 'exit_commands' AND NOT FIND_IN_SET('關閉', REPLACE(`param_value`, ';', ','));

-- Home Assistant 示範裝置（小米 cuco_cn／iot_cn 實體）不應作為預設
UPDATE `sys_params` SET `param_value` = ''
WHERE `param_code` = 'plugins.home_assistant.devices' AND `param_value` LIKE '%cuco_cn_460494544%';
