-- 非中國化稽核查詢（唯讀）。輸出已遮蔽金鑰，只顯示 type / endpoint / model。
-- 用法：docker exec -i xiaozhi-esp32-server-db mysql -uroot -p xiaozhi_esp32_server < docs/migration/audit.sql
-- 結果仍屬內部資料（含角色名稱與設定），不要貼到公開 Issue。

-- 1. 每個角色實際指派的模型，並標示是否為中國服務／中國來源模型
SET @cn = 'LLM_AliLLM,LLM_AliAppLLM,LLM_DoubaoLLM,LLM_DeepSeekLLM,LLM_ChatGLMLLM,LLM_CozeLLM,LLM_VolcesAiGatewayLLM,LLM_XunfeiSparkLLM,VLLM_ChatGLMVLLM,VLLM_QwenVLVLLM,ASR_FunASR,ASR_FunASRServer,ASR_SherpaASR,ASR_DoubaoASR,ASR_DoubaoStreamASR,ASR_DoubaoStreamASRV2,ASR_TencentASR,ASR_AliyunASR,ASR_AliyunStreamASR,ASR_AliyunBLStream,ASR_BaiduASR,ASR_XunfeiStream,ASR_Qwen3Flash,TTS_DoubaoTTS,TTS_HuoshanDoubleStreamTTS,TTS_HSDSTTS_V2,TTS_CosyVoiceSiliconflow,TTS_CozeCnTTS,TTS_VolcesAiGatewayTTS,TTS_MinimaxTTS,TTS_MinimaxStreamTTS,TTS_AliyunTTS,TTS_AliyunStreamTTS,TTS_AliBLStreamTTS,TTS_TencentTTS,TTS_XunFeiStreamTTS,TTS_GizwitsTTS,TTS_LinkeraiTTS,TTS_ACGNTTS,TTS_TTS302AI,TTS_PaddleSpeechTTS,TTS_IndexStreamTTS,TTS_FishSpeech,TTS_GPT_SOVITS_V2,TTS_GPT_SOVITS_V3';

SELECT a.id, a.agent_name,
       a.asr_model_id,  IF(FIND_IN_SET(a.asr_model_id,  @cn), 'CN', '') AS asr_flag,
       a.llm_model_id,  IF(FIND_IN_SET(a.llm_model_id,  @cn), 'CN', '') AS llm_flag,
       a.vllm_model_id, IF(FIND_IN_SET(a.vllm_model_id, @cn), 'CN', '') AS vllm_flag,
       a.slm_model_id,  IF(FIND_IN_SET(a.slm_model_id,  @cn), 'CN', '') AS slm_flag,
       a.tts_model_id,  IF(FIND_IN_SET(a.tts_model_id,  @cn), 'CN', '') AS tts_flag,
       a.updated_at
FROM ai_agent a
ORDER BY (FIND_IN_SET(a.asr_model_id, @cn) + FIND_IN_SET(a.llm_model_id, @cn)
          + FIND_IN_SET(IFNULL(a.vllm_model_id, ''), @cn) + FIND_IN_SET(a.tts_model_id, @cn)) DESC,
         a.updated_at DESC;

-- 2. 角色範本（新建角色的預設）
SELECT id, agent_name, asr_model_id, llm_model_id, vllm_model_id, tts_model_id, sort FROM ai_agent_template ORDER BY sort;

-- 3. 模型設定（遮蔽金鑰）：是否啟用、是否預設、實際 endpoint
SELECT id, model_type, is_default, is_enabled,
       IF(FIND_IN_SET(id, @cn), 'CN', '') AS cn_flag,
       JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.type')) AS type,
       COALESCE(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.base_url')),
                JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.url')),
                JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.api_url'))) AS endpoint,
       JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.model_name')) AS model_name,
       IF(JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.api_key')) IN ('', 'null') OR JSON_EXTRACT(config_json, '$.api_key') IS NULL
          OR JSON_UNQUOTE(JSON_EXTRACT(config_json, '$.api_key')) LIKE '你的%', 'missing', 'set') AS api_key
FROM ai_model_config
WHERE model_type IN ('ASR', 'LLM', 'VLLM', 'TTS', 'Intent', 'Memory')
ORDER BY model_type, is_enabled DESC, id;

-- 4. 仍被引用的中國模型（必須為 0 才能宣告 S2 完成）
SELECT 'ai_agent' AS source, a.id AS ref_id, m.id AS model_id
FROM ai_model_config m JOIN ai_agent a
  ON m.id IN (a.asr_model_id, a.llm_model_id, a.vllm_model_id, a.slm_model_id, a.tts_model_id)
WHERE FIND_IN_SET(m.id, @cn)
UNION ALL
SELECT 'template', t.id, m.id
FROM ai_model_config m JOIN ai_agent_template t
  ON m.id IN (t.asr_model_id, t.llm_model_id, t.vllm_model_id, t.tts_model_id)
WHERE FIND_IN_SET(m.id, @cn)
UNION ALL
SELECT 'helper_llm', m.id, JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.llm'))
FROM ai_model_config m
WHERE FIND_IN_SET(JSON_UNQUOTE(JSON_EXTRACT(m.config_json, '$.llm')), @cn);

-- 5. 外掛映射（遮蔽金鑰）：確認沒有 newsnow／中新網／秘塔／和風天氣
SELECT m.agent_id, m.plugin_id, p.provider_code,
       JSON_UNQUOTE(JSON_EXTRACT(m.param_info, '$.provider')) AS provider,
       JSON_UNQUOTE(JSON_EXTRACT(m.param_info, '$.default_location')) AS default_location,
       JSON_EXTRACT(m.param_info, '$.api_host') IS NOT NULL AS legacy_qweather_host,
       IF(IFNULL(JSON_UNQUOTE(JSON_EXTRACT(m.param_info, '$.api_key')), '') = '', 'missing', 'set') AS api_key
FROM ai_agent_plugin_mapping m LEFT JOIN ai_model_provider p ON p.id = m.plugin_id
ORDER BY m.agent_id, m.plugin_id;

-- 6. 相關系統參數
SELECT param_code, param_value FROM sys_params
WHERE param_code IN ('wakeup_words', 'server.websocket', 'server.vision_explain', 'server.auth.enabled',
                     'geolocation.provider', 'system_error_response')
   OR param_code LIKE 'plugins.%';
