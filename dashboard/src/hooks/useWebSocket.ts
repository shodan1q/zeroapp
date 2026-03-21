"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import type { WsEvent } from "@/lib/types";

interface UseWebSocketReturn {
  connected: boolean;
  lastEvent: WsEvent | null;
  events: WsEvent[];
  sendMessage: (data: unknown) => void;
}

const MAX_EVENTS = 200;
const MAX_RECONNECT_DELAY = 30_000;
const BASE_RECONNECT_DELAY = 1_000;

function getWsUrl(): string {
  if (typeof window === "undefined") return "";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws`;
}

export function useWebSocket(): UseWebSocketReturn {
  const [connected, setConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WsEvent | null>(null);
  const [events, setEvents] = useState<WsEvent[]>([]);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelay = useRef(BASE_RECONNECT_DELAY);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const url = getWsUrl();
    if (!url) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setConnected(true);
        reconnectDelay.current = BASE_RECONNECT_DELAY;
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        setConnected(false);
        wsRef.current = null;
        scheduleReconnect();
      };

      ws.onerror = () => {
        // onclose will fire after onerror, so reconnection is handled there.
        ws.close();
      };

      ws.onmessage = (evt: MessageEvent) => {
        if (!mountedRef.current) return;
        try {
          const parsed = JSON.parse(evt.data as string) as WsEvent;
          setLastEvent(parsed);
          setEvents((prev) => {
            const next = [parsed, ...prev];
            return next.length > MAX_EVENTS ? next.slice(0, MAX_EVENTS) : next;
          });
        } catch {
          // Ignore non-JSON messages
        }
      };
    } catch {
      scheduleReconnect();
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    if (reconnectTimer.current) return;

    const delay = reconnectDelay.current;
    reconnectDelay.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);

    reconnectTimer.current = setTimeout(() => {
      reconnectTimer.current = null;
      connect();
    }, delay);
  }, [connect]);

  const sendMessage = useCallback((data: unknown) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return { connected, lastEvent, events, sendMessage };
}
