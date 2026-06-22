import "@testing-library/jest-dom";
import { createElement, forwardRef } from "react";
import { vi } from "vitest";

// next/link and next/image don't function inside jsdom.
// Replace them with plain HTML equivalents so route components can render.
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => createElement("a", { href, className }, children),
}));

vi.mock("next/image", () => ({
  default: ({
    src,
    alt,
    width,
    height,
    className,
  }: {
    src: string;
    alt: string;
    width?: number;
    height?: number;
    className?: string;
  }) => createElement("img", { src, alt, width, height, className }),
}));

// Framer-motion mock: render motion.* as plain HTML elements, strip animation
// props, so jsdom tests see correct DOM content without animation overhead.
// ResizeObserver/rAF issues in jsdom are sidestepped entirely.
vi.mock("framer-motion", () => {
  const MOTION_PROPS = new Set([
    "initial", "animate", "exit", "variants", "transition",
    "layout", "layoutId", "layoutDependency", "layoutScroll",
    "whileHover", "whileTap", "whileFocus", "whileInView", "whileDrag",
    "drag", "dragConstraints", "dragElastic", "dragMomentum", "dragTransition",
    "onHoverStart", "onHoverEnd", "onTap", "onTapStart", "onTapCancel",
    "onAnimationStart", "onAnimationComplete", "onDrag", "onDragStart", "onDragEnd",
  ]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const makePassthrough = (tag: string) =>
    forwardRef<HTMLElement, Record<string, unknown>>(function MotionEl(props, ref) {
      const rest: Record<string, unknown> = { ref };
      for (const [k, v] of Object.entries(props)) {
        if (!MOTION_PROPS.has(k)) rest[k] = v;
      }
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return createElement(tag as any, rest);
    });

  const TAGS = [
    "div", "span", "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "main", "header", "footer", "nav", "aside",
    "ul", "ol", "li", "a", "button", "form", "input", "label", "img",
  ];

  const motion = Object.fromEntries(TAGS.map((t) => [t, makePassthrough(t)]));

  return {
    motion,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
    useInView: () => true,
    useReducedMotion: () => false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useMotionValue: (v: any) => ({ get: () => v, set: vi.fn(), on: vi.fn() }),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    useSpring: (v: any) => ({ get: () => v, set: vi.fn() }),
    useTransform: () => ({ get: () => 0, on: vi.fn() }),
  };
});
