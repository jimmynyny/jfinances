import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

/**
 * Hover and select for a chart's marks. A mouse or pen previews a mark on
 * hover and opens it on click. Touch has no hover, so the first tap on a mark
 * previews it (its tooltip stays up) and a second tap on the same mark opens
 * it; a tap outside the chart puts the preview away.
 *
 * `H` is what the chart hovers (a column index, a node key); `pick` is the
 * mark inside it that a click would open (a series, or null for all of it).
 */
export function useMarkSelect<H>(root: RefObject<HTMLElement | null>) {
  const [hover, setHover] = useState<H | null>(null);
  const [pick, setPick] = useState<string | null>(null);
  const [touch, setTouch] = useState(false);
  const touchNow = useRef(false); // read in click handlers, before state catches up
  const armed = useRef<string | null>(null);

  useEffect(() => {
    if (!touch || hover === null) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) {
        setHover(null);
        armed.current = null;
      }
    };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [touch, hover, root]);

  return {
    hover,
    pick,
    touch,
    setHover,
    setPick,
    /** Spread on the chart's root element. */
    rootProps: {
      onPointerDownCapture: (e: ReactPointerEvent) => {
        touchNow.current = e.pointerType === "touch";
        setTouch(touchNow.current);
      },
    },
    enter: (h: H) => setHover(h),
    leave: (e: ReactPointerEvent) => {
      if (e.pointerType !== "touch") setHover(null);
    },
    /** A click on the mark `key`: open it, unless this is the first tap on it. */
    click: (key: string, open?: () => void) => {
      if (!open) return;
      if (touchNow.current && armed.current !== key) {
        armed.current = key;
        return;
      }
      armed.current = null;
      open();
    },
  };
}
