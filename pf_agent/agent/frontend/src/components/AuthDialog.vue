<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

const emit = defineEmits<{ 'logged-in': [] }>()

const auth = useAuthStore()
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const localError = ref('')

watch(
  () => auth.dialogOpen,
  (open) => {
    if (!open) {
      password.value = ''
      confirmPassword.value = ''
      localError.value = ''
    }
  },
)

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && auth.dialogOpen) auth.closeDialog()
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown))

async function submit(): Promise<void> {
  localError.value = ''
  const name = username.value.trim()
  if (!name || !password.value) {
    localError.value = '请输入用户名和密码'
    return
  }
  if (auth.mode === 'register' && password.value !== confirmPassword.value) {
    localError.value = '两次输入的密码不一致'
    return
  }
  const ok =
    auth.mode === 'login'
      ? await auth.login(name, password.value)
      : await auth.register(name, password.value)
  if (!ok) return
  username.value = ''
  password.value = ''
  confirmPassword.value = ''
  emit('logged-in')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="auth.dialogOpen" class="modal-root">
      <div class="modal-mask" @click="auth.closeDialog()"></div>
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="auth-title">
        <h2 id="auth-title">{{ auth.mode === 'login' ? '登录' : '注册' }}</h2>
        <form @submit.prevent="submit">
          <label class="field">
            <span>用户名</span>
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="3～64 位字母 / 数字 / 下划线 / 中文"
            />
          </label>
          <label class="field">
            <span>密码</span>
            <input
              v-model="password"
              type="password"
              :autocomplete="auth.mode === 'login' ? 'current-password' : 'new-password'"
              placeholder="至少 8 位"
            />
          </label>
          <label v-if="auth.mode === 'register'" class="field">
            <span>确认密码</span>
            <input v-model="confirmPassword" type="password" autocomplete="new-password" placeholder="再次输入密码" />
          </label>

          <p v-if="localError || auth.error" class="form-error" role="alert">{{ localError || auth.error }}</p>
          <p v-if="auth.mode === 'register' && !auth.registrationEnabled" class="form-hint">
            当前未开放注册，请联系管理员。
          </p>

          <div class="modal-actions">
            <button
              class="primary"
              type="submit"
              :disabled="auth.busy || (auth.mode === 'register' && !auth.registrationEnabled)"
            >
              {{ auth.busy ? '请稍候…' : auth.mode === 'login' ? '登录' : '注册并登录' }}
            </button>
            <button class="ghost" type="button" @click="auth.closeDialog()">取消</button>
          </div>

          <div class="modal-links">
            <button class="link" type="button" @click="auth.switchMode()">
              {{ auth.mode === 'login' ? '没有账号？注册' : '已有账号？登录' }}
            </button>
            <span class="form-hint">忘记密码请联系管理员重置</span>
          </div>
        </form>
      </section>
    </div>
  </Teleport>
</template>
