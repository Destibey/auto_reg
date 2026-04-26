export const CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN = 'refresh_token'
export const CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY = 'access_token_only'
export const CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF =
  'browser_manual_handoff'
export const CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP =
  'camoufox_assisted_signup'
export const CHATGPT_REGISTRATION_MODE_STORAGE_KEY = 'chatgpt-registration-mode'

export type ChatGPTRegistrationMode =
  | typeof CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN
  | typeof CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY
  | typeof CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF
  | typeof CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP

export const DEFAULT_CHATGPT_REGISTRATION_MODE: ChatGPTRegistrationMode =
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN

export function normalizeChatGPTRegistrationMode(
  value: unknown,
): ChatGPTRegistrationMode {
  if (value === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF) {
    return CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF
  }
  if (value === CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP) {
    return CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP
  }
  if (value === CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY) {
    return CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY
  }
  return DEFAULT_CHATGPT_REGISTRATION_MODE
}

export function isChatGPTBrowserSignupMode(
  mode: ChatGPTRegistrationMode,
): boolean {
  return (
    mode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF ||
    mode === CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP
  )
}

export function loadChatGPTRegistrationMode(): ChatGPTRegistrationMode {
  if (typeof window === 'undefined') {
    return DEFAULT_CHATGPT_REGISTRATION_MODE
  }

  return normalizeChatGPTRegistrationMode(
    window.localStorage.getItem(CHATGPT_REGISTRATION_MODE_STORAGE_KEY),
  )
}

export function saveChatGPTRegistrationMode(
  mode: ChatGPTRegistrationMode,
): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(CHATGPT_REGISTRATION_MODE_STORAGE_KEY, mode)
}
