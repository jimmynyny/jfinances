import { useEffect } from "react";
import { Button } from "@mooney/ui";
import { useStoredChoice } from "../lib/storedView";

const KEY = "jf.blur";
const MODES = ["off", "on"] as const;

// Applied before the first render, so a reload with blur on never flashes the numbers.
try {
  document.documentElement.dataset.blur = localStorage.getItem(KEY) === "on" ? "on" : "off";
} catch {
  document.documentElement.dataset.blur = "off";
}

/**
 * Blur numbers, for screenshots: the top bar's master switch, on every page.
 * Off by default, remembered per viewer. The design system blurs every
 * number it draws while <html data-blur="on"> (docs/70 "Blur numbers").
 */
export function BlurToggle() {
  const [mode, setMode] = useStoredChoice(KEY, MODES, "off");
  useEffect(() => {
    document.documentElement.dataset.blur = mode;
  }, [mode]);
  const on = mode === "on";
  return (
    <Button size="sm" variant={on ? "primary" : "quiet"} aria-pressed={on} onClick={() => setMode(on ? "off" : "on")}
      title={on ? "Show numbers" : "Blur every number on screen, for screenshots"}>
      blur
    </Button>
  );
}
