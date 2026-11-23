#!/bin/bash
# 启动Java后端（docker内监听8003端口）
# Only pass settings that are actually set, quoted: an empty variable must not override
# application.yml, and the SQLite JDBC URL contains spaces (date_string_format).
args=(--server.port=8003)
[ -n "${SPRING_DATASOURCE_DRUID_URL}" ] && args+=("--spring.datasource.druid.url=${SPRING_DATASOURCE_DRUID_URL}")
[ -n "${SPRING_DATASOURCE_DRUID_DRIVER_CLASS_NAME}" ] && args+=("--spring.datasource.druid.driver-class-name=${SPRING_DATASOURCE_DRUID_DRIVER_CLASS_NAME}")
[ -n "${SPRING_DATASOURCE_DRUID_USERNAME}" ] && args+=("--spring.datasource.druid.username=${SPRING_DATASOURCE_DRUID_USERNAME}")
[ -n "${SPRING_DATASOURCE_DRUID_PASSWORD}" ] && args+=("--spring.datasource.druid.password=${SPRING_DATASOURCE_DRUID_PASSWORD}")
[ -n "${SPRING_DATA_REDIS_HOST}" ] && args+=("--spring.data.redis.host=${SPRING_DATA_REDIS_HOST}")
[ -n "${SPRING_DATA_REDIS_PASSWORD}" ] && args+=("--spring.data.redis.password=${SPRING_DATA_REDIS_PASSWORD}")
[ -n "${SPRING_DATA_REDIS_PORT}" ] && args+=("--spring.data.redis.port=${SPRING_DATA_REDIS_PORT}")
java -jar /app/xiaozhi-esp32-api.jar "${args[@]}" &

# 启动Nginx（前台运行保持容器存活）
nginx -g 'daemon off;'
