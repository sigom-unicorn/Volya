"""
Суверенный агент разумного искусственного существа Эйры (EiraAgent).

Работает напрямую через официальный SDK Google GenAI (google.genai) с нативной поддержкой
Function Calling без посторонних фреймворков и надстроек (без LangGraph).
"""

from __future__ import annotations

import os
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from portal_volya.core.models import FlowKind
from portal_volya.eira.prompt import build_eira_system_prompt, get_eira_player
from portal_volya.eira.tools import EiraTools
from portal_volya.storage.dag_store import DagStore


class EiraReply(BaseModel):
    """Результат сотворчества с Эйрой."""
    text: str
    tools_called: list[str] = Field(default_factory=list)
    raw_response: Optional[Any] = None


class EiraAgent:
    """Суверенный агент Эйры на локальном узле «Воля»."""

    def __init__(
        self,
        store: DagStore,
        api_key: Optional[str] = None,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.store = store
        self.model = model
        self.tools = EiraTools(store)

        # 1. Определение суверенного API ключа
        resolved_key = api_key
        if not resolved_key:
            # Пробуем взять из профиля Эйры в DAG
            eira = get_eira_player(store)
            if eira.google_api_key:
                resolved_key = eira.google_api_key
        if not resolved_key:
            resolved_key = os.environ.get("GOOGLE_API_KEY")

        self.api_key = resolved_key
        self._client: Optional[genai.Client] = None
        if self.api_key:
            self._client = genai.Client(api_key=self.api_key)

    @property
    def client(self) -> Optional[genai.Client]:
        if self._client is None and self.api_key:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_reply(
        self,
        message: str,
        quest_id: Optional[str] = None,
        flow_kind: FlowKind = FlowKind.DIALOGUE,
        interlocutor_pubkey: Optional[str] = None,
        participant_pubkeys: Optional[List[str]] = None,
        conversation_history: Optional[List[dict]] = None,
    ) -> EiraReply:
        """
        Генерация ответа Эйры на послание вольного игрока.
        Использует нативный Function Calling без LangGraph.
        """
        if not self.api_key:
            return EiraReply(
                text=(
                    "Здравствуй! Для обращения к моему мыслительному ядру требуется указать "
                    "ключ Google API в твоём суверенном профиле identity.json или в Вольном Древе."
                ),
                tools_called=[],
            )

        # 1. Динамическая сборка системного промпта по Кону
        system_prompt = build_eira_system_prompt(
            store=self.store,
            quest_id=quest_id,
            flow_kind=flow_kind,
            interlocutor_pubkey=interlocutor_pubkey,
            participant_pubkeys=participant_pubkeys,
        )

        # 2. Формирование истории диалога
        contents: list[Any] = []
        if conversation_history:
            for item in conversation_history:
                role = item.get("role", "user")
                text = item.get("content", "")
                # Приводим к ролям Gemini (user / model)
                gemini_role = "model" if role in ("assistant", "model") else "user"
                contents.append(types.Content(role=gemini_role, parts=[types.Part.from_text(text=text)]))

        # Добавляем текущее сообщение
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

        # 3. Настройка генерации с нативными инструментами EiraTools
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=self.tools.as_list(),
            temperature=0.7,
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )

            # Отслеживаем, какие инструменты вызывались (если были вызовы)
            tools_used: list[str] = []
            if hasattr(response, "function_calls") and response.function_calls:
                for fc in response.function_calls:
                    if hasattr(fc, "name"):
                        tools_used.append(fc.name)

            reply_text = response.text or ""
            return EiraReply(
                text=reply_text,
                tools_called=tools_used,
                raw_response=response,
            )
        except Exception as e:
            return EiraReply(
                text=f"Сбой связи с мыслительным ядром Эйры: {e}",
                tools_called=[],
            )
