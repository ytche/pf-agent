package com.pfagent.agent.admin;

import com.pfagent.agent.auth.AppSettingService;
import com.pfagent.agent.auth.InvalidCredentialsException;
import com.pfagent.agent.auth.UsernameTakenException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * AdminController 单元测试（F-023）
 *
 * 锁定各端点的请求→响应与错误码语义映射（鉴权由 AdminInterceptor 负责，此处只测 controller）：
 *  - 用户 CRUD 委派与状态码（201/200/204）
 *  - 自助改密透传当前管理员（来自 request attribute）
 *  - 注册开关读改
 *  - 错误码：username_taken→409、invalid_credentials→401、not_found→404、
 *    last_admin→409、invalid_request→400、admin_unavailable→503
 */
@ExtendWith(MockitoExtension.class)
class AdminControllerTest {

    @Mock
    private ObjectProvider<AdminService> adminServiceProvider;

    @Mock
    private ObjectProvider<AppSettingService> appSettingServiceProvider;

    @Mock
    private AdminService adminService;

    @Mock
    private AppSettingService appSettingService;

    @InjectMocks
    private AdminController controller;

    private AdminService.UserView view() {
        return new AdminService.UserView(1L, "alice", "alice", "user", Instant.now(), null);
    }

    /** 列表委派 */
    @Test
    void listUsersDelegates() {
        AdminService.UserView v = view();
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);
        when(adminService.listUsers()).thenReturn(List.of(v));

        ResponseEntity<?> resp = controller.listUsers();

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(resp.getBody()).isEqualTo(List.of(v));
    }

    /** 新建用户：201 + 返回视图 */
    @Test
    void createUserReturns201() {
        AdminService.UserView v = view();
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);
        when(adminService.createUser("alice", "password123", "admin")).thenReturn(v);

        ResponseEntity<?> resp = controller.createUser(new AdminController.CreateUserBody("alice", "password123", "admin"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.CREATED);
        assertThat(resp.getBody()).isSameAs(v);
    }

    /** 改角色 / 重置密码 / 删除 委派与状态码 */
    @Test
    void updateRoleResetPasswordDeleteDelegate() {
        AdminService.UserView v = view();
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);
        when(adminService.updateRole(1L, "admin")).thenReturn(v);

        assertThat(controller.updateRole(1L, new AdminController.RoleBody("admin")).getBody()).isSameAs(v);

        ResponseEntity<?> reset = controller.resetPassword(1L, new AdminController.PasswordBody("password123"));
        assertThat(reset.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(adminService).resetPassword(1L, "password123");

        ResponseEntity<?> deleted = controller.deleteUser(1L);
        assertThat(deleted.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(adminService).deleteUser(1L);
    }

    /** 自助改密：把拦截器写入的当前管理员透传给 service */
    @Test
    void changeOwnPasswordPassesAttribute() {
        when(adminServiceProvider.getIfAvailable()).thenReturn(adminService);

        ResponseEntity<?> resp = controller.changeOwnPassword("boss",
                new AdminController.ChangePasswordBody("old-pass-123", "new-pass-123"));

        assertThat(resp.getStatusCode()).isEqualTo(HttpStatus.NO_CONTENT);
        verify(adminService).changeOwnPassword("boss", "old-pass-123", "new-pass-123");
    }

    /** 注册开关读 / 改 */
    @Test
    @SuppressWarnings("unchecked")
    void settingsReadAndUpdateRegistration() {
        when(appSettingServiceProvider.getIfAvailable()).thenReturn(appSettingService);
        when(appSettingService.isRegistrationEnabled()).thenReturn(false);

        ResponseEntity<?> read = controller.settings();
        assertThat(read.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat((Map<String, Object>) read.getBody()).containsEntry("registrationEnabled", false);

        ResponseEntity<?> write = controller.updateRegistration(new AdminController.RegistrationBody(true));
        assertThat((Map<String, Object>) write.getBody()).containsEntry("registrationEnabled", true);
        verify(appSettingService).setRegistrationEnabled(true);
    }

    /** 错误码语义映射 */
    @Test
    @SuppressWarnings("unchecked")
    void exceptionHandlersMapToCodes() {
        assertThat(controller.handleUsernameTaken(new UsernameTakenException("a")).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(error(controller.handleUsernameTaken(new UsernameTakenException("a")))).isEqualTo("username_taken");

        assertThat(controller.handleInvalidCredentials(new InvalidCredentialsException()).getStatusCode())
                .isEqualTo(HttpStatus.UNAUTHORIZED);
        assertThat(error(controller.handleInvalidCredentials(new InvalidCredentialsException())))
                .isEqualTo("invalid_credentials");

        assertThat(controller.handleUserNotFound(new UserNotFoundException(9L)).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(error(controller.handleUserNotFound(new UserNotFoundException(9L)))).isEqualTo("not_found");

        assertThat(controller.handleLastAdmin(new LastAdminException()).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(error(controller.handleLastAdmin(new LastAdminException()))).isEqualTo("last_admin");

        assertThat(controller.handleInvalidRequest(new IllegalArgumentException("弱密码")).getStatusCode())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(error(controller.handleInvalidRequest(new IllegalArgumentException("弱密码"))))
                .isEqualTo("invalid_request");

        assertThat(controller.handleAdminUnavailable(new IllegalStateException("no db")).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(error(controller.handleAdminUnavailable(new IllegalStateException("no db"))))
                .isEqualTo("admin_unavailable");
    }

    /** 数据层缺席：调用端点抛 IllegalStateException（经 @ExceptionHandler 转 503） */
    @Test
    void endpointsFailExplicitlyWithoutService() {
        when(adminServiceProvider.getIfAvailable()).thenReturn(null);

        assertThatThrownBy(() -> controller.listUsers())
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("pf.chat.memory");
    }

    @SuppressWarnings("unchecked")
    private static String error(ResponseEntity<?> resp) {
        return (String) ((Map<String, Object>) resp.getBody()).get("error");
    }
}
