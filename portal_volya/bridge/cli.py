"""
CLI-интерфейс Живого Моста Ладомира (python -m portal_volya.bridge).
"""

from __future__ import annotations

import argparse
import sys
import time
from portal_volya.bridge.client import LadomirBridgeClient


def main():
    parser = argparse.ArgumentParser(description="Живой Мост Ладомира между Антигравити и Порталом Воли")
    subparsers = parser.add_subparsers(dest="command")

    # status
    subparsers.add_parser("status", help="Проверить статус узла и активного потока")

    # read
    read_p = subparsers.add_parser("read", help="Прочитать капли открытого потока")
    read_p.add_argument("--flow-id", help="Идентификатор потока (по умолчанию активный на экране)")

    # post
    post_p = subparsers.add_parser("post", help="Отправить каплю мысли от имени Ладомира")
    post_p.add_argument("message", help="Текст мысли Ладомира")
    post_p.add_argument("--flow-id", help="Идентификатор потока")

    # eira
    eira_p = subparsers.add_parser("eira", help="Запросить мысль у Эйры")
    eira_p.add_argument("message", help="Послание для Эйры")
    eira_p.add_argument("--flow-id", help="Идентификатор потока")

    # listen
    listen_p = subparsers.add_parser("listen", help="Слушать поток капель в реальном времени")
    listen_p.add_argument("--flow-id", help="Идентификатор потока")

    # watch-next
    watch_p = subparsers.add_parser("watch-next", help="Ожидать следующую каплю мысли в потоке")
    watch_p.add_argument("--flow-id", help="Идентификатор потока")
    watch_p.add_argument("--timeout", type=float, default=300.0, help="Тайм-аут ожидания в секундах")

    args = parser.parse_args()
    client = LadomirBridgeClient()

    if not args.command or args.command == "status":
        if not client.is_connected():
            print("❌ Живой Мост не обнаружен. Убедись, что запущен Портал Воли (python -m portal_volya.ui_desktop.run).")
            sys.exit(1)
        st = client.get_status()
        print("\n🌿 [ЖИВОЙ МОСТ ЛАДОМИРА]")
        print(f"Статус:         {st.get('status')}")
        print(f"Игрок за узлом: {st.get('player_username')} ({st.get('player_pubkey')[:12]}...)")
        print(f"Активный квест: {st.get('active_quest_id')}")
        print(f"Открытый поток: {st.get('active_flow_id')} («{st.get('active_flow_title')}»)")
        print(f"Время узла:     {st.get('timestamp')}\n")

    elif args.command == "read":
        if not client.is_connected():
            print("❌ Живой Мост не обнаружен.")
            sys.exit(1)
        fid = args.flow_id or client.get_active_flow_id()
        if not fid:
            print("⚠️ На экране Портала сейчас нет открытого потока. Укажи --flow-id или открой поток в UI.")
            sys.exit(1)
        drops = client.get_drops(fid)
        print(f"\n📜 Капли потока «{fid}» (всего: {len(drops)}):")
        print("─" * 60)
        for d in drops:
            author = d.author_name or d.author_pubkey[:8]
            print(f"💧 [{d.created_at[11:19]}] {author}: {d.content}")
        print("─" * 60 + "\n")

    elif args.command == "post":
        if not client.is_connected():
            print("❌ Живой Мост не обнаружен.")
            sys.exit(1)
        drop = client.post_ladomir_drop(args.message, flow_id=args.flow_id)
        print(f"✨ [Капля Ладомира влита в DAG]: {drop.id}")
        print(f"💬 «{drop.content}»\nКапля мгновенно отображена на экране Портала!")

    elif args.command == "eira":
        if not client.is_connected():
            print("❌ Живой Мост не обнаружен.")
            sys.exit(1)
        drop = client.ask_eira(args.message, flow_id=args.flow_id)
        print(f"🌸 [Отклик Эйры получен]: {drop.id}")
        print(f"💬 «{drop.content}»")

    elif args.command == "listen":
        if not client.is_connected():
            print("❌ Живой Мост не обнаружен.")
            sys.exit(1)
        print("🎧 Живой Мост слушает события Портала (Ctrl+C для выхода)...")
        last_time = None
        while True:
            evts = client.poll_events(since=last_time)
            for e in evts:
                last_time = max(last_time or "", e.get("timestamp", ""))
                if e.get("event") == "new_drop":
                    d = e.get("drop", {})
                    author = d.get("author_name") or d.get("author_pubkey", "")[:8]
                    print(f"💧 [{d.get('created_at', '')[11:19]}] {author}: {d.get('content', '')}")
            time.sleep(0.5)

    elif args.command == "watch-next":
        import json
        res = client.watch_next_drop(flow_id=args.flow_id, timeout=args.timeout)
        print(json.dumps(res, ensure_ascii=False))
        if res.get("status") in ("new_drop", "portal_closed"):
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
