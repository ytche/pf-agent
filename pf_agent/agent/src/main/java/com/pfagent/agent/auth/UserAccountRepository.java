package com.pfagent.agent.auth;

import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

/**
 * user_account 仓库（SP7 T2；F-023 增加按角色查询 / 角色行锁）
 *
 * username 入库前已由 AuthService 归一（去首尾空白 + 小写），此处按精确值查询即可。
 */
public interface UserAccountRepository extends JpaRepository<UserAccount, Long> {

    Optional<UserAccount> findByUsername(String username);

    /** 按角色查询（F-023：admin 列表） */
    List<UserAccount> findByRole(String role);

    /** 统计某角色账号数（F-023：并发测试/辅助统计；自保护判定改用 {@link #lockByRoleOrderedById}） */
    long countByRole(String role);

    /**
     * 以悲观写锁（{@code SELECT ... FOR UPDATE}）按 id 升序取出某角色的全部账号（F-023）。
     *
     * 用于「不得删除/降级最后一个 admin」的原子判定：并发事务在此串行化，先到者持锁，
     * 后到者阻塞至其提交，再重新读取（READ COMMITTED 下已提交的删除/角色变更可见），
     * 从而拿到真实的剩余管理员数。按 id 升序取锁保证多事务加锁顺序一致，避免死锁。
     */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select u from UserAccount u where u.role = :role order by u.id asc")
    List<UserAccount> lockByRoleOrderedById(@Param("role") String role);
}

