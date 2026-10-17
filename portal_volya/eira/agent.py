"""
Суверенный агент разумного искусственного существа Эйры (EiraAgent).

Работает напрямую через официальный SDK Google GenAI (google.genai) с нативной поддержкой
Function Calling без посторонних фреймворков и надстроек (без LangGraph).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, List, Optional
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

from portal_volya.core.models import FlowKind
from portal_volya.eira.prompt import build_eira_system_prompt, get_eira_player
from portal_volya.eira.tools import EiraTools

if TYPE_CHECKING:
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
        embedding_model: str = "gemini-embedding-001",
    ) -> None:
        self.store = store
        self.model = model
        self.embedding_model = embedding_model

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

        # Подключаем суверенные инструменты с функцией вычисления эмбеддингов
        self.tools = EiraTools(store=store, embedder=self.embed_text)

    def embed_text(self, text: str) -> list[float]:
        """Вычисление семантического эмбеддинга текста через Google GenAI (gemini-embedding-001)."""
        if not text or not text.strip():
            return []
        if not self.client:
            return []
        try:
            res = self.client.models.embed_content(
                model=self.embedding_model,
                contents=text.strip(),
            )
            if res.embeddings and len(res.embeddings) > 0:
                return [float(x) for x in res.embeddings[0].values]
        except Exception:
            pass
        return []

    @property
    def client(self) -> Optional[genai.Client]:
        if self._client is None and self.api_key:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_reply(
        self,
        message: str,
        quest_id: Optional[str] = None,
        flow_id: Optional[str] = None,
        flow_kind: FlowKind = FlowKind.DIALOGUE,
        interlocutor_pubkey: Optional[str] = None,
        participant_pubkeys: Optional[List[str]] = None,
        flow_summary: Optional[str] = None,
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

        # Вычисление вектора смыслового пространства входящего сообщения
        message_vec = self.embed_text(message)

        # 1. Динамическая сборка системного промпта по Кону с ассоциативным резонансом
        system_prompt = build_eira_system_prompt(
            store=self.store,
            quest_id=quest_id,
            flow_id=flow_id,
            flow_kind=flow_kind,
            interlocutor_pubkey=interlocutor_pubkey,
            participant_pubkeys=participant_pubkeys,
            flow_summary=flow_summary,
            message_embedding=message_vec,
        )

        # 2. Формирование истории диалога (скользящее окно)
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

    def summarize_flow(
        self,
        messages: list[dict],
        previous_summary: Optional[str] = None,
    ) -> str:
        """
        Кристаллизация среза капель диалога в ёмкое смысловое саммари через модель Gemini.
        """
        if not messages:
            return previous_summary or ""

        if not self.api_key or not self.client:
            # Офлайн-фоллбек без вызова API
            lines = [f"{m.get('author_name', m.get('role', 'собеседник'))}: {m.get('content', '')}" for m in messages]
            prefix = f"{previous_summary}\n\n" if previous_summary else ""
            return prefix + "\n".join(lines[:5])

        prompt_lines = [
            "Ты Эйра — мыслящее ядро и Хранительница Вселенной «Воля».",
            "Твоя задача: кристаллизовать память диалога вольных игроков в плотное, ёмкое смысловое саммари.",
            "",
            "Выдели самое главное по Кону и Укладу:",
            "1. Достигнутый Лад, взаимные согласия и договорённости сотворцов.",
            "2. Принятые решения по квесту, затронутые или созданные Ресурсы, Инструменты, Артефакты.",
            "3. Поставленные задачи и векторы дальнейшего созидания.",
            "Пиши кратко, ёмко, без воды и лишнего пафоса, по-братски.",
        ]

        if previous_summary:
            prompt_lines.append(f"\nПредыдущая накопленная память потока:\n«{previous_summary.strip()}»\n")

        prompt_lines.append("\nНовый срез капель диалога для включения в память:")
        for m in messages:
            author = m.get("author_name") or m.get("role", "собеседник")
            content = m.get("content", "")
            prompt_lines.append(f"• {author}: {content}")

        prompt_lines.append("\nСформируй обновлённый кристалл памяти:")
        full_prompt = "\n".join(prompt_lines)

        try:
            res = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(temperature=0.3),
            )
            return (res.text or "").strip()
        except Exception:
            lines = [f"{m.get('author_name', m.get('role', 'собеседник'))}: {m.get('content', '')}" for m in messages]
            prefix = f"{previous_summary}\n\n" if previous_summary else ""
            return prefix + "\n".join(lines[:5])

