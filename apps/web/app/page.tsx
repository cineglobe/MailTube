import { ConvertScreen } from "@/components/convert-screen"
import { ProtectedShell } from "@/components/protected-shell"

export default function HomePage() {
  return (
    <ProtectedShell>
      <ConvertScreen />
    </ProtectedShell>
  )
}
