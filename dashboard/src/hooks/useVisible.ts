import { useEffect, useState } from "react"

/**
 * Whether this tab is in front. Streams are held only while it is: a browser keeps at most 6 connections per
 * site, and a stream held by every background tab of the dashboard soon leaves none for ordinary requests.
 */
export function useVisible() {
  const [visible, setVisible] = useState(() => document.visibilityState !== "hidden")
  useEffect(() => {
    const on = () => setVisible(document.visibilityState !== "hidden")
    document.addEventListener("visibilitychange", on)
    return () => document.removeEventListener("visibilitychange", on)
  }, [])
  return visible
}
