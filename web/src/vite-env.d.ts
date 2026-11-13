/// <reference types="vite/client" />

declare module "@strings" {
  const value: Record<string, { en: string; ms: string; check?: string }>;
  export default value;
}

declare module "@plan" {
  const value: unknown;
  export default value;
}
