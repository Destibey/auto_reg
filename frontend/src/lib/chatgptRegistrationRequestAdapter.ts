import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF,
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
  type ChatGPTRegistrationMode,
} from '@/lib/chatgptRegistrationMode'
import { parseBooleanConfigValue } from '@/lib/configValueParsers'

type RegistrationExtra = Record<string, unknown>

export interface ChatGPTRegistrationRequestAdapter {
  readonly mode: ChatGPTRegistrationMode
  extendExtra(extra: RegistrationExtra): RegistrationExtra
}

class RefreshTokenChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return {
      ...extra,
      chatgpt_registration_mode: this.mode,
      chatgpt_has_refresh_token_solution: true,
    }
  }
}

class AccessTokenOnlyChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return {
      ...extra,
      chatgpt_registration_mode: this.mode,
      chatgpt_has_refresh_token_solution: false,
    }
  }
}

class BrowserManualHandoffChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    const enableTokenCallback = parseBooleanConfigValue(
      extra.chatgpt_manual_enable_token_callback,
    )

    return {
      ...extra,
      chatgpt_registration_mode: this.mode,
      chatgpt_has_refresh_token_solution: enableTokenCallback,
      chatgpt_manual_browser_provider: 'camoufox',
      ...(enableTokenCallback
        ? {}
        : {
            cpa_api_url: '',
            cpa_api_key: '',
            sub2api_api_url: '',
            sub2api_api_key: '',
            sub2api_group_ids: '',
            codex_proxy_url: '',
            codex_proxy_key: '',
            team_manager_url: '',
            team_manager_key: '',
          }),
    }
  }
}

export function buildChatGPTRegistrationRequestAdapter(
  platform: string | undefined,
  mode: ChatGPTRegistrationMode,
): ChatGPTRegistrationRequestAdapter | null {
  if (platform !== 'chatgpt') return null

  if (mode === CHATGPT_REGISTRATION_MODE_BROWSER_MANUAL_HANDOFF) {
    return new BrowserManualHandoffChatGPTRegistrationRequestAdapter()
  }

  if (mode === CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY) {
    return new AccessTokenOnlyChatGPTRegistrationRequestAdapter()
  }

  return new RefreshTokenChatGPTRegistrationRequestAdapter()
}
