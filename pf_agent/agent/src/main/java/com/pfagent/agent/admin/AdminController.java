package com.pfagent.agent.admin;

import com.pfagent.agent.auth.AppSettingService;
import com.pfagent.agent.auth.InvalidCredentialsException;
import com.pfagent.agent.auth.UsernameTakenException;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 管理后台接口（F-023）：用户增删改查 + 注册开关 + 自助改密。
 *
 * 全部路由 {@code /api/admin/**}，由 {@link AdminInterceptor} 统一守卫（auth 开关、
 * 有效 JWT、role=admin），controller 内不再重复鉴权。
 *
 * 端点：
 * - GET    /api/admin/users                    用户列表（不含密码哈希）
 * - POST   /api/admin/users                    新建用户（指定角色）
 * - PUT    /api/admin/users/{id}/role          改角色
 * - PUT    /api/admin/users/{id}/password      重置指定用户密码
 * - DELETE /api/admin/users/{id}               删除用户
 * - POST   /api/admin/me/password              当前管理员自助改密（校验原密码）
 * - GET    /api/admin/settings                 配置快照（当前含 registrationEnabled）
 * - PUT    /api/admin/settings/registration    切换注册入口开关
 *
 * 错误码语义：username_taken→409、invalid_credentials→401、invalid_request→400、
 * not_found→404、last_admin→409（自保护）、admin_unavailable→503（数据层缺席）。
 */
@RestController
@RequestMapping("/api/admin")
public class AdminController {

    @Autowired
    private ObjectProvider<AdminService> adminServiceProvider;

    @Autowired
    private ObjectProvider<AppSettingService> appSettingServiceProvider;

    @GetMapping("/users")
    public ResponseEntity<?> listUsers() {
        return ResponseEntity.ok(requireAdminService().listUsers());
    }

    @PostMapping("/users")
    public ResponseEntity<?> createUser(@RequestBody CreateUserBody body) {
        AdminService.UserView created =
                requireAdminService().createUser(body.username(), body.password(), body.role());
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }

    @PutMapping("/users/{id}/role")
    public ResponseEntity<?> updateRole(@PathVariable Long id, @RequestBody RoleBody body) {
        return ResponseEntity.ok(requireAdminService().updateRole(id, body.role()));
    }

    @PutMapping("/users/{id}/password")
    public ResponseEntity<?> resetPassword(@PathVariable Long id, @RequestBody PasswordBody body) {
        requireAdminService().resetPassword(id, body.password());
        return ResponseEntity.noContent().build();
    }

    @DeleteMapping("/users/{id}")
    public ResponseEntity<?> deleteUser(@PathVariable Long id) {
        requireAdminService().deleteUser(id);
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/me/password")
    public ResponseEntity<?> changeOwnPassword(
            @RequestAttribute(name = AdminInterceptor.ADMIN_USERNAME_ATTRIBUTE, required = false) String adminUsername,
            @RequestBody ChangePasswordBody body) {
        requireAdminService().changeOwnPassword(adminUsername, body.currentPassword(), body.newPassword());
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/settings")
    public ResponseEntity<?> settings() {
        return ResponseEntity.ok(Map.of("registrationEnabled", requireAppSettingService().isRegistrationEnabled()));
    }

    @PutMapping("/settings/registration")
    public ResponseEntity<?> updateRegistration(@RequestBody RegistrationBody body) {
        requireAppSettingService().setRegistrationEnabled(body.enabled());
        return ResponseEntity.ok(Map.of("registrationEnabled", body.enabled()));
    }

    /** UsernameTakenException → 409 username_taken */
    @ExceptionHandler(UsernameTakenException.class)
    public ResponseEntity<?> handleUsernameTaken(UsernameTakenException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "username_taken", "message", ex.getMessage()));
    }

    /** InvalidCredentialsException → 401 invalid_credentials（改密原密码错误） */
    @ExceptionHandler(InvalidCredentialsException.class)
    public ResponseEntity<?> handleInvalidCredentials(InvalidCredentialsException ex) {
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials", "message", ex.getMessage()));
    }

    /** UserNotFoundException → 404 not_found */
    @ExceptionHandler(UserNotFoundException.class)
    public ResponseEntity<?> handleUserNotFound(UserNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(Map.of("error", "not_found", "message", ex.getMessage()));
    }

    /** LastAdminException → 409 last_admin（自保护：不得删/降级最后一个管理员） */
    @ExceptionHandler(LastAdminException.class)
    public ResponseEntity<?> handleLastAdmin(LastAdminException ex) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body(Map.of("error", "last_admin", "message", ex.getMessage()));
    }

    /** 参数校验失败（非法用户名/弱密码/非法角色等）→ 400 invalid_request */
    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<?> handleInvalidRequest(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", "invalid_request", "message", ex.getMessage()));
    }

    /** 数据层缺席（memory 模式误调 admin 接口）→ 503 admin_unavailable */
    @ExceptionHandler(IllegalStateException.class)
    public ResponseEntity<?> handleAdminUnavailable(IllegalStateException ex) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("error", "admin_unavailable", "message", ex.getMessage()));
    }

    private AdminService requireAdminService() {
        AdminService adminService = adminServiceProvider.getIfAvailable();
        if (adminService == null) {
            throw new IllegalStateException(
                    "管理后台不可用：pf.chat.memory=memory 时无用户表，请将 pf.chat.memory 设为 jdbc");
        }
        return adminService;
    }

    private AppSettingService requireAppSettingService() {
        AppSettingService appSettingService = appSettingServiceProvider.getIfAvailable();
        if (appSettingService == null) {
            throw new IllegalStateException(
                    "配置不可用：pf.chat.memory=memory 时无配置表，请将 pf.chat.memory 设为 jdbc");
        }
        return appSettingService;
    }

    /** 新建用户请求体 */
    public record CreateUserBody(String username, String password, String role) {
    }

    /** 改角色请求体 */
    public record RoleBody(String role) {
    }

    /** 重置密码请求体 */
    public record PasswordBody(String password) {
    }

    /** 自助改密请求体 */
    public record ChangePasswordBody(String currentPassword, String newPassword) {
    }

    /** 注册开关请求体 */
    public record RegistrationBody(boolean enabled) {
    }
}
