package com.pfagent.agent.auth;

import com.pfagent.agent.config.AuthProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AuthController 注册开关测试（F-023）
 *
 * 锁定注册入口可经 app_setting 开关关闭：
 *  - 开关关闭：POST /api/auth/register 抛 RegistrationClosedException（→ 403 registration_closed），
 *    且不触达 AuthService（连用户表都不查）
 *  - 开关开启：照常注册
 *  - GET /api/auth/status 暴露 registrationEnabled（前端据此隐藏注册入口）
 *  - 无配置表（memory 模式）时回退 yml 默认值
 */
@ExtendWith(MockitoExtension.class)
class AuthControllerRegistrationTest {

    @Mock
    private AuthProperties authProperties;

    @Mock
    private JwtService jwtService;

    @Mock
    private ObjectProvider<AuthService> authServiceProvider;

    @Mock
    private ObjectProvider<AppSettingService> appSettingServiceProvider;

    @Mock
    private AppSettingService appSettingService;

    @Mock
    private AuthService authService;

    @InjectMocks
    private AuthController controller;

    /** 开关关闭：注册被拒且不触达 AuthService */
    @Test
    void registerRejectedWhenSwitchOff() {
        when(appSettingServiceProvider.getIfAvailable()).thenReturn(appSettingService);
        when(appSettingService.isRegistrationEnabled()).thenReturn(false);

        assertThatThrownBy(() -> controller.register(new AuthController.AuthBody("alice", "password123")))
                .isInstanceOf(RegistrationClosedException.class);

        verify(authServiceProvider, never()).getIfAvailable();
    }

    /** 开关开启：注册照常委派 AuthService */
    @Test
    void registerAllowedWhenSwitchOn() {
        when(appSettingServiceProvider.getIfAvailable()).thenReturn(appSettingService);
        when(appSettingService.isRegistrationEnabled()).thenReturn(true);
        when(authServiceProvider.getIfAvailable()).thenReturn(authService);
        AuthService.AuthResult result = new AuthService.AuthResult("jwt-1", 7L, "alice", "alice");
        when(authService.register("alice", "password123")).thenReturn(result);

        ResponseEntity<?> resp = controller.register(new AuthController.AuthBody("alice", "password123"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isSameAs(result);
    }

    /** status 暴露 registrationEnabled：开关关闭时前端可隐藏注册入口 */
    @Test
    void statusExposesRegistrationEnabledOff() {
        when(authProperties.isAuthEnabled()).thenReturn(true);
        when(appSettingServiceProvider.getIfAvailable()).thenReturn(appSettingService);
        when(appSettingService.isRegistrationEnabled()).thenReturn(false);

        assertThat(controller.status())
                .containsEntry("enabled", true)
                .containsEntry("registrationEnabled", false);
    }

    /** 无配置表（memory 模式）：registrationEnabled 回退 yml 默认值 */
    @Test
    void statusFallsBackToConfiguredDefaultWithoutSettingService() {
        when(authProperties.isAuthEnabled()).thenReturn(false);
        when(appSettingServiceProvider.getIfAvailable()).thenReturn(null);
        ReflectionTestUtils.setField(controller, "registrationEnabledDefault", true);

        assertThat(controller.status())
                .containsEntry("enabled", false)
                .containsEntry("registrationEnabled", true);
    }

    /** RegistrationClosedException → 403 registration_closed（错误体统一 {error,...}） */
    @Test
    @SuppressWarnings("unchecked")
    void registrationClosedHandlerMapsTo403() {
        ResponseEntity<?> resp = controller.handleRegistrationClosed(new RegistrationClosedException());

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat((Map<String, Object>) resp.getBody()).containsEntry("error", "registration_closed");
    }
}
