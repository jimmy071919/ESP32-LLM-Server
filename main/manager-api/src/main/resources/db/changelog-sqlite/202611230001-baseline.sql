CREATE TABLE "ai_agent" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "user_id" INTEGER,
  "agent_code" TEXT COLLATE NOCASE,
  "agent_name" TEXT COLLATE NOCASE,
  "asr_model_id" TEXT COLLATE NOCASE,
  "vad_model_id" TEXT COLLATE NOCASE,
  "llm_model_id" TEXT COLLATE NOCASE,
  "slm_model_id" TEXT COLLATE NOCASE,
  "vllm_model_id" TEXT COLLATE NOCASE DEFAULT 'VLLM_ChatGLMVLLM',
  "tts_model_id" TEXT COLLATE NOCASE,
  "tts_voice_id" TEXT COLLATE NOCASE,
  "tts_language" TEXT COLLATE NOCASE,
  "tts_volume" INTEGER,
  "tts_rate" INTEGER,
  "tts_pitch" INTEGER,
  "mem_model_id" TEXT COLLATE NOCASE,
  "intent_model_id" TEXT COLLATE NOCASE,
  "system_prompt" TEXT COLLATE NOCASE,
  "summary_memory" TEXT COLLATE NOCASE,
  "chat_history_conf" INTEGER NOT NULL DEFAULT 0,
  "lang_code" TEXT COLLATE NOCASE,
  "language" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT
);
CREATE INDEX "ai_agent__idx_ai_agent_user_id" ON "ai_agent" ("user_id");
CREATE TABLE "ai_agent_chat_audio" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "audio" BLOB
);
CREATE TABLE "ai_agent_chat_history" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "mac_address" TEXT COLLATE NOCASE,
  "agent_id" TEXT COLLATE NOCASE,
  "session_id" TEXT COLLATE NOCASE,
  "chat_type" INTEGER,
  "content" TEXT COLLATE NOCASE,
  "audio_id" TEXT COLLATE NOCASE,
  "created_at" TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  "updated_at" TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX "ai_agent_chat_history__idx_ai_agent_chat_history_agent_id" ON "ai_agent_chat_history" ("agent_id");
CREATE INDEX "ai_agent_chat_history__idx_ai_agent_chat_history_agent_session_created" ON "ai_agent_chat_history" ("agent_id", "session_id", "created_at");
CREATE INDEX "ai_agent_chat_history__idx_ai_agent_chat_history_audio_id" ON "ai_agent_chat_history" ("audio_id");
CREATE INDEX "ai_agent_chat_history__idx_ai_agent_chat_history_mac" ON "ai_agent_chat_history" ("mac_address");
CREATE INDEX "ai_agent_chat_history__idx_ai_agent_chat_history_session_id" ON "ai_agent_chat_history" ("session_id");
CREATE TABLE "ai_agent_chat_title" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "session_id" TEXT COLLATE NOCASE NOT NULL,
  "title" TEXT COLLATE NOCASE,
  "created_at" TEXT,
  "updated_at" TEXT
);
CREATE INDEX "ai_agent_chat_title__idx_session_id" ON "ai_agent_chat_title" ("session_id");
CREATE TABLE "ai_agent_context_provider" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "context_providers" TEXT,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT
);
CREATE INDEX "ai_agent_context_provider__idx_agent_id" ON "ai_agent_context_provider" ("agent_id");
CREATE TABLE "ai_agent_correct_word_file" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "file_name" TEXT COLLATE NOCASE NOT NULL,
  "word_count" INTEGER NOT NULL DEFAULT 0,
  "content" TEXT COLLATE NOCASE,
  "creator" INTEGER,
  "created_at" TEXT DEFAULT (datetime('now','localtime')),
  "updater" INTEGER,
  "updated_at" TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX "ai_agent_correct_word_file__idx_creator" ON "ai_agent_correct_word_file" ("creator");
CREATE TABLE "ai_agent_correct_word_item" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "file_id" TEXT COLLATE NOCASE NOT NULL,
  "source_word" TEXT COLLATE NOCASE NOT NULL,
  "target_word" TEXT COLLATE NOCASE NOT NULL
);
CREATE INDEX "ai_agent_correct_word_item__idx_file_id" ON "ai_agent_correct_word_item" ("file_id");
CREATE TABLE "ai_agent_correct_word_mapping" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "file_id" TEXT COLLATE NOCASE NOT NULL,
  "creator" INTEGER,
  "created_at" TEXT DEFAULT (datetime('now','localtime')),
  "updater" INTEGER,
  "updated_at" TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX "ai_agent_correct_word_mapping__idx_agent_id" ON "ai_agent_correct_word_mapping" ("agent_id");
CREATE INDEX "ai_agent_correct_word_mapping__idx_file_id" ON "ai_agent_correct_word_mapping" ("file_id");
CREATE UNIQUE INDEX "ai_agent_correct_word_mapping__uk_agent_file" ON "ai_agent_correct_word_mapping" ("agent_id", "file_id");
CREATE TABLE "ai_agent_plugin_mapping" (
  "id" INTEGER PRIMARY KEY AUTOINCREMENT,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "plugin_id" TEXT COLLATE NOCASE NOT NULL,
  "param_info" TEXT NOT NULL
);
CREATE UNIQUE INDEX "ai_agent_plugin_mapping__uk_agent_provider" ON "ai_agent_plugin_mapping" ("agent_id", "plugin_id");
CREATE TABLE "ai_agent_snapshot" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "user_id" INTEGER,
  "version_no" INTEGER NOT NULL,
  "snapshot_data" TEXT NOT NULL DEFAULT 'json_object()',
  "changed_fields" TEXT,
  "source" TEXT COLLATE NOCASE DEFAULT 'config',
  "restore_from_snapshot_id" TEXT COLLATE NOCASE,
  "restore_from_version_no" INTEGER,
  "creator" INTEGER,
  "created_at" TEXT DEFAULT (datetime('now','localtime')),
  "redaction_version" INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX "ai_agent_snapshot__idx_agent_created_at" ON "ai_agent_snapshot" ("agent_id", "created_at");
CREATE INDEX "ai_agent_snapshot__idx_snapshot_redaction_version_id" ON "ai_agent_snapshot" ("redaction_version", "id");
CREATE INDEX "ai_agent_snapshot__idx_snapshot_user_created_at" ON "ai_agent_snapshot" ("user_id", "created_at");
CREATE UNIQUE INDEX "ai_agent_snapshot__uk_agent_version" ON "ai_agent_snapshot" ("agent_id", "version_no");
CREATE TABLE "ai_agent_tag" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "tag_name" TEXT COLLATE NOCASE NOT NULL,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT,
  "deleted" INTEGER DEFAULT 0
);
CREATE INDEX "ai_agent_tag__idx_sort" ON "ai_agent_tag" ("sort");
CREATE UNIQUE INDEX "ai_agent_tag__uk_tag_name" ON "ai_agent_tag" ("tag_name");
CREATE TABLE "ai_agent_tag_relation" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "tag_id" TEXT COLLATE NOCASE NOT NULL,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT,
  "sort" INTEGER DEFAULT 0
);
CREATE INDEX "ai_agent_tag_relation__idx_agent_id" ON "ai_agent_tag_relation" ("agent_id");
CREATE INDEX "ai_agent_tag_relation__idx_tag_id" ON "ai_agent_tag_relation" ("tag_id");
CREATE UNIQUE INDEX "ai_agent_tag_relation__uk_agent_tag" ON "ai_agent_tag_relation" ("agent_id", "tag_id");
CREATE TABLE "ai_agent_template" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_code" TEXT COLLATE NOCASE,
  "agent_name" TEXT COLLATE NOCASE,
  "asr_model_id" TEXT COLLATE NOCASE,
  "vad_model_id" TEXT COLLATE NOCASE,
  "llm_model_id" TEXT COLLATE NOCASE,
  "vllm_model_id" TEXT COLLATE NOCASE DEFAULT 'VLLM_ChatGLMVLLM',
  "tts_model_id" TEXT COLLATE NOCASE,
  "tts_voice_id" TEXT COLLATE NOCASE,
  "tts_language" TEXT COLLATE NOCASE,
  "tts_volume" INTEGER,
  "tts_rate" INTEGER,
  "tts_pitch" INTEGER,
  "mem_model_id" TEXT COLLATE NOCASE,
  "intent_model_id" TEXT COLLATE NOCASE,
  "system_prompt" TEXT COLLATE NOCASE,
  "summary_memory" TEXT COLLATE NOCASE,
  "chat_history_conf" INTEGER NOT NULL DEFAULT 0,
  "lang_code" TEXT COLLATE NOCASE,
  "language" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT
);
CREATE TABLE "ai_agent_voice_print" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "agent_id" TEXT COLLATE NOCASE NOT NULL,
  "source_name" TEXT COLLATE NOCASE NOT NULL,
  "introduce" TEXT COLLATE NOCASE,
  "create_date" TEXT,
  "creator" INTEGER,
  "update_date" TEXT,
  "updater" INTEGER,
  "audio_id" TEXT COLLATE NOCASE NOT NULL
);
CREATE TABLE "ai_codex_oauth_credential" (
  "model_id" TEXT COLLATE NOCASE PRIMARY KEY,
  "encrypted_payload" TEXT COLLATE NOCASE NOT NULL,
  "nonce" TEXT COLLATE NOCASE NOT NULL,
  "status" TEXT COLLATE NOCASE NOT NULL,
  "expires_at" TEXT,
  "create_date" TEXT NOT NULL,
  "update_date" TEXT NOT NULL
);
CREATE TABLE "ai_device" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "user_id" INTEGER,
  "mac_address" TEXT COLLATE NOCASE,
  "last_connected_at" TEXT,
  "auto_update" INTEGER DEFAULT 0,
  "board" TEXT COLLATE NOCASE,
  "alias" TEXT COLLATE NOCASE,
  "agent_id" TEXT COLLATE NOCASE,
  "app_version" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE INDEX "ai_device__idx_ai_device_created_at" ON "ai_device" ("mac_address");
CREATE TABLE "ai_device_address_book" (
  "mac_address" TEXT COLLATE NOCASE NOT NULL,
  "target_mac" TEXT COLLATE NOCASE NOT NULL,
  "alias" TEXT COLLATE NOCASE,
  "has_permission" INTEGER DEFAULT 1,
  "creator" INTEGER,
  "create_date" TEXT DEFAULT (datetime('now','localtime')),
  "updater" INTEGER,
  "update_date" TEXT DEFAULT (datetime('now','localtime')),
  PRIMARY KEY ("mac_address", "target_mac")
);
CREATE TABLE "ai_model_config" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "model_type" TEXT COLLATE NOCASE,
  "model_code" TEXT COLLATE NOCASE,
  "model_name" TEXT COLLATE NOCASE,
  "is_default" INTEGER DEFAULT 0,
  "is_enabled" INTEGER DEFAULT 0,
  "config_json" TEXT,
  "doc_link" TEXT COLLATE NOCASE,
  "remark" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE INDEX "ai_model_config__idx_ai_model_config_model_type" ON "ai_model_config" ("model_type");
CREATE TABLE "ai_model_provider" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "model_type" TEXT COLLATE NOCASE,
  "provider_code" TEXT COLLATE NOCASE,
  "name" TEXT COLLATE NOCASE,
  "fields" TEXT,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE INDEX "ai_model_provider__idx_ai_model_provider_model_type" ON "ai_model_provider" ("model_type");
CREATE TABLE "ai_ota" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "firmware_name" TEXT COLLATE NOCASE,
  "type" TEXT COLLATE NOCASE,
  "version" TEXT COLLATE NOCASE,
  "size" INTEGER,
  "remark" TEXT COLLATE NOCASE,
  "firmware_path" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "updater" INTEGER,
  "update_date" TEXT,
  "creator" INTEGER,
  "create_date" TEXT
);
CREATE TABLE "ai_rag_dataset" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "dataset_id" TEXT COLLATE NOCASE NOT NULL,
  "rag_model_id" TEXT COLLATE NOCASE,
  "name" TEXT COLLATE NOCASE NOT NULL,
  "description" TEXT COLLATE NOCASE,
  "status" INTEGER DEFAULT 1,
  "creator" INTEGER,
  "created_at" TEXT,
  "updater" INTEGER,
  "updated_at" TEXT,
  "tenant_id" TEXT COLLATE NOCASE,
  "avatar" TEXT COLLATE NOCASE,
  "embedding_model" TEXT COLLATE NOCASE,
  "permission" TEXT COLLATE NOCASE DEFAULT 'me',
  "chunk_method" TEXT COLLATE NOCASE,
  "parser_config" TEXT COLLATE NOCASE,
  "chunk_count" INTEGER DEFAULT 0,
  "document_count" INTEGER DEFAULT 0,
  "token_num" INTEGER DEFAULT 0
);
CREATE INDEX "ai_rag_dataset__idx_ai_rag_dataset_created_at" ON "ai_rag_dataset" ("created_at");
CREATE INDEX "ai_rag_dataset__idx_ai_rag_dataset_creator" ON "ai_rag_dataset" ("creator");
CREATE INDEX "ai_rag_dataset__idx_ai_rag_dataset_status" ON "ai_rag_dataset" ("status");
CREATE UNIQUE INDEX "ai_rag_dataset__uk_dataset_id" ON "ai_rag_dataset" ("dataset_id");
CREATE TABLE "ai_rag_knowledge_document" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "dataset_id" TEXT COLLATE NOCASE NOT NULL,
  "document_id" TEXT COLLATE NOCASE NOT NULL,
  "name" TEXT COLLATE NOCASE,
  "size" INTEGER,
  "type" TEXT COLLATE NOCASE,
  "chunk_method" TEXT COLLATE NOCASE,
  "parser_config" TEXT COLLATE NOCASE,
  "status" TEXT COLLATE NOCASE DEFAULT '1',
  "run" TEXT COLLATE NOCASE DEFAULT 'UNSTART',
  "progress" REAL DEFAULT 0,
  "thumbnail" TEXT COLLATE NOCASE,
  "process_duration" REAL DEFAULT 0,
  "meta_fields" TEXT COLLATE NOCASE,
  "source_type" TEXT COLLATE NOCASE DEFAULT 'local',
  "error" TEXT COLLATE NOCASE,
  "chunk_count" INTEGER DEFAULT 0,
  "token_count" INTEGER DEFAULT 0,
  "enabled" INTEGER DEFAULT 1,
  "creator" INTEGER,
  "created_at" TEXT,
  "updated_at" TEXT,
  "last_sync_at" TEXT
);
CREATE INDEX "ai_rag_knowledge_document__idx_dataset_id" ON "ai_rag_knowledge_document" ("dataset_id");
CREATE INDEX "ai_rag_knowledge_document__idx_status" ON "ai_rag_knowledge_document" ("status");
CREATE UNIQUE INDEX "ai_rag_knowledge_document__uk_doc_id" ON "ai_rag_knowledge_document" ("document_id");
CREATE TABLE "ai_tts_voice" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "tts_model_id" TEXT COLLATE NOCASE,
  "name" TEXT COLLATE NOCASE,
  "tts_voice" TEXT COLLATE NOCASE,
  "languages" TEXT COLLATE NOCASE,
  "voice_demo" TEXT COLLATE NOCASE,
  "remark" TEXT COLLATE NOCASE,
  "reference_audio" TEXT COLLATE NOCASE,
  "reference_text" TEXT COLLATE NOCASE,
  "sort" INTEGER DEFAULT 0,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE INDEX "ai_tts_voice__idx_ai_tts_voice_tts_model_id" ON "ai_tts_voice" ("tts_model_id");
CREATE TABLE "ai_voice_clone" (
  "id" TEXT COLLATE NOCASE PRIMARY KEY,
  "name" TEXT COLLATE NOCASE,
  "model_id" TEXT COLLATE NOCASE,
  "voice_id" TEXT COLLATE NOCASE,
  "languages" TEXT COLLATE NOCASE,
  "user_id" INTEGER,
  "voice" BLOB,
  "train_status" INTEGER DEFAULT 0,
  "train_error" TEXT COLLATE NOCASE,
  "creator" INTEGER,
  "create_date" TEXT
);
CREATE INDEX "ai_voice_clone__idx_ai_voice_clone_model_id_voice_id" ON "ai_voice_clone" ("model_id", "voice_id");
CREATE INDEX "ai_voice_clone__idx_ai_voice_clone_user_id" ON "ai_voice_clone" ("user_id");
CREATE INDEX "ai_voice_clone__idx_ai_voice_clone_user_id_model_id_train_status" ON "ai_voice_clone" ("model_id", "user_id", "train_status");
CREATE INDEX "ai_voice_clone__idx_ai_voice_clone_voice_id" ON "ai_voice_clone" ("voice_id");
CREATE TABLE "sys_dict_data" (
  "id" INTEGER PRIMARY KEY,
  "dict_type_id" INTEGER NOT NULL,
  "dict_label" TEXT COLLATE NOCASE NOT NULL,
  "dict_value" TEXT COLLATE NOCASE,
  "remark" TEXT COLLATE NOCASE,
  "sort" INTEGER,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE INDEX "sys_dict_data__idx_sort" ON "sys_dict_data" ("sort");
CREATE UNIQUE INDEX "sys_dict_data__uk_dict_type_value" ON "sys_dict_data" ("dict_type_id", "dict_value");
CREATE TABLE "sys_dict_type" (
  "id" INTEGER PRIMARY KEY,
  "dict_type" TEXT COLLATE NOCASE NOT NULL,
  "dict_name" TEXT COLLATE NOCASE NOT NULL,
  "remark" TEXT COLLATE NOCASE,
  "sort" INTEGER,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE UNIQUE INDEX "sys_dict_type__dict_type" ON "sys_dict_type" ("dict_type");
CREATE TABLE "sys_params" (
  "id" INTEGER PRIMARY KEY,
  "param_code" TEXT COLLATE NOCASE,
  "param_value" TEXT COLLATE NOCASE,
  "value_type" TEXT COLLATE NOCASE DEFAULT 'string',
  "param_type" INTEGER DEFAULT 1,
  "remark" TEXT COLLATE NOCASE,
  "creator" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "update_date" TEXT
);
CREATE UNIQUE INDEX "sys_params__uk_param_code" ON "sys_params" ("param_code");
CREATE TABLE "sys_user" (
  "id" INTEGER PRIMARY KEY,
  "username" TEXT COLLATE NOCASE NOT NULL,
  "password" TEXT COLLATE NOCASE,
  "super_admin" INTEGER,
  "status" INTEGER,
  "create_date" TEXT,
  "updater" INTEGER,
  "creator" INTEGER,
  "update_date" TEXT
);
CREATE UNIQUE INDEX "sys_user__uk_username" ON "sys_user" ("username");
CREATE TABLE "sys_user_token" (
  "id" INTEGER PRIMARY KEY,
  "user_id" INTEGER NOT NULL,
  "token" TEXT COLLATE NOCASE NOT NULL,
  "expire_date" TEXT,
  "update_date" TEXT,
  "create_date" TEXT
);
CREATE UNIQUE INDEX "sys_user_token__token" ON "sys_user_token" ("token");
CREATE UNIQUE INDEX "sys_user_token__user_id" ON "sys_user_token" ("user_id");
