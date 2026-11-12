package com.pfagent.agent.auth;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;

/**
 * 应用运行时配置读写（F-023）
 *
 * 配置存 app_setting（Flyway V5，种子行 registration_enabled=true）。读取时若键不存在
 * 则回退到配置默认值（默认值来自 application.yml / 配置种子），保证迁移种子缺失或
 * 新键上线时行为可预期。
 *
 * 只在 jdbc 模式装配（配置在 PG）；memory 模式下调用方经 ObjectProvider 判空降级。
 */
@Service
@ConditionalOnProperty(name = "pf.chat.memory", havingValue = "jdbc")
public class AppSettingService {

    /** 注册入口开关的配置键 */
    public static final String KEY_REGISTRATION_ENABLED = "registration_enabled";

    @Autowired
    private AppSettingRepository appSettingRepository;

    /** 注册开关默认值（app_setting 无该行时的兜底；与 V5 种子、yml 默认一致） */
    @Value("${pf.auth.registration-enabled:true}")
    private boolean registrationEnabledDefault;

    /** 注册入口是否开放（缺行时回退配置默认值） */
    @Transactional(readOnly = true)
    public boolean isRegistrationEnabled() {
        return getValue(KEY_REGISTRATION_ENABLED)
                .map(Boolean::parseBoolean)
                .orElse(registrationEnabledDefault);
    }

    /** 设置注册入口开关（admin 界面调用） */
    @Transactional
    public void setRegistrationEnabled(boolean enabled) {
        put(KEY_REGISTRATION_ENABLED, Boolean.toString(enabled));
    }

    /** 读取配置值（不存在返回空） */
    @Transactional(readOnly = true)
    public Optional<String> getValue(String key) {
        return appSettingRepository.findById(key).map(AppSetting::getValue);
    }

    /** 写入/覆盖配置值（键存在则更新，不存在则插入） */
    @Transactional
    public void put(String key, String value) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("配置键不能为空");
        }
        if (value == null) {
            throw new IllegalArgumentException("配置值不能为空: " + key);
        }
        AppSetting setting = appSettingRepository.findById(key)
                .orElseGet(() -> new AppSetting(key, value, Instant.now()));
        setting.setValue(value);
        setting.setUpdatedAt(Instant.now());
        appSettingRepository.save(setting);
    }

    /** 全量配置快照（admin 展示用） */
    @Transactional(readOnly = true)
    public Map<String, String> allSettings() {
        Map<String, String> snapshot = new LinkedHashMap<>();
        appSettingRepository.findAll().forEach(s -> snapshot.put(s.getKey(), s.getValue()));
        return snapshot;
    }
}
