import { HealthScreen } from "@/components/health-screen"
import { ProtectedShell } from "@/components/protected-shell"

export default function HealthPage() {
  return (
    <ProtectedShell>
      <HealthScreen />
    </ProtectedShell>
  )
}
