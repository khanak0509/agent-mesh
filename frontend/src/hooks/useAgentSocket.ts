import { useCallback, useEffect, useRef, useState } from "react";
import type { WsMsg } from "../types";

type Handlers = {
  onMessage: (msg: WsMsg) => void;
};

export function useAgentSocket({ onMessage }: Handlers) {
  const [live, setLive] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    let timer: number | undefined;
    let closed = false;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      wsRef.current = ws;
      ws.onopen = () => setLive(true);
      ws.onclose = () => {
        setLive(false);
        if (!closed) timer = window.setTimeout(connect, 1400);
      };
      ws.onerror = () => setLive(false);
      ws.onmessage = (ev) => {
        try {
          onMessageRef.current(JSON.parse(ev.data) as WsMsg);
        } catch {
          /* ignore bad frames */
        }
      };
    };

    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback((payload: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(payload));
    return true;
  }, []);

  return { live, send };
}
