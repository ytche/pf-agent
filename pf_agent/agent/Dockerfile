# syntax=docker/dockerfile:1
# PF Agent 运行镜像（multi-stage：Node 前端构建 → Maven 构建 → JRE 运行）
#
# 基线说明：
# - 编译/运行均用 eclipse-temurin 17，对齐 pom <java.version>17</java.version>
#   （SP6 方案 D5 草案写 21；17-jre 更小且与编译目标一致，运行行为等价）。
# - 前端（Vue 3 + Vite）先构建到 src/main/resources/static/dist，再交给 Maven
#   打包；dist 与 node_modules 不入库（见 .gitignore），镜像内由 Node 阶段生成。
# - 镜像只含应用 jar，不含向量库/数据：chunks 与 vector_store 走卷挂载
#   （见仓库根 docker-compose.yml 与 docs/DEPLOYMENT.md「数据目录速查」）。
# - 构建期跳过测试编译/执行（CI 的 agent-ci.yml 单独跑 npm 与 mvn test；此处只打包）。

# ---- 前端构建阶段 ----
FROM node:22-alpine AS frontend
WORKDIR /build/frontend
# 只 COPY 依赖清单以复用层缓存；lockfile 保证可复现
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# vite.config.ts 的 outDir 为 ../src/main/resources/static/dist
# → 容器内输出 /build/src/main/resources/static/dist
RUN npm run build

# ---- 构建阶段 ----
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
# 先只 COPY pom 拉依赖，利用层缓存；源文件变动不触发全量重下
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
COPY --from=frontend /build/src/main/resources/static/dist ./src/main/resources/static/dist
RUN mvn -q -B -Dmaven.test.skip=true package

# ---- 运行阶段 ----
FROM eclipse-temurin:17-jre
WORKDIR /app
# 非 root 运行。user.home = /home/appuser → 应用把向量库/JSONL 写到
# ~/.pf_agent/ 即 /home/appuser/.pf_agent/（compose 卷挂 ./data 到此路径持久化）
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
COPY --from=build /build/target/pf-agent-*.jar /app/pf-agent.jar
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/pf-agent.jar"]
