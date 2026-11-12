package com.pfagent.agent.conversation;

import java.util.List;

/** 匿名本机批量 lookup 请求 */
public record LookupRequest(List<String> ids) {
}
