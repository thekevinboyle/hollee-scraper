"use client";
import { useEffect, useRef, useState, useCallback } from "react";

interface UseSSEOptions {
  onMessage?: (data: unknown) => void;
  onError?: (error: Event) => void;
}

export function useSSE(url: string | null, options?: UseSSEOptions) {
  const [data, setData] = useState<unknown>(null);
  const [isConnected, setIsConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  const disconnect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    if (!url) return;
    const source = new EventSource(url);
    sourceRef.current = source;

    source.onopen = () => setIsConnected(true);
    source.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        setData(parsed);
        options?.onMessage?.(parsed);
      } catch {
        setData(event.data);
      }
    };
    source.onerror = (e) => {
      options?.onError?.(e);
      if (source.readyState === EventSource.CLOSED) {
        setIsConnected(false);
      }
    };

    return () => {
      source.close();
      setIsConnected(false);
    };
  }, [url]);

  return { data, isConnected, disconnect };
}
