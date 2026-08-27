export interface WsMeta {
  session_id: string
  sources: any[]
}

export interface WsCallbacks {
  onMeta?: (meta: WsMeta) => void
  onDelta?: (text: string) => void
  onError?: (message: string) => void
}

export function useWebSocket() {
  function wsUrl(): string {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    return `${proto}://${location.host}/ws/chat/stream`
  }

  /**
   * 通过 WebSocket 发送一条消息并流式接收回复。
   * 成功流式完成后 resolve(true)；任何失败 resolve(false)，由调用方降级 REST。
   */
  function send(payload: any, cb: WsCallbacks, timeout = 30000): Promise<boolean> {
    return new Promise((resolve) => {
      let settled = false
      const finish = (ok: boolean) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        try {
          ws.close()
        } catch {
          /* noop */
        }
        resolve(ok)
      }

      let ws: WebSocket
      try {
        ws = new WebSocket(wsUrl())
      } catch {
        resolve(false)
        return
      }

      const timer = window.setTimeout(() => finish(false), timeout)

      ws.onopen = () => ws.send(JSON.stringify(payload))
      ws.onmessage = (ev) => {
        let msg: any
        try {
          msg = JSON.parse(ev.data)
        } catch {
          return
        }
        if (msg.type === 'meta') cb.onMeta?.(msg)
        else if (msg.type === 'delta') cb.onDelta?.(msg.text || '')
        else if (msg.type === 'done') finish(true)
        else if (msg.type === 'error') {
          cb.onError?.(msg.message || '服务异常')
          finish(true)
        }
      }
      ws.onerror = () => finish(false)
      ws.onclose = () => finish(false)
    })
  }

  return { send }
}
