package com.pfagent.agent.auth;

import org.springframework.data.jpa.repository.JpaRepository;

/**
 * app_setting 仓库（F-023）
 *
 * 配置项为主键，按 key 精确读取/写入；无需自定义方法。
 */
public interface AppSettingRepository extends JpaRepository<AppSetting, String> {
}
