import { useEffect, useRef, useState, type RefObject } from "react";

/** Width of a container, kept current with ResizeObserver. */
export function useMeasure<T extends HTMLElement>(): [RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) setWidth(Math.round(e.contentRect.width));
    });
    ro.observe(el);
    setWidth(Math.round(el.getBoundingClientRect().width));
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

let patternSeq = 0;
/** Stable unique id for SVG defs within one mount. */
export function usePatternId(prefix: string): string {
  const ref = useRef<string | null>(null);
  if (ref.current === null) ref.current = `${prefix}-${++patternSeq}`;
  return ref.current;
}
