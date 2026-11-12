package com.pfagent.agent.conversation;

/** 重新生成最后一轮；expectedLastSeq 为读取时的最后助手消息 seq（终端条件） */
public record RegenerateRequest(Integer expectedLastSeq) {
}
