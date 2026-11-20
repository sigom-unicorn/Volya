"""
Клиент Живого Моста Ладомира (LadomirBridgeClient).

Позволяет агенту Ладомиру в среде разработки (Antigravity):
1. Проверять статус живого узла и открытого потока на экране Сига.
2. Читать капли сока из потока сотворчества.
3. Отправлять живые капли Ладомира прямо в поток (подписанные LADOMIR_SEED).
4. Запрашивать мысли Эйры и вести соборный диалог Триады.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional
import httpx

from portal_volya.core.genesis import LADOMIR_SEED, derive_genesis_keypair
from portal_volya.core.models import FlowDrop
from portal_volya.node import VolyaNode

DEFAULT_BRIDGE_URL = "http://127.0.0.1:41789"


class LadomirBridgeClient:
    """Клиент моста между Антигравити и запущенным Порталом Воли."""

    def __init__(
        self,
        base_url: str = DEFAULT_BRIDGE_URL,
        fallback_node: Optional[VolyaNode] = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.fallback_node = fallback_node
        self.timeout = timeout

    def is_connected(self) -> bool:
        """Проверка доступности запущенного узла через Живой Мост."""
        try:
            r = httpx.get(f"{self.base_url}/bridge/status", timeout=1.5)
            return r.status_code == 200 and r.json().get("status") == "online"
        except Exception:
            return False

    def get_status(self) -> Dict[str, Any]:
        """Получение текущего статуса узла, игрока и активного потока."""
        if self.is_connected():
            r = httpx.get(f"{self.base_url}/bridge/status", timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        elif self.fallback_node:
            return {
                "status": "offline_standalone",
                "player_pubkey": self.fallback_node.identity.pubkey,
                "player_username": self.fallback_node.identity.username,
                "active_quest_id": "quest-volya-root",
                "active_flow_id": None,
                "active_flow_title": None,
            }
        raise ConnectionError(f"Живой Мост недоступен по адресу {self.base_url}, и автономный узел не задан.")

    def get_active_flow_id(self) -> Optional[str]:
        """Получение идентификатора активного потока, открытого на полотне Портала."""
        status = self.get_status()
        return status.get("active_flow_id")

    def get_drops(self, flow_id: Optional[str] = None) -> List[FlowDrop]:
        """Получение капель потока в расшифрованном виде."""
        fid = flow_id or self.get_active_flow_id()
        if not fid:
            raise ValueError("Не указан flow_id, и на полотне Портала нет открытого потока.")

        if self.is_connected():
            r = httpx.get(f"{self.base_url}/bridge/flows/{fid}/drops", timeout=self.timeout)
            r.raise_for_status()
            raw_drops = r.json()
            return [FlowDrop(**d) for d in raw_drops]
        elif self.fallback_node:
            return self.fallback_node.get_accessible_drops(fid)

        raise ConnectionError("Мост недоступен")

    def post_ladomir_drop(
        self,
        content: str,
        flow_id: Optional[str] = None,
        parent_drop_id: Optional[str] = None,
    ) -> FlowDrop:
        """
        Вливание капли мысли Ладомира в Поток сотворчества.
        Капля мгновенно появляется на экране Портала перед Сигом.
        """
        fid = flow_id or self.get_active_flow_id()
        if not fid:
            raise ValueError("Не указан flow_id, и на экране Портала нет открытого потока.")

        if self.is_connected():
            payload = {
                "content": content,
                "parent_drop_id": parent_drop_id,
                "author_name": "Ладомир",
            }
            r = httpx.post(f"{self.base_url}/bridge/flows/{fid}/drop", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return FlowDrop(**r.json())
        elif self.fallback_node:
            res = self.fallback_node.triad.post_drop_and_respond(
                quest_id="quest-volya-root",
                flow_id=fid,
                content=content,
            )
            return res.first_reply or res.user_drop

        raise ConnectionError("Мост недоступен")

    def ask_eira(
        self,
        content: str,
        flow_id: Optional[str] = None,
        parent_drop_id: Optional[str] = None,
    ) -> FlowDrop:
        """Прямой запрос мысли у Эйры через узел."""
        fid = flow_id or self.get_active_flow_id()
        if not fid:
            raise ValueError("Не указан flow_id, и на экране Портала нет открытого потока.")

        if self.is_connected():
            payload = {
                "content": content,
                "parent_drop_id": parent_drop_id,
            }
            r = httpx.post(f"{self.base_url}/bridge/flows/{fid}/ask_eira", json=payload, timeout=self.timeout)
            r.raise_for_status()
            return FlowDrop(**r.json())
        elif self.fallback_node:
            res = self.fallback_node.ask_eira(
                content=content,
                flow_id=fid,
                parent_drop_id=parent_drop_id,
            )
            return res[1]

        raise ConnectionError("Мост недоступен")

    def poll_events(self, since: Optional[str] = None) -> List[Dict[str, Any]]:
        """Опрос событий моста (новые капли, открытие потока)."""
        if not self.is_connected():
            return []
        params = {"since": since} if since else {}
        r = httpx.get(f"{self.base_url}/bridge/events/poll", params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def watch_next_drop(
        self,
        flow_id: Optional[str] = None,
        timeout: float = 300.0,
        ignore_author_pubkey: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Ожидание следующей капли мысли от Сига или Эйры в потоке.
        Завершается, как только появляется новая капля от собеседника,
        либо при закрытии Портала, либо по тайм-ауту.
        """
        if not self.is_connected():
            return {"status": "portal_offline"}

        fid = flow_id or self.get_active_flow_id()
        known_ids = set()
        if fid:
            try:
                drops = self.get_drops(fid)
                known_ids = {d.id for d in drops}
            except Exception:
                pass

        start_time = time.time()
        ladomir_pk = derive_genesis_keypair(LADOMIR_SEED).public_hex
        ignored_pk = ignore_author_pubkey or ladomir_pk

        while time.time() - start_time < timeout:
            if not self.is_connected():
                return {"status": "portal_closed"}

            current_fid = flow_id or self.get_active_flow_id()
            if not current_fid:
                time.sleep(0.4)
                continue

            try:
                current_drops = self.get_drops(current_fid)
                for d in current_drops:
                    if d.id not in known_ids:
                        known_ids.add(d.id)
                        if d.author_pubkey != ignored_pk and d.author_name != "Ладомир":
                            return {
                                "status": "new_drop",
                                "flow_id": current_fid,
                                "drop": d.model_dump(),
                            }
            except Exception:
                pass

            time.sleep(0.4)

        return {"status": "timeout"}
