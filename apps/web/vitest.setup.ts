import "@testing-library/jest-dom";
import { createElement } from "react";
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
