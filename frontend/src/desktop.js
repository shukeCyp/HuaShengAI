export const desktopEventName = 'huashengai:desktop-event'

export function hasDesktopApi() {
  return Boolean(window.pywebview?.api)
}

export function subscribeDesktopEvents(listener) {
  const handleEvent = (event) => listener(event.detail)
  window.addEventListener(desktopEventName, handleEvent)

  return () => {
    window.removeEventListener(desktopEventName, handleEvent)
  }
}

export async function callDesktop(method, ...args) {
  if (!hasDesktopApi()) {
    throw new Error('PyWebView API is not available in the current window')
  }

  const fn = window.pywebview.api?.[method]
  if (typeof fn !== 'function') {
    throw new Error(`PyWebView API method not found: ${method}`)
  }

  return fn(...args)
}
