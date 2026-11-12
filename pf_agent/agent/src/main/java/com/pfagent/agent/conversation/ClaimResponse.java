package com.pfagent.agent.conversation;

import java.util.List;

/** 认领结果：claimed 本次认领成功，alreadyOwned 幂等重复，rejected 被他人认领或不存在 */
public record ClaimResponse(List<String> claimed, List<String> alreadyOwned, List<String> rejected) {
}
