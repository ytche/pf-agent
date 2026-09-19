package com.pfagent.agent.auth;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * user_account 仓库（SP7 T2）
 *
 * username 入库前已由 AuthService 归一（去首尾空白 + 小写），此处按精确值查询即可。
 */
public interface UserAccountRepository extends JpaRepository<UserAccount, Long> {

    Optional<UserAccount> findByUsername(String username);
}
