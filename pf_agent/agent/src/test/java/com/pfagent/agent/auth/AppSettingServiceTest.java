package com.pfagent.agent.auth;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.test.util.ReflectionTestUtils;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * AppSettingService 集成测试（F-023，@DataJpaTest + H2 内嵌库）
 *
 * 锁定注册开关配置的读写与缺行回退语义：配置在 app_setting 表（实体映射驱动建表），
 * 缺行时回退 yml 默认值；写开关后落库并可回读。
 */
@DataJpaTest(properties = {"spring.flyway.enabled=false", "spring.jpa.hibernate.ddl-auto=create-drop"})
class AppSettingServiceTest {

    @Autowired
    private AppSettingRepository appSettingRepository;

    private AppSettingService appSettingService;

    @BeforeEach
    void setUp() {
        appSettingService = new AppSettingService();
        ReflectionTestUtils.setField(appSettingService, "appSettingRepository", appSettingRepository);
        ReflectionTestUtils.setField(appSettingService, "registrationEnabledDefault", true);
    }

    /** 缺行时回退配置默认值（这里是 true） */
    @Test
    void registrationEnabledFallsBackToDefaultWhenRowMissing() {
        assertThat(appSettingRepository.count()).isZero();
        assertThat(appSettingService.isRegistrationEnabled()).isTrue();
    }

    /** 默认值可配置：默认 false 时缺行回退 false */
    @Test
    void registrationDefaultValueRespected() {
        ReflectionTestUtils.setField(appSettingService, "registrationEnabledDefault", false);
        assertThat(appSettingService.isRegistrationEnabled()).isFalse();
    }

    /** 写入开关落库并可回读（关闭 → 关；再改回开启） */
    @Test
    void setRegistrationEnabledPersistsAndReadsBack() {
        appSettingService.setRegistrationEnabled(false);
        assertThat(appSettingService.isRegistrationEnabled()).isFalse();
        assertThat(appSettingService.getValue(AppSettingService.KEY_REGISTRATION_ENABLED))
                .contains("false");

        appSettingService.setRegistrationEnabled(true);
        assertThat(appSettingService.isRegistrationEnabled()).isTrue();
        assertThat(appSettingRepository.count()).isEqualTo(1);
    }

    /** 缺行时（种子被删）默认值兜底，不被 DB 的空结果误判 */
    @Test
    void missingRowDoesNotThrow() {
        assertThat(appSettingService.getValue("nope")).isEmpty();
    }

    /** 通用读写：put 新键则插入、已存在则更新；allSettings 返回快照 */
    @Test
    void putInsertsThenUpdatesAndAllSettingsSnapshots() {
        appSettingService.put("foo", "1");
        appSettingService.put("foo", "2");

        assertThat(appSettingService.getValue("foo")).contains("2");
        assertThat(appSettingService.allSettings()).containsEntry("foo", "2");
    }

    /** 非法入参拒绝：空键 / null 值 */
    @Test
    void putRejectsBlankKeyAndNullValue() {
        assertThatThrownBy(() -> appSettingService.put(" ", "x"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> appSettingService.put("k", null))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
