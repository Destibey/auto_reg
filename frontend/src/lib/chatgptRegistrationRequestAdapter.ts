import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
  CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP,
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
  type ChatGPTRegistrationMode,
} from '@/lib/chatgptRegistrationMode'

type RegistrationExtra = Record<string, unknown>

export interface ChatGPTRegistrationRequestAdapter {
  readonly mode: ChatGPTRegistrationMode
  extendExtra(extra: RegistrationExtra): RegistrationExtra
}

function buildSignupOnlyExtra(
  extra: RegistrationExtra,
  mode: ChatGPTRegistrationMode,
): RegistrationExtra {
  return {
    ...extra,
    chatgpt_registration_mode: mode,
    chatgpt_has_refresh_token_solution: false,
    chatgpt_manual_enable_token_callback: false,
    cpa_api_url: '',
    cpa_api_key: '',
    sub2api_api_url: '',
    sub2api_api_key: '',
    sub2api_group_ids: '',
    codex_proxy_url: '',
    codex_proxy_key: '',
    team_manager_url: '',
    team_manager_key: '',
  }
}

class RefreshTokenChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return buildSignupOnlyExtra(extra, this.mode)
  }
}

class AccessTokenOnlyChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return buildSignupOnlyExtra(extra, this.mode)
  }
}

class BrowserManualHandoffChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return {
      ...buildSignupOnlyExtra(extra, this.mode),
      chatgpt_manual_browser_provider: 'camoufox',
    }
  }
}

class CamoufoxAssistedSignupChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return {
      ...buildSignupOnlyExtra(extra, this.mode),
      chatgpt_manual_browser_provider: 'camoufox',
      chatgpt_assisted_signup: true,
    }
  }
}

export function buildChatGPTRegistrationRequestAdapter(
  platform: string | undefined,
  mode: ChatGPTRegistrationMode,
): ChatGPTRegistrationRequestAdapter | null {
  if (platform !== 'chatgpt') return null

  if (mode === CHATGPT_REGISTRATION_MODE_CAMOUFOX_ASSISTED_SIGNUP) {
    return new CamoufoxAssistedSignupChatGPTRegistrationRequestAdapter()
  }

  if (mode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF) {
    return new BrowserManualHandoffChatGPTRegistrationRequestAdapter()
  }

  if (mode === CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY) {
    return new AccessTokenOnlyChatGPTRegistrationRequestAdapter()
  }

  return new RefreshTokenChatGPTRegistrationRequestAdapter()
}
