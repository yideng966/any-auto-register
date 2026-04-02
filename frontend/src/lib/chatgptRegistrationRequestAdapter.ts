import {
  CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY,
  CHATGPT_REGISTRATION_MODE_HAIGE,
  CHATGPT_REGISTRATION_MODE_REFRESH_TOKEN,
  type ChatGPTRegistrationMode,
} from '@/lib/chatgptRegistrationMode'

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

class HaigeChatGPTRegistrationRequestAdapter
  implements ChatGPTRegistrationRequestAdapter
{
  readonly mode = CHATGPT_REGISTRATION_MODE_HAIGE

  extendExtra(extra: RegistrationExtra): RegistrationExtra {
    return {
      ...extra,
      chatgpt_registration_mode: this.mode,
      chatgpt_has_refresh_token_solution: true,
    }
  }
}

export function buildChatGPTRegistrationRequestAdapter(
  platform: string | undefined,
  mode: ChatGPTRegistrationMode,
): ChatGPTRegistrationRequestAdapter | null {
  if (platform !== 'chatgpt') return null

  if (mode === CHATGPT_REGISTRATION_MODE_ACCESS_TOKEN_ONLY) {
    return new AccessTokenOnlyChatGPTRegistrationRequestAdapter()
  }
  if (mode === CHATGPT_REGISTRATION_MODE_HAIGE) {
    return new HaigeChatGPTRegistrationRequestAdapter()
  }

  return new RefreshTokenChatGPTRegistrationRequestAdapter()
}
