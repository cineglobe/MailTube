export function loginDestination(search: string) {
  const requested = new URLSearchParams(search).get("next")
  return requested?.startsWith("/") && !requested.startsWith("//")
    ? requested
    : "/convert/"
}
