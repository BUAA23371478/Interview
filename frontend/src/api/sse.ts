// SSE (Server-Sent Events) connection utility

export interface SSECallbacks {
  onEvent?: (eventType: string, data: string) => void;
  onError?: (error: string) => void;
  onFatal?: () => void;
}

export function createSSEConnection(
  url: string,
  callbacks: SSECallbacks,
  maxRetries: number = 3
): () => void {
  let retries = 0;
  let es: EventSource | null = null;
  let disposed = false;

  const connect = () => {
    if (disposed) return;

    const fullUrl = url.startsWith('http') ? url : `/api${url}`;
    const userId = localStorage.getItem('userId');

    // Append userId as query parameter since EventSource doesn't support custom headers
    const separator = fullUrl.includes('?') ? '&' : '?';
    const finalUrl = userId ? `${fullUrl}${separator}user_id=${userId}` : fullUrl;

    console.log(`[SSE] 正在连接: ${finalUrl}`);
    es = new EventSource(finalUrl);

    es.onopen = () => {
      console.log('[SSE] 连接已建立 (onopen)');
    };

    es.onmessage = (event) => {
      console.log(`[SSE] onmessage raw:`, event.data.slice(0, 120));
      try {
        const data = JSON.parse(event.data);
        const eventType = data.type || 'message';
        callbacks.onEvent?.(eventType, JSON.stringify(data));
      } catch {
        callbacks.onEvent?.('raw', event.data);
      }
    };

    // Register common event types
    const eventTypes = [
      'session_ready', 'session_completed',
      'question_start', 'question_chunk', 'question_done',
      'feedback_start', 'feedback_chunk', 'feedback_done',
      'interview_started', 'report_generating', 'report_chunk',
      'report_done', 'interview_complete',
      'follow_up', 'round_advanced',
      'ping', 'error',
    ];

    eventTypes.forEach((eventType) => {
      es?.addEventListener(eventType, (event: MessageEvent) => {
        console.log(`[SSE] 收到事件: ${eventType}`, event.data.slice(0, 150));
        try {
          const data = JSON.parse(event.data);
          callbacks.onEvent?.(eventType, JSON.stringify(data));
        } catch (e) {
          console.warn(`[SSE] 事件解析失败: ${eventType}`, e);
          callbacks.onEvent?.(eventType, event.data);
        }
      });
    });

    es.onerror = () => {
      console.warn(`[SSE] onerror readyState=${es?.readyState} retries=${retries}`);
      es?.close();
      if (disposed) return;

      if (retries < maxRetries) {
        retries++;
        console.log(`[SSE] 重连 (${retries}/${maxRetries})...`);
        setTimeout(connect, 1000 * retries);
      } else {
        console.error('[SSE] 连接失败，已达最大重试次数');
        callbacks.onFatal?.();
      }
    };
  };

  connect();

  return () => {
    console.log('[SSE] 清理连接');
    disposed = true;
    es?.close();
  };
}

// Helper to parse SSE event data
export function parseSSEData<T>(data: string): T {
  return JSON.parse(data) as T;
}
