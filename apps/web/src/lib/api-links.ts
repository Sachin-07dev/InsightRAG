// Public configuration contains an origin only. Never place credentials here.
export function getApiOrigin(): string {
  const configured =
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
  const url = new URL(configured);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash
  ) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL must be an HTTP(S) origin without credentials, path, query, or fragment",
    );
  }
  return url.origin;
}
