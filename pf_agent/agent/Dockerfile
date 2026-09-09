# syntax=docker/dockerfile:1
# PF Agent 运行镜像（multi-stage：Maven 构建 → JRE 运行）
#
# 基线说明：
# - 编译/运行均用 eclipse-temurin 17，对齐 pom <java.version>17</java.version>
#   （SP6 方案 D5 草案写 21；17-jre 更小且与编译目标一致，运行行为等价）。
# - 镜像只含应用 jar，不含向量库/数据：chunks 与 vector_store 走卷挂载
#   （见仓库根 docker-compose.yml 与 docs/DEPLOYMENT.md「数据目录速查」）。
# - 构建期跳过测试编译/执行（CI 的 agent-ci.yml 单独跑 mvn test；此处只打包）。

# ---- 构建阶段 ----
FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /build
# 先只 COPY pom 拉依赖，利用层缓存；源文件变动不触发全量重下
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -Dmaven.test.skip=true package

# ---- 运行阶段 ----
FROM eclipse-temurin:17-jre
WORKDIR /app
# 非 root 运行。user.home = /home/appuser → 应用把向量库/JSONL 写到
# ~/.pf_agent/ 即 /home/appuser/.pf_agent/（compose 卷挂 ./data 到此路径持久化）
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
COPY --from=build /build/target/pf-agent-0.1.0-SNAPSHOT.jar /app/pf-agent.jar
USER appuser
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/pf-agent.jar"]
